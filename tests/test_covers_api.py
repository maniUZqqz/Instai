"""The cover maker end to end: the API, the job, the A/B versions, the episode's cover, the publishing package, the AI background that WAITS for ComfyUI and finishes by itself, the ideas
(offline and AI), the logo upload, the downloads and the self-test rows. Everything runs with the project's fakes (no GPU)."""
from __future__ import annotations

import base64
import io
import json
import zipfile
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from PIL import Image

from instai.core import settings_store
from instai.covers import ideation, selftest, service
from instai.covers.engine import fixtures
from instai.covers.engine import formats as F
from instai.covers.engine.styles import STYLES
from instai.covers.models import Cover
from instai.gpu import compute
from instai.jobs.models import Job
from tests.conftest import finish, run_jobs
from tests.test_identity import make_world

pytestmark = pytest.mark.django_db(transaction=True)


def locked_world(api):
    """A page with two stick characters, the hero locked, and one episode."""
    page, series, ep = make_world()
    hero = page.characters.get(name="رامین")
    r = api.post(f"/api/characters/{hero.pk}/identity/stick", {"spec": {"limb_colour": "#2f7fd1", "hat": "cap", "hat_colour": "#e8a22b"}}, format="json")
    assert r.status_code == 200, r.content
    assert api.post(f"/api/characters/{hero.pk}/identity/lock", {}, format="json").status_code == 200
    return page, series, ep, hero


def context(api, ep, **extra):
    r = api.get("/api/covers/context", {"episode": ep.pk, **extra})
    assert r.status_code == 200, r.content
    return r.json()


def make_cover(api, worker, ep, spec=None, variants=3, **extra):
    spec = spec or context(api, ep)["spec"]
    r = api.post("/api/covers", {"episode": ep.pk, "spec": spec, "variants": variants, **extra}, format="json")
    assert r.status_code == 202, r.content
    return r.json()["cover"]["id"], r


def pic(asset_url_or_path):
    from instai.assets import storage as asset_storage

    return Image.open(asset_storage.storage.path_for(asset_url_or_path))


# ------------------------------------------------------------------ meta and context

def test_meta_lists_every_format_and_layout_with_both_languages(api):
    m = api.get("/api/covers/meta").json()
    assert [f["key"] for f in m["formats"]] == ["youtube", "aparat", "telegram", "ig_portrait", "ig_square", "story", "poster", "yt_banner", "season_card"]
    assert len(m["styles"]) == 16 and {s["key"] for s in m["styles"]} >= {"episode_card", "cliffhanger", "choice_split", "character_face", "question_hook", "cinema_poster", "split_ba"}
    for s in m["styles"]:
        assert s["title_fa"] and s["title_en"] and s["fields"] and all(f["label_fa"] and f["label_en"] for f in s["fields"]), s["key"]
    assert {m["key"] for m in m["moods"]} >= {"vivid", "dark", "cinema"} and {f["key"] for f in m["fonts"]} == {"lalezar", "sahel", "vazirmatn"}
    assert m["max_variants"] == 6 and len(m["archetypes"]) == 16 and "available" in m["ai"] and "demo" in m["ai"]
    assert m["limits"]["title"] == 110 and "price" not in m["limits"] and "cta" not in m["limits"]


def test_context_gives_the_facts_a_ready_spec_and_where_each_character_picture_comes_from(api):
    page, series, ep, hero = locked_world(api)
    j = context(api, ep)
    c = j["context"]
    assert c["series"] == "فرار" and c["episode_number"] == 1 and c["episode_title"] == "قسمت ۱" and c["kind"] == "episode" and c["lang"] == "fa" and c["channel"] == "کانال"
    assert c["hook"] == "h" and c["characters"][:2] == ["رامین", "نگهبان"]
    assert j["spec"]["format"] == "youtube" and j["spec"]["lang"] == "fa" and j["spec"]["style"] in STYLES and j["spec"]["content"]["title"]
    assert j["spec"]["subject"]["character"] == hero.pk
    src = {s["name"]: s["source"] for s in j["subjects"]}
    assert src["رامین"] == "stick" and src["نگهبان"] == "none"
    assert j["target"]["episode"] == ep.pk
    en = context(api, ep, lang="en", fmt="story", style="cliffhanger")
    assert en["spec"]["lang"] == "en" and en["spec"]["format"] == "story" and en["spec"]["style"] == "cliffhanger"
    assert api.get("/api/covers/context", {"episode": 99999}).status_code == 404 and api.get("/api/covers/context").status_code == 400


def test_preview_is_a_small_jpeg_of_the_real_size_with_the_report(api):
    page, series, ep, hero = locked_world(api)
    spec = context(api, ep)["spec"]
    r = api.post("/api/covers/preview", {"episode": ep.pk, "spec": spec, "side": 480}, format="json")
    assert r.status_code == 200, r.content
    j = r.json()
    im = Image.open(io.BytesIO(base64.b64decode(j["image"].split(",", 1)[1])))
    assert im.format == "JPEG" and im.size == (j["width"], j["height"]) and max(im.size) == 480 and j["full"] == [1280, 720]
    assert j["info"]["subjects"][0]["source"] == "stick" and not j["warnings"]
    assert any(t["name"].startswith("title") for t in j["texts"]) and j["guides"]["avoid"]
    assert api.post("/api/covers/preview", {"episode": ep.pk, "spec": {**spec, "style": "product_hero"}}, format="json").status_code == 400


# ------------------------------------------------------------------ making, A/B, the episode's cover, the package

def test_a_cover_is_made_with_six_versions_becomes_the_episode_cover_and_ships_in_the_package(api, worker):
    from instai.assets import storage as asset_storage
    from instai.assets.models import Asset
    from instai.publishing.models import Publication
    from instai.story import states

    page, series, ep, hero = locked_world(api)
    pub = api.post(f"/api/pages/{page.pk}/publications", {"episode": ep.pk}, format="json").json()
    cid, r = make_cover(api, worker, ep, variants=6)
    j = finish(api, worker, r)
    assert j["result"]["variants"] == 6 and j["result"]["status"] == "ready"
    c = api.get(f"/api/covers/{cid}").json()
    assert c["status"] == "ready" and c["bg_state"] == "procedural" and c["chosen"] == 0 and len(c["variants"]) == 6
    assert [v["letter"] for v in c["variants"]] == list("ABCDEF")
    assert all((v["width"], v["height"]) == (1280, 720) for v in c["variants"]) and c["asset"]["width"] == 1280
    cover_assets = Asset.objects.filter(episode=ep, role="cover", is_current=True)
    assert cover_assets.count() == 1 and cover_assets.first().pk == c["asset"]["id"]
    assert Publication.objects.get(pk=pub["id"]).cover_id == c["asset"]["id"], "the unpublished publication of the episode got the chosen cover"
    # publishing: the package ships the cover of the new maker
    ep.state = states.READY_FOR_APPROVAL
    ep.save(update_fields=["state"])
    mp4 = asset_storage.storage.root / "x" / "final.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    asset_storage.register(mp4, f"episodes/{ep.pk}/final.mp4", kind="video", role="final", page=page, episode=ep, probe=False)
    ex = api.post(f"/api/publications/{pub['id']}/export", {}, format="json")
    assert ex.status_code == 202, ex.content
    finish(api, worker, ex)
    p = Publication.objects.get(pk=pub["id"])
    with zipfile.ZipFile(asset_storage.storage.path_for(p.package.path)) as z:
        names = z.namelist()
        assert "cover.png" in names and "cover.jpg" in names, names
        assert z.read("cover.png") == asset_storage.storage.path_for(Asset.objects.get(pk=c["asset"]["id"]).path).read_bytes()
        assert len(z.read("cover.jpg")) <= 2000 * 1024
    assert Image.open(io.BytesIO(zipfile.ZipFile(asset_storage.storage.path_for(p.package.path)).read("cover.jpg"))).size == (1280, 720)


def test_choosing_another_version_updates_the_episode_cover_and_its_publications(api, worker):
    from instai.assets.models import Asset
    from instai.publishing.models import Publication

    page, series, ep, hero = locked_world(api)
    pub = api.post(f"/api/pages/{page.pk}/publications", {"episode": ep.pk}, format="json").json()
    cid, r = make_cover(api, worker, ep, variants=3)
    finish(api, worker, r)
    first = api.get(f"/api/covers/{cid}").json()["asset"]["id"]
    assert Publication.objects.get(pk=pub["id"]).cover_id == first
    u = api.post(f"/api/covers/{cid}/use", {"variant": 2}, format="json")
    assert u.status_code == 200, u.content
    now = u.json()
    assert now["chosen"] == 2 and now["asset"]["id"] != first and Publication.objects.get(pk=pub["id"]).cover_id == now["asset"]["id"]
    assert Asset.objects.get(pk=first).is_current is False and Asset.objects.filter(episode=ep, role="cover", is_current=True).count() == 1
    assert api.post(f"/api/covers/{cid}/use", {"variant": 5}, format="json").status_code == 404
    # a published publication keeps the cover it was published with
    Publication.objects.filter(pk=pub["id"]).update(status="published")
    api.post(f"/api/covers/{cid}/use", {"variant": 1}, format="json")
    assert Publication.objects.get(pk=pub["id"]).cover_id == now["asset"]["id"]


def test_more_versions_up_to_six_then_a_conflict(api, worker):
    page, series, ep, hero = locked_world(api)
    cid, r = make_cover(api, worker, ep, variants=2)
    finish(api, worker, r)
    m = api.post(f"/api/covers/{cid}/more", {"count": 3}, format="json")
    assert m.status_code == 202, m.content
    finish(api, worker, m)
    c = api.get(f"/api/covers/{cid}").json()
    assert len(c["variants"]) == 5 and [v["letter"] for v in c["variants"]] == list("ABCDE")
    finish(api, worker, api.post(f"/api/covers/{cid}/more", {"count": 4}, format="json"))
    assert len(api.get(f"/api/covers/{cid}").json()["variants"]) == 6
    assert api.post(f"/api/covers/{cid}/more", {}, format="json").status_code == 409


def test_history_keeps_every_design_and_editing_again_makes_a_new_one_from_the_old_spec(api, worker):
    page, series, ep, hero = locked_world(api)
    a, r = make_cover(api, worker, ep, variants=1)
    finish(api, worker, r)
    old = api.get(f"/api/covers/{a}").json()
    spec = {**old["spec"], "style": "cliffhanger", "content": {**old["spec"]["content"], "title": "و ناگهان در باز شد"}}
    b, r2 = make_cover(api, worker, ep, spec=spec, variants=2, parent=a, note="v2")
    finish(api, worker, r2)
    hist = api.get("/api/covers", {"episode": ep.pk}).json()
    assert [h["id"] for h in hist] == [b, a] and hist[0]["parent"] == a and hist[0]["style"] == "cliffhanger" and hist[0]["note"] == "v2" and hist[1]["style"] != "cliffhanger"
    assert api.get(f"/api/covers/{a}").json()["spec"]["content"]["title"] == old["spec"]["content"]["title"], "the old design is untouched"
    assert api.delete(f"/api/covers/{b}").status_code == 204 and [h["id"] for h in api.get("/api/covers", {"episode": ep.pk}).json()] == [a]


def test_a_series_cover_and_a_banner_have_no_episode(api, worker):
    page, series, ep, hero = locked_world(api)
    j = api.get("/api/covers/context", {"series": series.pk, "fmt": "poster", "style": "cinema_poster"}).json()
    assert j["target"]["episode"] is None and j["context"]["kind"] == "series" and j["spec"]["style"] == "cinema_poster" and j["spec"]["format"] == "poster"
    r = api.post("/api/covers", {"series": series.pk, "spec": j["spec"], "variants": 1}, format="json")
    assert r.status_code == 202
    finish(api, worker, r)
    c = Cover.objects.get(pk=r.json()["cover"]["id"])
    assert c.episode_id is None and c.series_id == series.pk and c.status == "ready" and c.variants[0]["asset"]
    ban = api.get("/api/covers/context", {"page": page.pk, "kind": "banner", "fmt": "yt_banner"}).json()
    assert ban["context"]["kind"] == "banner" and ban["spec"]["format"] == "yt_banner"
    r2 = api.post("/api/covers", {"page": page.pk, "kind": "banner", "spec": ban["spec"], "variants": 1}, format="json")
    finish(api, worker, r2)
    assert (Cover.objects.get(pk=r2.json()["cover"]["id"]).report["size"]) == [2560, 1440]


# ------------------------------------------------------------------ downloads, uploads

def test_downloads_png_jpg_under_two_megabytes_and_the_zip(api, worker):
    page, series, ep, hero = locked_world(api)
    cid, r = make_cover(api, worker, ep, variants=2)
    finish(api, worker, r)
    png = api.get(f"/api/covers/{cid}/download", {"variant": "B"})
    assert png.status_code == 200 and png["Content-Type"] == "image/png" and Image.open(io.BytesIO(png.content)).size == (1280, 720)
    jpg = api.get(f"/api/covers/{cid}/download", {"variant": "A", "fmt": "jpg"})
    assert jpg["Content-Type"] == "image/jpeg" and len(jpg.content) <= 2000 * 1024 and Image.open(io.BytesIO(jpg.content)).format == "JPEG"
    z = zipfile.ZipFile(io.BytesIO(api.get(f"/api/covers/{cid}/zip").content))
    assert sorted(z.namelist()) == ["README.txt", "cover-A.jpg", "cover-A.png", "cover-B.jpg", "cover-B.png"]
    assert api.get(f"/api/covers/{cid}/download", {"variant": "F"}).status_code == 404


def test_upload_a_logo_and_see_it_on_the_cover(api):
    page, series, ep, hero = locked_world(api)
    buf = io.BytesIO()
    Image.new("RGBA", (300, 120), (20, 120, 140, 255)).save(buf, "PNG")
    buf.seek(0)
    buf.name = "logo.png"
    r = api.post("/api/covers/upload", {"page": page.pk, "kind": "logo", "file": buf}, format="multipart")
    assert r.status_code == 201, r.content
    aid = r.json()["asset"]["id"]
    spec = context(api, ep)["spec"]
    spec["logo"] = {"show": True, "position": "auto", "asset": aid}
    from instai.covers.engine import render as R

    inp, _ = service.build_inputs(R.clean_spec(spec, STYLES), page, series, ep)
    assert inp.logo is not None and inp.logo.size == (300, 120)
    bad = io.BytesIO(b"not a picture")
    bad.name = "x.png"
    assert api.post("/api/covers/upload", {"page": page.pk, "kind": "logo", "file": bad}, format="multipart").status_code == 400
    assert api.post("/api/covers/upload", {"page": page.pk, "kind": "weird", "file": bad}, format="multipart").status_code == 400


# ------------------------------------------------------------------ ideas

def test_ideas_offline_are_sound_in_both_languages_and_never_invent_numbers(api):
    page, series, ep, hero = locked_world(api)
    for lang in ("fa", "en"):
        j = api.post("/api/covers/ideas", {"episode": ep.pk, "format": "youtube", "use_ai": False, "lang": lang, "count": 8}, format="json").json()
        assert j["via"] == "rules" and 3 <= len(j["ideas"]) <= 8 and j["message_fa"] and j["message_en"] and j["lang"] == lang
        for i in j["ideas"]:
            assert i["style"] in STYLES and i["spec_patch"]["style"] == i["style"] and i["title"] and i["concept_fa"] and i["concept_en"] and i["bg_prompt_en"].endswith("no people, high quality")
            assert not any(w in (i["title"] + i["subtitle"]).lower() for w in ("درصد", "تومان", "percent", "price", "free"))
            import re

            assert set(re.findall(r"[0-9۰-۹]+", i["title"])) <= {"1", "۱"}, i["title"]


def test_ideas_use_the_ai_when_it_answers_and_say_why_when_it_does_not(api, monkeypatch):
    page, series, ep, hero = locked_world(api)
    j = api.post("/api/covers/ideas", {"episode": ep.pk, "use_ai": True, "count": 4}, format="json").json()        # the fake text provider answers in tests
    assert j["ai"]["tried"] and j["ai"]["ok"] and j["via"] in ("ai", "mixed") and any(i["source"] == "ai" for i in j["ideas"])
    for i in j["ideas"]:
        assert i["style"] in STYLES and i["title"]

    def broken(*a, **k):
        raise ideation.AIUnavailable("اعتبارِ سرویسِ ابری تمام شده است (۴۰۲).", "The cloud service is out of credit (402).")

    monkeypatch.setattr(ideation, "_default_ask", broken)
    j2 = api.post("/api/covers/ideas", {"episode": ep.pk, "use_ai": True}, format="json").json()
    assert j2["via"] == "rules" and not j2["ai"]["ok"] and "۴۰۲" in j2["message_fa"] and "402" in j2["message_en"] and j2["ideas"]


def test_the_ai_answer_is_checked_for_invented_claims_numbers_and_unknown_layouts():
    from instai.covers.engine import hooks

    ctx = hooks.make_ctx(fixtures.sample_context("fa"))
    src = "ماجراهای چغر ۱"
    raw = {"ideas": [{"title": "تخفیف ویژهٔ مربی چغر", "style": "episode_card"}, {"title": "۹۸٪ مربی‌ها این را دیدند", "style": "neon"}, {"title": "مربی چغر و رازِ کیف", "style": "nope"},
                     {"title": "یک", "style": "neon"}, {"title": "کیفِ *گم‌شده* کجاست؟", "style": "cliffhanger", "subtitle": "قسمت ۱", "bg_prompt_en": "سلام"}]}
    out = ideation.clean_ai_ideas(raw, ctx=ctx, fmt="youtube", source_text=src)
    titles = [i["title"] for i in out]
    assert titles == ["مربی چغر و رازِ کیف", "کیفِ *گم‌شده* کجاست؟"], titles
    assert out[0]["style"] in STYLES and out[1]["style"] == "cliffhanger" and out[1]["bg_prompt_en"].startswith("dark moody scene")


# ------------------------------------------------------------------ the AI background waits for ComfyUI and finishes by itself

def test_the_ai_background_waits_for_comfyui_and_the_cover_is_already_usable(api, worker, monkeypatch, tmp_path):
    from instai.assets.models import Asset

    page, series, ep, hero = locked_world(api)
    series.look = {"style_key": "modern_tv_anime"}
    series.save(update_fields=["look"])
    settings_store.set_setting("image_engine", "comfyui")
    state = {"up": False, "graphs": []}
    monkeypatch.setattr(compute, "workflow_available", lambda wid: state["up"])
    spec = context(api, ep)["spec"]
    spec["background"] = {**spec["background"], "kind": "ai"}
    cid, r = make_cover(api, worker, ep, spec=spec, variants=3)
    job_id = r.json()["job"]["id"]
    run_jobs(worker)
    j = Job.objects.get(pk=job_id)
    assert j.status == Job.QUEUED and j.wait_code == "comfy_down" and j.attempts == 0 and "ComfyUI" in j.waiting_reason, (j.status, j.wait_code, j.error)
    c = Cover.objects.get(pk=cid)
    assert c.status == "waiting_bg" and c.bg_state == "waiting" and len(c.variants) == 3 and c.asset_id, "usable now with the procedural background"
    assert Asset.objects.filter(episode=ep, role="cover", is_current=True).count() == 1
    waiting_asset = c.asset_id
    # ComfyUI comes up: the same job finishes by itself, with the picture the image model drew
    def fake_run_task(ctx, kind, payload, inputs=None, **kw):
        state["graphs"].append(json.dumps(payload["graph"], ensure_ascii=False))
        out = tmp_path / "gen.png"
        fixtures.scene(size=(1344, 768)).save(out)
        return SimpleNamespace(of_kind=lambda *s: [out], cleanup=lambda: None, device="test-gpu", seconds=1.0, files=[out])

    state["up"] = True
    monkeypatch.setattr(compute, "run_task", fake_run_task)
    Job.objects.filter(pk=job_id).update(run_after=timezone.now() - timedelta(seconds=1))
    run_jobs(worker)
    j = Job.objects.get(pk=job_id)
    assert j.status == Job.SUCCEEDED and j.attempts == 1, (j.status, j.error)
    c = Cover.objects.get(pk=cid)
    assert c.status == "ready" and c.bg_state == "ai" and c.bg_asset_id and c.spec["background"]["asset"] == c.bg_asset_id and len(c.variants) == 3
    assert all(Asset.objects.get(pk=v["asset"]).provenance["background"] == "ai" for v in c.variants)
    assert c.asset_id != waiting_asset and Asset.objects.filter(episode=ep, role="cover", is_current=True).count() == 1
    g = state["graphs"][0]
    from instai.covers import background

    w, h = background.size_for(1280, 720)
    assert "no text, no letters" in g and "no people" in g, "the scene prompt carries the no-text rules"
    assert f'"width": {w}' in g and f'"height": {h}' in g and w % 16 == 0 and h % 16 == 0, (w, h)
    from instai.styles import library

    assert library.get_style("modern_tv_anime")["image_positive"].split(",")[0].strip() in g, "the prompt carries the series look"
    assert Asset.objects.get(pk=c.bg_asset_id).provenance["cover"] == cid and "Pillow" in Asset.objects.get(pk=c.bg_asset_id).provenance["note"]


def test_demo_mode_never_asks_a_model_and_says_so(api, worker, monkeypatch):
    page, series, ep, hero = locked_world(api)
    assert settings_store.effective("image_engine") == "placeholder"
    monkeypatch.setattr(compute, "run_task", lambda *a, **k: pytest.fail("a model must not be asked in demo mode"))
    spec = context(api, ep)["spec"]
    spec["background"] = {**spec["background"], "kind": "ai"}
    cid, r = make_cover(api, worker, ep, spec=spec, variants=1)
    finish(api, worker, r)
    c = Cover.objects.get(pk=cid)
    assert c.status == "ready" and c.bg_state == "demo" and c.bg_asset_id is None
    assert api.get("/api/covers/meta").json()["ai"]["demo"] is True


# ------------------------------------------------------------------ the self-test rows

def test_the_selftest_rows_exist_and_the_cpu_check_passes():
    from pathlib import Path
    import tempfile

    from instai.ops import pcselftest

    rows = {c["key"]: c for c in pcselftest.CHECKS}
    assert rows["covers"]["group"] == "tools" and rows["covers_bg"]["group"] == "gpu" and rows["covers_bg"].get("ready") is not None
    assert rows["covers"]["fa"] and rows["covers"]["en"] and rows["covers_bg"]["fa"] and rows["covers_bg"]["en"]
    with tempfile.TemporaryDirectory() as d:
        res = selftest.check_covers(Path(d))
    assert res["verdict"] == "ok", res
    assert res["metrics"]["styles"] == 16 and res["metrics"]["formats"] == 9 and res["metrics"]["renders"] == 9 + 16 * 9


def test_the_gpu_check_waits_when_comfyui_is_down_and_passes_with_a_background(monkeypatch, tmp_path):
    from instai.ops import pcselftest

    settings_store.set_setting("image_engine", "comfyui")
    assert selftest.check_covers_bg(tmp_path)["verdict"] == "pending", "no job context: only from the self-test job"
    pcselftest._CTX[0] = SimpleNamespace(check=lambda: None, waiting=lambda t: None, log=lambda *a: None, progress=lambda *a: None)
    try:
        monkeypatch.setattr(compute, "workflow_available", lambda wid: False)
        res = selftest.check_covers_bg(tmp_path)
        assert res["verdict"] == "pending" and "ComfyUI" in res["reason_fa"]
        monkeypatch.setattr(compute, "workflow_available", lambda wid: True)

        def fake_run_task(ctx, kind, payload, inputs=None, **kw):
            out = tmp_path / "gen.png"
            fixtures.scene(size=(512, 512)).save(out)
            assert payload["graph"] and "512" in json.dumps(payload["graph"])
            return SimpleNamespace(of_kind=lambda *s: [out], cleanup=lambda: None, device="test-gpu", seconds=2.0, files=[out])

        monkeypatch.setattr(compute, "run_task", fake_run_task)
        ok = selftest.check_covers_bg(tmp_path)
        assert ok["verdict"] == "ok" and ok["metrics"]["device"] == "test-gpu", ok
    finally:
        pcselftest._CTX[0] = None
    settings_store.set_setting("image_engine", "placeholder")
    assert selftest.check_covers_bg(tmp_path)["verdict"] == "skip"


def test_the_job_kind_has_a_name_in_both_languages():
    from instai.jobs import describe

    assert describe.KIND_TEXT["covers.make"][0] and describe.KIND_TEXT["covers.make"][1]
