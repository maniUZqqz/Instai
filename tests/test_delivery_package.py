"""The delivery package of a publication (0.16): one file per network the page's targets name - exactly those - the caption after its check (never rewritten), the repaired hashtags,
the subtitles and covers when they exist, and a README / delivery.json in both languages. Nothing is ever posted. Real ffmpeg on a tiny episode."""
from __future__ import annotations

import json
import zipfile

import pytest

np = pytest.importorskip("numpy")

from instai.assets import storage as asset_storage  # noqa: E402
from instai.assets.models import Asset  # noqa: E402
from instai.pages.models import Character, ContentPage  # noqa: E402
from instai.publishing import delivery_package as dp  # noqa: E402
from instai.publishing import services  # noqa: E402
from instai.publishing.models import Publication, PublishTarget  # noqa: E402
from instai.render import audiofixtures as fx  # noqa: E402
from instai.render import delivery, ffmpeg, loudness  # noqa: E402
from instai.story.models import Episode, Series  # noqa: E402
from tests.conftest import finish  # noqa: E402

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


def build(tmp_path, *, targets=(), caption="سلام؛ قسمت اول", tags=("سریالکوتاه", "#انیمیشن"), size="270x480", role="final", ai_label=True):
    """A page, a series, an episode with a real tiny final video, and a publication whose page targets the given `(platform, enabled, fit)` rows."""
    page = ContentPage.objects.create(name="کانال آزمون", languages=["fa"])
    page.set_profile("audio", {"target_lufs": -14})
    series = Series.objects.create(page=page, title="ماجراهای آزمون")
    ep = Episode.objects.create(series=series, number=1, title="قسمت اول", state="ready_for_approval")
    Character.objects.create(page=page, name="پلنگ صورتی")
    wav = fx.write_wav(tmp_path / "s.wav", fx.speechlike(3.0, seed=12))
    mp4 = fx.synthetic_video(tmp_path / "s.mp4", wav, ffmpeg_exe=ffmpeg.binaries()[0], seconds=3.0, size=size, fps=30, loudnorm_to=-14.0)
    video = asset_storage.register(mp4, f"episodes/{ep.pk}/renders/{role}.mp4", kind="video", role=role, page=page, episode=ep, loudness=True)
    for platform, enabled, fit in targets:
        PublishTarget.objects.create(page=page, platform=platform, enabled=enabled, config={"fit": fit} if fit else {})
    pub = Publication.objects.create(episode=ep, target=page.targets.first(), caption=caption, hashtags=list(tags), ai_label=ai_label)
    return page, ep, video, pub


def names(pub):
    return set(zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path)).namelist())


def export(pub):
    services.export_package(pub.pk)
    pub.refresh_from_db()
    return pub.package


def extract(pub, tmp_path, member):
    z = zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path))
    out = tmp_path / "x" / member.replace("/", "_")
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(z.read(member))
    return out


# ------------------------------------------------------------------------------------------------------------------------------ the package lists exactly the networks the page targets

def test_a_page_without_targets_gets_the_package_it_always_got(tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path)
    export(pub)
    n = names(pub)
    assert {"episode-01.mp4", "caption.txt", "hashtags.txt", "README.txt", "delivery.json"} <= n
    assert not [x for x in n if "/" in x], "no network folder when the page names no network"
    assert pub.status == "exported"
    plan = dp.plan_for(pub)
    assert plan["no_targets"] is True and plan["networks"] == []


def test_the_package_has_exactly_the_networks_the_page_targets(tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path, targets=[("ig_reel", True, ""), ("telegram", True, ""), ("tiktok", True, ""), ("yt_wide", False, ""), ("aparat", True, "")])
    r = services.export_package(pub.pk)
    pub.refresh_from_db()
    n = names(pub)
    folders = {x.split("/")[0] for x in n if "/" in x}
    assert folders == {"ig_reel", "telegram", "tiktok"}, folders                    # yt_wide is switched off; aparat wants 16:9 and the episode is 9:16: no crop, no file
    assert r["networks"] == ["ig_reel", "tiktok", "telegram"] or set(r["networks"]) == {"ig_reel", "tiktok", "telegram"}
    for k in folders:
        assert f"{k}/episode-01-{k}.mp4" in n
    man = json.loads(zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path)).read("delivery.json"))
    by = {x["key"]: x for x in man["networks"]}
    assert set(by) == {"ig_reel", "telegram", "tiktok", "aparat"}                  # a disabled target is not even in the plan
    assert by["aparat"]["status"] == "needs_aspect" and by["aparat"]["result"] == {"status": "skipped", "reason": "needs_aspect"}
    assert by["ig_reel"]["result"]["status"] == "made" and by["telegram"]["result"]["status"] == "made"
    pkg = pub.package
    assert pkg.provenance["networks"] == r["networks"] and pkg.provenance["not_made"] == ["aparat"] and man["approximate_numbers"] is True


def test_every_network_file_has_its_networks_loudness_and_shape(tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path, targets=[("ig_reel", True, ""), ("telegram", True, "")])
    export(pub)
    ig, tg = extract(pub, tmp_path, "ig_reel/episode-01-ig_reel.mp4"), extract(pub, tmp_path, "telegram/episode-01-telegram.mp4")
    assert abs(loudness.measure(ig)["lufs"] + 14.0) <= 0.8 and abs(loudness.measure(tg)["lufs"] + 16.0) <= 0.8
    assert loudness.measure(ig)["tp"] <= -0.95 and loudness.measure(tg)["tp"] <= -0.95
    for f in (ig, tg):
        info = ffmpeg.probe(f)
        assert info["has_audio"] and info["has_video"] and (info["width"], info["height"]) == (270, 480)          # the tiny source is never enlarged


def test_a_shape_that_does_not_fit_is_explained_in_both_languages_and_the_whole_frame_option_makes_the_file(tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path, targets=[("yt_wide", True, ""), ("aparat", True, "blur"), ("ig_post", True, "")])
    export(pub)
    n = names(pub)
    assert {x.split("/")[0] for x in n if "/" in x} == {"aparat"}                                  # only the one the owner switched to «whole frame with blurred sides»
    readme = zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path)).read("README.txt").decode("utf-8")
    assert "yt_wide" in readme and "NOT MADE" in readme and "ساخته نشد" in readme and "crop" in readme and "برش" in readme
    out = extract(pub, tmp_path, "aparat/episode-01-aparat.mp4")
    info = ffmpeg.probe(out)
    assert info["width"] / info["height"] == pytest.approx(16 / 9, abs=0.02) and round(info["fps"]) == 25
    assert abs(loudness.measure(out)["lufs"] + 16.0) <= 0.8


def test_a_target_may_still_say_instagram_and_an_unknown_one_is_named_not_dropped(tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path, targets=[("instagram", True, ""), ("facebook", True, "")])
    export(pub)
    assert {x.split("/")[0] for x in names(pub) if "/" in x} == {"ig_reel"}
    man = json.loads(zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path)).read("delivery.json"))
    assert [i["platform"] for i in man["ignored"]] == ["facebook"]
    assert "facebook" in zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path)).read("README.txt").decode("utf-8")


def test_an_episode_without_a_video_says_so_instead_of_an_unknown_shape(tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path, targets=[("ig_reel", True, "")])
    Asset.objects.filter(pk=video.pk).delete()
    plan = dp.plan_for(pub)
    assert plan["source"]["asset"] is None and plan["networks"][0]["status"] == "no_video" and "ساخته نشده" in plan["networks"][0]["notes"][0]["fa"]
    assert plan["networks"][0]["offers"] == []


def test_a_preview_source_is_used_and_said(tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path, targets=[("ig_reel", True, "")], role="preview")
    plan = dp.plan_for(pub)
    assert plan["source"]["preview"] is True and any("پیش‌نمایش" in w["fa"] for w in plan["networks"][0]["warnings"])


def test_one_network_failing_does_not_lose_the_others(tmp_path, ffmpeg_available, monkeypatch):
    page, ep, video, pub = build(tmp_path, targets=[("ig_reel", True, ""), ("telegram", True, "")])
    real = delivery.render_network

    def flaky(src, dst, key, info, **kw):
        if key == "telegram":
            raise ffmpeg.FFmpegError("encoder exploded")
        return real(src, dst, key, info, **kw)

    monkeypatch.setattr(delivery, "render_network", flaky)
    r = services.export_package(pub.pk)
    pub.refresh_from_db()
    assert r["networks"] == ["ig_reel"] and {x.split("/")[0] for x in names(pub) if "/" in x} == {"ig_reel"}
    readme = zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path)).read("README.txt").decode("utf-8")
    assert "encoder exploded" in readme and "ساخته نشد" in readme


# ------------------------------------------------------------------------------------------------------------------------------ the caption, the hashtags, the soft inputs

def test_the_caption_is_kept_as_written_the_check_goes_to_the_readme_and_glued_tags_are_repaired(tmp_path, ffmpeg_available):
    caption = "۶۰۰٬۰۰ تومان!!  و دوباره  ۶۰۰٬۰۰ تومان"
    page, ep, video, pub = build(tmp_path, caption=caption, targets=[("ig_reel", True, "")])
    export(pub)
    z = zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path))
    text = z.read("caption.txt").decode("utf-8")
    assert text.startswith(caption + "\n\n") and "#سریال_کوتاه" in text and "#انیمیشن" in text and "#سریالکوتاه" not in text      # the caption is never rewritten; the glued tag is split
    assert z.read("hashtags.txt").decode("utf-8") == "#سریال_کوتاه #انیمیشن"
    readme = z.read("README.txt").decode("utf-8")
    assert "Checks" in readme and "عددِ ناقص" in readme and "A number looks cut short" in readme and "سریال_کوتاه" in readme
    pub.refresh_from_db()
    assert pub.caption == caption and pub.hashtags == ["سریالکوتاه", "#انیمیشن"], "the stored caption and tags are untouched"


def test_the_pages_own_words_repair_its_tags(tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path, tags=("خرسکوچولو",), targets=[])
    assert dp.tags_for(pub, page, ep.series, ep)[1] == ["خرسکوچولو"]                    # «خرس» is not an everyday word of the list, «کوچولو» is the name of a character
    page.set_profile("identity", {"niche": "خرس و دوستانش"})
    Character.objects.create(page=page, name="کوچولو")
    assert dp.tags_for(pub, page, ep.series, ep) == (["خرسکوچولو"], ["خرس_کوچولو"])      # the page's own niche + a character name: the glued tag is split


def test_a_series_started_from_an_idea_knows_the_ideas_own_words(tmp_path, ffmpeg_available):
    from instai.ideabank.models import IdeaUse

    page, ep, video, pub = build(tmp_path, tags=("ساندویچتورم",), targets=[])
    assert dp.tags_for(pub, page, ep.series, ep)[1] == ["ساندویچتورم"]
    from instai.ideabank import bank

    idea = next(i for i in bank.all_ideas() if i["title_fa"] == "تورم با یک ساندویچ")
    IdeaUse.objects.create(key=idea["key"], series=ep.series, page_id=page.pk)                       # the idea «تورم با یک ساندویچ» of the idea bank
    assert dp.tags_for(pub, page, ep.series, ep)[1] == ["ساندویچ_تورم"]


def test_subtitles_and_covers_are_included_when_they_exist_and_nothing_breaks_when_they_do_not(tmp_path, ffmpeg_available):
    from PIL import Image

    page, ep, video, pub = build(tmp_path, targets=[("ig_reel", True, ""), ("telegram", True, "")])
    export(pub)
    base = names(pub)
    assert not [x for x in base if x.endswith(".srt")] and "cover.png" not in base and not [x for x in base if "/cover" in x]
    srt = tmp_path / "e.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nسلام\n", encoding="utf-8")
    asset_storage.register(srt, f"episodes/{ep.pk}/renders/final.srt", kind="subtitle", role="subtitles", page=page, episode=ep, probe=False)
    Image.new("RGB", (64, 64), "#336699").save(tmp_path / "a.png")
    asset_storage.register(tmp_path / "a.png", f"episodes/{ep.pk}/covers/a.png", kind="image", role="cover", page=page, episode=ep, probe=False)            # the one cover
    export(pub)
    n = names(pub)
    assert "episode-01.srt" in n and "cover.png" in n and "ig_reel/cover.png" in n and "telegram/cover.png" in n               # the one cover serves every network
    # a cover MADE FOR a network (the cover work records the network in its provenance) wins for that network
    Image.new("RGB", (64, 64), "#aa3366").save(tmp_path / "b.png")
    rel = f"episodes/{ep.pk}/covers/ig.png"
    asset_storage.storage.import_file(tmp_path / "b.png", rel)
    made = Asset.objects.create(kind="image", role="cover", path=rel, page=page, episode=ep, provenance={"network": "ig_reel"}, is_current=True, mime="image/png", size_bytes=10)
    assert dp.cover_for(ep, "ig_reel", pub).pk == made.pk and dp.cover_for(ep, "telegram", pub).pk != made.pk
    export(pub)
    z = zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path))
    assert z.read("ig_reel/cover.png") != z.read("telegram/cover.png")


def test_a_cover_made_by_the_cover_maker_also_ships_its_jpeg_when_that_module_exists(tmp_path, ffmpeg_available, monkeypatch):
    import sys
    import types

    from PIL import Image

    page, ep, video, pub = build(tmp_path, targets=[("ig_reel", True, "")])
    Image.new("RGB", (64, 64), "#336699").save(tmp_path / "c.png")
    asset_storage.register(tmp_path / "c.png", f"episodes/{ep.pk}/covers/c.png", kind="image", role="cover", page=page, episode=ep, probe=False, provenance={"tool": "instai.covers"})
    monkeypatch.setitem(sys.modules, "instai.covers", None)          # the cover maker exists now: make it unimportable on purpose for the 'not installed' half
    export(pub)
    assert "cover.png" in names(pub) and "cover.jpg" not in names(pub)                  # no cover maker installed: just the file
    fake = types.ModuleType("instai.covers.service")
    fake.jpeg_of_asset = lambda cover: b"JPEG-FAKE-BYTES"
    monkeypatch.setitem(sys.modules, "instai.covers", types.ModuleType("instai.covers"))
    monkeypatch.setitem(sys.modules, "instai.covers.service", fake)
    sys.modules["instai.covers"].service = fake
    export(pub)
    n = names(pub)
    assert {"cover.png", "cover.jpg", "ig_reel/cover.png", "ig_reel/cover.jpg"} <= n
    assert zipfile.ZipFile(asset_storage.storage.path_for(pub.package.path)).read("cover.jpg") == b"JPEG-FAKE-BYTES"
    fake.jpeg_of_asset = lambda cover: (_ for _ in ()).throw(RuntimeError("boom"))       # a failing cover maker never breaks the package
    export(pub)
    assert "cover.png" in names(pub) and "cover.jpg" not in names(pub)


# ------------------------------------------------------------------------------------------------------------------------------ the API

def test_the_networks_catalogue_and_the_targets_api(api, tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path)
    cat = api.get("/api/delivery/networks").json()
    assert [n["key"] for n in cat["networks"]] == list(delivery.KEYS) and [p["key"] for p in cat["loudness_profiles"]] == ["social", "messenger", "broadcast"]
    assert cat["rerender_aspects"] == ["9:16"] and cat["legacy"]["instagram"] == "ig_reel"
    r = api.post(f"/api/pages/{page.pk}/targets", {"platform": "yt_shorts"}, format="json")
    assert r.status_code == 201 and r.json()["network"] == "yt_shorts" and r.json()["network_fa"] == "شورتسِ یوتیوب"
    assert api.post(f"/api/pages/{page.pk}/targets", {"platform": "myspace"}, format="json").status_code == 400
    assert api.post(f"/api/pages/{page.pk}/targets", {}, format="json").json()["network"] == "ig_reel"        # no platform = what it always meant
    rows = api.get(f"/api/pages/{page.pk}/targets").json()
    assert [x["network"] for x in rows] == ["yt_shorts", "ig_reel"] and rows[0]["fit"] == "" and rows[0]["enabled"] is True
    t = rows[0]["id"]
    assert api.patch(f"/api/targets/{t}", {"config": {"fit": "blur"}}, format="json").json()["config"]["fit"] == "blur"
    assert api.get(f"/api/pages/{page.pk}/targets").json()[0]["fit"] == "blur"
    assert api.patch(f"/api/targets/{t}", {"config": {"fit": "stretch"}}, format="json").status_code == 400
    assert api.patch(f"/api/targets/{t}", {"enabled": False}, format="json").json()["enabled"] is False


def test_the_delivery_endpoint_plans_the_package_and_checks_a_draft_caption(api, tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path, targets=[("ig_reel", True, ""), ("yt_wide", True, "")], caption="متن درست.", tags=("سریال_کوتاه",))
    d = api.get(f"/api/publications/{pub.pk}/delivery").json()
    by = {n["key"]: n for n in d["networks"]}
    assert by["ig_reel"]["status"] == "ready" and by["yt_wide"]["status"] == "needs_aspect" and by["yt_wide"]["offers"] == ["fit_blur"] and d["no_targets"] is False
    assert d["source"]["aspect"] == "9:16" and d["source"]["loudness_lufs"] is not None and d["page_lufs"] == -14.0 and d["lint"] == []
    draft = api.post(f"/api/publications/{pub.pk}/delivery", {"caption": "۶۰۰٬۰۰ تومان", "hashtags": ["سریالکوتاه"]}, format="json").json()
    assert [w["code"] for w in draft["lint"]] == ["broken_number", "glued_hashtag"] and draft["hashtags"]["changed"] == ["سریالکوتاه"] and draft["hashtags"]["repaired"] == ["سریال_کوتاه"]
    assert Publication.objects.get(pk=pub.pk).caption == "متن درست.", "checking a draft saves nothing"
    assert api.get(f"/api/publications/{pub.pk + 99}/delivery").status_code == 404


def test_the_export_job_reports_the_networks_and_never_posts(api, worker, tmp_path, ffmpeg_available):
    page, ep, video, pub = build(tmp_path, targets=[("ig_story", True, ""), ("yt_wide", True, "")], tags=("سریال_کوتاه",))
    j = finish(api, worker, api.post(f"/api/publications/{pub.pk}/export"))
    assert j["result"]["networks"] == ["ig_story"] and j["result"]["warnings"] == 0 and j["result"]["size_bytes"] > 1000
    pub.refresh_from_db()
    assert pub.status == "exported" and pub.external_url == "" and pub.package_id
    assert "ig_story/episode-01-ig_story.mp4" in names(pub)


def test_the_instagram_api_adapter_accepts_the_reel_key_like_the_old_name(tmp_path, ffmpeg_available):
    from instai.publishing import adapters

    page, ep, video, pub = build(tmp_path, targets=[])
    for platform in ("instagram", "ig_reel"):
        t = PublishTarget.objects.create(page=page, platform=platform, mode="api")
        assert adapters.adapter_for(t).name == "instagram_graph", platform
    t = PublishTarget.objects.create(page=page, platform="ig_post", mode="api")
    assert adapters.adapter_for(t).name == "manual"                              # the API posts a Reel only
