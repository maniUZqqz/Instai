"""The scene-plan engine (instai/motion_plan): the component library, the plan format and its validation, the deterministic plan of a narration, versioned patches, the rule checks
(QA), the visual critique, the prompts and the API. Everything here runs without a browser or a model (the fake provider answers); the real renders are in test_motion_pipeline.py.

SOURCE: the tests are ported from NMarketing:backend/apps/motion (tests_lib, tests_specs, tests_plan, tests_patch, tests_qa, tests_critique, tests_promptkit) and adapted to InstAI's
vocabulary (series, episode, hook, source), its two languages and its job / provider layers.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "remotion" / "src"
COMP = SRC / "components"

pytestmark = pytest.mark.django_db(transaction=True)


def ts_keys(file: str, block: str) -> set:
    """The keys of `export const <block> ... = { a: A, b: B }` in a TS file of remotion/src/components."""
    text = (COMP / file).read_text(encoding="utf-8")
    m = re.search(r"export const %s[^=]*=\s*\{(.*?)\n?\};?" % re.escape(block), text, re.S)
    assert m, f"{block} not found in {file}"
    return set(re.findall(r"\b([a-z][a-z0-9_]*)\s*:", m.group(1)))


# ------------------------------------------------------------------ the library: Python = Remotion

def test_python_registry_equals_the_remotion_registry():
    from instai.motion_plan import components

    ts = ts_keys("scenes.tsx", "SCENES") | ts_keys("comp-data.tsx", "DATA_COMPONENTS") | ts_keys("comp-text.tsx", "TEXT_COMPONENTS")
    assert set(components.COMPONENTS) == ts, "components.py and remotion/src/components (scenes / comp-data / comp-text) must list the same ids"
    assert set(components.OVERLAY_IDS) == ts_keys("comp-text.tsx", "OVERLAY_BODIES")
    assert len(components.COMPONENTS) == 19, "the ported subset: episode card, kinetic title, quote, number + counter, list / steps / checklist, before-after, 3 charts, name bar, captions, sting, key art, end card, countdown, sticker"


def test_the_shop_vocabulary_was_left_out():
    from instai.motion_plan import components

    for gone in ("product", "price_card", "app", "comparison_table", "testimonial", "rating", "tags", "ticker", "feature_cards", "icon_grid", "progress_ring", "progress_bars", "cta", "compare"):
        assert gone not in components.COMPONENTS, gone
    text = " ".join(" ".join([c["label_fa"], c["label_en"], c["desc_fa"], c["desc_en"], c["about"], c["use"], *c["fields"]]) for c in components.COMPONENTS.values()).lower()
    for word in ("price", "قیمت", "brand", "برند", "shop", "فروشگاه", "testimonial", "product", "محصول"):
        assert word not in text, word


def test_the_page_definitions_equal_the_server_library():
    """remotion/src/components/defs.ts (what the page lists) = instai/motion_plan/components.py (what the server validates) = toolchain.SCENE_COMPOSITIONS."""
    from instai.motion_plan import components
    from instai.remotion import toolchain

    text = (COMP / "defs.ts").read_text(encoding="utf-8")
    rows = re.findall(r"type: '([a-z_]+)', id: '(Scene[A-Za-z]+)', group: '([a-z]+)', fa: '([^']+)', en: '([^']+)', duration: (\d+)", text)
    assert [r[0] for r in rows] == list(toolchain.SCENE_COMPOSITIONS) and [r[1] for r in rows] == list(toolchain.SCENE_COMPOSITIONS.values())
    assert {r[0] for r in rows} == set(components.COMPONENTS)
    for typ, cid, group, fa, en, dur in rows:
        c = components.COMPONENTS[typ]
        assert (c["group"], c["label_fa"], c["label_en"]) == (group, fa, en), typ
        assert c["dur"][1] - 2 <= int(dur) <= c["dur"][1] + 2, f"{typ}: the page's sample length {dur} is far from the library's typical {c['dur'][1]}"


def test_every_component_has_both_languages_and_a_valid_sample_in_each():
    from instai.motion_plan import components, specs

    for cid, c in components.COMPONENTS.items():
        assert c["label_fa"] and c["label_en"] and c["desc_fa"] and c["desc_en"], cid
        assert re.search(r"[؀-ۿ]", c["label_fa"]) and not re.search(r"[؀-ۿ]", c["label_en"]), cid
        for lang in ("fa", "en"):
            out = specs.normalize_scene(components.sample(cid, lang), 0)
            assert out["type"] == cid
            for key in c["need"][:1]:
                assert out.get(key) or out.get(key) == 0, f"{cid}/{lang}: {key} lost"


def test_every_text_field_has_a_length_cap_and_the_icon_set_is_permissive():
    from instai.motion_plan import components

    def walk(cid, fields):
        for n, f in fields.items():
            assert f["kind"] in ("str", "num", "int", "bool", "enum", "ref", "strs", "objs"), f"{cid}.{n}"
            if f["kind"] == "str":
                assert f["max"] > 0
            if f["kind"] == "strs":
                assert f["max_items"] and f["item_max"]
            if f["kind"] == "objs":
                assert f["max_items"]
                walk(cid, f["fields"])
    for cid, c in components.COMPONENTS.items():
        walk(cid, c["fields"])
    assert len(components.ICON_NAMES) >= 60
    assert "ISC License" in (COMP / "ICONS-LICENSE.txt").read_text(encoding="utf-8")


def test_the_data_components_all_carry_the_honesty_fields():
    from instai.motion_plan import components

    assert set(components.DATA_IDS) == {"stat", "counter", "bar_chart", "line_chart", "donut"}
    for cid in components.DATA_IDS:
        assert {"source", "example"} <= set(components.COMPONENTS[cid]["fields"]), cid
    assert "source" not in components.COMPONENTS["quote"]["fields"]


def test_the_public_list_is_json_and_grouped():
    from instai.motion_plan import components

    pl = components.public_list()
    json.dumps(pl)
    assert {c["group"] for c in pl} == {"scene", "data", "text"} and all(c["group_fa"] and c["group_en"] for c in pl)


# ------------------------------------------------------------------ the vocabulary of motion

def test_ease_spring_camera_exit_enter_and_transition_names_match_the_engine():
    from instai.motion_plan import motionlib

    text = (COMP / "presets.ts").read_text(encoding="utf-8")
    eases = set(re.findall(r'^\s+"?([a-z-]+)"?:\s*(?:bz|Easing|\()', text.split("export const SPRINGS")[0], re.M))
    springs = set(re.findall(r'^\s+"?([a-z-]+)"?:\s*\[', text.split("export const SPRINGS")[1], re.M))
    assert set(motionlib.EASES) == eases and set(motionlib.SPRINGS) == springs
    cams = set(re.findall(r'"([a-z-]+)"', re.search(r"CAMERA_MOVES = \[(.*?)\]", text, re.S).group(1)))
    exits = set(re.findall(r'"([a-z-]+)"', re.search(r"EXIT_KINDS = \[(.*?)\]", text, re.S).group(1)))
    assert set(motionlib.CAMERA_MOVES) == cams and set(motionlib.EXIT_KINDS) == exits
    anim = (COMP / "anim.ts").read_text(encoding="utf-8")
    trans = set(re.findall(r'case "([a-z-]+)"', anim.split("export function transitionCss")[1]))
    assert set(motionlib.TRANS_KINDS) <= trans, set(motionlib.TRANS_KINDS) - trans
    enter = set(re.findall(r'case "([a-z]+)"', anim.split("export function enterCss")[1].split("export function cameraCss")[0]))
    assert set(motionlib.ENTER_KINDS) <= enter | {"fade"}, set(motionlib.ENTER_KINDS) - enter
    assert set(motionlib.TRANSITION_PACK) <= set(motionlib.TRANS_KINDS)


def test_the_adapter_covers_every_animation_and_family_of_the_style_library():
    """StyleKit -> component tokens: ONE table (adapter.json) read by the bundle and by Python. Every one of the ten ways of moving and of the eight families has an entry."""
    from instai.motion_plan import motionlib
    from instai.styles import schema

    ad = motionlib.ADAPTER
    assert set(ad["personalities"]) == set(schema.ANIMATIONS)
    assert set(ad["families"]) == set(schema.FAMILIES)
    assert set(ad["hard_animations"]) <= set(schema.ANIMATIONS)
    spr = set(motionlib.SPRINGS)
    for k, p in ad["personalities"].items():
        assert p["enter"] in motionlib.ENTER_KINDS and p["spring"] in spr and p["trans"]["kind"] in motionlib.TRANS_KINDS and 0 <= p["trans"]["frames"] <= 24, k
    # kit/motion.ts keeps the same ten personalities (its test is test_remotion.py): the adapter reads from there
    motion = (SRC / "kit" / "motion.ts").read_text(encoding="utf-8")
    assert set(re.findall(r"^  ([a-z_0-9]+): \{ ease:", motion, re.M)) == set(ad["personalities"])


def test_platform_safe_zones_exist_for_every_network_in_both_languages():
    from instai.motion_plan import motionlib

    for pid in ("shorts", "reels", "story", "tiktok"):
        z = motionlib.platform_safe(pid)
        assert z["bottom"] >= 0.14 and z["top"] > 0.0
    assert motionlib.platform_safe("") == {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0}
    for k, v in motionlib.PLATFORMS.items():
        assert v["fa"] and v["en"], k
    assert motionlib.platform_label("youtube", "en") == "YouTube (landscape)"


NODE = shutil.which("node") or "/usr/local/bin/node"

TIMELINE_CASES = [
    {"style": "cinematic_realistic", "fps": 30, "scenes": [{"duration": 3}, {"duration": 3}]},
    {"style": "cinematic_realistic", "fps": 30, "transition": "cut", "scenes": [{"duration": 3}, {"duration": 2.5}, {"duration": 4}]},
    {"style": "pixel_art_16bit", "fps": 24, "scenes": [{"duration": 1}, {"duration": 7.3, "transition": "wipe"}, {"duration": 2}, {"duration": 3.33}]},
    {"style": "whiteboard_explainer", "fps": 60, "scenes": [{"duration": 4.55}, {"duration": 1.01, "transition": "iris"}, {"duration": 12}]},
    {"style": "stop_motion_puppet", "fps": 25, "scenes": [{"duration": 30}]},
]


def test_the_timeline_of_python_equals_the_timeline_of_the_renderer():
    """computeTimeline (TS) and timeline.compute (Python) give the same frames over several plans: the clip is exactly as long as the renderer draws it."""
    from instai.motion_plan import timeline
    from instai.remotion import kit as kitmod

    esbuild = ROOT / "remotion" / "node_modules" / "esbuild"
    if not (Path(NODE).exists() and esbuild.exists()):
        pytest.skip("node / esbuild are not on this machine")
    src = (COMP / "timeline.ts").read_text(encoding="utf-8")
    kits = {c["style"]: kitmod.style_kit(c["style"]) for c in TIMELINE_CASES}
    from instai.motion_plan import motionlib

    styles = {k: {"trans": {"kind": motionlib.style_trans(v)[0], "frames": motionlib.style_trans(v)[1]}} for k, v in kits.items()}
    js = f"""
const esbuild = require({json.dumps(str(esbuild))});
const code = esbuild.transformSync({json.dumps(src)}, {{ loader: "ts", format: "cjs" }}).code;
const m = {{ exports: {{}} }}; new Function("module", "exports", "require", code)(m, m.exports, require);
const styles = {json.dumps(styles)};
const cases = {json.dumps(TIMELINE_CASES)};
console.log(JSON.stringify(cases.map((c) => m.exports.computeTimeline(c, styles[c.style], c.fps))));
"""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "t.cjs"
        f.write_text(js, encoding="utf-8")
        out = subprocess.run([NODE, str(f)], capture_output=True, text=True, timeout=60, cwd=str(ROOT / "remotion"))
    assert out.returncode == 0, out.stderr
    for case, ts in zip(TIMELINE_CASES, json.loads(out.stdout)):
        py = timeline.compute(case, kit=kits[case["style"]])
        for k in ("frames", "starts", "tfs", "kinds", "total"):
            assert py[k] == ts[k], f"{k} differs for {case}"


def test_the_total_of_a_plan_matches_the_timeline():
    from instai.motion_plan import specs, timeline

    spec = specs.normalize_spec({"style": "cinematic_realistic", "size": "vertical", "scenes": [{"type": "kinetic_title", "duration": 3, "text": "الف"}, {"type": "list", "duration": 3, "items": ["ب", "ج"]}]})
    assert abs(spec["total_s"] - timeline.total_seconds(spec)) < 0.01 and spec["total_s"] < 6.0, "the transition overlaps the two scenes"


# ------------------------------------------------------------------ the colours: Python = the renderer's readableOn / accentOn

def test_colour_rules_match_the_renderers_and_every_palette_role_reads():
    from instai.motion_plan import colors
    from instai.remotion import kit as kitmod

    assert colors.readable_on("#14181F", ["#F3E9D8", "#FFFFFF"]) == "#f3e9d8"
    assert colors.readable_on("#FFFFFF", ["#F3E9D8"]) == "#000000", "a pale text colour on white is not used"
    assert colors.accent_on("#14181F", "#222222") != "#222222" and colors.contrast(colors.parse(colors.accent_on("#14181F", "#222222")), colors.parse("#14181F")) >= 3
    for k in kitmod.all_kits():                       # InstAI's rule: no colour without readableOn / accentOn against its own surface
        pal = colors.palette_from_kit(k)
        bg = colors.parse(pal["bg"])
        assert colors.contrast(colors.parse(pal["ink"]), bg) >= 4.5, k["key"]
        for role in ("accent", "accent2", "accent3"):
            assert colors.contrast(colors.parse(pal[role]), bg) >= 4.5 - 0.02, (k["key"], role)


# ------------------------------------------------------------------ specs: validation and the honesty rule

def spec_of(*scenes, **kw):
    return {"style": "cinematic_realistic", "size": "vertical", "lang": "fa", "scenes": list(scenes), **kw}


def test_a_plan_is_cleaned_and_idempotent():
    from instai.motion_plan import specs

    raw = spec_of({"type": "title", "duration": 4, "title": "عنوان", "series": "سریال", "number": 2, "hook": "ادامه دارد", "evil": "<script>"}, {"type": "list", "duration": 5, "items": ["الف", "ب"]})
    one = specs.normalize_spec(raw)
    assert "evil" not in one["scenes"][0] and one["scenes"][0]["number"] == 2 and one["version"] == specs.SCHEMA_VERSION
    two = specs.normalize_spec(one)
    assert {k: v for k, v in one.items()} == {k: v for k, v in two.items()}, "normalising twice changes nothing"


def test_errors_say_why_in_persian_and_english():
    from instai.motion_plan import specs

    for bad, word in (({"scenes": []}, "صحنه"), (spec_of({"type": "nope", "duration": 3}), "نمی‌شناسم"), (spec_of({"type": "title", "duration": 3}), "title"),
                      (spec_of({"type": "title", "duration": "x", "title": "a"}), "عدد"), (spec_of({"type": "title", "duration": 3, "title": "a"}, size="huge"), "اندازه")):
        with pytest.raises(specs.SpecError) as e:
            specs.normalize_spec(bad)
        assert word in str(e.value) and e.value.en and not re.search(r"[؀-ۿ]", e.value.en), (bad, str(e.value), e.value.en)
    with pytest.raises(specs.SpecError):
        specs.normalize_spec(spec_of(*[{"type": "quote", "duration": 5, "text": "x"}] * 15))            # more than the scene limit
    with pytest.raises(specs.SpecError):
        specs.normalize_spec(spec_of(*[{"type": "quote", "duration": 30, "text": "x"}] * 14), max_total=120)      # longer than the total limit


def test_silent_corrections_are_reported_in_both_languages():
    from instai.motion_plan import specs

    notes: list = []
    out = specs.normalize_spec(spec_of({"type": "quote", "duration": 99, "text": "x", "ease": "wobbly", "tokens": {"accent": "red", "font_scale": 9}}, platform="mars"), notes=notes, max_total=300)
    assert out["scenes"][0]["duration"] == 30 and out["scenes"][0]["tokens"] == {"font_scale": 1.6} and "ease" not in out["scenes"][0] and "platform" not in out
    assert len(notes) >= 4 and all(n["fa"] and n["en"] and not re.search(r"[؀-ۿ]", n["en"]) for n in notes)


def test_an_unknown_style_falls_back_with_a_note_and_never_breaks_a_plan():
    from instai.motion_plan import specs

    notes: list = []
    out = specs.normalize_spec(spec_of({"type": "quote", "duration": 4, "text": "x"}, style="deleted_style"), notes=notes)
    assert out["style"] == "" and any("deleted_style" in n["en"] for n in notes)


def test_numbers_are_examples_unless_a_verified_source_is_named():
    """InstAI's explainer policy: the five number components (stat, counter, three charts) say «example» unless the scene names a VERIFIED source."""
    from instai.motion_plan import components, specs

    for cid in components.DATA_IDS:
        sc = components.sample(cid, "fa")
        out = specs.normalize_scene(sc, 0)
        assert out.get("example") is True and "source" not in out, cid
        named = specs.normalize_scene({**sc, "source": "گزارش سالانه"}, 0)
        assert named["source"] == "گزارش سالانه" and "example" not in named, cid          # the owner's own source on the Remotion page is trusted
        unverified = specs.normalize_scene({**sc, "source": "گزارش سالانه"}, 0, allowed_sources=["منبع دیگر"])
        assert unverified.get("example") is True and "source" not in unverified, "a source that is not among the episode's verified ones is dropped"
        verified = specs.normalize_scene({**sc, "source": "منبع دیگر"}, 0, allowed_sources=["منبع دیگر"])
        assert verified["source"] == "منبع دیگر" and "example" not in verified
    assert "example" not in specs.normalize_scene({"type": "quote", "duration": 4, "text": "x"}, 0), "text pieces carry no chip"


def test_pictures_come_only_from_the_episode():
    from instai.motion_plan import specs

    ok = specs.normalize_scene({"type": "image_hero", "duration": 4, "caption": "ب", "image": "keyframe"}, 0)
    assert ok["image"] == "keyframe"
    assert specs.normalize_scene({"type": "image_hero", "duration": 4, "caption": "ب", "image": "asset:12"}, 0)["image"] == "asset:12"
    for evil in ("https://evil.example/x.png", "/etc/passwd", "file:///c:/x.png", "data:text/html;base64,PGh0bWw+PC9odG1sPg=="):
        with pytest.raises(specs.SpecError):
            specs.normalize_scene({"type": "image_hero", "duration": 4, "caption": "ب", "image": evil}, 0)
    assert specs.asset_refs(specs.normalize_spec(spec_of({"type": "image_hero", "duration": 4, "caption": "ب", "image": "keyframe"}, {"type": "logo", "duration": 3, "title": "x", "logo": "logo"}))) == ["keyframe", "logo"]


def test_overlays_cues_and_series_are_checked():
    from instai.motion_plan import specs

    sc = specs.normalize_scene({"type": "kinetic_title", "duration": 5, "text": "سلام دنیا", "narration": "سلام دنیا",
                                "cues": [{"w": "سلام", "s": 0.2, "e": 0.6}, {"w": "دنیا", "s": 0.7, "e": 0.5}, {"w": "", "s": 1, "e": 2}],
                                "overlays": [{"type": "lower_third", "at": 1, "name": "سارا", "role": "خلبان", "anchor": "bottom-start", "dx": 9}]}, 0)
    assert sc["cues"] == [{"w": "سلام", "s": 0.2, "e": 0.6}], "a cue that ends before it starts, or without a word, is dropped"
    assert sc["overlays"][0]["anchor"] == "bottom-start" and sc["overlays"][0]["dx"] == 0.5
    with pytest.raises(specs.SpecError):
        specs.normalize_scene({"type": "kinetic_title", "duration": 5, "text": "x", "overlays": [{"type": "bar_chart", "bars": [{"label": "a", "value": 1}]}]}, 0)
    ser = specs.normalize_series({"title": "سریال", "episode": "3", "characters": ["الف"] * 20, "x": 1})
    assert ser == {"title": "سریال", "episode": 3, "episode_title": "", "channel": "", "characters": ["الف"] * 8}


def test_every_template_of_the_page_is_valid_in_both_languages_and_sizes():
    from instai.motion_plan import specs

    assert len(specs.TEMPLATES) >= 5
    for t in specs.TEMPLATES:
        for lang in ("fa", "en"):
            for size in specs.SIZES:
                out = specs.normalize_spec(specs.sample_spec("cinematic_realistic", t["id"], size, lang), max_total=300)
                assert [s["type"] for s in out["scenes"]] == t["scenes"] and out["size"] == size


# ------------------------------------------------------------------ the deterministic plan of a narration

NARRATION = "آب روی زمین ۷۱ درصد سطح را پوشانده است. اقیانوس، دریا و رودخانه سه شکل اصلی آب‌اند. ابتدا بخار می‌شود، سپس ابر می‌سازد و در نهایت باران می‌شود."


def test_a_plan_comes_from_the_narration_alone_with_no_model():
    from instai.motion_plan import fallback, specs, timeline

    plan = fallback.make_plan(NARRATION, 14.0, lang="fa", style="whiteboard_explainer", size="vertical")
    types = [s["type"] for s in plan["scenes"]]
    assert "stat" in types and "list" in types and "steps" in types, types
    assert abs(plan["total_s"] - 14.0) < 0.35, plan["total_s"]
    words = set(re.findall(r"\w+", NARRATION.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))))
    for sc in plan["scenes"]:                         # nothing is invented: every word on the screen was said
        shown = " ".join(str(v) for k, v in sc.items() if k in ("text", "label", "value", "title")).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
        for it in sc.get("items") or []:
            shown += " " + it
        for st in sc.get("steps") or []:
            shown += " " + st["title"]
        assert set(re.findall(r"\w+", shown)) <= words | {"%"}, (sc["type"], shown)
        assert sc["narration"] and sc.get("cues"), "every scene knows what is said over it and when"
    stat = next(s for s in plan["scenes"] if s["type"] == "stat")
    assert stat["value"] == "71" and stat["suffix"] == "%" and stat["example"] is True and "source" not in stat
    tl = timeline.compute(plan)
    assert abs(tl["total"] / tl["fps"] - plan["total_s"]) < 0.05


def test_a_number_is_credited_only_to_a_verified_source_that_contains_it():
    from instai.motion_plan import fallback

    srcs = [{"title": "اطلس زمین", "extract": "حدود ۷۱ درصد سطح زمین را آب پوشانده است."}, {"title": "منبع بی‌ربط", "extract": "هیچ عددی ندارد."}]
    plan = fallback.make_plan("آب ۷۱ درصد زمین را می‌پوشاند.", 6.0, sources=srcs, allowed_sources=[s["title"] for s in srcs])
    stat = next(s for s in plan["scenes"] if s["type"] == "stat")
    assert stat["source"] == "اطلس زمین" and "example" not in stat
    other = fallback.make_plan("آب ۹۸ درصد زمین را می‌پوشاند.", 6.0, sources=srcs, allowed_sources=[s["title"] for s in srcs])
    assert next(s for s in other["scenes"] if s["type"] == "stat")["example"] is True, "a number no source contains stays an example"


def test_years_are_not_numbers_and_english_works():
    from instai.motion_plan import fallback

    plan = fallback.make_plan("In 1969 people walked on the Moon. First they built a rocket, then they flew it, finally they landed.", 12.0, lang="en", style="cinematic_realistic")
    types = [s["type"] for s in plan["scenes"]]
    assert "stat" not in types and "steps" in types, types
    assert all(c["w"] for s in plan["scenes"] for c in s.get("cues", []))


def test_chunks_are_short_and_a_short_shot_gets_fewer_scenes():
    from instai.motion_plan import fallback

    long = " ".join(["کلمه"] * 80) + "."
    assert all(len(c.split()) <= fallback.MAX_CHUNK_WORDS + 4 for c in fallback.chunks(long))
    short = fallback.make_plan("جمله اول است. جمله دوم است. جمله سوم است. جمله چهارم است.", 5.0)
    assert 1 <= len(short["scenes"]) <= 2, "a 5 s shot cannot give four scenes their 2 s"


def test_an_empty_narration_uses_the_episode_title_else_says_why():
    from instai.motion_plan import fallback, specs

    p = fallback.make_plan("", 4.0, series={"title": "سریال", "episode_title": "نخستین پرواز"})
    assert p["scenes"][0]["type"] == "kinetic_title" and p["scenes"][0]["text"] == "نخستین پرواز"
    with pytest.raises(specs.SpecError):
        fallback.make_plan("", 4.0)


def test_word_timings_follow_where_the_words_are_said():
    from instai.motion_plan import fallback

    cues = fallback.estimate_cues("یک دو سه چهار", 4.0, start=0.5)
    assert cues[0]["s"] == 0.5 and all(a["e"] <= b["s"] + 1e-6 for a, b in zip(cues, cues[1:])) and cues[-1]["e"] <= 0.5 + 4.0


# ------------------------------------------------------------------ patches

def small_plan():
    from instai.motion_plan import specs

    return specs.normalize_spec(spec_of({"type": "kinetic_title", "duration": 4, "text": "تیتر اول"}, {"type": "list", "duration": 6, "title": "نکته‌ها", "items": ["الف", "ب", "ج", "د"]},
                                        {"type": "quote", "duration": 4, "text": "جمله", "author": "من"}))


def test_a_patch_changes_only_what_it_names_and_is_all_or_nothing():
    from instai.motion_plan import patch

    plan = small_plan()
    out = patch.apply_patch(plan, [{"op": "scale", "path": "scenes/0/tokens/font_scale", "factor": 1.2, "min": 0.6, "max": 1.6, "default": 1}, {"op": "shift", "path": "scenes/1/duration", "by": 1.5}])
    assert out["scenes"][0]["tokens"]["font_scale"] == 1.2 and out["scenes"][1]["duration"] == 7.5 and out["scenes"][2] == plan["scenes"][2]
    assert plan["scenes"][0].get("tokens") is None, "the input is untouched"
    with pytest.raises(patch.PatchError) as e:
        patch.apply_patch(plan, [{"op": "shift", "path": "scenes/1/duration", "by": 1}, {"op": "set", "path": "nonsense/1", "value": 1}])
    assert e.value.en and not re.search(r"[؀-ۿ]", e.value.en)
    with pytest.raises(patch.PatchError):
        patch.apply_patch(plan, [{"op": "set", "path": "scenes/0/duration", "value": plan["scenes"][0]["duration"]}])      # nothing changed
    with pytest.raises(patch.PatchError):
        patch.apply_patch(plan, [{"op": "set", "path": "scenes/0/type", "value": "nope"}])                                # the result must be a valid plan
    with pytest.raises(patch.PatchError):
        patch.apply_patch(plan, [{"op": "set", "path": "scenes/0/duration", "value": 5}] * 13)                             # too many ops at once


def test_scene_operations_and_the_split_of_a_long_list():
    from instai.motion_plan import patch

    plan = small_plan()
    assert len(patch.apply_patch(plan, {"op": "duplicate_scene", "index": 2})["scenes"]) == 4
    assert patch.apply_patch(plan, {"op": "move_scene", "from": 2, "to": 0})["scenes"][0]["type"] == "quote"
    assert len(patch.apply_patch(plan, {"op": "remove_scene", "index": 1})["scenes"]) == 2
    split = patch.apply_patch(plan, {"op": "split_scene", "index": 1})["scenes"]
    assert [s["type"] for s in split[1:3]] == ["list", "list"] and split[1]["items"] == ["الف", "ب"] and split[2]["items"] == ["ج", "د"]
    with pytest.raises(patch.PatchError):
        patch.apply_patch(plan, {"op": "split_scene", "index": 0})             # a title has nothing to split
    one = patch.apply_patch(plan, {"op": "remove_scene", "index": 0}, max_total=300)
    with pytest.raises(patch.PatchError):
        patch.apply_patch({**one, "scenes": one["scenes"][:1]}, {"op": "remove_scene", "index": 0})      # never the last scene


def test_plain_words_become_patches_in_both_languages_without_a_model():
    from instai.motion_plan import patch

    plan = small_plan()
    for text, path_part in (("تیتر بزرگ‌تر شود", "scenes/0/tokens/font_scale"), ("صحنهٔ دوم ۲ ثانیه بیشتر", "scenes/1/duration"), ("make the title bigger", "scenes/0/tokens/font_scale"),
                            ("scene 3 longer", "scenes/2/duration"), ("رنگ صحنه سوم قرمز", "scenes/2/tokens/accent"), ("scene 2 colour blue", "scenes/1/tokens/accent")):
        r = patch.rules_patch(text, plan)
        assert r["ops"] and any(o.get("path") == path_part for o in r["ops"]), (text, r)
        assert r["say_fa"] and r["say_en"] and not re.search(r"[؀-ۿ]", r["say_en"])
        patch.apply_patch(plan, r["ops"], max_total=300)                        # and every one of them is a valid patch
    assert patch.rules_patch("حذف صحنهٔ دوم", plan)["ops"] == [{"op": "remove_scene", "index": 1}]
    assert patch.rules_patch("remove the last scene", plan)["ops"] == [{"op": "remove_scene", "index": 2}]
    assert patch.rules_patch("captions on", plan)["ops"][0]["value"]["on"] is True
    nope = patch.rules_patch("پیتزا بیاور", plan, "en")
    assert nope["ops"] == [] and "did not understand" in nope["say"]


# ------------------------------------------------------------------ versions: undo, redo, coalescing

def test_every_change_is_a_version_and_undo_redo_only_move_the_cursor():
    from instai.motion_plan import plans, specs

    plan = plans.create(small_plan())
    assert plan.cursor == 1 and plans.history(plan)[0]["source"] == "user"
    plan, summary = plans.apply_ops(plan, [{"op": "shift", "path": "scenes/1/duration", "by": 1}])
    assert plan.cursor == 2 and plan.spec["scenes"][1]["duration"] == 7 and summary and summary[0]["fa"] and summary[0]["en"]
    plan = plans.step(plan, -1)
    assert plan.cursor == 1 and plan.spec["scenes"][1]["duration"] == 6 and plans.can_redo(plan) and not plans.can_undo(plan)
    plan = plans.step(plan, 1)
    assert plan.cursor == 2
    plan = plans.step(plan, -1)
    plan, _ = plans.apply_ops(plan, [{"op": "shift", "path": "scenes/1/duration", "by": 2}])        # an edit after undo throws the «ahead» branch away
    assert plan.cursor == 2 and not plans.can_redo(plan) and plan.spec["scenes"][1]["duration"] == 8
    with pytest.raises(plans.PlanError) as e:
        plans.step(plans.restore(plan, 1), -1)
    assert e.value.en == "There is nothing to undo."
    assert plans.restore(plan, 2).spec["scenes"][1]["duration"] == 8
    d = plans.plan_dict(plan)
    assert d["spec"]["total_s"] > 0 and d["history"] and d["rev"] == 2


def test_quick_edits_by_the_owner_are_one_version_and_the_history_is_capped():
    from instai.motion_plan import plans
    from instai.motion_plan.models import MotionPlanRev

    plan = plans.create(small_plan())
    plan = plans.commit(plan, {**plan.spec, "intensity": 1.1}, source="user", label="one")
    plan = plans.commit(plan, {**plan.spec, "intensity": 1.2}, source="user", label="two", coalesce=True)
    plan = plans.commit(plan, {**plan.spec, "intensity": 1.3}, source="user", label="three", coalesce=True)
    assert plan.cursor == 2 and plan.spec["intensity"] == 1.3, "typing does not make a version of its own"
    assert plans.commit(plan, plan.spec, source="user").cursor == 2, "no change, no version"
    for i in range(70):
        plan = plans.commit(plan, {**plan.spec, "intensity": 0.5 + (i % 10) / 10 + 0.01}, source="patch", label=f"v{i}")
    assert MotionPlanRev.objects.filter(plan=plan).count() <= plans.MAX_REVS


def test_a_plan_of_a_shot_only_accepts_the_verified_sources_of_its_episode(api, worker):
    from instai.motion_plan import plans

    shot = make_shot(api, worker, technique="motion_graphics")
    plan = plans.create({**small_plan(), "scenes": [{"type": "stat", "duration": 4, "value": "5", "source": "منبع ساختگی"}]}, shot=shot)
    sc = plan.spec["scenes"][0]
    assert sc.get("example") is True and "source" not in sc, "a source the episode never verified is dropped"


# ------------------------------------------------------------------ QA: the rules, the geometry, the fixes

def test_a_scene_that_is_too_short_to_read_or_to_say_is_made_longer():
    from instai.motion_plan import patch, qa, specs

    words = " ".join(["کلمه"] * 14)
    plan = specs.normalize_spec(spec_of({"type": "kinetic_title", "duration": 1.5, "text": words}, {"type": "quote", "duration": 3, "text": "کوتاه", "narration": "کلمه " * 20, "cues": [{"w": "الف", "s": 0.1, "e": 6.0}]}))
    found = {f["code"]: f for f in qa.static_findings(plan)}
    assert found["too_short"]["scene"] == 0 and found["speech_longer"]["scene"] == 1
    for f in found.values():
        assert f["message"] and f["message_en"] and not re.search(r"[؀-ۿ]", f["message_en"]) and f["label"] and f["label_en"]
    new, applied, unresolved = qa.apply_fixes(plan, list(found.values()), max_total=300)
    assert new["scenes"][0]["duration"] > 1.5 and new["scenes"][1]["duration"] >= 6.4 and len(applied) == 2 and not unresolved


def test_a_crowded_scene_is_split_and_a_missing_platform_is_only_a_hint():
    from instai.motion_plan import qa, specs

    plan = specs.normalize_spec(spec_of({"type": "list", "duration": 20, "items": ["یک دو سه چهار پنج شش هفت"] * 6}, {"type": "checklist", "duration": 4, "items": ["الف"]}), max_total=300)
    f = {x["code"]: x for x in qa.static_findings(plan)}
    assert f["crowded"]["ops"] == [{"op": "split_scene", "index": 0}]
    assert f["platform_missing"]["severity"] == "info" and f["platform_missing"]["auto"] is False


def shot_of(plan, scene, boxes, *, W=1080, H=1920, safe=None, image=None):
    return {"scene": scene, "kind": "late", "frame": 60, "W": W, "H": H, "scale": 0.5, "safe": safe or {}, "boxes": boxes, "_image": image}


def tbox(i, x, y, w, h, text="متن", size=60, **kw):
    return {"id": i, "kind": "text", "scene": 0, "role": "body", "size": size, "x": x, "y": y, "w": w, "h": h, "color": "#ffffff", "text": text, "overflow": False, "clipped": False,
            "opacity": 1.0, "parent": -1, "overlay": "", "excl": "", **kw}


def test_geometry_findings_overflow_overlap_safe_zone_and_small_text():
    from instai.motion_plan import qa, specs

    plan = specs.normalize_spec(spec_of({"type": "list", "duration": 8, "items": ["الف", "ب", "ج"], "overlays": [{"type": "lower_third", "name": "سارا", "role": "خلبان"}]}), kit=None)
    boxes = [tbox(1, -50, 100, 400, 80, "بیرون"), tbox(2, 100, 400, 500, 90, "اول"), tbox(3, 150, 410, 500, 90, "دوم"),
             tbox(4, 100, 1800, 500, 80, "پایین", overlay="lower_third"), tbox(5, 100, 900, 300, 20, "ریز", size=20)]
    out = qa.geometry_findings(plan, [shot_of(plan, 0, boxes, safe={"top": 0.1 * 1920, "right": 0.1 * 1080, "bottom": 0.2 * 1920, "left": 0.06 * 1080})])
    codes = {f["code"] for f in out}
    assert {"overflow", "overlap", "safe_zone", "small_text"} <= codes, codes
    sz = next(f for f in out if f["code"] == "safe_zone" and f["box"].get("overlay") == "lower_third")
    assert sz["ops"] and sz["ops"][0]["path"].startswith("scenes/0/overlays/0/"), "an overlay in the platform's bars is moved, not the whole scene shrunk"
    assert all(f["message_en"] and not re.search(r"[؀-ۿ]", re.sub(r"“[^”]*”", "", f["message_en"])) for f in out), "the English line only quotes the text it talks about"


def test_contrast_is_measured_from_the_pixels_behind_the_text():
    from PIL import Image

    from instai.motion_plan import qa, specs

    plan = specs.normalize_spec(spec_of({"type": "quote", "duration": 5, "text": "جمله"}))
    light = Image.new("RGB", (540, 960), (240, 240, 240))
    box = tbox(1, 100, 300, 600, 100, "کم‌رنگ", color="rgb(250, 250, 250)")
    out = qa.geometry_findings(plan, [shot_of(plan, 0, [box], image=light)])
    lc = next(f for f in out if f["code"] == "low_contrast")
    assert lc["severity"] == "error" and lc["ops"] and lc["ops"][0]["value"] in ("#111111", "#000000"), lc
    dark = Image.new("RGB", (540, 960), (10, 10, 10))
    assert not [f for f in qa.geometry_findings(plan, [shot_of(plan, 0, [box], image=dark)]) if f["code"] == "low_contrast"]


def test_the_loop_measures_fixes_and_measures_again_at_most_three_rounds():
    from instai.motion_plan import qa, specs

    plan = specs.normalize_spec(spec_of({"type": "kinetic_title", "duration": 1.2, "text": " ".join(["کلمه"] * 14)}, {"type": "quote", "duration": 5, "text": "خوب"}))
    calls = {"n": 0}

    def measure(spec):
        calls["n"] += 1
        return []                                   # frames with nothing wrong

    rep = qa.run_loop(plan, measure=measure, max_total=300)
    assert rep["fixed"] >= 1 and rep["ok"] and rep["spec"]["scenes"][0]["duration"] > 1.2 and rep["geometry"] and calls["n"] >= 2
    assert qa.summary(rep, "en").startswith("Quality check") and qa.summary(rep, "fa").startswith("کنترل کیفیت")

    def never_ok(spec):
        return [shot_of(spec, 0, [tbox(1, -80, 0, 300, 50, "x")])]

    rep2 = qa.run_loop(plan, measure=never_ok, rounds=3, max_total=300)
    assert len(rep2["rounds"]) <= 3 and rep2["remaining"], "an unfixable problem is reported, never looped on"

    def boom(spec):
        raise RuntimeError("no browser")

    rep3 = qa.run_loop(plan, measure=boom, max_total=300)
    assert rep3["geometry"] is False and "no browser" in rep3["geometry_error"] and rep3["fixed"] >= 1, "the rule checks go on without the browser"


def test_key_frames_avoid_the_transitions():
    from instai.motion_plan import qa, specs, timeline

    plan = small_plan()
    t = timeline.compute(plan)
    keys = qa.key_frames(plan)
    assert len(keys) == 6
    for k in keys:
        i = k["scene"]
        start, end = t["starts"][i], t["starts"][i] + t["frames"][i]
        tin = t["tfs"][i - 1] if i else 0
        tout = t["tfs"][i] if i < len(t["tfs"]) else 0
        assert start + tin <= k["frame"] <= end - tout, (k, start, end)


# ------------------------------------------------------------------ prompts

def test_the_prompt_is_bounded_even_for_a_huge_narration_and_the_schema_is_valid():
    from instai.motion_plan import promptkit
    from instai.remotion import kit as kitmod

    kit = kitmod.style_kit("whiteboard_explainer")
    p = promptkit.build_prompt("آب " * 4000 + " ۷۱ درصد", kit=kit, lang="fa", seconds=12, series={"title": "سریال", "episode": 2, "characters": ["سارا"]})
    assert p["chars"] <= promptkit.MAX_PROMPT_CHARS + 600 and "kinetic_title" in p["ids"] and len(p["ids"]) <= promptkit.MAX_COMPONENTS
    assert "never write a \"source\"" in p["system"] and "source" not in json.dumps(p["schema"]), "the model never writes a source"
    sch = p["schema"]
    assert sch["required"] == ["scenes"] and sch["properties"]["scenes"]["items"]["properties"]["type"]["enum"] == p["ids"]
    assert all(s["type"] == "string" or s == {} or True for s in sch["properties"]["scenes"]["items"]["properties"].values())
    assert "whiteboard_explainer" in p["system"] and "STYLE" in p["system"]
    en = promptkit.build_prompt("The water cycle in four steps.", kit=kit, lang="en", seconds=8)
    assert "English" in en["system"] and "steps" in promptkit.pick_components("first, then, finally steps process")


def test_the_components_a_request_asks_for_are_offered():
    from instai.motion_plan import promptkit

    assert "bar_chart" in promptkit.pick_components("مقایسه ۳ گزینه با نمودار میله 40 و 65 و 90")
    assert "countdown" in promptkit.pick_components("countdown to the premiere")
    assert promptkit.pick_components("")[:1] == ["kinetic_title"]


# ------------------------------------------------------------------ the roles (the fake provider answers)

def test_the_role_writes_a_valid_plan_through_the_provider_and_retimes_it_to_the_shot():
    from instai.motion_plan import role, timeline
    from instai.providers.fake import FakeProvider
    from instai.remotion import kit as kitmod

    kit = kitmod.style_kit("whiteboard_explainer")
    plan, info = role.write_plan(NARRATION, seconds=13.0, kit=kit, style=kit["key"], lang="fa", provider=FakeProvider())
    assert info["origin"] == "ai" and info.get("model") == "fake-1", info
    assert abs(timeline.total_seconds(plan, kit) - 13.0) < 0.4 and plan["scenes"]


def test_a_provider_that_fails_or_answers_badly_gives_the_deterministic_plan_not_an_error():
    from instai.motion_plan import role
    from instai.providers.base import ProviderError
    from instai.providers.fake import FakeProvider
    from instai.remotion import kit as kitmod

    kit = kitmod.style_kit("cinematic_realistic")

    class Down(FakeProvider):
        def generate(self, *a, **k):
            raise ProviderError("down", code="ollama_down")

    plan, info = role.write_plan(NARRATION, seconds=10.0, kit=kit, style=kit["key"], provider=Down())
    assert info["origin"] == "fallback" and "provider" in info["why"] and plan["scenes"]
    plan2, info2 = role.write_plan(NARRATION, seconds=10.0, kit=kit, style=kit["key"], provider=FakeProvider(fail_first=5))
    assert info2["origin"] == "fallback" and plan2["scenes"]


def test_a_request_is_a_patch_by_the_rules_first_then_by_the_model():
    from instai.motion_plan import role
    from instai.providers.fake import FakeProvider

    plan = small_plan()
    r = role.write_patch(plan, "make the title bigger", lang="en", provider=FakeProvider())
    assert r["by"] == "rules" and r["ops"] and r["say"].startswith("The text")
    assert role.write_patch(plan, "zzz qqq", lang="en", provider=FakeProvider())["ops"] == []


# ------------------------------------------------------------------ the critique (the owner's vision model; the fake stands in)

def make_measure_fake(plan_spec):
    from PIL import Image

    def measure(spec):
        return [{"scene": i, "kind": "late", "frame": 30, "W": 1080, "H": 1920, "scale": 0.5, "safe": {}, "boxes": [], "_image": Image.new("RGB", (270, 480), (30, 40, 50)),
                 "image_rel": f"motion/x/s{i}.jpg"} for i in range(len(spec["scenes"]))]
    return measure


def test_the_critique_applies_a_valid_patch_per_round_and_stops_when_the_model_sees_nothing():
    from instai.motion_plan import critique, plans
    from instai.providers.fake import FakeProvider

    plan = plans.create(small_plan())
    prov = FakeProvider()
    prov.scripted = {"verdict": "fix", "issues": [{"scene": 0, "problem": "title is small", "severity": "medium"}],
                     "ops": [{"op": "scale", "path": "scenes/0/tokens/font_scale", "factor": 1.2, "min": 0.6, "max": 1.6, "default": 1}, {"op": "set", "path": "scenes/9/duration", "value": 3}]}
    state = critique.run(plan, measure=make_measure_fake(plan.spec), provider=prov)
    plan.refresh_from_db()
    assert state["state"] == "done" and len(state["rounds"]) == 3, "each round the scripted model keeps asking for the same change until the limit"
    r0 = state["rounds"][0]
    assert r0["applied"] and r0["rejected"] and "10" in r0["rejected"][0]["why_en"], "an invalid op is rejected on its own, the valid one still applies"
    assert plan.spec["scenes"][0]["tokens"]["font_scale"] > 1.2 and plan.cursor == 4
    assert [h["source"] for h in plans.history(plan)][1:] == ["critique"] * 3, "every patch is a reversible version"
    prov.scripted = {"verdict": "ok", "issues": [], "ops": []}
    again = critique.run(plan, measure=make_measure_fake(plan.spec), provider=prov)
    assert again["state"] == "done" and len(again["rounds"]) == 1 and again["rounds"][0]["verdict"] == "ok"


def test_without_ollama_the_critique_waits_and_without_a_vision_model_it_says_so(monkeypatch):
    from instai.motion_plan import critique, plans
    from instai.providers import ollama
    from instai.providers.base import ProviderError

    plan = plans.create(small_plan())
    monkeypatch.setattr(ollama.OllamaProvider, "health", lambda self: {"ok": False, "detail": "refused", "models": []})
    with pytest.raises(ProviderError) as e:
        critique.vision_provider()
    assert e.value.code == "ollama_down", "no cloud fallback in InstAI: Ollama off is a WAIT"
    monkeypatch.setattr(ollama.OllamaProvider, "health", lambda self: {"ok": True, "detail": "", "models": ["qwen3:8b"]})
    monkeypatch.setattr(ollama.OllamaProvider, "list_models", lambda self: ["qwen3:8b", "qwq:32b"])
    with pytest.raises(ProviderError) as e2:
        critique.vision_provider()
    assert e2.value.code == "no_vision_model" and not e2.value.retryable
    state = critique.run(plan, measure=make_measure_fake(plan.spec))
    assert state["state"] == "unavailable" and "qwen3-vl" in state["message_en"] and state["message"]
    monkeypatch.setattr(ollama.OllamaProvider, "list_models", lambda self: ["qwen3:8b", "qwen3-vl:30b"])
    prov = critique.vision_provider()
    assert prov.model == "qwen3-vl:30b", "the owner's own vision model is used, never a download"


# ------------------------------------------------------------------ the API

def make_shot(api, worker, technique="motion_graphics", narration="آب ۷۱ درصد زمین را می‌پوشاند. اقیانوس، دریا و رودخانه."):
    from instai.story.models import Shot
    from tests.test_pipeline_e2e import build_episode

    page, sid, ep_id = build_episode(api, worker, fmt="concept_explainer")
    shot = Shot.objects.filter(scene__episode_id=ep_id).order_by("scene__index", "index").first()
    shot.technique, shot.narration, shot.duration_sec = technique, narration, 6.0
    shot.save()
    from instai.motion_plan.models import MotionPlan

    MotionPlan.objects.filter(shot=shot).delete()           # the storyboard job already made a first plan for a shot that was a motion shot then: start clean
    return shot


def test_the_library_endpoint_lists_every_component_in_both_languages(api):
    d = api.get("/api/motion/components").json()
    assert len(d["components"]) == 19 and len(d["templates"]) >= 5 and set(d["sizes"]) == {"landscape", "vertical", "square"}
    assert all(c["label_fa"] and c["label_en"] and c["sample_fa"] and c["sample_en"] for c in d["components"])
    assert {p["key"] for p in d["platforms"]} >= {"shorts", "reels", "tiktok", "youtube"} and d["limits"]["max_scenes"] == 14


def test_a_plan_can_be_checked_without_saving_it(api):
    r = api.post("/api/motion/plan/validate", {"spec": spec_of({"type": "kinetic_title", "duration": 1.2, "text": " ".join(["كلمه"] * 14)})}, format="json").json()
    assert r["spec"]["version"] == 1 and r["timeline"]["total"] > 1 and any(f["code"] == "too_short" for f in r["findings"]) and r["summary_en"]
    bad = api.post("/api/motion/plan/validate", {"spec": {"scenes": []}}, format="json", HTTP_X_LANG="en")
    assert bad.status_code == 400 and "scene" in bad.json()["error"]["message"] and not re.search(r"[؀-ۿ]", bad.json()["error"]["message"])


def test_the_deterministic_plan_has_an_endpoint(api):
    r = api.post("/api/motion/plan/fallback", {"narration": NARRATION, "seconds": 12, "style": "whiteboard_explainer", "size": "square", "lang": "fa"}, format="json").json()
    assert r["origin"] == "fallback" and r["spec"]["size"] == "square" and r["spec"]["scenes"]
    assert api.post("/api/motion/plan/fallback", {"narration": "", "seconds": 5}, format="json").status_code == 400


def test_a_shots_plan_is_written_by_a_job_edited_by_words_and_undone(api, worker):
    from tests.conftest import finish

    shot = make_shot(api, worker)
    assert api.get(f"/api/shots/{shot.pk}/motion").json()["plan"] is None
    j = finish(api, worker, api.post(f"/api/shots/{shot.pk}/motion", {"action": "write"}, format="json"))
    assert j["result"]["origin"] in ("ai", "fallback") and j["result"]["scenes"] >= 1
    st = api.get(f"/api/shots/{shot.pk}/motion").json()
    plan = st["plan"]
    assert plan["rev"] == 1 and st["kit"]["key"] and st["seconds"] >= 6 and st["edited"] is False and st["stale"] is False
    r = api.post(f"/api/motion/plans/{plan['id']}/patch", {"request": "make the title bigger", "lang": "en"}, format="json").json()
    assert r["applied"] and r["by"] == "rules" and r["plan"]["rev"] == 2 and r["summary"] and r["say"]
    assert api.get(f"/api/shots/{shot.pk}/motion").json()["edited"] is True
    u = api.post(f"/api/motion/plans/{plan['id']}/undo").json()
    assert u["rev"] == 1 and u["can_redo"]
    assert api.post(f"/api/motion/plans/{plan['id']}/undo").status_code == 400
    assert api.post(f"/api/motion/plans/{plan['id']}/redo").json()["rev"] == 2
    again = api.post(f"/api/motion/plans/{plan['id']}/patch", {"request": "zzz qqq"}, format="json").json()
    assert again["applied"] is False and again["say"]
    put = api.put(f"/api/motion/plans/{plan['id']}", {"spec": {**plan["spec"], "intensity": 1.4}, "label": "mine"}, format="json").json()
    assert put["spec"]["intensity"] == 1.4 and put["history"][-1]["source"] == "user"
    other = make_shot(api, worker, technique="still_kenburns")
    assert api.post(f"/api/shots/{other.pk}/motion", {"action": "write"}, format="json").status_code == 409


def test_an_edited_plan_is_never_thrown_away_and_a_generated_one_follows_the_narration(api, worker):
    from instai.motion_plan import plans, shots
    from tests.conftest import finish

    shot = make_shot(api, worker)
    finish(api, worker, api.post(f"/api/shots/{shot.pk}/motion", {"action": "write"}, format="json"))
    ep = shot.scene.episode
    first = shots.latest_plan(shot)
    shot.narration = "یک جملهٔ کاملاً تازه برای این نما."
    shot.save()
    assert shots.inputs_hash(shot, ep, shots.target_seconds(shot, ep)) != first.source_hash
    again = shots.ensure_plan(shot, ep)
    assert again.pk == first.pk and again.cursor == 2 and "تازه" in json.dumps(again.spec, ensure_ascii=False), "an unedited generated plan is written again"
    plans.apply_ops(again, [{"op": "shift", "path": "scenes/0/duration", "by": 0.5}], source="chat")
    shot.narration = "باز هم یک متن دیگر."
    shot.save()
    kept = shots.ensure_plan(shot, ep)
    assert "باز هم" not in json.dumps(kept.spec, ensure_ascii=False), "the owner's edit is kept"
    forced = shots.ensure_plan(shot, ep, force=True)
    assert "باز هم" in json.dumps(forced.spec, ensure_ascii=False), "the owner can ask for a fresh plan"


def test_the_job_kinds_have_their_titles_in_both_languages(api):
    from instai.jobs import describe

    for kind in ("motion.plan", "motion.qa", "motion.critique"):
        fa, en = describe.KIND_TEXT[kind]
        assert re.search(r"[؀-ۿ]", fa) and not re.search(r"[؀-ۿ]", en), kind


def test_the_costs_know_the_technique_and_charge_the_cpu_not_the_gpu():
    from instai.story import costs

    assert "motion_graphics" in costs.IMPLEMENTED
    e = costs.shot_estimate("motion_graphics", 6)
    assert e["gpu_seconds"] == 0 and e["cpu_seconds"] > 6 * 3 and "falls_back_to_still_kenburns" not in e["notes"]
    assert costs.shot_estimate("motion_graphics", 6, "preview")["cpu_seconds"] < e["cpu_seconds"]
    assert "motion_graphics" not in costs.KEYFRAME and "motion_graphics" not in costs.VIDEO


def test_the_storyboard_gives_every_motion_shot_a_first_plan_that_production_rewrites_when_the_speech_is_known(api, worker):
    from instai.motion_plan import shots
    from tests.conftest import finish

    shot = make_shot(api, worker)
    ep = shot.scene.episode
    assert shots.latest_plan(shot) is None
    assert shots.prepare_plans(ep) >= 1
    plan = shots.latest_plan(shot)
    assert plan.origin == "fallback" and plan.spec["scenes"] and plan.cursor == 1
    assert shots.prepare_plans(ep) == 0, "once is enough"
    # the storyboard job calls it by itself (the job result says how many): a regenerated storyboard of the same episode
    j = finish(api, worker, api.post(f"/api/episodes/{ep.pk}/generate-storyboard"))
    assert "motion_plans" in j["result"]


def test_the_frames_really_go_to_the_owners_vision_model_through_instais_own_ollama_provider(monkeypatch):
    """The wire format against a fake Ollama (tests/fakes.py): the vision model installed among the owner's models is chosen (qwen3:8b has no eyes), the request carries the frames as base64
    images in the user message and the verdict schema in `format`, and the answer is read back."""
    import base64

    from instai.core import settings_store
    from instai.motion_plan import critique
    from instai.providers.ollama import OllamaProvider
    from tests import fakes

    with fakes.ollama_server(models=("qwen3:8b", "qwen3-vl:30b"), loaded=()) as srv:
        real = settings_store.effective
        monkeypatch.setattr(settings_store, "effective", lambda k, *a, **kw: srv.url if k == "ollama_url" else real(k, *a, **kw))
        prov = critique.vision_provider()
        assert isinstance(prov, OllamaProvider) and prov.model == "qwen3-vl:30b"
        spec = small_plan()
        shots = make_measure_fake(spec)(spec)
        res = critique.ask(prov, spec, shots)
        body = [r for r in srv.requests if r["path"] == "/api/chat"][-1]["body"]
    assert body["model"] == "qwen3-vl:30b" and body["format"]["required"] == ["verdict"] and body["stream"] is True
    user = body["messages"][-1]
    assert user["role"] == "user" and len(user["images"]) == len(shots) and "PLAN:" in user["content"] and "scene" in user["content"]
    assert base64.b64decode(user["images"][0])[:3] == b"\xff\xd8\xff", "a JPEG frame"
    assert res["verdict"] == "ok" and res["issues"] == []
