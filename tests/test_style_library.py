"""The art/animation style library (v2): 100+ looks, browse groups, suitability, generation hints, search by the names people use (without ever putting
those names into a prompt), built-in preview pictures, real sample images made by the GPU, and the wiring of the chosen look into every generation path
(keyframes, video clips, design sheets, the storyboard prompt) with the series' own pick winning over the page's."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import pytest

from instai.styles import aliases, library, preview_svg, previews, schema
from instai.styles.builtin_styles import BUILTIN_STYLES
from instai.styles.builtin_themes import BUILTIN_THEMES

pytestmark = pytest.mark.django_db(transaction=True)

# names a style's own data (name, description, prompts, tags) must never contain: studios, franchises, brands, creators, artists
BANNED = ["ghibli", "pixar", "disney", "dreamworks", "cartoon network", "nickelodeon", "lego", "minecraft", "playstation", "ps2", "zackd", "zack d", "dan koe", "kodak",
          "polaroid", "funko", "warhol", "lichtenstein", "hokusai", "mucha", "monet", "simpsons", "adventure time", "wallace", "alegria", "naruto", "dragon ball",
          "one piece", "marvel", "blade runner", "gatsby", "frutiger"]

# the owner's list, written the way he wrote it: every one must find at least one style
OWNER_LIST = ["Pixel Art", "ChalkBoard", "Glow Sketch", "PS2 style", "Comic Art", "Flat Vector", "Dan Koe style", "CGI Motion", "Lego", "ZackD Films style", "Anime",
              "Studio Ghibli", "Disney", "Cartoon Network", "Watercolor", "Cel Shading", "Line Art", "Silhouette", "Claymation", "Stop Motion", "Low Poly", "Voxel Art",
              "Papercraft", "Origami", "Isometric", "Photorealistic CGI", "2.5D Parallax", "Synthwave", "Film Noir", "Cyberpunk", "Steampunk", "Pop Art", "Stained Glass",
              "Graffiti", "Blueprint", "Glitch Art", "Whiteboard", "Kinetic Typography", "Infographic", "Corporate Memphis", "Stickman", "Flat 2D", "3D Claymation",
              "Glassmorphism", "Chrome 22K", "Cineview", "Risograph", "Paper Collage", "Particles", "Neo-brutalism", "Bauhaus", "Memphis", "Vaporwave"]


@pytest.fixture(autouse=True)
def _fresh_library():
    library.clear_cache()          # user presets are cached for a moment; the previous test's rows must not leak into this one
    yield
    library.clear_cache()


def rows() -> list[dict]:
    return library.list_presets("style")


def test_library_has_a_hundred_looks_and_every_group_is_filled():
    assert len(BUILTIN_STYLES) >= 100 and len(BUILTIN_THEMES) >= 24
    by_group: dict[str, int] = {}
    for s in BUILTIN_STYLES.values():
        by_group[s["group"]] = by_group.get(s["group"], 0) + 1
    assert set(by_group) == set(schema.GROUPS), "every group has styles and every style a known group"
    assert min(by_group.values()) >= 8


def test_every_look_is_complete_and_has_valid_generation_hints():
    for key, s in BUILTIN_STYLES.items():
        assert s["name_fa"] and s["name_en"] and s["description_fa"] and s["description_en"], key
        assert s["image_positive"] and s["image_negative"] and s["video_positive"] and s["video_negative"] and s["sample_prompt"], key
        assert s["group"] in schema.GROUPS and s["suitability"] and set(s["suitability"]) <= set(schema.SUITABILITY), key
        assert s["theme_key"] in BUILTIN_THEMES and len(s["palette"]) >= 5, key
        g = s["gen"]
        assert g["model"] in schema.BASE_MODELS and g["aspect"] in schema.ASPECTS and 4 <= g["steps"] <= 60 and 0 <= g["cfg"] <= 30 and g["sampler"], key
        assert s["motif"] in preview_svg.MOTIFS, f"{key}: the preview picture has no drawing for motif {s['motif']!r}"
        assert re.search(r"[؀-ۿ]", s["name_fa"]), f"{key}: the Persian name is not Persian"
    kinds = {x for s in BUILTIN_STYLES.values() for x in s["suitability"]}
    assert kinds == set(schema.SUITABILITY)
    assert sum("character" in s["suitability"] for s in BUILTIN_STYLES.values()) >= 40
    assert sum("video" in s["suitability"] for s in BUILTIN_STYLES.values()) >= 70


def test_no_studio_brand_or_creator_name_is_in_the_style_data_or_any_composed_prompt():
    blob = json.dumps([BUILTIN_STYLES, BUILTIN_THEMES], ensure_ascii=False).lower()
    assert [w for w in BANNED if w in blob] == []
    for key in BUILTIN_STYLES:
        c = library.compose(key)
        text = " ".join(str(c[k]) for k in ("positive", "negative", "video_positive", "video_negative")).lower()
        assert [w for w in BANNED if w in text] == [], key


def test_the_owners_whole_list_is_searchable_by_the_names_he_uses():
    lib = rows()
    for name in OWNER_LIST:
        assert library.filter_styles(lib, q=name), f"nothing found for {name!r}"
    # the names he uses lead to the generic look that stands in for them
    expect = {"ghibli": "painterly_pastoral", "lego": "toy_brick_3d", "ps2": "early_console_3d", "dan koe": "minimal_bw_essay", "zackd": "fast_3d_explainer",
              "disney": "fairytale_feature_2d", "cartoon network": "bold_angular_tv_toon", "pixar": "cg_family_3d", "chrome 22k": "chrome_metal_type"}
    for q, key in expect.items():
        assert key in [r["key"] for r in library.filter_styles(lib, q=q)], q
    # Persian spellings and digit alphabets work too
    assert "painterly_pastoral" in [r["key"] for r in library.filter_styles(lib, q="ژیبلی")]
    assert "early_console_3d" in [r["key"] for r in library.filter_styles(lib, q="پی اس ۲")]
    assert library.filter_styles(lib, q="نئوبروتالیسم")
    assert library.filter_styles(lib, q="zzzz-not-a-style") == []


def test_aliases_only_name_real_styles_and_never_reach_a_prompt():
    assert [k for k in aliases.ALIASES if k not in BUILTIN_STYLES] == []
    for row in rows():
        if row["builtin"]:
            assert row["search_terms"] == aliases.terms_for(row["key"])
    c = library.compose("toy_brick_3d")
    assert "lego" not in json.dumps(c, ensure_ascii=False).lower()


def test_filters_by_group_suitability_and_realism_through_the_api(api):
    lib = api.get("/api/library").json()
    assert {g["key"] for g in lib["groups"]} == set(schema.GROUPS) and {s["key"] for s in lib["suitability"]} == set(schema.SUITABILITY)
    assert len(lib["styles"]) >= 100 and all("preview_url" in s for s in lib["styles"])
    r = api.get("/api/library/style?group=craft").json()
    assert r and all(s["group"] == "craft" for s in r)
    r = api.get("/api/library/style?suitability=character&group=anime_toon").json()
    assert r and all("character" in s["suitability"] and s["group"] == "anime_toon" for s in r)
    r = api.get("/api/library/style?q=lego").json()
    assert [s["key"] for s in r] == ["toy_brick_3d"]
    assert api.get("/api/library/style?realism=realistic").json()
    # the list is grouped in the owner's order
    order = [g["key"] for g in lib["groups"]]
    seen = [s["group"] for s in lib["styles"] if s["builtin"]]
    assert seen == sorted(seen, key=order.index)


def test_every_style_has_a_valid_preview_picture(api):
    for key, s in BUILTIN_STYLES.items():
        svg = preview_svg.render({**s, "key": key})
        root = ET.fromstring(svg)                      # well-formed XML
        assert root.tag.endswith("svg") and len(svg) < 120_000, key
    a = preview_svg.render({**BUILTIN_STYLES["cg_family_3d"], "key": "cg_family_3d"})
    b = preview_svg.render({**BUILTIN_STYLES["cg_family_3d"], "key": "cg_family_3d"})
    assert a == b, "deterministic"
    assert preview_svg.render({"key": "x"}).startswith("<svg"), "a user style without a motif still gets one"
    r = api.get("/api/library/style/pixel_art_16bit/preview.svg")
    assert r.status_code == 200 and r["Content-Type"].startswith("image/svg+xml") and b"<svg" in r.content
    assert api.get("/api/library/style/nope/preview.svg").status_code == 404


def test_gradient_ids_of_two_previews_do_not_collide():
    ids = []
    for key in ("cg_family_3d", "claymation_stopmotion"):
        svg = preview_svg.render({**BUILTIN_STYLES[key], "key": key})
        ids += re.findall(r'id="([a-z0-9]+)"', svg)
    assert len(ids) == len(set(ids))


def test_old_user_styles_and_bundles_still_work_with_the_new_fields(api):
    st = schema.normalize_style({"name_en": "old", "image_positive": "x"})
    assert st["group"] == "" and st["suitability"] == ["image", "video", "character"] and st["gen"]["steps"] == 24 and st["motif"] == ""
    st = schema.normalize_style({"name_en": "n", "gen": {"steps": 999, "model": "weird", "aspect": "7:3", "lora": ["a" * 300], "cfg": "x"}, "group": "nope",
                                 "suitability": ["video", "bogus"], "motif": "Pixel!!"})
    assert st["gen"]["steps"] == 60 and st["gen"]["model"] == "flux_dev" and st["gen"]["aspect"] == "9:16" and len(st["gen"]["lora"][0]) == 120 and st["gen"]["cfg"] == 1.0
    assert st["group"] == "" and st["suitability"] == ["video"] and st["motif"] == "pixel"
    made = api.post("/api/library/style", {"name_en": "Mine", "image_positive": "p", "group": "craft", "suitability": ["image"], "motif": "paper",
                                           "gen": {"steps": 30}}, format="json").json()
    assert made["group"] == "craft" and made["gen"]["steps"] == 30 and made["preview_url"].endswith("/preview.svg")
    # a copy of a built-in keeps its hints, and the export bundle carries them
    copy = api.post("/api/library/style/pixel_art_16bit/duplicate", {}, format="json").json()
    assert copy["group"] == "retro_digital" and copy["gen"]["steps"] == 28 and copy["motif"] == "pixel"
    bundle = json.loads(api.get(f"/api/library/export?styles={copy['key']}").content)
    assert bundle["styles"][0]["gen"]["steps"] == 28 and bundle["format"] == "instai.styles@1"


# ------------------------------------------------------------------ wiring: the look in force reaches every generation path

def make_project(api, series_look=None, page_style="modern_tv_anime"):
    from instai.story.models import Episode, Series

    page = api.post("/api/pages", {"name": "p", "format": "recurring_character", "languages": ["fa"]}, format="json").json()
    api.post(f"/api/pages/{page['id']}/apply-look", {"style_key": page_style, "style_notes": "my page note"}, format="json")
    s = api.post(f"/api/pages/{page['id']}/series", {"title": "s", "look": series_look or {}}, format="json").json()
    series = Series.objects.get(pk=s["id"])
    ep = Episode.objects.create(series=series, number=1, title="e")
    return page, series, ep


def test_the_series_own_pick_wins_over_the_pages_look_and_defaults_its_theme(api):
    from instai.production import pipeline

    page, series, ep = make_project(api)
    page_prompt = pipeline.style_prompt(ep)
    assert "modern anime style" in page_prompt and "my page note" in page_prompt
    series.look = {"style_key": "pixel_art_16bit"}                  # picked once for the project: only the style, no theme
    series.save()
    ep.refresh_from_db()
    ep = type(ep).objects.select_related("series__page").get(pk=ep.pk)
    prompt = pipeline.style_prompt(ep)
    assert "pixel art" in prompt.lower() and "modern anime style" not in prompt and "my page note" in prompt, "the page's free-text notes still apply"
    comp = library.compose_for_series(series)
    th = library.get_theme(library.get_style("pixel_art_16bit")["theme_key"])
    assert th["prompt_fragment"].split(",")[0] in comp["positive"], "the project's style brings ITS default colour theme, not the page's"
    assert library.look_of(series.page, series)["own"] is True
    # the API shows what is sent to the models
    c = api.get(f"/api/library/compose?series={series.pk}").json()
    assert c["style"] == "pixel_art_16bit" and c["look"]["own"] and c["gen"]["steps"] == 28
    p = api.get(f"/api/library/compose?page={page['id']}").json()
    assert p["style"] == "modern_tv_anime" and not p["look"]["own"]
    assert api.get("/api/library/compose?series=99999").status_code == 404


def test_changing_the_look_makes_the_keyframes_and_clips_out_of_date(api):
    from instai.production import pipeline
    from instai.story.models import Scene, Shot

    page, series, ep = make_project(api)
    sc = Scene.objects.create(episode=ep, index=1)
    shot = Shot.objects.create(scene=sc, index=1, image_prompt="a cat", technique="wan_i2v")
    h1 = pipeline.keyframe_hash(shot, ep, "preview")
    series.look = {"style_key": "claymation_stopmotion"}
    series.save()
    ep = type(ep).objects.select_related("series__page").get(pk=ep.pk)
    assert pipeline.keyframe_hash(shot, ep, "preview") != h1
    pos, neg = pipeline.style_video(ep)
    assert "stop-motion" in pos and "smooth fluid motion" in neg
    assert 12 <= pipeline.style_steps(ep) <= 40


def test_video_clip_prompts_carry_the_looks_motion_fragments(monkeypatch):
    """The Wan call gets the shot's own negative AND the look's motion negatives (e.g. 'too smooth interpolation' for limited animation)."""
    from pathlib import Path

    from instai.gpu import compute
    from instai.production import hero
    from instai.providers.base import ProviderError

    seen = {}

    def fake_run_task(ctx, kind, payload, inputs=None, **kw):
        g = payload["graph"]
        seen["texts"] = [n["inputs"].get("text") for n in g.values() if n.get("class_type") == "CLIPTextEncode"]
        raise ProviderError("stop here", retryable=False, code="test_stop")

    monkeypatch.setattr(compute, "run_task", fake_run_task)
    monkeypatch.setattr(hero, "i2v_workflow", lambda page: ("wan22_i2v_a14b_fp8", None))

    class Ctx:
        def check(self):
            pass

    with pytest.raises(ProviderError):
        hero.generate_chain(Ctx(), page=None, start_path=Path("x.png"), end_path=None, duration=2.0, prompt="a cat walks, slow pan", negative="my shot negative",
                            seed=1, work=Path("."), negative_extra="too smooth interpolation, 3d camera orbit")
    joined = " | ".join(t for t in seen["texts"] if t)
    assert "a cat walks, slow pan" in joined and "my shot negative" in joined and "too smooth interpolation" in joined


def test_design_sheet_image_uses_the_series_look(api, monkeypatch):
    """A design sheet of an episode is rendered in the look of that episode's series (not only the page's), with the style's recommended steps."""
    from instai.core import settings_store
    from instai.gpu import compute
    from instai.studio.models import DesignSheet
    from tests import fakes
    from tests.conftest import finish
    from tests.test_gpu_use import GPU, comfy_stats

    from instai.core import hardware

    monkeypatch.setattr(hardware, "gpu_status", lambda: dict(GPU))
    compute._CAP_CACHE.update(at=0.0, value=None)
    page, series, ep = make_project(api, series_look={"style_key": "voxel_art"})
    sheet = DesignSheet.objects.create(page_id=page["id"], episode=ep, kind="prop", subject="red scarf", prompt="a red scarf")
    from instai.jobs.worker import WorkerRunner

    worker = WorkerRunner("t")
    with fakes.comfy_server() as c:
        c.stats = comfy_stats("cuda")
        settings_store.set_setting("comfyui_url", c.url)
        settings_store.set_setting("image_engine", "comfyui")
        try:
            finish(api, worker, api.post(f"/api/design-sheets/{sheet.pk}/image", {}, format="json"))
        finally:
            settings_store.set_setting("image_engine", "")
            settings_store.set_setting("comfyui_url", "")
            compute._CAP_CACHE.update(at=0.0, value=None)
    texts = " ".join(str(n["inputs"].get("text", "")) for n in c.prompts[-1].values() if n.get("class_type") == "CLIPTextEncode").lower()
    assert "a red scarf" in texts and "voxel" in texts and "modern anime style" not in texts


def test_storyboard_prompt_sees_the_series_look(api):
    from instai.jobs.handlers import story

    page, series, ep = make_project(api, series_look={"style_key": "origami_fold"})
    from instai.pages.models import ContentPage

    assert "origami" in story._style(ContentPage.objects.get(pk=page["id"]), series).lower()
    assert "origami" not in story._style(ContentPage.objects.get(pk=page["id"])).lower()


# ------------------------------------------------------------------ real sample images from the GPU

def test_sample_images_are_made_by_comfyui_once_and_replace_the_swatch(api, monkeypatch):
    from instai.core import hardware, settings_store
    from instai.gpu import compute
    from instai.jobs.worker import WorkerRunner
    from instai.styles.models import StylePreview
    from tests import fakes
    from tests.conftest import finish
    from tests.test_gpu_use import GPU, comfy_stats

    monkeypatch.setattr(hardware, "gpu_status", lambda: dict(GPU))
    compute._CAP_CACHE.update(at=0.0, value=None)
    worker = WorkerRunner("t")
    st = api.get("/api/library/previews").json()
    assert st["total"] >= 100 and st["pending"] == st["total"] and st["expected_seconds"] > 0
    # demo mode (placeholder engine): no real image can be made, and the job says so plainly
    j = api.post("/api/library/previews", {"keys": ["pixel_art_16bit"]}, format="json")
    assert j.status_code == 202
    failed = finish(api, worker, j, expect="failed")
    assert "ComfyUI" in failed["error"]
    with fakes.comfy_server() as c:
        c.stats = comfy_stats("cuda")
        settings_store.set_setting("comfyui_url", c.url)
        settings_store.set_setting("image_engine", "comfyui")
        try:
            r = api.post("/api/library/previews", {"keys": ["pixel_art_16bit", "low_poly_3d"]}, format="json")
            done = finish(api, worker, r)
            assert done["result"]["made"] == 2 and done["resource"] == "gpu"
            sheet = StylePreview.objects.get(style_key="pixel_art_16bit")
            assert sheet.asset_id and sheet.asset.provenance["provider"] == "comfyui" and sheet.asset.provenance["style"] == "pixel_art_16bit"
            graph_text = " ".join(str(n["inputs"].get("text", "")) for g in c.prompts for n in g.values() if n.get("class_type") == "CLIPTextEncode").lower()
            assert "pixel" in graph_text and "low-poly" in graph_text and len(c.prompts) == 2
            n_prompts = len(c.prompts)
            # the gallery shows the real picture now, and a second run skips what is up to date
            lib = {s["key"]: s for s in api.get("/api/library").json()["styles"]}
            assert lib["pixel_art_16bit"]["thumbnail_url"].startswith("/media/styles/pixel_art_16bit/")
            assert not lib["cg_family_3d"].get("thumbnail_url") and lib["cg_family_3d"]["preview_url"]
            assert api.get("/api/library/previews").json()["done"] == 2
            again = api.post("/api/library/previews", {"keys": ["pixel_art_16bit", "low_poly_3d"]}, format="json")
            assert again.status_code == 200 and again.json()["queued"] is False
            assert len(c.prompts) == n_prompts
        finally:
            settings_store.set_setting("image_engine", "")
            settings_store.set_setting("comfyui_url", "")
            compute._CAP_CACHE.update(at=0.0, value=None)


def test_a_changed_prompt_makes_the_sample_out_of_date():
    from instai.assets.models import Asset
    from instai.styles.models import StylePreview

    st = library.get_style("pixel_art_16bit")
    h = previews.prompt_hash(st, "flux_dev_fp8_t2i")
    StylePreview.objects.create(style_key="pixel_art_16bit", prompt_hash=h)       # no picture yet: still pending
    assert "pixel_art_16bit" in previews.pending("flux_dev_fp8_t2i")
    asset = Asset.objects.create(kind="image", role="reference", path="styles/pixel_art_16bit/x.png")
    StylePreview.objects.filter(style_key="pixel_art_16bit").update(asset=asset)
    assert "pixel_art_16bit" not in previews.pending("flux_dev_fp8_t2i"), "made from the same prompt: up to date"
    StylePreview.objects.filter(style_key="pixel_art_16bit").update(prompt_hash="old")
    assert "pixel_art_16bit" in previews.pending("flux_dev_fp8_t2i"), "made from an older prompt: out of date"
    assert "pixel_art_16bit" in previews.pending("flux_dev_fp8_t2i", force=True) and previews.pending("flux_dev_fp8_t2i", keys=["low_poly_3d"]) == ["low_poly_3d"]
    assert previews.prompt_hash(st, "flux_dev_fp8_t2i") != previews.prompt_hash(st, "sdxl_anime_t2i")
    assert previews.seed_for("a") == previews.seed_for("a") and previews.seed_for("a") != previews.seed_for("b")


def test_samples_are_queued_by_themselves_in_the_night_window_once_comfyui_is_ready(monkeypatch):
    """Nothing is left for the owner: when ComfyUI answers with the image workflow, the sample job is queued by the worker's tick (night window, low priority)."""
    from instai.core import hardware, settings_store
    from instai.gpu import compute
    from instai.jobs import schedule
    from instai.jobs.models import Job
    from tests import fakes
    from tests.test_gpu_use import GPU, comfy_stats

    monkeypatch.setattr(hardware, "gpu_status", lambda: dict(GPU))
    compute._CAP_CACHE.update(at=0.0, value=None)
    try:
        assert previews.auto_queue(force=True) is None, "demo mode (placeholder image engine): nothing to make"
        settings_store.set_setting("image_engine", "comfyui")
        assert previews.auto_queue(force=True) is None, "ComfyUI is not running: nothing yet"
        with fakes.comfy_server() as c:
            c.stats = comfy_stats("cuda")
            settings_store.set_setting("comfyui_url", c.url)
            compute._CAP_CACHE.update(at=0.0, value=None)
            monkeypatch.setenv("INSTAI_STYLE_SAMPLES_AUTO", "0")
            assert previews.auto_queue(force=True) is None, "switched off"
            monkeypatch.delenv("INSTAI_STYLE_SAMPLES_AUTO")
            job = previews.auto_queue(force=True)
            assert job is not None and job.kind == "styles.preview" and job.payload["auto"] is True
            assert job.window == schedule.config()["download_window"] and job.priority < 0
            assert previews.auto_queue(force=True) is None, "one at a time"
            Job.objects.filter(pk=job.pk).update(status=Job.SUCCEEDED)
            assert previews.auto_queue(force=True) is None, "a run finished a moment ago: not again for hours"
    finally:
        settings_store.set_setting("image_engine", "")
        settings_store.set_setting("comfyui_url", "")
        compute._CAP_CACHE.update(at=0.0, value=None)
