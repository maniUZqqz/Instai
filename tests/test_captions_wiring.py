"""Word-by-word captions in the product: the page profile and the episode override, the catalogue and the real preview pictures of the API, the episode render with
fake providers (a real mp4 with captions burned in by libass, the soft .srt next to it, the publishing package), the staleness hash, and the plain look that nothing
changes for a page that never picks a preset."""
from __future__ import annotations

import io
import zipfile

import pytest
from PIL import Image

from instai.pages import profiles
from instai.render import captions, safezones, titles_ass
from tests.conftest import finish
from tests.test_pipeline_e2e import build_episode, produce

pytestmark = pytest.mark.django_db(transaction=True)


# ------------------------------------------------------------------ the profile

def test_the_visual_profile_has_the_caption_style_and_the_default_is_the_plain_look():
    d = profiles.default_data("visual")
    assert d["caption_style"] == {"preset": "classic", "mode": "burned", "zone": "auto"} and d["subtitle"]["font"], "the old subtitle settings are untouched"
    assert profiles.normalize("visual", None)["caption_style"] == captions.DEFAULT_CONFIG
    assert profiles.normalize("visual", {"caption_style": {"preset": "karaoke", "mode": "soft", "zone": "tiktok", "junk": 1}})["caption_style"] == {"preset": "karaoke", "mode": "soft", "zone": "tiktok"}
    assert profiles.normalize("visual", {"caption_style": {"preset": "nope", "mode": "x", "zone": "mars"}})["caption_style"] == captions.DEFAULT_CONFIG
    assert profiles.normalize("visual", {"caption_style": "pop"})["caption_style"] == captions.DEFAULT_CONFIG
    for kind in profiles.KINDS:
        assert profiles.normalize(kind, profiles.default_data(kind)) == profiles.default_data(kind)
    assert profiles.default_data("publishing")["caption_style"] == "", "the PUBLISHING caption_style (the post text's tone) is another thing and keeps its name"


def test_the_profile_api_keeps_the_choice_and_an_old_page_reads_the_default(api):
    page = api.post("/api/pages", {"name": "پیج", "format": "anime_whatif", "languages": ["fa"], "idea": "x"}, format="json").json()
    assert api.get(f"/api/pages/{page['id']}").json()["profiles"]["visual"]["caption_style"] == captions.DEFAULT_CONFIG
    r = api.put(f"/api/pages/{page['id']}/profiles/visual", {"caption_style": {"preset": "neon", "mode": "burned", "zone": "auto"}}, format="json")
    assert r.status_code == 200 and r.json()["profiles"]["visual"]["caption_style"]["preset"] == "neon"
    assert r.json()["profiles"]["visual"]["subtitle"]["position"] == "bottom", "saving the caption style does not lose the other visual settings"


# ------------------------------------------------------------------ the catalogue and the previews

def test_the_catalogue_lists_all_presets_modes_zones_and_fonts(api, ffmpeg_available):
    j = api.get("/api/captions").json()
    assert [p["key"] for p in j["presets"]] == ["classic", "pop", "box", "karaoke", "clean", "neon", "typewriter", "lower"]
    assert all(p["fa"] and p["en"] and p["hint_fa"] and p["hint_en"] for p in j["presets"])
    assert {m["key"] for m in j["modes"]} == {"burned", "soft", "none"} and j["zones"][0]["key"] == "auto" and len(j["zones"]) == 1 + len(safezones.ZONES)
    assert {f["key"] for f in j["fonts"]} >= {"vazir", "vazir_black", "vazir_light"} and all(f["licence"] == "SIL OFL 1.1" for f in j["fonts"])
    assert j["default"] == captions.DEFAULT_CONFIG and j["libass"] is True and j["shapes"] == ["vertical", "landscape"] and j["samples"]["fa"] and j["samples"]["en"]


@pytest.fixture
def page(api):
    return api.post("/api/pages", {"name": "پیج", "format": "anime_whatif", "languages": ["fa"], "idea": "x"}, format="json").json()


def png(api, url) -> Image.Image:
    r = api.get(url)
    assert r.status_code == 200
    data = b"".join(r.streaming_content) if hasattr(r, "streaming_content") else r.content
    return Image.open(io.BytesIO(data)).convert("RGB")


@pytest.mark.slow
def test_the_previews_are_real_pictures_drawn_by_the_engine_and_cached(api, page, ffmpeg_available):
    if not (ffmpeg_available.get("features") or {}).get("ass"):
        pytest.skip("no ass filter")
    j = api.get(f"/api/captions/previews?page={page['id']}").json()
    assert j["ok"] and j["shape"] == "vertical" and j["zone"] == "reels" and len(j["previews"]) == 8 and j["margins"]["bottom"] >= 0.2
    images = {}
    for row in j["previews"]:
        assert row["url"] and not row.get("error") and row["fa"] and row["en"], row
        images[row["key"]] = png(api, row["url"])
        assert images[row["key"]].size == (450, 800)
        if row["key"] != "classic":
            assert row["contrast"]["text"] >= 4.5 and row["contrast"]["highlight"] >= 4.5
    assert len({im.tobytes() for im in images.values()}) == 8, "every preset has its own picture"
    again = api.get(f"/api/captions/previews?page={page['id']}").json()
    assert [r["url"] for r in again["previews"]] == [r["url"] for r in j["previews"]], "the same look gives the same files (a cache, not new pictures each time)"
    land = api.get(f"/api/captions/previews?page={page['id']}&shape=landscape").json()
    assert land["zone"] == "youtube" and png(api, land["previews"][1]["url"]).size == (800, 450)
    tiktok = api.get(f"/api/captions/previews?page={page['id']}&zone=tiktok").json()
    assert tiktok["zone"] == "tiktok" and tiktok["previews"][1]["url"] != j["previews"][1]["url"]


@pytest.mark.slow
def test_a_series_look_changes_the_preview_colours(api, page, ffmpeg_available):
    if not (ffmpeg_available.get("features") or {}).get("ass"):
        pytest.skip("no ass filter")
    from instai.remotion import kit

    kits = [k for k in kit.all_kits()]
    first = kits[0]
    other = next(k for k in kits if k["palette"] != first["palette"])
    api.put(f"/api/pages/{page['id']}/profiles/visual", {"style_key": first["key"], "theme_key": first["theme_key"]}, format="json")
    a = api.get(f"/api/captions/previews?page={page['id']}").json()
    api.put(f"/api/pages/{page['id']}/profiles/visual", {"style_key": other["key"], "theme_key": other["theme_key"]}, format="json")
    b = api.get(f"/api/captions/previews?page={page['id']}").json()
    assert a["look"]["style_key"] == first["key"] and b["look"]["style_key"] == other["key"]
    assert b["look"]["palette"] != a["look"]["palette"] and b["previews"][1]["url"] != a["previews"][1]["url"], "another series look, other colours, other pictures"


def test_the_previews_need_a_page_or_an_episode(api):
    r = api.get("/api/captions/previews")
    assert r.status_code == 400
    assert api.get("/api/captions/previews?page=99999").status_code == 404


# ------------------------------------------------------------------ the episode override

def test_an_episode_overrides_the_page_key_by_key_and_can_go_back(api, worker):
    page, sid, ep_id = build_episode(api, worker)
    api.put(f"/api/pages/{page['id']}/profiles/visual", {"caption_style": {"preset": "pop", "mode": "burned", "zone": "auto"}}, format="json")
    j = api.get(f"/api/episodes/{ep_id}/captions").json()
    assert j["override"] == {} and j["effective"]["preset"] == "pop" and j["page"]["preset"] == "pop" and j["language"] == "fa" and j["platform"] == "instagram"
    r = api.put(f"/api/episodes/{ep_id}/captions", {"preset": "neon"}, format="json").json()
    assert r["override"] == {"preset": "neon"} and r["effective"] == {"preset": "neon", "mode": "burned", "zone": "auto"} and r["page"]["preset"] == "pop"
    r = api.put(f"/api/episodes/{ep_id}/captions", {"mode": "soft"}, format="json").json()
    assert r["override"] == {"mode": "soft"} and r["effective"]["preset"] == "pop", "a PUT replaces the override; the page's value shows through again"
    assert api.get(f"/api/episodes/{ep_id}").json()["captions"]["effective"]["mode"] == "soft"
    assert api.put(f"/api/episodes/{ep_id}/captions", {"preset": "comic_sans"}, format="json").status_code == 400
    assert api.put(f"/api/episodes/{ep_id}/captions", {"zone": "mars"}, format="json").status_code == 400
    assert api.delete(f"/api/episodes/{ep_id}/captions").json()["override"] == {} and api.get(f"/api/episodes/{ep_id}/captions").json()["effective"]["mode"] == "burned"
    assert api.put(f"/api/episodes/{ep_id}/captions", {}, format="json").json()["override"] == {}


def test_the_hash_part_and_the_default_check_follow_the_choice(api, worker):
    from instai.production import captions as ep_captions
    from instai.production import pipeline
    from instai.story.models import Episode

    page, sid, ep_id = build_episode(api, worker)
    ep = Episode.objects.get(pk=ep_id)
    assert pipeline.captions_default(ep), "a page that never picked keeps the hashes it had"
    base = pipeline.timeline_hash(ep, "preview")
    api.put(f"/api/episodes/{ep_id}/captions", {"preset": "karaoke"}, format="json")
    ep.refresh_from_db()
    assert not pipeline.captions_default(ep) and pipeline.timeline_hash(ep, "preview") != base, "another caption style means the video is made again (only the joining step)"
    h = ep_captions.hash_part(ep)
    api.put(f"/api/episodes/{ep_id}/captions", {"preset": "neon"}, format="json")
    ep.refresh_from_db()
    assert ep_captions.hash_part(ep) != h
    api.delete(f"/api/episodes/{ep_id}/captions")
    ep.refresh_from_db()
    assert pipeline.timeline_hash(ep, "preview") == base


# ------------------------------------------------------------------ the real render

def _assets(ep_id, suffix):
    from instai.assets.models import Asset

    return list(Asset.objects.filter(episode_id=ep_id, role="subtitles", path__endswith=suffix).order_by("id"))


def _text(asset) -> str:
    from instai.assets.storage import storage

    return storage.path_for(asset.path).read_text(encoding="utf-8-sig")


@pytest.mark.slow
def test_a_page_that_never_picked_a_preset_renders_exactly_as_before_and_gets_an_srt(api, worker, ffmpeg_available):
    if not (ffmpeg_available.get("features") or {}).get("ass"):
        pytest.skip("no ass filter")
    page, sid, ep_id = build_episode(api, worker)
    ep = produce(api, worker, ep_id, "preview")
    assert ep["state"] == "ready_for_approval"
    video = next(v for v in ep["videos"] if v["role"] == "preview")
    assert video["provenance"]["captions"]["preset"] == "classic" and video["provenance"]["captions"]["estimated"] is True and video["provenance"]["subtitle_cues"] >= 3
    ass = _assets(ep_id, ".ass")
    assert ass and "Style: Default," in _text(ass[-1]) and "Style: T0" not in _text(ass[-1]), "the plain InstAI subtitle: its own ASS, untouched"
    srt = _assets(ep_id, ".srt")
    assert srt and srt[-1].provenance["from"] == video["id"] and srt[-1].provenance["captions"]["preset"] == "classic"
    raw = open(__import__("instai.assets.storage", fromlist=["storage"]).storage.path_for(srt[-1].path), "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf") and "-->" in raw.decode("utf-8-sig")


@pytest.mark.slow
def test_a_preset_is_burned_in_with_the_series_colours_and_only_the_join_is_redone(api, worker, ffmpeg_available):
    from instai.assets.models import Asset

    if not (ffmpeg_available.get("features") or {}).get("ass"):
        pytest.skip("no ass filter")
    page, sid, ep_id = build_episode(api, worker)
    produce(api, worker, ep_id, "preview")
    clips_before = Asset.objects.filter(episode_id=ep_id, role="render_clip").count()
    kf_before = Asset.objects.filter(episode_id=ep_id, role="keyframe").count()
    api.put(f"/api/pages/{page['id']}/profiles/visual", {"caption_style": {"preset": "karaoke", "mode": "burned", "zone": "auto"}}, format="json")
    ep = produce(api, worker, ep_id, "preview")
    assert ep["state"] == "ready_for_approval"
    assert Asset.objects.filter(episode_id=ep_id, role="render_clip").count() == clips_before and Asset.objects.filter(episode_id=ep_id, role="keyframe").count() == kf_before, \
        "a caption change re-joins the video; keyframes, narration and shot clips are reused"
    video = next(v for v in ep["videos"] if v["role"] == "preview")
    info = video["provenance"]["captions"]
    assert info["preset"] == "karaoke" and info["estimated"] is True and info["zone"] == "reels" and info["contrast"]["text"] >= 4.5 and info["contrast"]["marker"] >= 4.5
    ass = _text(_assets(ep_id, ".ass")[-1])
    assert "Style: T0,Vazirmatn Black," in ass and "Dialogue: 1," in ass and info["colors"]["highlight"].lstrip("#")[4:6] in ass.upper().replace("&H", ""), "the word-by-word script, in the series' accent colour"
    assert (video["width"], video["height"]) == (360, 640) and video["codec"] == "h264"
    # an episode override wins over the page, and the video records it
    api.put(f"/api/episodes/{ep_id}/captions", {"preset": "box"}, format="json")
    ep = produce(api, worker, ep_id, "preview")
    assert next(v for v in ep["videos"] if v["role"] == "preview")["provenance"]["captions"]["preset"] == "box"


@pytest.mark.slow
def test_soft_and_none_modes_and_the_publishing_package(api, worker, ffmpeg_available):
    from instai.assets.models import Asset
    from instai.assets.storage import storage
    from instai.story.models import Episode

    if not (ffmpeg_available.get("features") or {}).get("ass"):
        pytest.skip("no ass filter")
    page, sid, ep_id = build_episode(api, worker)
    api.put(f"/api/episodes/{ep_id}/captions", {"preset": "pop", "mode": "soft"}, format="json")
    ep = produce(api, worker, ep_id, "preview")
    video = next(v for v in ep["videos"] if v["role"] == "preview")
    assert video["provenance"]["captions"]["mode"] == "soft" and video["provenance"]["subtitle_cues"] == 0, "soft: nothing burned into the picture"
    assert _assets(ep_id, ".srt")[-1].provenance["from"] == video["id"]
    pub = api.post(f"/api/pages/{page['id']}/publications", {"episode": ep_id, "caption": "متن", "hashtags": ["انیمه"]}, format="json").json()
    j = finish(api, worker, api.post(f"/api/publications/{pub['id']}/export"))
    z = zipfile.ZipFile(storage.path_for(Asset.objects.get(pk=j["result"]["package_asset_id"]).path))
    name = f"episode-{Episode.objects.get(pk=ep_id).number:02d}.srt"
    assert {"caption.txt", "hashtags.txt", "README.txt", "cover.png", name} <= set(z.namelist())
    assert z.read(name).startswith(b"\xef\xbb\xbf") and b"-->" in z.read(name) and name in z.read("README.txt").decode()
    # none: neither burned in nor a file; an older .srt of an earlier render is not shipped with the new video
    api.put(f"/api/episodes/{ep_id}/captions", {"mode": "none"}, format="json")
    ep = produce(api, worker, ep_id, "preview")
    video2 = next(v for v in ep["videos"] if v["role"] == "preview")
    assert video2["provenance"]["captions"]["mode"] == "none" and video2["id"] != video["id"]
    from instai.production import captions as ep_captions
    from instai.story.models import Episode

    assert ep_captions.srt_asset(Episode.objects.get(pk=ep_id), Asset.objects.get(pk=video2["id"])) is None, "no caption file belongs to this video"
    pub2 = api.post(f"/api/pages/{page['id']}/publications", {"episode": ep_id, "caption": "دوم"}, format="json").json()
    j2 = finish(api, worker, api.post(f"/api/publications/{pub2['id']}/export"))
    z2 = zipfile.ZipFile(storage.path_for(Asset.objects.get(pk=j2["result"]["package_asset_id"]).path))
    assert not [n for n in z2.namelist() if n.endswith(".srt")]


@pytest.mark.slow
def test_an_english_page_gets_left_to_right_captions(api, worker, ffmpeg_available):
    if not (ffmpeg_available.get("features") or {}).get("ass"):
        pytest.skip("no ass filter")
    from instai.production import captions as ep_captions
    from instai.story.models import Episode

    page, sid, ep_id = build_episode(api, worker)
    from instai.pages.models import ContentPage

    ContentPage.objects.filter(pk=page["id"]).update(languages=["en"])
    ep = Episode.objects.get(pk=ep_id)
    assert ep.series.page.language == "en" and ep_captions.summary(ep)["language"] == "en"
    cfg = {"preset": "pop", "mode": "burned", "zone": "auto"}
    api.put(f"/api/pages/{page['id']}/profiles/visual", {"caption_style": cfg}, format="json")
    plan = captions.plan([{"text": "This reads left to right", "start": 0.0, "duration": 2.0}], cfg, 360, 640, language="en")
    assert titles_ass.LRM in plan["ass"] and titles_ass.RLM not in plan["ass"]
