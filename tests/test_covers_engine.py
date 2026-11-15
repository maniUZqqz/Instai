"""The cover engine (pure Pillow, no database): every layout in every format with Persian and English text - exact size, not blank, the title really drawn, inside the safe area and
out of the platform's avoid zones - plus the layouts written for this studio (episode card, cliffhanger, A/B choice poster), the formats, the spec and the palette.

Ported from NMarketing's apps/thumbs tests_render.py / tests_fixes.py (adapted: the store layouts and the pinterest format are gone, the layers are named in English, both languages)."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageChops

from instai.covers.engine import fixtures, palette, typo
from instai.covers.engine import formats as F
from instai.covers.engine import render as R
from instai.covers.engine.styles import STYLES

SCALE = 0.24                 # a small preview keeps the 16 x 9 matrix fast
FA, EN = fixtures.sample_content("fa"), fixtures.sample_content("en")
PORTED = ["character_face", "split_ba", "number_list", "question_hook", "minimal_luxury", "cinema_poster", "sticker_outline", "neon", "news_bold", "versus", "magazine_cover",
          "retro_poster", "quote_card"]
INSTAI = ["episode_card", "cliffhanger", "choice_split"]


def spec(style, fmt, lang="fa", **over):
    raw = {"format": fmt, "style": style, "lang": lang, "content": dict(FA if lang == "fa" else EN)}
    raw.update(over)
    return R.clean_spec(raw, STYLES)


def inputs(subject=True, second=True, bg=False, logo=False):
    inp = R.Inputs(brand_colors=list(fixtures.CHAGHER_COLORS), channel_name="Chagher")
    if subject:
        inp.subject, inp.subject_is_cutout = fixtures.person(), True
    if second:
        inp.subject2, inp.subject2_is_cutout = fixtures.person(skin="#d9a577", shirt="#dc2626", mood="sad"), True
    if bg:
        inp.background = fixtures.scene()
    if logo:
        inp.logo = Image.new("RGBA", (300, 120), (20, 120, 140, 255))
    return inp


def stddev(img):
    return float(np.asarray(img.convert("L"), dtype=np.float32).std())


def overlap_frac(box, rect):
    ix = max(0, min(box[2], rect[2]) - max(box[0], rect[0]))
    iy = max(0, min(box[3], rect[3]) - max(box[1], rect[1]))
    return ix * iy / max(1, (box[2] - box[0]) * (box[3] - box[1]))


def titles(res):
    return [t for t in res.texts if t["name"].startswith("title")]


# ------------------------------------------------------------------ the brief: every layout and every format exists (the owner's "you did not add all of them" lesson)

def test_the_brief_formats_exist_with_the_documented_sizes():
    want = {"youtube": (1280, 720), "aparat": (1280, 720), "telegram": (1280, 720), "ig_portrait": (1080, 1350), "ig_square": (1080, 1080), "story": (1080, 1920),
            "poster": (1200, 1800), "yt_banner": (2560, 1440), "season_card": (1920, 1080)}
    assert set(F.FORMATS) == set(want), "pinterest is dropped; yt_banner and season_card are added"
    for key, size in want.items():
        assert F.get(key).size == size, key
    assert F.get("poster").w * 3 == F.get("poster").h * 2, "a series poster is 2:3"
    assert F.get("youtube").max_kb == 2000 and F.get("youtube").aspect_label == "16:9"
    story = F.get("story")
    tops = [a for a in story.avoid if a[1] == 0.0 and a[3] == 0.13]
    bottoms = [a for a in story.avoid if abs(a[1] - 0.82) < 1e-9 and a[3] == 1.0]
    assert tops and bottoms, "Reels / Shorts: the top 13% and the bottom 18% are avoid zones"
    x0, y0, x1, y1 = F.safe_rect(F.get("yt_banner"), F.get("yt_banner").size)
    assert abs((x1 - x0) - 1546) <= 2 and abs((y1 - y0) - 423) <= 2, "the banner's safe centre is about 1546x423"
    for f in F.FORMATS.values():
        assert f.title_fa and f.title_en and f.note_fa and f.note_en and f.margin[0] > 0
        assert not re_persian(f.title_en) and not re_persian(f.note_en), f.key
        assert set(f.public()) >= {"key", "title_fa", "title_en", "avoid", "margin"}


def re_persian(text: str) -> bool:
    import re

    return bool(re.search("[؀-ۿ]", text))


def test_the_layouts_are_the_brief_plus_the_three_studio_layouts():
    assert set(PORTED) <= set(STYLES) and set(INSTAI) <= set(STYLES)
    assert "product_hero" not in STYLES and "pinterest_collage" not in STYLES, "store vocabulary is not ported"
    assert len(STYLES) >= 15 + 1
    assert len([k for k, s in STYLES.items() if s.origin == "ported"]) >= 12
    assert {k for k, s in STYLES.items() if s.origin == "instai"} == set(INSTAI)
    for k, s in STYLES.items():
        assert any(a == "title" for a, _, _ in s.fields), k
        assert set(s.formats) <= set(F.FORMATS), k
        assert s.mood in palette.MOODS and s.font in typo.FONT_CHOICES, k
        assert s.title_fa and s.title_en and s.short_fa and s.short_en and s.pattern_fa and s.pattern_en, k
        assert not re_persian(s.title_en + s.short_en + s.pattern_en), k
        for key, fa, en in s.fields:
            assert fa and en and not re_persian(en), (k, key)
        from instai.covers.engine import hooks

        assert k in hooks.CONCEPTS and k in hooks.BG_PROMPTS, k


# ------------------------------------------------------------------ the matrix

@pytest.mark.parametrize("lang", ["fa", "en"])
def test_every_layout_on_every_format(lang):
    inp = inputs()
    for style in STYLES:
        for fmt in F.FORMATS:
            res = R.render(spec(style, fmt, lang), inp, scale=SCALE)
            assert res.image.size == F.scaled(F.get(fmt), SCALE) == res.size, (style, fmt)
            assert stddev(res.image) > 18, ("blank", style, fmt)
            assert titles(res), ("the title was not drawn", style, fmt)
            W, H = res.size
            for t in res.texts:
                x0, y0, x1, y1 = t["bbox"]
                assert 0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H, ("text outside the canvas", style, fmt, t)
            kinds = {layer["kind"] for layer in res.layers}
            assert "background" in kinds and "text" in kinds, (style, fmt)


def test_every_format_is_rendered_at_its_exact_size_in_full():
    inp = inputs()
    for fmt, f in F.FORMATS.items():
        res = R.render(spec("episode_card", fmt), inp, scale=1.0)
        assert res.image.size == f.size, fmt
        if f.max_kb:
            assert len(R.to_jpeg_bytes(res.image, 90, f.max_kb)) <= f.max_kb * 1024, fmt


def test_titles_respect_the_platform_avoid_zones_and_the_safe_area():
    inp = inputs()
    for style in STYLES:
        for fmt, f in F.FORMATS.items():
            res = R.render(spec(style, fmt), inp, scale=SCALE)
            avoid = F.avoid_rects(f, res.size)
            sx0, sy0, sx1, sy1 = F.safe_rect(f, res.size)
            pad = res.size[0] * 0.05                      # shadows and glows reach a little outside
            for t in titles(res):
                for a in avoid:
                    assert overlap_frac(t["bbox"], a) < 0.12, (style, fmt, t["bbox"], a)
                b = t["bbox"]
                assert b[0] >= sx0 - pad and b[2] <= sx1 + pad and b[1] >= sy0 - pad and b[3] <= sy1 + pad, (style, fmt, b, (sx0, sy0, sx1, sy1))


def test_text_is_really_drawn_where_the_report_says():
    inp = inputs()
    for style in STYLES:
        for fmt in ("youtube", "story", "poster"):
            with_t = R.render(spec(style, fmt), inp, scale=SCALE)
            bare = R.render(R.clean_spec({"format": fmt, "style": style, "content": dict(FA, title="")}, STYLES), inp, scale=SCALE)
            t = titles(with_t)[0]
            x0, y0, x1, y1 = t["bbox"]
            diff = np.asarray(ImageChops.difference(with_t.image.crop((x0, y0, x1, y1)), bare.image.crop((x0, y0, x1, y1))).convert("L"), dtype=np.float32)
            assert float((diff > 40).mean()) > 0.03, (style, fmt)


# ------------------------------------------------------------------ inputs: no picture, photos, background, logo, scale, determinism, A/B

def test_no_images_at_all_is_never_empty_and_warns_in_both_languages():
    for style in STYLES:
        res = R.render(spec(style, "ig_portrait"), R.Inputs(), scale=SCALE)
        assert stddev(res.image) > 18 and titles(res), style
    res = R.render(spec("character_face", "youtube"), R.Inputs(), scale=SCALE)
    w = next(w for w in res.warnings if w["code"] == "no_subject")
    assert w["fa"] and w["en"] and not re_persian(w["en"])
    assert not R.render(spec("character_face", "youtube"), inputs(), scale=SCALE).warnings, "with a character there is no warning"


def test_a_photo_instead_of_a_cutout_a_photo_background_and_a_logo():
    photo = R.Inputs(subject=fixtures.scene(), subject_is_cutout=False, subject2=fixtures.scene(seed=2), subject2_is_cutout=False)
    for style in STYLES:
        assert stddev(R.render(spec(style, "youtube"), photo, scale=SCALE).image) > 18, style
    for style in STYLES:
        res = R.render(spec(style, "ig_square", background={"kind": "photo"}), inputs(bg=True, logo=True), scale=SCALE)
        assert any(layer["kind"] == "logo" for layer in res.layers), style
        assert stddev(res.image) > 18, style
    assert stddev(R.render(spec("neon", "youtube", background={"kind": "photo"}), inputs(), scale=SCALE).image) > 18, "a photo background without a picture falls back"


def test_the_logo_never_covers_a_title_or_a_badge_and_the_channel_name_gets_a_free_corner():
    inp = inputs(logo=True)
    for style in STYLES:
        for fmt in ("youtube", "story", "ig_square", "poster"):
            res = R.render(spec(style, fmt), inp, scale=SCALE)
            logo = next(layer for layer in res.layers if layer["kind"] == "logo")
            for t in titles(res):
                assert overlap_frac(t["bbox"], logo["bbox"]) < 0.2, (style, fmt)
            tag = [layer for layer in res.layers if layer["name"] == "channel tag"]
            assert tag, (style, fmt, "the channel name is drawn")
            for t in titles(res):
                assert overlap_frac(tag[0]["bbox"], t["bbox"]) < 0.2, (style, fmt, "the channel tag sits on the title")
    assert not [layer for layer in R.render(spec("neon", "youtube", content=dict(FA, channel="")), inp, scale=SCALE).layers if layer["name"] == "channel tag"]


def test_long_text_and_mixed_scripts_stay_inside_the_canvas():
    long_title = "این یک عنوانِ بسیار بسیار بلند است که باید خودش را در جعبه جا بدهد بدونِ بیرون‌زدن از بوم و بدونِ همپوشانی"
    for style in STYLES:
        res = R.render(spec(style, "youtube", content={"title": long_title, "subtitle": long_title, "kicker": long_title, "badge": long_title}), inputs(), scale=SCALE)
        for t in res.texts:
            b = t["bbox"]
            assert 0 <= b[0] and b[2] <= res.size[0] and 0 <= b[1] and b[3] <= res.size[1], (style, t)
    assert R.render(spec("character_face", "youtube", content={"title": "قسمت ۲ از *Chagher* 2026"}), inputs(), scale=SCALE).texts


def test_scale_changes_the_size_not_the_layout_and_the_render_is_deterministic():
    sp = spec("character_face", "youtube")
    a, b = R.render(sp, inputs(), scale=0.3), R.render(sp, inputs(), scale=0.6)
    assert b.size == F.scaled(F.get("youtube"), 0.6)
    ta, tb = titles(a)[0]["bbox"], titles(b)[0]["bbox"]
    ca = ((ta[0] + ta[2]) / 2 / a.size[0], (ta[1] + ta[3]) / 2 / a.size[1])
    cb = ((tb[0] + tb[2]) / 2 / b.size[0], (tb[1] + tb[3]) / 2 / b.size[1])
    assert abs(ca[0] - cb[0]) < 0.03 and abs(ca[1] - cb[1]) < 0.03
    s5 = spec("sticker_outline", "story", seed=5)
    assert R.render(s5, inputs(), scale=SCALE).image.tobytes() == R.render(s5, inputs(), scale=SCALE).image.tobytes()


def test_ab_versions_differ_and_the_subject_changes_side():
    base = R.render(spec("character_face", "youtube"), inputs(), scale=SCALE).image
    other = R.render(spec("character_face", "youtube", colors={"variation": 1}), inputs(), scale=SCALE).image
    assert float(np.abs(np.asarray(base, dtype=int) - np.asarray(other, dtype=int)).mean()) > 5
    from instai.covers import service

    # all six versions of every layout are clearly different pictures (the A/B point), each with a note that names the change
    for style in STYLES:
        sp = spec(style, "youtube")
        imgs = [np.asarray(R.render(service.variant_spec(sp, i), inputs(), scale=0.18).image, dtype=int) for i in range(6)]
        for i in range(6):
            for j in range(i + 1, 6):
                assert float(np.abs(imgs[i] - imgs[j]).mean()) > 2.0, (style, i, j)
    notes = [service.variant_plan(spec("episode_card", "youtube"), i) for i in range(6)]
    assert all(n["fa"] and n["en"] and not re_persian(n["en"]) for n in notes) and len({n["en"] for n in notes}) == 6
    assert service.variant_plan(spec("cliffhanger", "youtube"), 2)["mood"] != "dark", "a dark layout does not get its own mood as a 'new' version"


def test_guides_draw_the_safe_area_and_the_layers_can_be_kept():
    plain = R.render(spec("character_face", "story"), inputs(), scale=SCALE)
    guided = R.render(spec("character_face", "story", guides=True), inputs(), scale=SCALE)
    assert plain.image.tobytes() != guided.image.tobytes()
    kept = R.render(spec("character_face", "youtube"), inputs(), scale=SCALE, keep_layers=True)
    assert len(kept.kept) >= 5 and len(kept.kept) == len(kept.layers)
    kinds = {layer["kind"] for layer in R.render(spec("character_face", "youtube"), inputs(bg=True, logo=True), scale=SCALE).layers}
    assert {"background", "subject", "text", "badge", "accent"} <= kinds


# ------------------------------------------------------------------ the layouts written for this studio

def test_episode_card_draws_the_series_the_big_number_and_the_hook():
    for fmt in ("youtube", "story", "ig_portrait", "poster"):
        res = R.render(spec("episode_card", fmt), inputs(), scale=SCALE)
        names = {t["name"] for t in res.texts}
        assert {"title", "number", "subtitle"} <= names, (fmt, names)
        badge = next(layer for layer in res.layers if layer["name"] == "episode badge")
        num = next(t for t in res.texts if t["name"] == "number")
        assert overlap_frac(num["bbox"], badge["bbox"]) > 0.9, (fmt, "the number sits inside the badge")
        assert (badge["bbox"][2] - badge["bbox"][0]) > res.size[0] * 0.1, (fmt, "the badge is big")
    # without a number the badge text can stand in; without both there is no badge
    assert "episode badge" not in [layer["name"] for layer in R.render(spec("episode_card", "youtube", content=dict(FA, number="", badge="")), inputs(), scale=SCALE).layers]
    assert "episode badge" in [layer["name"] for layer in R.render(spec("episode_card", "youtube", content=dict(FA, number="", badge="جدید")), inputs(), scale=SCALE).layers]


def test_cliffhanger_is_dark_and_its_headline_fades_at_the_end():
    res = R.render(spec("cliffhanger", "youtube"), inputs(), scale=0.5)
    lum = float(np.asarray(res.image.convert("L"), dtype=np.float32).mean())
    assert lum < 70, "an almost black scene"
    assert any(layer["name"] == "to be continued" for layer in res.layers)
    kept = R.render(spec("cliffhanger", "youtube", content=dict(FA, title="و ناگهان در باشگاه باز شد")), inputs(), scale=0.5, keep_layers=True)
    title = next(l for l in kept.kept if l["name"] == "title")
    a = np.asarray(title["img"].getchannel("A"), dtype=float)
    h, w = a.shape
    last = a[int(h * 0.55):, :]                                   # the last line
    cols = np.where(last.max(axis=0) > 10)[0]
    third = max(1, (cols[-1] - cols[0]) // 3)
    left, right = last[:, cols[0]: cols[0] + third], last[:, cols[-1] - third: cols[-1]]
    assert left.mean() < right.mean() * 0.8, "Persian reads right to left: the END (the left side) fades"


def test_choice_split_has_two_letters_two_plates_and_the_or_disc_in_both_languages():
    for lang, letters, word in (("fa", ("الف", "ب"), "یا"), ("en", ("A", "B"), "OR")):
        for fmt in ("youtube", "story", "ig_square"):
            res = R.render(spec("choice_split", fmt, lang), inputs(), scale=SCALE)
            seen = {t["name"]: t["text"] for t in res.texts}
            assert seen["letter a"] == letters[0] and seen["letter b"] == letters[1] and seen["or"] == word, (lang, fmt, seen)
            assert "choice a" in seen and "choice b" in seen and "title" in seen, (lang, fmt)


def test_english_covers_mirror_the_persian_layout():
    """Persian: the text on the right, the subject on the left; English: the other way round."""
    for style in ("character_face", "episode_card", "neon"):
        fa = R.render(spec(style, "youtube", "fa"), inputs(), scale=SCALE)
        en = R.render(spec(style, "youtube", "en"), inputs(), scale=SCALE)
        cx = lambda r: (titles(r)[0]["bbox"][0] + titles(r)[0]["bbox"][2]) / 2 / r.size[0]  # noqa: E731
        assert cx(fa) > 0.5 > cx(en), (style, cx(fa), cx(en))


# ------------------------------------------------------------------ spec, palette, text

def test_clean_spec_rejects_unknown_and_trims():
    with pytest.raises(R.SpecError) as e:
        R.clean_spec({"format": "pinterest", "style": "neon"}, STYLES)
    assert e.value.fa and e.value.en and not re_persian(e.value.en)
    with pytest.raises(R.SpecError):
        R.clean_spec({"format": "youtube", "style": "product_hero"}, STYLES)
    sp = R.clean_spec({"format": "story", "style": "neon", "lang": "de", "content": {"title": "x" * 500, "evil": "y", "channel": "c" * 99}, "colors": {"primary": "red", "accent": "#FFAA00"},
                       "subject": {"asset": "7", "character": "3", "expression": "Happy!!", "scale": 9}, "background": {"kind": "weird"}, "font": "comic"}, STYLES)
    assert len(sp["content"]["title"]) == R.MAX_TITLE and "evil" not in sp["content"] and len(sp["content"]["channel"]) == 40
    assert sp["lang"] == "fa" and sp["colors"]["primary"] == "" and sp["colors"]["accent"] == "#ffaa00"
    assert sp["subject"]["asset"] == 7 and sp["subject"]["character"] == 3 and sp["subject"]["scale"] == 1.4 and sp["subject"]["expression"] == ""
    assert sp["background"]["kind"] == "auto" and sp["font"] == typo.AUTO_FONT
    assert "price" not in sp["content"] and "cta" not in sp["content"], "no store fields"


def test_the_palette_comes_from_the_series_colours_and_keeps_its_contrast():
    for mood in palette.MOODS:
        p = palette.build(mood, list(fixtures.CHAGHER_COLORS))
        assert palette.colorx.contrast(p.text, p.bg1) >= 3.0, mood
        assert palette.colorx.contrast(p.accent, p.bg1) >= 2.0, mood
    a, b = palette.build("vivid", ["#126F85"], variation=0), palette.build("vivid", ["#126F85"], variation=1)
    assert (a.bg1, a.bg2) != (b.bg1, b.bg2)
    roles = ["#0A0F1F", "#12E2D5", "#FF2E97", "#FFD23F", "#05060F", "#E6F9FF"]            # the 6 roles of a colour theme
    t = palette.from_theme(roles, "dark")
    assert t.accent and palette.colorx.contrast(t.text, t.bg1) >= 3.0
    assert palette.from_theme([], "dark").bg1, "an invalid theme falls back to the mood"
    assert palette.brand_colors_of(["#112233"], ["#445566"]) == ["#445566"] and palette.brand_colors_of(["#112233"], None) == ["#112233"] and palette.brand_colors_of(None, None) == []
    res = R.render(spec("episode_card", "youtube"), R.Inputs(theme_roles=roles), scale=SCALE)
    assert res.palette["primary"] == "#12e2d5" or res.palette["primary"].lower() == "#12e2d5"


def test_persian_digits_markup_and_fitting():
    assert typo.to_fa_digits("۷ روش و 12 نکته، 1,250,000 تومان") == "۷ روش و ۱۲ نکته، ۱٬۲۵۰٬۰۰۰ تومان"
    assert typo.to_fa_digits("iPhone 16") == "iPhone 16"
    assert typo.plain("الف *ب* ج|د") == "الف ب ج د"
    groups, marked = typo.parse_marked("الف *ب ج* د|ه")
    assert marked and len(groups) == 2 and [w for w, h in groups[0] if h] == ["ب", "ج"]
    st = typo.TextStyle(font_key="lalezar", weight=400, stroke_w=0.08, stroke="#000000")
    blk = typo.render_text("این یک عنوانِ نسبتاً بلند برای آزمونِ جاگیری است", 500, 260, st, max_lines=3, min_px=12, max_px=200)
    assert blk is not None and blk.nominal[0] <= 502 and blk.nominal[1] <= 262 and blk.px > 20
    assert typo.render_text("   ", 100, 100, st) is None


def test_english_digits_stay_latin_on_an_english_cover():
    res = R.render(spec("number_list", "youtube", "en", content=dict(EN, number="7")), inputs(), scale=SCALE)
    assert next(t for t in res.texts if t["name"] == "number")["text"] == "7"
    res = R.render(spec("number_list", "youtube", "fa", content=dict(FA, number="7")), inputs(), scale=SCALE)
    assert next(t for t in res.texts if t["name"] == "number")["text"] == "۷"


def test_the_bundled_fonts_are_ofl_and_have_their_licence_next_to_them():
    from pathlib import Path

    fonts = Path(typo.FONT_DIR)
    for name in ("Lalezar-Regular.ttf", "Sahel-Black.ttf", "Sahel-Regular.ttf"):
        assert (fonts / name).is_file(), name
    assert "Open Font License" in (fonts / "Lalezar-OFL.txt").read_text(encoding="utf-8")
    assert "Open Font License" in (fonts / "Sahel-LICENSE.txt").read_text(encoding="utf-8")
    assert (fonts / "README.md").is_file()
    for key in typo.FONTS:
        for w in (300, 400, 500, 700, 800):
            assert Path(typo.font_path(key, w)).is_file(), (key, w)


# ------------------------------------------------------------------ the port rules

def test_nothing_imports_nmarketing_and_every_ported_module_names_its_source():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "instai" / "covers"
    bad = []
    for p in root.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*(from|import)\s+(apps|services|photoedit|backend)\b", line) or re.search(r"(from|import)\s+apps\.", line):
                bad.append(f"{p.name}:{i}: {line.strip()}")
    assert bad == [], bad
    for name in ("render", "primitives", "shapes", "typo", "palette", "formats", "styles", "archetypes", "hooks", "phrases", "colorx", "fixtures"):
        text = (root / "engine" / f"{name}.py").read_text(encoding="utf-8")
        assert "SOURCE:" in text and "NMarketing:backend/apps/" in text and "c23f861" in text, name
    for name in ("ideation", "background", "selftest"):
        assert "SOURCE:" in (root / f"{name}.py").read_text(encoding="utf-8"), name
