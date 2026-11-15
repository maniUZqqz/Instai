"""Word-by-word captions, the engine without ffmpeg: the cleaner, the ASS writer (and that typed text can never inject tags), karaoke slices, estimated versus real
word times, grouping into screen lines, the seven presets with the series look and the contrast rule, the safe zones, the soft .srt copy and the config rules.

Ported with their intent from NMarketing's tests_titles / tests_captions / tests_subtitles (v3.02, c23f861) and adapted to InstAI's engine; the real-libass checks are in
tests/test_captions_render.py."""
from __future__ import annotations

import random
import re
import struct

import pytest

from instai.render import captions, contrast, safezones, srt, titles_ass

FA = "قهوهٔ تازه با تخفیفِ ویژهٔ امروز و ارسالِ رایگان برای همهٔ سفارش‌ها"
LOOK_CHAGHER = {"palette": {"background": "#0B1F3A", "primary": "#126F85", "secondary": "#163F75", "accent": "#FFB703", "shadow": "#05070A", "highlight": "#F3E9D8"},
                "typography": {"title_weight": "bold", "subtitle_color": "#FFFFFF"}}


def words(texts, step=0.4, dur=0.3, t0=0.0):
    return [{"w": w, "s": round(t0 + i * step, 3), "e": round(t0 + i * step + dur, 3)} for i, w in enumerate(texts)]


def dialogues(ass: str) -> list[str]:
    return [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]


# ------------------------------------------------------------------ the cleaner

def test_a_bare_clip_gets_every_key_with_the_default_look():
    d = titles_ass.clean({"text": "سلام", "at": 1, "duration": 2})
    assert (d["color"], d["box"], d["size"], d["font"], d["bold"]) == ("#FFFFFF", False, 6.0, "vazir", True)
    assert (d["x"], d["y"], d["position"], d["align"], d["words"]) == (0.5, 0.86, "bottom", "center", [])
    assert (d["stroke"], d["shadow"], d["anim_in"], d["anim_out"], d["hl_mode"], d["direction"]) == (0.0, 0.0, "none", "none", "color", "auto")
    assert titles_ass.clean(d) == d, "cleaning a cleaned clip changes nothing"


def test_values_are_clamped_and_bad_values_fall_back():
    d = titles_ass.clean({"text": "x", "size": 99, "duration": -5, "stroke": 500, "opacity": 0, "scale": 99, "color": "red", "stroke_color": "#abc", "font": "comic",
                          "anim_in": "explode", "align": "diagonal", "hl_mode": "x", "box_opacity": 7, "direction": "up"})
    assert (d["size"], d["duration"], d["stroke"], d["opacity"], d["scale"]) == (30.0, 0.1, 100.0, 0.05, 4.0)
    assert (d["color"], d["stroke_color"], d["font"], d["anim_in"], d["align"], d["hl_mode"], d["box_opacity"], d["direction"]) == \
           ("#FFFFFF", "#AABBCC", "vazir", "none", "center", "color", 1.0, "auto")
    assert titles_ass.clean({"text": "x", "size": float("nan")})["size"] == 6.0


def test_an_empty_text_is_refused_and_the_text_is_sanitised():
    for bad in ("   ", "", None):
        with pytest.raises(titles_ass.CaptionError):
            titles_ass.clean({"text": bad})
    with pytest.raises(titles_ass.CaptionError):
        titles_ass.clean("not a dict")
    d = titles_ass.clean({"text": "a\x00b\r\nc\td" + "x" * 900})
    assert "\x00" not in d["text"] and "ab\nc d" in d["text"] and len(d["text"]) == titles_ass.MAX_TEXT


def test_words_are_cleaned_sorted_and_clamped_to_the_clip():
    d = titles_ass.clean({"text": "a b c", "duration": 2, "words": [{"w": "b", "s": 1.0, "e": 1.4}, {"w": "a", "s": 0.0, "e": 0.9}, {"w": "", "s": 1, "e": 2},
                                                                   {"word": "c", "start": 1.5, "end": 9}, {"w": "bad"}, "junk"]})
    assert [w["w"] for w in d["words"]] == ["a", "b", "c"] and d["words"][2] == {"w": "c", "s": 1.5, "e": 2.0}


def test_rtl_detection_follows_the_first_strong_letter():
    assert titles_ass.is_rtl("سلام Hello") and not titles_ass.is_rtl("Hello سلام") and not titles_ass.is_rtl("۱۲۳ 456")


# ------------------------------------------------------------------ the ASS writer

def test_document_shape_timing_and_the_play_resolution_is_the_render_size():
    ass = titles_ass.build_ass([{"text": "سلام", "at": 2.0, "duration": 3.0}, {"text": "بعدی", "at": 6.0, "duration": 1.0}], 540, 960)
    assert "PlayResX: 540" in ass and "PlayResY: 960" in ass and "ScaledBorderAndShadow: yes" in ass
    d = dialogues(ass)
    assert d[0].split(",")[1].startswith("0:00:02.00") and any(",0:00:05.00," in x for x in d) and d[-1].split(",")[1].startswith("0:00:06.00")


def test_typed_text_cannot_inject_ass_tags():
    ass = titles_ass.build_ass([{"text": "a{\\fs300}B\\Nc{x}\n{\\an9}z", "at": 0, "duration": 2}], 540, 960)
    body = "\n".join(dialogues(ass))
    assert "{\\fs300}" not in body and "{\\an9}" not in body and "\\{" in body and "\\}" in body
    assert "B\\Nc" not in body and "\\​Nc" in body, "a typed backslash-N is broken by a zero-width space; only our own line break is a real \\N"
    from instai.render import captions_check

    assert captions_check.braces_clean(ass) and captions_check.injection_ok()


def test_the_same_style_is_the_same_picture_at_any_size():
    def fontsize(h):
        ass = titles_ass.build_ass([{"text": "x", "at": 0, "duration": 1, "size": 6}], h * 9 // 16, h)
        return float(next(ln for ln in ass.splitlines() if ln.startswith("Style: T0")).split(",")[2])

    assert fontsize(1920) / fontsize(960) == pytest.approx(2.0, abs=0.01)
    assert fontsize(1000) == pytest.approx(0.06 * 1000 * titles_ass.FONTS["vazir"]["line"], abs=0.05), "ASS Fontsize is the LINE height: em x the measured line ratio"


def test_the_ass_filter_uses_relative_names_so_a_windows_path_cannot_break_the_graph():
    f = titles_ass.ass_filter()
    assert f == "ass=sub.ass:fontsdir=fonts" and "/" not in f and "\\" not in f


@pytest.mark.parametrize("anim", titles_ass.ANIMATIONS_IN)
@pytest.mark.parametrize("hl", titles_ass.HL_MODES)
def test_every_animation_and_highlight_mode_builds(anim, hl):
    clip = {"text": "قهوه تازه امروز", "at": 0, "duration": 3, "anim_in": anim, "anim_out": anim, "hl_mode": hl, "box": hl == "box",
            "words": words(["قهوه", "تازه", "امروز"], step=0.9, dur=0.8)}
    ass = titles_ass.build_ass([clip], 360, 640)
    assert ass.count("Dialogue:") >= 3 and "nan" not in ass.lower().replace("sans", "") and "inf" not in ass.lower().replace("info", "")


def test_karaoke_marks_each_word_once_in_reading_order_and_the_slices_tile_the_clip():
    clip = {"text": "یک دو سه", "at": 0, "duration": 3.0, "hl_color": "#FF0000", "color": "#FFFFFF", "stroke": 0,
            "words": [{"w": "یک", "s": 0.0, "e": 0.8}, {"w": "دو", "s": 1.0, "e": 1.8}, {"w": "سه", "s": 2.0, "e": 2.8}]}
    ass = titles_ass.build_ass([clip], 360, 640)
    rows = [d.split(",", 9) for d in dialogues(ass)]
    seen = []
    for r in rows:
        m = re.findall(r"\{\\1c&H0000FF&\}([^{]+)\{\\1c&HFFFFFF&\}", r[9])      # the highlight colour (red, BGR) wraps exactly the active word
        seen += m
    assert seen == ["یک", "دو", "سه"], seen
    starts, ends = [r[1] for r in rows], [r[2] for r in rows]
    assert starts[0] == "0:00:00.00" and ends[-1] == "0:00:03.00" and all(e == s for e, s in zip(ends, starts[1:])), "the slices follow one another with no gap"


def test_a_clip_that_is_not_word_timed_has_no_highlight_and_one_dialogue():
    ass = titles_ass.build_ass([{"text": "یک دو سه", "at": 0, "duration": 3.0}], 360, 640)
    assert len(dialogues(ass)) == 1


def test_the_box_is_a_layer_under_the_text():
    ass = titles_ass.build_ass([{"text": "سلام", "at": 0, "duration": 2, "box": True, "box_color": "#112233", "box_opacity": 1.0}], 360, 640)
    d = dialogues(ass)
    assert len(d) == 2 and d[0].startswith("Dialogue: 0,") and d[1].startswith("Dialogue: 1,") and "&H332211&" in d[0]


def test_the_box_layer_leaves_out_the_marks_under_the_baseline_but_the_text_keeps_them():
    """A kasra at the end of a line pulls a stub out of the bottom of the box (the box is the outline of the glyphs; seen on a real 1080x1920 frame). The box layer is drawn without such marks."""
    kasra = chr(0x0650)
    text = "هوش مصنوعی" + kasra
    ass = titles_ass.build_ass([{"text": text, "at": 0, "duration": 2, "box": True, "box_color": "#112233", "box_opacity": 1.0}], 360, 640)
    d = dialogues(ass)
    assert kasra not in d[0] and kasra in d[1], "box layer without the mark, text layer with it"
    assert all(chr(c) not in d[0] for c in (0x064D, 0x0655, 0x0656, 0x065F))
    plain = titles_ass.build_ass([{"text": "هوش مصنوعی", "at": 0, "duration": 2, "box": True}], 360, 640)
    assert dialogues(plain)[0].split("}")[-1] == d[0].split("}")[-1], "the box text is the same letters either way (the mark is zero width, the lines do not move)"


def test_a_long_text_is_wrapped_inside_the_frame_and_the_block_is_pulled_in():
    clip = titles_ass.clean({"text": FA, "size": 7, "y": 0.97, "region": 0.8})
    g = titles_ass.geometry(clip, 1080, 1920)
    assert g["lines"] >= 3 and g["y"] + g["block_h"] / 2 <= 1920 and g["left"] >= 0 and g["right"] <= 1080
    assert g["y"] < 0.97 * 1920, "a bottom caption that wraps to several lines is pulled up, it does not hang off the frame"


# ------------------------------------------------------------------ fonts

def _name_table(path) -> dict[int, str]:
    b = path.read_bytes()
    n = struct.unpack(">H", b[4:6])[0]
    tables = {b[12 + 16 * i:16 + 16 * i].decode(): struct.unpack(">II", b[20 + 16 * i:28 + 16 * i]) for i in range(n)}
    off = tables["name"][0]
    count, store = struct.unpack(">HH", b[off + 2:off + 6])
    out = {}
    for i in range(count):
        pid, _, _, nid, ln, o = struct.unpack(">HHHHHH", b[off + 6 + 12 * i:off + 18 + 12 * i])
        if pid == 3:
            out[nid] = b[off + store + o:off + store + o + ln].decode("utf-16-be")
    return out


def test_the_fonts_are_bundled_with_their_licence_and_libass_finds_them_by_their_family():
    fonts = titles_ass.FONTS_DIR
    assert (fonts / "OFL.txt").is_file() and "SIL OPEN FONT LICENSE" in (fonts / "OFL.txt").read_text(encoding="utf-8", errors="replace").upper()
    assert set(titles_ass.FONT_FILES) == {"Vazirmatn-Regular.ttf", "Vazirmatn-Bold.ttf", "Vazirmatn-Black.ttf", "Vazirmatn-Light.ttf"}
    for key, f in titles_ass.FONTS.items():
        for fname in (f["file"], f["bold_file"]):
            assert (fonts / fname).is_file(), f"{key}: {fname}"
        names = _name_table(fonts / f["file"])
        assert names[1] == f["family"], f"{key}: libass resolves the family from the font's own name table ({names[1]!r} vs {f['family']!r})"
        assert f["fa"] and f["en"]
    assert {k for k in titles_ass.FONTS} >= {"vazir", "vazir_black", "vazir_light"}, "NM's font keys keep working"


# ------------------------------------------------------------------ word times: estimated or real

def test_estimated_words_cover_the_narration_in_reading_order_and_breathe_at_full_stops():
    text = "این یک جمله است. جملهٔ دوم کمی بلندتر از اولی است، و تمام می‌شود."
    w = captions.estimated_words(text, 2.0, 8.0)
    assert [x["w"] for x in w] == text.split()
    assert w[0]["s"] == 2.0 and w[-1]["e"] == pytest.approx(10.0, abs=0.01), "from the start of the audio to its end"
    assert all(a["e"] <= b["s"] + 1e-6 for a, b in zip(w, w[1:])) and all(x["e"] > x["s"] for x in w)
    gap = w[4]["s"] - w[3]["e"]                      # after "است." the narration pauses
    assert gap > 0.1 and w[1]["s"] - w[0]["e"] < 1e-6
    assert captions.estimated_words("", 0, 3) == [] and captions.estimated_words("a", 0, 0) == []
    longer = captions.estimated_words("کوتاه خیلی‌خیلی‌بلندتر", 0, 3.0)
    assert (longer[1]["e"] - longer[1]["s"]) > (longer[0]["e"] - longer[0]["s"]), "a longer word gets more time"


def test_without_a_recogniser_the_times_are_flagged_as_estimated():
    w, info = captions.shot_words("یک دو سه چهار", 1.0, 4.0)
    assert info == {"estimated": True, "words": 4, "aligned": 0} and len(w) == 4


def test_real_word_times_are_laid_on_our_spelling_and_the_flag_clears_when_all_match():
    text = "سلام به همهٔ شما دوستان"
    heard = [{"w": "سلام", "s": 0.1, "e": 0.5}, {"w": "به", "s": 0.55, "e": 0.7}, {"w": "همه", "s": 0.8, "e": 1.2}, {"w": "شما", "s": 1.3, "e": 1.6},
             {"w": "دوستان", "s": 1.7, "e": 2.3}]
    w, info = captions.shot_words(text, 5.0, 2.5, heard)
    assert [x["w"] for x in w] == text.split(), "the screen shows OUR text, never the recogniser's mistakes"
    assert w[0]["s"] == 5.1 and w[-1]["e"] == 7.3 and info["estimated"] is False and info["aligned"] == 5
    off = [dict(h, w=h["w"] + "ی") if h["w"] == "شما" else h for h in heard]
    w2, info2 = captions.shot_words(text, 0.0, 2.5, off)
    assert [x["w"] for x in w2] == text.split() and info2["estimated"] is True and info2["aligned"] == 4, "one unmatched word: its time is filled in, the flag stays"
    assert w2[3]["s"] >= w2[2]["e"] - 1e-6 and w2[3]["e"] <= w2[4]["s"] + 1e-6


def test_recogniser_junk_falls_back_to_estimates():
    for junk in ([{"w": "کاملا", "s": 0, "e": 1}], [{"nope": 1}], ["x"], [], None):
        w, info = captions.shot_words("یک دو سه", 0.0, 3.0, junk)
        assert len(w) == 3 and info["estimated"] is True and w[0]["s"] >= 0


# ------------------------------------------------------------------ grouping and clips

def test_a_long_gap_a_sentence_end_and_the_limits_start_new_lines():
    ws = words(["a", "b", "c"]) + words(["d", "e"], t0=5.0)
    assert [g["text"] for g in captions.group_words(ws)] == ["a b c", "d e"]
    assert [g["text"] for g in captions.group_words(words(["سلام.", "دنیا", "خوبی؟", "من"]))] == ["سلام.", "دنیا خوبی؟", "من"]
    many = words([f"w{i}" for i in range(15)], step=0.2, dur=0.15)
    assert [len(g["words"]) for g in captions.group_words(many, max_words=5)] == [5, 5, 5]
    for g in captions.group_words(words(["قهوهٔ", "تازه", "با", "تخفیفِ", "ویژهٔ", "امروز", "برای", "شما"], step=0.3, dur=0.25), max_chars=20):
        assert len(g["text"]) <= 20
    assert len(captions.group_words(words(list("abcdef"), step=1.2, dur=1.0), max_dur=3.0, max_gap=2)) > 1
    assert [g["text"] for g in captions.group_words(words(list("abcdef")), fits=lambda t: len(t.split()) <= 2)] == ["a b", "c d", "e f"]


def test_groups_keep_every_word_with_absolute_times():
    ws = words([f"w{i}" for i in range(12)], step=0.35, dur=0.3, t0=2.0)
    groups = captions.group_words(ws)
    assert [w["w"] for g in groups for w in g["words"]] == [w["w"] for w in ws] and groups[0]["s"] == 2.0 and groups[-1]["e"] == ws[-1]["e"]


def _clips(zone="reels", w=1080, h=1920, preset="pop", **kw):
    style = captions.resolve_style(preset, LOOK_CHAGHER)
    ws = words(["قهوه", "تازه", "امروز"], t0=1.0) + words(["تخفیف", "ویژه"], t0=6.0)
    return captions.caption_clips(captions.group_words(ws), style, w, h, zone=zone, **kw)


def test_clips_carry_word_timing_relative_to_the_clip_and_never_overlap():
    clips = _clips()
    assert len(clips) == 2 and clips[0]["at"] == 1.0 and clips[0]["text"] == "قهوه تازه امروز" and clips[0]["words"][0]["s"] == 0.0
    assert clips[0]["words"][2]["s"] == pytest.approx(0.8, abs=0.001) and clips[0]["duration"] >= clips[0]["words"][-1]["e"]
    assert clips[0]["at"] + clips[0]["duration"] <= clips[1]["at"] + 1e-6 and all(c["duration"] >= 0.3 for c in clips)
    assert titles_ass.clean(clips[0])["text"] == clips[0]["text"]
    tight = captions.caption_clips([{"text": "a", "s": 0.0, "e": 0.1, "words": words(["a"])}, {"text": "b", "s": 0.12, "e": 0.22, "words": words(["b"])}],
                                   captions.resolve_style("clean", None), 360, 640, zone="feed")
    assert tight[0]["at"] + tight[0]["duration"] <= tight[1]["at"] + 0.2


@pytest.mark.parametrize("zone", [z for z in safezones.ZONES])
def test_a_clip_is_placed_inside_the_safe_zone_of_its_platform(zone):
    w, h = (1920, 1080) if zone in ("youtube", "telegram", "aparat") else (1080, 1920)
    m = safezones.margins(zone)
    for preset in captions.NEW_PRESETS:
        for c in _clips(zone, w, h, preset):
            g = titles_ass.geometry(titles_ass.clean(c), w, h)
            assert g["left"] >= m["left"] * w - 1 and g["right"] <= (1 - m["right"]) * w + 1, (zone, preset)
            assert g["y"] + g["block_h"] / 2 + g["pad"] <= (1 - m["bottom"]) * h + 2 and g["y"] - g["block_h"] / 2 - g["pad"] >= m["top"] * h - 2, (zone, preset)


def test_the_position_follows_the_page_top_middle_or_bottom():
    y = {pos: _clips(position=pos)[0]["y"] for pos in ("top", "middle", "bottom")}
    assert y["top"] < y["middle"] == 0.5 < y["bottom"]


# ------------------------------------------------------------------ the presets and the look

def test_all_seven_presets_and_the_classic_look_exist_with_both_languages():
    assert captions.NEW_PRESETS == ["pop", "box", "karaoke", "clean", "neon", "typewriter", "lower"] and captions.ORDER[0] == "classic" and len(captions.ORDER) == 8
    for k, p in captions.PRESETS.items():
        assert p["fa"] and p["en"] and p["hint_fa"] and p["hint_en"], k
        assert re.search("[؀-ۿ]", p["fa"]) and not re.search("[؀-ۿ]", p["en"] + p["hint_en"]), k
    cat = captions.catalogue()
    assert [p["key"] for p in cat["presets"]] == captions.ORDER and {m["key"] for m in cat["modes"]} == {"burned", "soft", "none"}
    assert cat["zones"][0]["key"] == "auto" and {z["key"] for z in cat["zones"]} == set(safezones.KEYS)
    with pytest.raises(ValueError):
        captions.resolve_style("classic")


def test_sizes_are_fractions_of_the_frame_and_the_presets_keep_their_character():
    p = captions.PRESETS
    assert all(0 < p[k]["size"] <= 9 for k in captions.NEW_PRESETS)
    assert p["pop"]["size"] > p["clean"]["size"] > p["lower"]["size"], "big and punchy > clean > quiet"
    assert p["box"]["box"] and p["lower"]["box"] and p["karaoke"]["hl_mode"] == "box" and p["neon"]["hl_mode"] == "scale" and p["typewriter"]["anim_in"] == "typewriter"
    assert not p["pop"]["box"] and p["pop"]["stroke"] > p["clean"]["stroke"], "pop has the thicker edge"


def _random_look(rng) -> dict:
    h = lambda: "#%02X%02X%02X" % (rng.randrange(256), rng.randrange(256), rng.randrange(256))  # noqa: E731
    return {"palette": {k: h() for k in captions.DEFAULT_PALETTE}, "typography": {"title_weight": rng.choice(["regular", "bold", "black"]), "subtitle_color": h()}}


EDGE_LOOKS = [None, {}, {"palette": "junk"}, LOOK_CHAGHER,
              {"palette": {k: "#FFFFFF" for k in captions.DEFAULT_PALETTE}}, {"palette": {k: "#000000" for k in captions.DEFAULT_PALETTE}},
              {"palette": {k: "#808080" for k in captions.DEFAULT_PALETTE}}, {"palette": {**captions.DEFAULT_PALETTE, "accent": "#FFFFFF", "highlight": "#FFFFFF"}},
              {"palette": {**captions.DEFAULT_PALETTE, "background": "#FFF8E1", "accent": "#FFE082"}, "typography": {"subtitle_color": "#FFFF00"}}]


@pytest.mark.parametrize("preset", captions.NEW_PRESETS)
def test_contrast_always_passes_for_any_series_look(preset):
    """The owner's rule: whatever the look, the plain words, the word being spoken and the letters on the marker read at 4.5:1 against their own surface."""
    rng = random.Random(7)
    for look in EDGE_LOOKS + [_random_look(rng) for _ in range(150)]:
        st = captions.resolve_style(preset, look)
        surface = st["surface"]
        assert contrast.contrast(st["color"], surface) >= contrast.TEXT_MIN, (preset, look, st["color"], surface)
        assert contrast.contrast(st["hl_color"], surface) >= contrast.TEXT_MIN, (preset, look, st["hl_color"], surface)
        assert st["contrast"]["text"] >= 4.5 and st["contrast"]["highlight"] >= 4.5
        if st["box"]:
            assert st["contrast"]["worst_text"] >= 4.5 and st["contrast"]["worst_highlight"] >= 4.5, (preset, look, "a see-through box over a pure white picture")
        if st["hl_mode"] == "box":
            assert contrast.contrast(st["hl_text"], st["hl_color"]) >= contrast.TEXT_MIN and st["contrast"]["marker"] >= 4.5, (preset, look)
        if preset != "lower":
            assert contrast.distance(st["hl_color"], st["color"]) >= 0.3, "the spoken word is clearly another colour than the plain words"
            assert contrast.chroma(st["hl_color"]) >= captions.MIN_CHROMA, (preset, look, st["hl_color"], "a highlight is a real colour, never a grey")
        else:
            assert st["hl_color"] == st["color"], "the quiet band never flashes"


def test_the_look_gives_the_colours_and_the_theme_typography_is_respected():
    st = captions.resolve_style("karaoke", LOOK_CHAGHER)
    assert st["hl_color"].upper() == "#FFB703" and st["color"] == "#FFFFFF"                  # the series' accent colour is the marker
    assert st["font"] == "vazir_black"
    light = {**LOOK_CHAGHER, "typography": {"title_weight": "regular", "subtitle_color": "#FFFF00"}}
    st2 = captions.resolve_style("karaoke", light)
    assert st2["font"] == "vazir" and st2["bold"] is True and st2["color"] == "#FFFF00", "title_weight 'regular' = one step lighter; a readable subtitle colour is kept"
    heavy = captions.resolve_style("clean", {**LOOK_CHAGHER, "typography": {"title_weight": "black"}})
    assert heavy["font"] == "vazir_black" and captions.resolve_style("clean", {"typography": {"title_weight": "regular"}})["font"] == "vazir", "weights move one step"
    assert captions.weight_font("black", "black") == ("vazir_black", False) and captions.weight_font("light", "regular") == ("vazir_light", False)
    other = captions.resolve_style("karaoke", {"palette": {**LOOK_CHAGHER["palette"], "accent": "#2ECC71"}})
    assert other["hl_color"].upper() == "#2ECC71", "another series, another highlight"


def test_english_captions_are_left_to_right_and_persian_right_to_left():
    assert captions.resolve_style("pop", None, language="en")["direction"] == "ltr" and captions.resolve_style("pop", None)["direction"] == "rtl"
    en = captions.plan([{"text": "This is how it reads", "start": 0.0, "duration": 2.0}], {"preset": "pop", "mode": "burned"}, 1080, 1920, language="en")
    fa = captions.plan([{"text": "این طور خوانده می‌شود", "start": 0.0, "duration": 2.0}], {"preset": "pop", "mode": "burned"}, 1080, 1920)
    assert titles_ass.LRM in "".join(dialogues(en["ass"])) and titles_ass.RLM not in "".join(dialogues(en["ass"]))
    assert titles_ass.RLM in "".join(dialogues(fa["ass"])), "a Persian line that starts with a number or a Latin word keeps its direction"


# ------------------------------------------------------------------ config

def test_the_config_falls_back_to_the_plain_look_and_an_episode_overrides_key_by_key():
    assert captions.normalize_config(None) == captions.DEFAULT_CONFIG == {"preset": "classic", "mode": "burned", "zone": "auto"}
    assert captions.normalize_config({"preset": "nope", "mode": 3, "zone": "mars"}) == captions.DEFAULT_CONFIG
    assert captions.normalize_config({"preset": "neon", "mode": "soft", "zone": "tiktok"}) == {"preset": "neon", "mode": "soft", "zone": "tiktok"}
    page = {"preset": "pop", "mode": "burned", "zone": "auto"}
    assert captions.merge_config(page, {"preset": "karaoke"}) == {"preset": "karaoke", "mode": "burned", "zone": "auto"}
    assert captions.merge_config(page, {}, {"preset": "", "mode": None}) == page and captions.merge_config(page, {"mode": "none"})["mode"] == "none"
    assert captions.is_default({}) and not captions.is_default({"preset": "pop"}) and not captions.is_default({"mode": "soft"})


def test_the_hash_changes_with_everything_that_changes_the_captions():
    base = captions.config_hash({"preset": "pop"}, LOOK_CHAGHER, "fa", "instagram", "bottom")
    assert base == captions.config_hash({"preset": "pop", "mode": "burned", "zone": "auto"}, LOOK_CHAGHER, "fa", "instagram", "bottom")
    for other in (captions.config_hash({"preset": "neon"}, LOOK_CHAGHER, "fa", "instagram", "bottom"), captions.config_hash({"preset": "pop"}, None, "fa", "instagram", "bottom"),
                  captions.config_hash({"preset": "pop"}, LOOK_CHAGHER, "en", "instagram", "bottom"), captions.config_hash({"preset": "pop"}, LOOK_CHAGHER, "fa", "tiktok", "bottom"),
                  captions.config_hash({"preset": "pop"}, LOOK_CHAGHER, "fa", "instagram", "top")):
        assert other != base


# ------------------------------------------------------------------ safe zones

def test_the_zone_follows_the_frame_shape_and_the_platform():
    z = safezones.zone_for
    assert z(1080, 1920, "instagram") == "reels" and z(1080, 1920, "tiktok") == "tiktok" and z(1080, 1920, "youtube") == "shorts"
    assert z(1080, 1920, "telegram") == "feed" and z(1080, 1920, "aparat") == "feed" and z(1080, 1920, "mars") == "reels"
    assert z(1080, 1350, "instagram") == "feed" and z(1080, 1080, "tiktok") == "feed"
    assert z(1920, 1080, "youtube") == "youtube" and z(1920, 1080, "telegram") == "telegram" and z(1920, 1080, "aparat") == "aparat" and z(1920, 1080, "instagram") == "youtube"
    assert z(1080, 1920, "instagram", "story") == "story" and z(1080, 1920, "instagram", "auto") == "reels"


def test_every_zone_has_hints_in_both_languages_and_vertical_zones_keep_the_button_column_clear():
    for k, v in safezones.ZONES.items():
        assert v["fa"] and v["en"] and v["hint_fa"] and v["hint_en"] and set(v["margins"]) == {"top", "bottom", "left", "right"}, k
        assert all(0 <= x < 0.3 for x in v["margins"].values()), k
    assert safezones.margins("tiktok")["right"] > safezones.margins("story")["right"] and safezones.margins("reels")["bottom"] >= 0.2
    assert safezones.margins("unknown") == safezones.margins("feed") and safezones.inside("reels", 0.5) and not safezones.inside("reels", 0.95)


# ------------------------------------------------------------------ the soft .srt copy

def test_srt_format_wrapping_and_the_bom():
    cues = srt.cues_from_groups([{"text": "سلام به همهٔ شما", "s": 1.0, "e": 3.5}, {"text": "این یک جملهٔ بلند است که باید روی دو خط شکسته شود و هیچ کلمه‌ای نصف نشود", "s": 4.0, "e": 8.0}])
    out = srt.to_srt(cues)
    assert out.startswith("1\n00:00:01,000 --> 00:00:04,000\nسلام")        # a gap shorter than a second is closed: the line does not blink between two sentences and "\n\n2\n00:00:04,000 --> 00:00:08,000\n" in out
    assert all(len(line) <= srt.MAX_LINE + 12 and len(c.text.split("\n")) <= 2 for c in cues for line in c.text.split("\n"))
    assert [c.index for c in cues] == [1, 2]


def test_short_cues_are_merged_and_long_ones_capped_and_a_short_gap_is_closed(tmp_path):
    cues = srt.cues_from_groups([{"text": "یک", "s": 0.0, "e": 0.3}, {"text": "دو", "s": 0.3, "e": 0.6}, {"text": "سه چهار پنج", "s": 0.6, "e": 3.0},
                                 {"text": "شش", "s": 3.5, "e": 4.5}, {"text": "هفت", "s": 9.0, "e": 20.0}])
    assert cues[0].text.replace("\n", " ").startswith("یک دو") and all(c.seconds >= srt.MIN_CUE for c in cues[:-1]) and all(c.seconds <= srt.MAX_CUE for c in cues)
    p = srt.write_srt(cues, tmp_path / "x" / "e.srt")
    assert p.read_bytes().startswith(b"\xef\xbb\xbf"), "UTF-8 with a BOM: a Persian subtitle guessed as cp1256 is mojibake"
    assert srt.cues_from_groups([]) == [] and srt.tidy([]) == []


def test_a_cue_never_flashes_even_as_the_only_one():
    only = srt.cues_from_groups([{"text": "سلام", "s": 2.0, "e": 2.2}])
    assert len(only) == 1 and only[0].seconds >= srt.MIN_CUE - 1e-6


# ------------------------------------------------------------------ the plan of a whole timeline

SEGS = [{"text": "این قسمت اول است و کلمه به کلمه نشان داده می‌شود.", "start": 0.15, "duration": 4.0},
        {"text": "قسمت دوم هم کمی بعد می‌آید؛ بی هیچ اشتباهی.", "start": 5.0, "duration": 3.5}]


def test_the_modes_decide_what_is_made_burned_soft_none_and_classic():
    pop = captions.plan(SEGS, {"preset": "pop", "mode": "burned"}, 1080, 1920, look=LOOK_CHAGHER)
    assert pop["ass"] and pop["srt"] and pop["cues"] == len(pop["clips"]) >= 4 and pop["info"]["zone"] == "reels"
    soft = captions.plan(SEGS, {"preset": "pop", "mode": "soft"}, 1080, 1920, look=LOOK_CHAGHER)
    assert soft["ass"] is None and soft["srt"] and soft["clips"] == [], "soft: the picture stays clean, the words travel as a file"
    none = captions.plan(SEGS, {"preset": "pop", "mode": "none"}, 1080, 1920)
    assert none["ass"] is None and none["srt"] is None and none["cues"] == 0
    classic = captions.plan(SEGS, captions.DEFAULT_CONFIG, 1080, 1920)
    assert classic["ass"] is None and classic["srt"], "classic: InstAI's own subtitle burns; only the soft copy is new"
    assert captions.plan([], {"preset": "pop"}, 1080, 1920)["ass"] is None and captions.plan([{"text": "  ", "start": 0, "duration": 2}], {"preset": "pop"}, 1080, 1920)["srt"] is None


def test_the_result_says_honestly_that_the_word_times_are_estimates():
    p = captions.plan(SEGS, {"preset": "karaoke", "mode": "burned"}, 1080, 1920, look=LOOK_CHAGHER)
    assert p["info"]["estimated"] is True and p["info"]["words"] == sum(len(s["text"].split()) for s in SEGS) and p["info"]["aligned"] == 0 and p["info"]["segments"] == 2
    assert p["info"]["contrast"]["text"] >= 4.5 and p["info"]["colors"]["highlight"].upper() == "#FFB703"
    heard = [dict(s, heard=[{"w": w, "s": 0.2 * i, "e": 0.2 * i + 0.15} for i, w in enumerate(s["text"].split())]) for s in SEGS]
    real = captions.plan(heard, {"preset": "karaoke", "mode": "burned"}, 1080, 1920, look=LOOK_CHAGHER)
    assert real["info"]["estimated"] is False and real["info"]["aligned"] == real["info"]["words"]


def test_a_preset_follows_the_frame_shape_not_the_pixels():
    v = captions.plan(SEGS, {"preset": "pop", "mode": "burned"}, 1080, 1920)
    land = captions.plan(SEGS, {"preset": "pop", "mode": "burned"}, 1920, 1080)
    assert "PlayResX: 1080" in v["ass"] and "PlayResX: 1920" in land["ass"] and land["info"]["zone"] == "youtube" and len(land["clips"]) <= len(v["clips"]), "a wide frame fits more words per line"
    sq = captions.plan(SEGS, {"preset": "pop", "mode": "burned"}, 1080, 1080, platform="tiktok")
    assert sq["info"]["zone"] == "feed"
    tg = captions.plan(SEGS, {"preset": "pop", "mode": "burned"}, 1920, 1080, platform="telegram")
    assert tg["info"]["zone"] == "telegram"


def test_no_clip_has_more_lines_than_the_preset_allows():
    long = [{"text": FA + " " + FA + " " + FA, "start": 0.0, "duration": 12.0}]
    for preset in captions.NEW_PRESETS:
        for w, h in ((1080, 1920), (1920, 1080), (1080, 1080)):
            p = captions.plan(long, {"preset": preset, "mode": "burned"}, w, h, look=LOOK_CHAGHER)
            allowed = captions.PRESETS[preset]["lines"]
            for c in p["clips"]:
                g = titles_ass.geometry(titles_ass.clean(c), w, h)
                assert g["lines"] <= allowed or len(c["text"].split()) == 1, (preset, w, h, c["text"], g["lines"])


# ------------------------------------------------------------------ the audible part of a narration file

def _wav(path, parts, rate=16000, channels=1, width=2):
    """parts = [(seconds, amplitude 0..1)]: a sine of that loudness (0 = silence), written as PCM."""
    import math
    import struct
    import wave

    frames = bytearray()
    t = 0
    for secs, amp in parts:
        for _ in range(int(secs * rate)):
            v = int(32767 * amp * math.sin(2 * math.pi * 220 * t / rate)) if width == 2 else int(127 * amp * math.sin(2 * math.pi * 220 * t / rate)) + 128
            frames += struct.pack("<" + ("h" if width == 2 else "B"), v) * channels
            t += 1
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


def test_the_audible_span_skips_the_breath_before_and_the_tail_after(tmp_path):
    a, b = captions.speech_span(_wav(tmp_path / "a.wav", [(0.5, 0), (1.0, 0.4), (0.3, 0)]))
    assert 0.44 <= a <= 0.5 and 1.5 <= b <= 1.56, (a, b)
    a, b = captions.speech_span(_wav(tmp_path / "quiet.wav", [(0.25, 0), (0.8, 0.02), (0.2, 0)]))              # a quiet recording: the threshold is relative to its own loudest part
    assert 0.2 <= a <= 0.25 and 1.05 <= b <= 1.1, (a, b)
    a, b = captions.speech_span(_wav(tmp_path / "st.wav", [(0.3, 0), (0.7, 0.5), (0.4, 0)], channels=2))
    assert 0.25 <= a <= 0.3 and 0.98 <= b <= 1.04
    inner = captions.speech_span(_wav(tmp_path / "gap.wav", [(0.2, 0), (0.5, 0.4), (0.4, 0), (0.5, 0.4), (0.2, 0)]))
    assert inner[0] < 0.2 and inner[1] > 1.55, "a pause between two phrases is not a reason to cut the middle"


def test_a_file_that_cannot_be_trimmed_gives_none(tmp_path):
    assert captions.speech_span(_wav(tmp_path / "s.wav", [(1.0, 0)])) is None, "all silence"
    assert captions.speech_span(_wav(tmp_path / "u8.wav", [(1.0, 0.5)], width=1)) is None, "8-bit is not read"
    (tmp_path / "x.mp3").write_bytes(b"ID3" + b"\0" * 50)
    assert captions.speech_span(tmp_path / "x.mp3") is None and captions.speech_span(tmp_path / "missing.wav") is None and captions.speech_span("") is None


def test_the_estimate_is_spread_over_the_audible_part_and_the_result_says_so(tmp_path):
    from instai.render import assemble as asm

    wav = _wav(tmp_path / "n.wav", [(0.6, 0), (2.0, 0.4), (0.4, 0)])
    shot = asm.ShotSpec(key="a", duration=3.0, audio=str(wav), audio_duration=3.0, subtitle="این یک جملهٔ آزمایشی برای زیرنویس است")
    tl = asm.plan_timeline([shot])
    seg = asm.caption_segments([shot], tl)[0]
    assert seg["trimmed"] is True and seg["start"] == pytest.approx(tl[0]["audio_start"] + 0.58, abs=0.03) and seg["duration"] == pytest.approx(2.04, abs=0.06)
    plan = captions.plan([seg], {"preset": "pop", "mode": "burned"}, 1080, 1920)
    assert plan["info"]["trimmed"] == 1 and plan["info"]["estimated"] is True
    first, last = plan["clips"][0], plan["clips"][-1]
    assert first["at"] >= tl[0]["audio_start"] + 0.55, "the first word is not shown during the breath before the voice"
    assert last["at"] + last["words"][-1]["e"] <= tl[0]["audio_start"] + 0.6 + 2.0 + 0.15, "and the last word ends with the voice, not with the file"
    real = asm.ShotSpec(key="b", duration=3.0, audio=str(wav), audio_duration=3.0, subtitle="یک دو سه", words=[{"w": "یک", "s": 0.7, "e": 1.0}, {"w": "دو", "s": 1.1, "e": 1.5}, {"w": "سه", "s": 1.6, "e": 2.0}])
    seg2 = asm.caption_segments([real], asm.plan_timeline([real]))[0]
    assert seg2["trimmed"] is False and seg2["start"] == asm.plan_timeline([real])[0]["audio_start"], "real word times are relative to the start of the audio: never shifted"
    nofile = asm.ShotSpec(key="c", duration=3.0, subtitle="بدون صدا")
    assert asm.caption_segments([nofile], asm.plan_timeline([nofile]))[0]["trimmed"] is False


def test_the_two_text_shapers_measure_alike(monkeypatch):
    """The owner's Windows Pillow may lack libraqm: the line widths then come from InstAI's own shaper (fa_text) and must stay within 3 % of libraqm's, so the wrap
    estimate (which keeps a 5 % safety margin) holds on both."""
    from instai.render import fa_text

    texts = ["این یک آزمون", "چغر دستیار تمرین و تغذیه شماست", "قهوهٔ تازه با تخفیفِ ویژهٔ امروز", "۱۲۳ کلمه به کلمه", "زیرنویسِ آرام و ساده"]
    for font in ("vazir", "vazir_black", "vazir_light"):
        for text in texts:
            widths = []
            for raqm in (True, False):
                monkeypatch.setattr(fa_text, "RAQM_OK", raqm)
                titles_ass._pil_font.cache_clear()
                widths.append(titles_ass.text_width(text, 100, font, False))
            assert widths[1] / widths[0] == pytest.approx(1.0, abs=0.03), (font, text, widths)
    titles_ass._pil_font.cache_clear()


# ------------------------------------------------------------------ the highlight of a look without a vivid accent (the Chagher brand: teal, navy, pale blue)

BRAND_LOOK = {"palette": {"background": "#163F75", "primary": "#126F85", "secondary": "#1B2B45", "accent": "#DBE6FF", "shadow": "#05070A", "highlight": "#F7FAFF"},
              "typography": {"title_weight": "bold", "subtitle_color": "#FFFFFF"}}


def _hue(c: str) -> float:
    import colorsys

    r, g, b = (v / 255 for v in contrast.channels(c))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def test_a_pale_accent_is_not_the_highlight_the_brand_teal_is_brightened_instead():
    """The brand's accent (#DBE6FF) is a pale cousin of the white text and its secondary a dark grey-blue: the first version highlighted in a muddy grey (#AFB5BE). The highlight
    now keeps a hue of the look (the primary teal, brightened until it reads) and is a real colour."""
    for preset in ("pop", "box", "karaoke", "clean", "typewriter"):
        st = captions.resolve_style(preset, BRAND_LOOK)
        hl = st["hl_color"]
        assert contrast.chroma(hl) >= captions.MIN_CHROMA and contrast.distance(hl, st["color"]) >= 0.3 and contrast.contrast(hl, st["surface"]) >= 4.5, (preset, hl)
        assert abs(_hue(hl) - _hue("#126F85")) < 12, (preset, hl, "still the brand's teal")
    neon = captions.resolve_style("neon", BRAND_LOOK)
    assert contrast.chroma(neon["hl_color"]) >= captions.MIN_CHROMA and contrast.distance(neon["hl_color"], neon["color"]) >= 0.3


def test_a_look_with_only_greys_gets_a_signal_colour():
    grey = {"palette": {k: g for k, g in zip(captions.DEFAULT_PALETTE, ["#202020", "#606060", "#808080", "#B0B0B0", "#101010", "#E0E0E0"])}}
    st = captions.resolve_style("pop", grey)
    assert st["hl_color"] in captions.FALLBACK_HIGHLIGHTS


def test_vivid_on_keeps_the_hue_and_only_gives_what_reads():
    teal = contrast.vivid_on("#163F75", "#126F85")
    assert teal and contrast.contrast(teal, "#163F75") >= 4.5 and abs(_hue(teal) - _hue("#126F85")) < 5 and contrast.chroma(teal) > 0.3
    dark = contrast.vivid_on("#FFF8E1", "#FFB703")                        # on a light surface it goes darker, not lighter
    assert dark is None or (contrast.contrast(dark, "#FFF8E1") >= 4.5 and contrast.luminance(dark) < contrast.luminance("#FFB703"))
    assert contrast.vivid_on("#808080", "#FF0000", 21.0) is None
    assert contrast.chroma("#808080") == 0 and contrast.chroma("#FF0000") == 1.0


def test_the_wrap_budget_shrinks_with_the_outline_the_marker_and_the_swelling():
    base = titles_ass.wrap_budget(900, 100, 0.0, "color", True)
    assert base == pytest.approx(900 * titles_ass.WRAP_SAFETY)
    assert titles_ass.wrap_budget(900, 100, 14.0, "color", True) == pytest.approx(base - 28.0)
    assert titles_ass.wrap_budget(900, 100, 0.0, "box", True) == pytest.approx(base - 32.0) and titles_ass.wrap_budget(900, 100, 0.0, "box", False) == pytest.approx(base)
    assert titles_ass.wrap_budget(900, 100, 0.0, "scale", True) == pytest.approx(base * 0.95)
    assert titles_ass.wrap_budget(10, 100, 50.0, "box", True) == 20.0, "never below a sliver"


def test_the_preview_cache_never_grows_without_bound(tmp_path):
    import os

    from instai.render import caption_previews

    for i in range(12):
        f = tmp_path / f"{i:02d}.png"
        f.write_bytes(b"x")
        os.utime(f, (1000 + i, 1000 + i))
    (tmp_path / "keep.txt").write_text("not a picture")
    assert caption_previews.prune(tmp_path, keep=5) == 7
    left = sorted(p.name for p in tmp_path.glob("*"))
    assert left == ["07.png", "08.png", "09.png", "10.png", "11.png", "keep.txt"], "the newest five pictures stay; nothing but *.png is touched"
    assert caption_previews.prune(tmp_path / "missing", keep=5) == 0


def test_neon_is_lit_the_look_colour_at_8_to_1_while_the_others_stay_at_the_minimum():
    neon = captions.resolve_style("neon", BRAND_LOOK)
    assert neon["contrast"]["highlight"] >= 8.0 and abs(_hue(neon["hl_color"]) - _hue("#126F85")) < 12, "a bright teal, not a dull one"
    assert captions.resolve_style("neon", LOOK_CHAGHER)["hl_color"].upper() == "#FFB703", "an accent that already glows is kept exactly"
    assert contrast.vivid_on("#05070A", "#FFB703") == "#FFB703", "a colour that already reads is returned as it is, not re-computed"
