"""Style & theme library: built-ins, duplicate / edit / delete, export / import, prompt composition, and the page's look."""
from __future__ import annotations

import json
import re

import pytest

from instai.styles import library, schema
from instai.styles.builtin_styles import BUILTIN_STYLES, LEGACY_ALIASES
from instai.styles.builtin_themes import BUILTIN_THEMES

pytestmark = pytest.mark.django_db

# Studios, franchises and artists must never appear in a prompt fragment (licence risk; docs/DECISIONS.md).
BANNED = ["ghibli", "pixar", "disney", "dreamworks", "toei", "madhouse", "kyoto animation", "ufotable", "mappa", "trigger", "naruto", "one piece", "dragon ball",
          "jujutsu", "attack on titan", "demon slayer", "miyazaki", "shinkai", "marvel", "dc comics", "cartoon network", "nickelodeon", "ghost in the shell", "akira"]


def test_library_has_many_built_ins_across_realism_levels():
    assert len(BUILTIN_STYLES) >= 30 and len(BUILTIN_THEMES) >= 12
    levels = {s["realism"] for s in BUILTIN_STYLES.values()}
    assert levels == set(schema.REALISM), "every realism level has at least one preset"
    assert len({s["animation"] for s in BUILTIN_STYLES.values()}) >= 8, "the animation approaches differ"
    for key, s in BUILTIN_STYLES.items():
        assert s["name_fa"] and s["name_en"] and s["description_fa"] and s["description_en"], key
        assert s["image_positive"] and s["image_negative"] and s["video_positive"] and s["video_negative"] and s["sample_prompt"], key
        assert len(s["palette"]) >= 5 and all(re.match(r"^#[0-9A-F]{6}$", c) for c in s["palette"]), key
        assert s["techniques"] and s["theme_key"] in BUILTIN_THEMES, key
    for key, t in BUILTIN_THEMES.items():
        assert t["name_fa"] and t["name_en"] and len(t["palette"]) == 6 and t["lighting"] and t["mood"] and t["prompt_fragment"], key
        assert t["typography"]["subtitle_color"].startswith("#"), key


def test_no_studio_or_franchise_names_in_any_prompt():
    blob = json.dumps([BUILTIN_STYLES, BUILTIN_THEMES], ensure_ascii=False).lower()
    assert [w for w in BANNED if w in blob] == []


def test_legacy_style_keys_still_resolve():
    for old, new in LEGACY_ALIASES.items():
        assert library.get_style(old)["key"] == new
    from instai.pages import formats

    assert any(s["key"] == "anime_soft" and s["prompt"] for s in formats.STYLES), "production code that looks a style up by its old key still finds a prompt"


def test_normalisers_clamp_and_drop_unknown_fields():
    st = schema.normalize_style({"name_en": "x", "realism": "nonsense", "palette": ["#fff", "#112233", "red"], "fps_feel": "999", "techniques": ["wan_i2v", "bogus"], "evil": 1})
    assert st["realism"] == "anime" and st["palette"] == ["#112233"] and st["fps_feel"] == 60 and st["techniques"] == ["wan_i2v"] and "evil" not in st
    th = schema.normalize_theme({"name_en": "t", "typography": {"title_weight": "huge", "subtitle_size": 5, "subtitle_color": "blue"}})
    assert th["typography"]["title_weight"] == "bold" and th["typography"]["subtitle_size"] == 24 and th["typography"]["subtitle_color"] == "#FFFFFF"


def test_user_presets_duplicate_edit_delete(api):
    r = api.post("/api/library/style/modern_tv_anime/duplicate", {}, format="json")
    assert r.status_code == 201
    copy = r.json()
    assert copy["builtin"] is False and copy["based_on"] == "modern_tv_anime" and copy["name_en"].endswith("(copy)")
    r = api.patch(f"/api/library/style/{copy['key']}", {"name_en": "My look", "image_positive": "my positive, soft light", "palette": ["#112233", "#445566"]}, format="json")
    assert r.status_code == 200 and r.json()["name_en"] == "My look"
    assert api.patch("/api/library/style/modern_tv_anime", {"name_en": "hack"}, format="json").status_code == 409, "built-ins are read-only"
    assert api.delete("/api/library/style/modern_tv_anime").status_code == 409
    # a brand new preset
    r = api.post("/api/library/style", {"name_fa": "سبک من", "name_en": "From scratch", "realism": "cartoon", "image_positive": "flat colours"}, format="json")
    assert r.status_code == 201 and r.json()["origin"] == "user"
    r = api.post("/api/library/style", {"name_en": "no prompt"}, format="json")
    assert r.status_code == 400
    lib = api.get("/api/library").json()
    assert any(s["key"] == copy["key"] and not s["builtin"] for s in lib["styles"]) and len(lib["styles"]) >= 46
    assert {x["key"] for x in lib["realism"]} == set(schema.REALISM)
    assert api.delete(f"/api/library/style/{copy['key']}").status_code == 204
    assert api.get(f"/api/library/style/{copy['key']}").status_code == 404


def test_user_style_is_visible_to_production_code_through_formats_styles(api):
    from instai.pages import formats

    key = api.post("/api/library/style", {"name_en": "Visible", "image_positive": "unique-visible-fragment"}, format="json").json()["key"]
    library.clear_cache()
    assert next(s["prompt"] for s in formats.STYLES if s["key"] == key) == "unique-visible-fragment"


def test_export_import_round_trip(api):
    key = api.post("/api/library/style", {"name_en": "Round trip", "name_fa": "رفت و برگشت", "image_positive": "rt prompt", "palette": ["#0A0B0C"]}, format="json").json()["key"]
    tkey = api.post("/api/library/theme", {"name_en": "RT theme", "palette": ["#010203"], "prompt_fragment": "rt theme"}, format="json").json()["key"]
    body = api.get("/api/library/export").content
    bundle = json.loads(body)
    assert bundle["format"] == schema_format() and [s["key"] for s in bundle["styles"]] == [key] and [t["key"] for t in bundle["themes"]] == [tkey]
    api.delete(f"/api/library/style/{key}")
    api.delete(f"/api/library/theme/{tkey}")
    r = api.post("/api/library/import", bundle, format="json")
    assert r.status_code == 201 and len(r.json()["imported"]["styles"]) == 1 and len(r.json()["imported"]["themes"]) == 1
    assert library.get_style(key)["image_positive"] == "rt prompt" and library.get_style(key)["origin"] == "imported"
    # importing again never overwrites: the key is made unique
    r = api.post("/api/library/import", bundle, format="json")
    assert r.json()["imported"]["styles"][0] != key
    # a built-in can be exported by name too
    one = json.loads(api.get("/api/library/export?styles=anime_90s_cel").content)
    assert one["styles"][0]["key"] == "anime_90s_cel"
    assert api.post("/api/library/import", {"format": "something-else"}, format="json").status_code == 400


def test_compose_merges_style_theme_and_notes():
    c = library.compose("anime_90s_cel", "persian_turquoise", "my note", "no blur")
    assert "1990s anime cel" in c["positive"] and "turquoise" in c["positive"] and c["positive"].endswith("my note")
    assert "no blur" in c["negative"] and c["video_positive"] and c["palette"] and c["subtitle"]["font"] == "Vazirmatn"
    # a style's own default theme is used when none is given
    assert library.compose("noir_bw")["theme"] == "mono_noir"
    assert library.compose("does-not-exist")["positive"] == ""


def test_apply_look_writes_the_visual_profile(api):
    page = api.post("/api/pages", {"name": "p", "format": "recurring_character", "languages": ["fa"]}, format="json").json()
    r = api.post(f"/api/pages/{page['id']}/apply-look", {"style_key": "noir_bw", "theme_key": "royal_gold", "style_notes": "extra"}, format="json")
    assert r.status_code == 200
    vis = r.json()["profiles"]["visual"]
    assert vis["style_key"] == "noir_bw" and vis["realism"] == "realistic" and vis["theme_key"] == "royal_gold" and vis["style_notes"] == "extra"
    assert vis["subtitle"]["position"] == "bottom" and vis["palette"] and "turquoise" not in vis["negative_prompt"]
    assert api.post(f"/api/pages/{page['id']}/apply-look", {"style_key": "nope"}, format="json").status_code == 400


def schema_format() -> str:
    return library.BUNDLE_FORMAT
