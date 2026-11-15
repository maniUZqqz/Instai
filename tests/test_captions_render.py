"""Word-by-word captions through the REAL ffmpeg + libass: the pictures are measured, because an ASS file that merely parses proves nothing about shaping, reading
order, boxes, animation, the safe zones or the contrast of what the viewer sees.

Ported with their intent from NMarketing's RealRenderTests (tests_titles.py, v3.02 c23f861), measured again on InstAI's own libass and fonts (so the `line` ratios of
`titles_ass.FONTS` are checked here), plus the seven presets in a vertical and a landscape frame, English captions, and a light series look. Pillow only (no numpy).
Skipped where this ffmpeg has no `ass` filter (START.bat installs one that has it)."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from instai.render import captions, captions_check, contrast, ffmpeg, safezones, titles_ass

pytestmark = pytest.mark.slow
BG = "#202020"
LOOK_CHAGHER = {"palette": {"background": "#0B1F3A", "primary": "#126F85", "secondary": "#163F75", "accent": "#FFB703", "shadow": "#05070A", "highlight": "#F3E9D8"},
                "typography": {"title_weight": "bold", "subtitle_color": "#FFFFFF"}}
LOOK_CHAGHER_BRAND = {"palette": {"background": "#163F75", "primary": "#126F85", "secondary": "#1B2B45", "accent": "#DBE6FF", "shadow": "#05070A", "highlight": "#F7FAFF"},
                      "typography": {"title_weight": "bold", "subtitle_color": "#FFFFFF"}}
LIGHT_LOOK = {"palette": {"background": "#FFF8E1", "primary": "#FFE082", "secondary": "#FFCA28", "accent": "#FFE082", "shadow": "#8D6E63", "highlight": "#FFFFFF"},
              "typography": {"title_weight": "bold", "subtitle_color": "#FFFF00"}}


@pytest.fixture(autouse=True)
def _libass(ffmpeg_available):
    if not (ffmpeg_available.get("features") or {}).get("ass"):
        pytest.skip("this ffmpeg has no `ass` filter")


def hexrgb(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def frame(items, t, w=240, h=426, bg=BG, work=None) -> Image.Image:
    """One frame of the caption clips over a flat background."""
    d = Path(tempfile.mkdtemp(prefix="cap-render-"))
    try:
        (d / "sub.ass").write_text(titles_ass.build_ass(items, w, h), encoding="utf-8")
        (d / "fonts").mkdir()
        for f in titles_ass.FONTS_DIR.glob("*.ttf"):
            shutil.copyfile(f, d / "fonts" / f.name)
        ffmpeg.run(["-f", "lavfi", "-i", f"color=c={bg}:s={w}x{h}:r=25:d={t + 1}", "-ss", f"{t}", "-vf", titles_ass.ass_filter(), "-frames:v", "1", str(d / "o.png")], cwd=d, timeout=60)
        return Image.open(d / "o.png").convert("RGB").copy()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def mask(img: Image.Image, pred) -> Image.Image:
    """255 where `pred(pixel)`. `ink` and `bright` (the two predicates used on big frames) take the fast path with Pillow's channel operations."""
    if pred is ink:
        r, g, b = ImageChops.difference(img, Image.new("RGB", img.size, (32, 32, 32))).split()
        return ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 255 if v > 40 else 0)
    if pred is bright:
        r, g, b = img.split()
        return ImageChops.darker(ImageChops.darker(r, g), b).point(lambda v: 255 if v > 200 else 0)
    out = Image.new("L", img.size, 0)
    out.putdata([255 if pred(p) else 0 for p in img.getdata()])
    return out


def near(color: str, tol=40):
    r, g, b = hexrgb(color)
    return lambda p: abs(p[0] - r) < tol and abs(p[1] - g) < tol and abs(p[2] - b) < tol


def bright(p) -> bool:
    return min(p) > 200


def ink(p) -> bool:
    return max(abs(p[0] - 32), abs(p[1] - 32), abs(p[2] - 32)) > 40


def count(img, pred) -> int:
    return mask(img, pred).histogram()[255]


def centroid(img, pred):
    m = mask(img, pred)
    w = m.width
    xs = ys = n = 0
    for i, v in enumerate(m.getdata()):
        if v:
            xs += i % w
            ys += i // w
            n += 1
    return (xs / n, ys / n) if n else (None, None)


def rows_of_ink(img, pred, gap) -> int:
    """How many text lines: bands of inked rows, a gap of `gap` px or more between two bands (a Persian line has dots well away from its body)."""
    ys = [y for y, v in enumerate(mask(img, pred).getprojection()[1]) if v]
    bands, prev = 0, None
    for y in ys:
        if prev is None or y - prev > gap:
            bands += 1
        prev = y
    return bands


FA = "تخفیف ویژه ۵۰٪ NMarketing 2026"


# ------------------------------------------------------------------ reading order, timing, highlight

def test_text_shows_only_inside_its_window_and_persian_reads_right_to_left():
    item = {"text": "اول دوم سوم", "at": 1.0, "duration": 2.0, "size": 9, "y": 0.5, "hl_color": "#FF0000", "color": "#FFFFFF",
            "words": [{"w": "اول", "s": 0.0, "e": 0.6}, {"w": "دوم", "s": 0.7, "e": 1.3}, {"w": "سوم", "s": 1.4, "e": 1.9}]}
    assert count(frame([item], 0.5), bright) == 0, "before the clip"
    assert count(frame([item], 3.5), bright) == 0, "after the clip"
    xs = []
    for t in (1.3, 2.0, 2.6):                                           # first, second, third word active
        img = frame([item], t)
        assert count(img, bright) > 100, f"white text at {t}"
        cx, _ = centroid(img, near("#FF0000"))
        assert cx is not None, f"highlight colour missing at {t}"
        xs.append(cx)
    assert xs[0] > xs[1] + 10 and xs[1] > xs[2] + 10, "the first word is rightmost, the third leftmost: the highlight walks left"


def test_english_reads_left_to_right():
    item = {"text": "one two three", "at": 0.0, "duration": 2.0, "size": 8, "y": 0.5, "hl_color": "#FF0000", "direction": "ltr",
            "words": [{"w": "one", "s": 0.0, "e": 0.6}, {"w": "two", "s": 0.7, "e": 1.3}, {"w": "three", "s": 1.4, "e": 1.9}]}
    xs = [centroid(frame([item], t), near("#FF0000"))[0] for t in (0.3, 1.0, 1.6)]
    assert xs[0] < xs[1] - 5 < xs[2] - 10


def test_a_persian_line_that_starts_with_a_number_keeps_its_right_to_left_order():
    words = [{"w": "۱۲۳", "s": 0.0, "e": 0.6}, {"w": "قهوه", "s": 0.7, "e": 1.3}, {"w": "تازه", "s": 1.4, "e": 1.9}]
    item = {"text": "۱۲۳ قهوه تازه", "at": 0.0, "duration": 2.0, "size": 9, "y": 0.5, "hl_color": "#FF0000", "direction": "rtl", "words": words}
    xs = [centroid(frame([item], t), near("#FF0000"))[0] for t in (0.3, 1.0, 1.6)]
    assert xs[0] > xs[1] > xs[2], xs


@pytest.mark.parametrize("mode", titles_ass.HL_MODES)
def test_every_highlight_mode_paints_the_spoken_word(mode):
    words = [{"w": w, "s": i * 0.5, "e": i * 0.5 + 0.45} for i, w in enumerate("قهوه تازه امروز".split())]
    item = {"text": "قهوه تازه امروز", "at": 0.0, "duration": 2.0, "words": words, "hl_color": "#00FF00", "hl_mode": mode, "size": 8, "y": 0.5}
    assert count(frame([item], 0.7), near("#00FF00")) > 80, mode
    assert count(frame([item], 1.5), near("#00FF00")) > 40, mode + ": the last word is lit too"


def test_the_box_the_stroke_and_the_shadow_are_drawn_only_when_asked():
    base = {"text": FA, "at": 0.0, "duration": 2.0, "y": 0.5, "size": 6}
    assert count(frame([base], 1.0), near("#C80000")) == 0
    assert count(frame([{**base, "box": True, "box_color": "#C80000", "box_opacity": 1.0}], 1.0), near("#C80000", 20)) > 800, "a solid red box behind the text"
    stroked = frame([{**base, "stroke": 25, "stroke_color": "#C80000"}], 1.0)
    assert count(stroked, near("#C80000", 30)) > 150 and count(stroked, bright) > 100, "a red outline around white letters"
    shadowed = frame([{**base, "shadow": 40, "shadow_color": "#00FF00"}], 1.0)
    assert count(shadowed, lambda p: p[1] > 120 and p[0] < 80 and p[2] < 80) > 40, "a coloured drop shadow"


# ------------------------------------------------------------------ size, wrapping

@pytest.mark.parametrize("font", ["vazir", "vazir_black", "vazir_light"])
def test_the_measured_text_width_is_what_libass_draws(font):
    """The `line` ratio of each bundled font: a line is measured by Pillow with the same shaper and must be as wide as libass draws it (within 3 %)."""
    text = "این یک آزمون"
    img = frame([{"text": text, "at": 0, "duration": 2, "font": font, "bold": False, "size": 6, "y": 0.5, "region": 0.98, "color": "#FFFFFF"}], 1.0, 540, 960)
    bbox = mask(img, bright).getbbox()
    est = titles_ass.text_width(text, 0.06 * 960, font, False)
    assert bbox and abs((bbox[2] - bbox[0]) / est - 1.0) < 0.03, (font, bbox, est)


def test_size_and_position_follow_the_frame_not_the_pixels():
    item = {"text": "H", "at": 0.0, "duration": 2.0, "size": 10, "x": 0.5, "y": 0.5}
    small, large = frame([item], 1.0, 200, 356), frame([item], 1.0, 400, 712)
    bs, bl = mask(small, bright).getbbox(), mask(large, bright).getbbox()
    assert (bl[3] - bl[1]) / (bs[3] - bs[1]) == pytest.approx(2.0, abs=0.3)
    for img in (small, large):
        cx, cy = centroid(img, bright)
        assert cx / img.width == pytest.approx(0.5, abs=0.05) and cy / img.height == pytest.approx(0.5, abs=0.05)


@pytest.mark.parametrize("size,font,bold", [(5.2, "vazir", True), (7.2, "vazir_black", False), (4.6, "vazir", False)])
def test_the_estimated_lines_are_never_fewer_than_the_lines_libass_draws(size, font, bold):
    texts = ["این یک آزمون زیرنویسِ کلمه به کلمه", "چغر دستیار تمرین و تغذیه شماست و همیشه کنار شماست", "کلمه به کلمه گفتن مهم است و باید خوب دیده شود امروز",
             "قهوهٔ تازه با تخفیفِ ویژهٔ امروز و ارسالِ رایگان برای همهٔ سفارش‌ها"]
    em = size / 100 * 960
    for text in texts:
        clip = titles_ass.clean({"text": text, "size": size, "font": font, "bold": bold, "x": 0.455, "region": 0.81, "y": 0.5, "color": "#FFFFFF"})
        g = titles_ass.geometry(clip, 540, 960)
        drawn = rows_of_ink(frame([clip], 1.0, 540, 960), bright, int(0.3 * em))
        assert g["lines"] >= drawn >= 1, (text, g["lines"], drawn)
        assert g["lines"] - drawn <= 1, "and not wildly more"


def test_a_long_text_wraps_inside_the_frame_and_stays_in_it():
    item = {"text": "قهوهٔ تازه با تخفیفِ ویژهٔ امروز و ارسالِ رایگان برای همهٔ سفارش‌ها در تهران و کرج و شیراز", "at": 0.0, "duration": 2.0, "size": 7, "y": 0.9}
    img = frame([item], 1.0)
    bbox = mask(img, bright).getbbox()
    assert bbox[0] > 2 and bbox[2] < 238 and bbox[3] < 424, "a bottom caption that wraps must not hang off the frame"
    assert bbox[3] - bbox[1] > 60, "several lines"


# ------------------------------------------------------------------ animation

def test_animations_change_the_picture_over_time():
    def clip(kind, **kw):
        return {"text": "تخفیف ۵۰٪ NMarketing", "at": 1.0, "duration": 3.0, "size": 7, "x": 0.5, "y": 0.5, "anim_in": kind, "anim_dur": 1.0, **kw}

    def inked(item, t):
        return count(frame([item], t), bright)

    fade = clip("fade")
    assert inked(fade, 1.05) < inked(fade, 2.5) * 0.35, "fade: transparent at the start, solid after"
    pop = clip("pop")
    assert inked(pop, 1.05) < inked(pop, 2.5) * 0.6, "pop: starts small, ends at full size"
    assert inked(clip("zoom"), 2.5) > 100
    tw = clip("typewriter")
    counts = [inked(tw, t) for t in (1.15, 1.6, 2.3)]
    assert counts[0] < counts[1] < counts[2], "typewriter: the ink grows with time"
    cy = lambda item, t: centroid(frame([item], t), ink)[1]  # noqa: E731
    cx = lambda item, t: centroid(frame([item], t), ink)[0]  # noqa: E731
    assert cy(clip("slide_up"), 1.3) > cy(clip("slide_up"), 2.5) + 3, "slide_up enters from below"
    assert cy(clip("slide_down"), 1.3) < cy(clip("slide_down"), 2.5) - 3, "slide_down enters from above"
    assert cx(clip("slide_left"), 1.3) > cx(clip("slide_left"), 2.5) + 3, "slide_left enters from the right"
    assert cx(clip("slide_right"), 1.3) < cx(clip("slide_right"), 2.5) - 3, "slide_right enters from the left"
    assert inked(clip("blur"), 1.1) < inked(clip("blur"), 2.5)
    out = clip("none", anim_out="fade")
    assert inked(out, 2.5) > 100 and inked(out, 3.95) < inked(out, 2.5) * 0.3, "out animations: gone by the very end of the clip"
    assert inked(clip("none", anim_out="typewriter"), 3.9) < inked(clip("none", anim_out="typewriter"), 2.5) * 0.5


def test_hostile_text_renders_as_plain_characters():
    item = {"text": "x{\\fs300}B \\N {\\an9} ok", "at": 0.0, "duration": 2.0, "size": 6, "y": 0.5}
    bbox = mask(frame([item], 1.0), bright).getbbox()
    assert bbox and (bbox[3] - bbox[1]) < 426 * 0.3, "an injected \\fs300 would fill the frame; literal text stays a couple of lines tall"


def test_two_clips_do_not_interfere():
    a = {"text": "اول", "at": 0.0, "duration": 1.0, "y": 0.2, "size": 8}
    b = {"text": "دوم", "at": 2.0, "duration": 1.0, "y": 0.8, "size": 8}
    assert centroid(frame([a, b], 0.5), bright)[1] < 426 * 0.35 and centroid(frame([a, b], 2.5), bright)[1] > 426 * 0.65
    assert count(frame([a, b], 1.5), bright) == 0


# ------------------------------------------------------------------ the seven presets, both frame shapes

@pytest.mark.parametrize("shape", ["vertical", "landscape"])
@pytest.mark.parametrize("preset", captions.NEW_PRESETS)
def test_each_preset_draws_inside_the_safe_zone_with_no_stray_braces(preset, shape, tmp_path):
    r = captions_check.check_preset(preset, tmp_path, shape=shape, look=LOOK_CHAGHER)
    assert r["ok"], r
    assert r["ink"] > 200 and r["inside"] and r["braces"] and r["contrast"]["text"] >= 4.5


@pytest.mark.parametrize("preset", captions.NEW_PRESETS)
def test_english_captions_draw_too(preset, tmp_path):
    assert captions_check.check_preset(preset, tmp_path, language="en", look=LOOK_CHAGHER)["ok"]


@pytest.mark.parametrize("zone", list(safezones.ZONES))
def test_the_captions_stay_inside_every_platforms_zone(zone, tmp_path):
    shape = "landscape" if zone in ("youtube", "telegram", "aparat") else "vertical"
    for preset in ("pop", "box", "lower"):
        r = captions_check.check_preset(preset, tmp_path / preset, shape=shape, zone=zone, look=LOOK_CHAGHER)
        assert r["ok"] and r["zone"] == zone, r


def test_a_light_series_look_still_gives_readable_letters(tmp_path):
    """On a pale look the engine does not paint white on cream: the surface behind the letters is dark and the letters pass 4.5:1."""
    for preset in captions.NEW_PRESETS:
        st = captions.resolve_style(preset, LIGHT_LOOK)
        assert contrast.contrast(st["color"], st["surface"]) >= 4.5 and contrast.contrast(st["hl_color"], st["surface"]) >= 4.5, preset
        assert captions_check.check_preset(preset, tmp_path / preset, look=LIGHT_LOOK)["ok"], preset


@pytest.mark.parametrize("look", [LOOK_CHAGHER, LIGHT_LOOK])
@pytest.mark.parametrize("preset", ["box", "lower"])
def test_a_translucent_box_over_a_pure_white_picture_still_gives_the_letters_their_contrast(preset, look, tmp_path):
    """Measured on the picture, in the worst case (a white frame under a see-through box): the box fill the viewer sees against the plain words is >= 4.5:1."""
    st = captions.resolve_style(preset, look)
    plan = captions.plan([{"text": "قهوه تازه امروز", "start": 0.0, "duration": 1.0}], {"preset": preset, "mode": "burned"}, 360, 640, look=look)
    d = tmp_path
    (d / "sub.ass").write_text(plan["ass"], encoding="utf-8")
    (d / "fonts").mkdir()
    for f in titles_ass.FONTS_DIR.glob("*.ttf"):
        shutil.copyfile(f, d / "fonts" / f.name)
    ffmpeg.run(["-f", "lavfi", "-i", "color=c=#FFFFFF:s=360x640:d=1.5:r=25", "-ss", "1.0", "-vf", titles_ass.ass_filter(), "-frames:v", "1", str(d / "o.png")], cwd=d, timeout=60)
    img = Image.open(d / "o.png").convert("RGB")
    box = ImageChops.difference(img, Image.new("RGB", img.size, (255, 255, 255))).convert("L").point(lambda v: 255 if v > 30 else 0).getbbox()
    assert box, "the box is drawn on a white frame"
    colors = sorted(img.crop(box).getcolors(maxcolors=100000), reverse=True)
    fill = next(c for n, c in colors if min(c) < 240 and abs(c[0] - c[1]) < 80 or min(c) < 200)          # the most common colour of the box area that is not the white of the frame
    fill_hex = "#%02X%02X%02X" % fill
    assert contrast.contrast(st["color"], fill_hex) >= 4.5, (preset, fill_hex, st["color"], st["box_opacity"])
    assert st["contrast"]["worst_text"] >= 4.5 and st["contrast"]["worst_highlight"] >= 4.5


# ------------------------------------------------------------------ a real sentence, every word state, the number of lines

CHAGHER_FA = ["چغر؛ دستیار هوش مصنوعیِ مربی‌ها. برنامهٔ ورزشی و غذاییِ هر ورزشکار را پیش‌نویس می‌کند.", "تصمیمِ نهایی همیشه با مربی است."]
CHAGHER_EN = ["Chagher is an AI assistant for coaches. It drafts each athlete's training and meal plan.", "The final decision always stays with the coach."]


@pytest.mark.parametrize("language,texts", [("fa", CHAGHER_FA), ("en", CHAGHER_EN)])
@pytest.mark.parametrize("preset", captions.NEW_PRESETS)
def test_no_word_state_of_a_real_sentence_draws_more_lines_than_the_preset_allows(preset, language, texts):
    """Every caption line of a real two-sentence narration, at the moment each of its words is the spoken one (the swollen word, the marker around it, the thick edge all
    widen the line): libass never draws more lines than the preset allows, so the block never grows into the platform's buttons."""
    w, h = 540, 960
    segments, t = [], 0.2
    for text in texts:
        segments.append({"text": text, "start": t, "duration": 0.42 * len(text.split())})
        t += 0.42 * len(text.split()) + 0.4
    plan = captions.plan(segments, {"preset": preset, "mode": "burned"}, w, h, look=LOOK_CHAGHER, language=language)
    allowed = captions.PRESETS[preset]["lines"]
    checked = 0
    for clip in plan["clips"]:
        em = clip["size"] / 100 * h
        times = [clip["at"] + (x["s"] + x["e"]) / 2 for x in clip["words"]][:: max(1, len(clip["words"]) // 3)] or [clip["at"] + clip["duration"] / 2]
        for when in times:
            if when - clip["at"] < titles_ass.entrance_seconds(clip) + 0.05:
                continue                                              # still typing / popping in
            drawn = rows_of_ink(frame([clip], when, w, h), ink, int(0.3 * em))
            assert drawn <= allowed or len(clip["text"].split()) == 1, (preset, language, clip["text"], when, drawn, allowed)
            checked += 1
    assert checked >= 3


def test_the_spoken_word_of_the_brand_look_is_a_colour_not_a_grey(tmp_path):
    """The Chagher look (teal, navy, pale blue) rendered: the word being spoken is clearly another hue than the white words, measured on the picture."""
    seg = [{"text": "چغر دستیار هوش مصنوعیِ مربی‌ها است", "start": 0.0, "duration": 3.0}]
    plan = captions.plan(seg, {"preset": "clean", "mode": "burned"}, 360, 640, look=LOOK_CHAGHER_BRAND)
    hl = plan["info"]["colors"]["highlight"]
    clip = plan["clips"][0]
    when = clip["at"] + (clip["words"][1]["s"] + clip["words"][1]["e"]) / 2
    img = frame([clip], when, 360, 640)
    assert count(img, near(hl, 30)) > 60, (hl, "the highlight colour is on the frame")
    assert count(img, bright) > 60 and contrast.chroma(hl) >= 0.3
