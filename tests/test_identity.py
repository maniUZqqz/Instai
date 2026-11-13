"""Character identity: the lock, the stick kit as an identity, the keyframe plan with references, the consistency check and its retakes, end to end with fakes."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tests.conftest import run_jobs

pytestmark = pytest.mark.django_db(transaction=True)


def make_world(fmt="mini_series_channel", names=("رامین", "نگهبان"), level="manual"):
    from instai.story import services as svc
    from instai.story import states
    from instai.story.models import Episode

    page = svc.create_page({"name": "کانال", "format": fmt, "languages": ["fa"], "idea": "x", "automation_level": level,
                            "characters": [{"name": n, "appearance": "a stick man", "role": "hero"} for n in names]})
    series = svc.create_series(page, {"title": "فرار", "premise": "گیر افتاده", "target_episodes": 3})
    ep = Episode.objects.create(series=series, number=1, title="قسمت ۱", state=states.PLANNED, duration_sec=20,
                                script={"title": "t", "hook": "h", "cta": "c", "language": "fa", "blocks": [{"id": i, "speaker": "", "text": f"جملهٔ {i}", "emotion": ""} for i in range(1, 5)]})
    sb = {"scenes": [{"index": 1, "title": "سلول", "summary": "", "location": "prison cell", "characters": [names[0]],
                      "shots": [{"index": 1, "description": "رامین در سلول با ترس می‌دود", "image_prompt": "a hero running in a prison cell", "technique": "puppet_2d", "camera": {"move": "zoom_in"},
                                 "duration_sec": 3.0, "narration": "او می‌دود", "speaker": names[0]},
                                {"index": 2, "description": "نگهبان به او اشاره می‌کند", "image_prompt": "a guard points", "technique": "still_kenburns", "camera": {"move": "pan_left"},
                                 "duration_sec": 3.0, "narration": "نگهبان", "speaker": names[1]}]}]}
    svc.save_storyboard(ep, sb)
    ep.state = states.STORYBOARDING
    ep.save(update_fields=["state"])
    return page, series, ep


def test_stick_character_is_built_locked_and_reused(api):
    from instai.identity import service
    from instai.production.models import CharacterRig

    page, series, ep = make_world()
    hero = page.characters.get(name="رامین")
    r = api.post(f"/api/characters/{hero.pk}/identity/stick", {"spec": {"limb_colour": "#2f7fd1", "hat": "cap", "hat_colour": "#e8a22b", "neck": "scarf"}}, format="json")
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["lock"]["status"] == "draft" and d["lock"]["source"] == "stick" and "blue-limbed" in d["lock"]["anchor"]
    assert d["rig"]["version"] == 1 and any(x["kind"] == "sheet" and x["url"] for x in d["references"])
    assert CharacterRig.objects.filter(character=hero, source="stick").count() == 1
    assert {p["role"] for p in d["lock"]["palette"]} >= {"limbs", "hat", "neck"}
    # editing is allowed while the identity is a draft, and refused when locked
    assert api.patch(f"/api/characters/{hero.pk}/identity", {"avoid": "no shading"}, format="json").status_code == 200
    locked = api.post(f"/api/characters/{hero.pk}/identity/lock", {}, format="json").json()
    assert locked["lock"]["status"] == "locked" and locked["lock"]["version"] == 2 and locked["lock"]["has_signature"] and service.get_lock(hero).signature["hist"]
    assert api.patch(f"/api/characters/{hero.pk}/identity", {"anchor": "other"}, format="json").status_code == 409
    assert api.post(f"/api/characters/{hero.pk}/identity/stick", {"spec": {"hat": "none"}}, format="json").status_code == 409
    assert next(s for s in locked["strategies"] if s["key"] == "stick_rig")["available"] is True
    assert locked["resolved"]["strategy"] == "stick_rig"
    # unlocking lets the owner change it; locking again bumps the version
    api.post(f"/api/characters/{hero.pk}/identity/unlock", {}, format="json")
    api.post(f"/api/characters/{hero.pk}/identity/stick", {"spec": {"hat": "beanie"}}, format="json")
    assert api.post(f"/api/characters/{hero.pk}/identity/lock", {}, format="json").json()["lock"]["version"] == 3
    assert service.get_lock(hero).stick["hat"] == "beanie"


def test_lock_needs_words_and_a_reference(api):
    page, series, ep = make_world()
    c = page.characters.get(name="رامین")
    r = api.post(f"/api/characters/{c.pk}/identity/lock", {}, format="json")
    assert r.status_code == 409                                  # the lock row is created with the appearance text, but no sheet exists yet
    api.patch(f"/api/characters/{c.pk}/identity", {"anchor": "a round-headed hero in a red coat"}, format="json")
    assert api.post(f"/api/characters/{c.pk}/identity/lock", {}, format="json").status_code == 409
    d = api.get(f"/api/characters/{c.pk}/identity").json()
    assert d["resolved"]["strategy"] == "anchor_seed" and next(s for s in d["strategies"] if s["key"] == "multiref_edit")["reason"] == "no_approved_sheet"


def test_stick_shots_are_drawn_with_the_locked_identity_not_an_image_model(api, worker):
    from instai.assets.models import Asset
    from instai.production import pipeline
    from instai.story import services as story_services

    page, series, ep = make_world()
    for c in page.characters.all():
        api.post(f"/api/characters/{c.pk}/identity/stick", {}, format="json")
        assert api.post(f"/api/characters/{c.pk}/identity/lock", {}, format="json").status_code == 200
    pipeline.start(ep, "preview")
    run_jobs(worker, limit=1)                                                          # the keyframe job (the first one queued)
    shots = story_services.all_shots(ep)
    kfs = [Asset.objects.filter(shot=s, role="keyframe", is_current=True).first() for s in shots]
    assert all(kfs)
    assert all(k.provenance.get("engine") == "stick" and k.provenance.get("provider") == "stick" for k in kfs)
    assert kfs[0].provenance["poses"] == ["run_a"] and kfs[0].provenance["expressions"] == ["scared"] and kfs[0].provenance["background"] == "cell"
    assert kfs[1].provenance["poses"][0] == "point_right"
    # the keyframe hash carries the lock version: a new lock version makes exactly these pictures stale
    before = pipeline.keyframe_hash(shots[0], ep, "preview")
    hero = page.characters.get(name="رامین")
    api.post(f"/api/characters/{hero.pk}/identity/unlock", {}, format="json")
    api.post(f"/api/characters/{hero.pk}/identity/lock", {}, format="json")
    assert pipeline.keyframe_hash(shots[0], ep, "preview") != before
    assert shots[0] in pipeline.missing_keyframes(ep, "preview")


def test_consistency_report_flags_a_wrong_character_and_opens_one_retake(api, worker, tmp_path):
    from instai.assets import storage as asset_storage
    from instai.assets.models import Asset
    from instai.production import pipeline
    from instai.story import services as story_services
    from instai.studio.models import RetakeRequest

    page, series, ep = make_world()
    for c in page.characters.all():
        api.post(f"/api/characters/{c.pk}/identity/stick", {}, format="json")
        api.post(f"/api/characters/{c.pk}/identity/lock", {}, format="json")
    pipeline.start(ep, "preview")
    run_jobs(worker, limit=1)
    rep = api.post(f"/api/episodes/{ep.pk}/consistency/run", {}, format="json").json()
    assert rep["checked"] >= 2 and rep["ok"] == rep["checked"] and rep["flagged"] == []
    # replace shot 1's picture by a wrong one (a plain placeholder): the check must flag it
    shot = story_services.all_shots(ep)[0]
    bad = tmp_path / "bad.png"
    Image.new("RGB", (448, 800), (20, 160, 20)).save(bad)
    asset_storage.register(bad, f"episodes/{ep.pk}/keyframes/wrong.png", kind="image", role="keyframe", page=page, episode=ep, shot=shot, input_hash="x")
    Asset.objects.filter(shot=shot, role="keyframe").exclude(path__endswith="wrong.png").update(is_current=False)
    rep = api.post(f"/api/episodes/{ep.pk}/consistency/run", {}, format="json").json()
    assert rep["flagged"] == [shot.pk]
    row = next(r for r in rep["shots"] if r["shot"] == shot.pk)
    assert row["characters"][0]["check"]["ok"] is False and any(n["code"] == "colour_missing" for n in row["characters"][0]["check"]["notes"])
    out = api.post(f"/api/episodes/{ep.pk}/consistency/retakes", {}, format="json").json()
    assert out["opened"] == 1
    assert RetakeRequest.objects.filter(shot=shot, reason__startswith="[identity]").count() == 1
    assert api.post(f"/api/episodes/{ep.pk}/consistency/retakes", {}, format="json").json()["opened"] == 0       # not repeated


def test_reference_plan_picks_the_strongest_strategy_that_can_run(api, monkeypatch, tmp_path):
    """Image-model route with approved sheets: multi-reference edit when its workflow is there, else sheet edit, else LoRA, else identity words + seed."""
    from instai.identity import service, strategies
    from instai.pages.models import CharacterReference
    from instai.production import hero
    from instai.assets import storage as asset_storage
    from instai.providers.comfy.workflows import get_workflow
    from instai.story import services as story_services

    page, series, ep = make_world(names=("رامین", "نگهبان"))
    shot = story_services.all_shots(ep)[0]
    shot.speaker = "رامین"
    shot.description = "رامین و نگهبان در راهرو"
    shot.save()
    for c in page.characters.all():
        png = tmp_path / f"{c.pk}.png"
        Image.new("RGB", (300, 200), (200, 50 + c.pk, 40)).save(png)
        a = asset_storage.register(png, f"characters/{c.pk}/sheet.png", kind="image", role="reference", page=page)
        ref = CharacterReference.objects.create(character=c, kind="sheet", asset=a)
        service.edit_lock(c, {"anchor": f"{c.name} wears a red coat", "palette": [{"role": "coat", "hex": "#c83c28"}]})
        lock = service.get_lock(c)
        lock.refs = {"sheet": ref.pk}
        lock.save()
        service.lock_identity(c)
    base = {"prompt": "in a corridor", "negative_prompt": "blurry", "width": 832, "height": 1472, "seed": 7, "steps": 24}

    monkeypatch.setattr(strategies, "_workflow_ok", lambda ids: "qwen_image_edit_multiref" in ids)
    plan = service.plan_for_shot(shot, ep, base, hero.reference_workflow)
    assert plan.strategy == "multiref_edit" and plan.workflow == "qwen_image_edit_multiref"
    assert set(plan.files) == {"ref.png", "ref2.png"} and "image 1 is the model sheet of رامین" in plan.inputs["prompt"]
    graph = get_workflow(plan.workflow).build(plan.inputs)                           # the graph is built with exactly the two references
    assert "7b" in graph and "7c" not in graph and "image2" in graph["9"]["inputs"] and "image3" not in graph["9"]["inputs"]
    assert graph["7b"]["inputs"]["image"] == "@input:ref2.png"

    monkeypatch.setattr(strategies, "_workflow_ok", lambda ids: False)
    monkeypatch.setattr(hero, "reference_workflow", lambda: "flux_dev_fp8_img2img")
    plan = service.plan_for_shot(shot, ep, base, hero.reference_workflow)
    assert plan.strategy == "sheet_edit" and plan.workflow == "flux_dev_fp8_img2img" and list(plan.files) == ["ref.png"]
    assert plan.inputs["negative_prompt"].startswith("blurry") and "red coat" in plan.inputs["prompt"]

    monkeypatch.setattr(hero, "reference_workflow", lambda: None)
    plan = service.plan_for_shot(shot, ep, base, hero.reference_workflow)
    assert plan.strategy == "anchor_seed" and plan.workflow == "" and not plan.files and "colour key" in plan.inputs["prompt"]
    assert service.default_seed(shot, ep) is None                                    # two characters: the pipeline keeps its own seed
    shot.description = "رامین تنها"
    shot.scene.characters.clear()
    assert service.default_seed(shot, ep) == service.get_lock(page.characters.get(name="رامین")).seed


def test_keyframe_inputs_use_the_lock_before_the_old_hero_path(monkeypatch):
    from instai.production import hero

    page, series, ep = make_world()
    from instai.story import services as story_services

    shot = story_services.all_shots(ep)[0]
    out = hero.keyframe_inputs(shot, ep, {"prompt": "p", "seed": 1, "width": 8, "height": 8}, {})
    assert out[0] == "" and out[3] == ""                                             # no locked identity: nothing changes


def test_identity_anchor_and_sheet_jobs_with_the_fake_engines(api, worker):
    from tests.conftest import finish

    page, series, ep = make_world()
    c = page.characters.get(name="رامین")
    j = finish(api, worker, api.post(f"/api/characters/{c.pk}/identity/anchor", {}, format="json"))
    assert j["result"]["anchor"] and j["result"]["provider"] == "fake"
    d = api.get(f"/api/characters/{c.pk}/identity").json()
    assert d["lock"]["anchor"] and d["lock"]["palette"]
    j = finish(api, worker, api.post(f"/api/characters/{c.pk}/identity/sheets", {}, format="json"))
    assert set(j["result"]["references"]) == {"sheet", "expression"}
    d = api.get(f"/api/characters/{c.pk}/identity").json()
    assert d["lock"]["refs"]["sheet"] and d["lock"]["refs"]["expressions"] and all(not r["approved"] for r in d["references"])
    pal = api.post(f"/api/characters/{c.pk}/identity/palette", {}, format="json").json()["palette"]
    assert isinstance(pal, list)
    assert api.post(f"/api/characters/{c.pk}/identity/lock", {}, format="json").json()["lock"]["status"] == "locked"


def test_stick_preview_endpoint_and_options(api):
    opt = api.get("/api/identity/options").json()
    assert "cap" in opt["stick"]["choices"]["hat"] and len(opt["stick"]["poses"]) >= 20 and len(opt["strategies"]) == 5 and {n["key"] for n in opt["not_used"]} == {"ipadapter_faceid", "pulid"}
    r = api.post("/api/stick/preview", {"spec": {"name": "a", "limb_colour": "#d94a3d"}, "pose": "wave", "expression": "happy", "background": "street"}, format="json").json()
    assert r["url"].startswith("/media/previews/stick-") and "red-limbed" in r["anchor"]
