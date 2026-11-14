"""Persian on a cover is shaped identically whether libraqm works (Linux) or not (the owner's Windows Pillow has no FriBidi): the engine goes through ``instai.render.fa_text`` for the
second case. Every bundled font must be drawable by the built-in shaper (a font whose presentation-form glyphs are empty would draw nothing on that PC)."""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw, ImageFont

from instai.covers.engine import typo
from instai.render import fa_text

LINES = ["مربی چغر و رازِ کیفِ گم‌شده", "قسمت ۱: اولین تمرین", "ماجراهای چغر", "و ناگهان دَرِ باشگاه باز شد…", "برو توی باشگاه یا برو بیرون؟", "iPhone ۱۶ را ببینید 2026"]


def ink(text: str, key: str, weight: int, basic: bool, px: int = 80) -> Image.Image:
    path = typo.font_path(key, weight)
    with typo.basic_layout(basic):
        f = typo._font(path, px)
        rtl = typo.is_rtl(text)
        shaped = typo._shape(text, rtl)
        kw = typo._kw(rtl)
        im = Image.new("L", (int(f.getlength(shaped, **kw)) + 80, px * 2), 0)
        ImageDraw.Draw(im).text((40, px * 0.2), shaped, font=f, fill=255, **kw)
    return im.point(lambda v: 255 if v > 128 else 0)


def test_every_bundled_font_draws_every_persian_letter_form_with_the_builtin_shaper():
    """The shaped string of a pangram: no letter may come out as the empty box of a missing glyph or as nothing at all."""
    text = "ژاله پنجشنبه چگونه گل‌های زردِ کوچک را در باغ دید؟ ۱۲۳۴۵۶۷۸۹۰ لا"
    shaped = fa_text.shape(text)
    for key in typo.FONTS:
        for w in sorted(typo.FONTS[key]["files"]):
            path = typo.font_path(key, w)
            f = ImageFont.truetype(path, 64, layout_engine=ImageFont.Layout.BASIC)
            notdef = f.getmask("￿").getbbox(), f.getlength("￿")
            for ch in set(shaped) - {" "}:
                if ch in "‌‍":
                    continue
                m = f.getmask(ch)
                assert m.getbbox() is not None, (key, w, hex(ord(ch)), "draws nothing")
                assert not (m.getbbox() == notdef[0] and f.getlength(ch) == notdef[1]), (key, w, hex(ord(ch)), "is the empty-box glyph")


@pytest.mark.parametrize("key,weight", [("lalezar", 400), ("sahel", 800), ("sahel", 400), ("vazirmatn", 700)])
def test_the_builtin_shaper_draws_every_cover_line(key, weight):
    for line in LINES:
        im = ink(line, key, weight, basic=True)
        assert im.getbbox() is not None and im.histogram()[255] > 400, (key, line)


def test_a_zero_width_non_joiner_is_never_drawn_as_a_box():
    """"گم‌شده" in Lalezar (which has no glyph for the half-space): the built-in path drops it after shaping, so no empty box appears."""
    with typo.basic_layout():
        assert "‌" not in typo._shape("گم‌شده", True)
        f = typo._font(typo.font_path("lalezar", 400), 80)
        assert f.getlength(typo._shape("گم‌شده", True)) > f.getlength(typo._shape("گمشده", True)) * 0.9


@pytest.mark.skipif(not typo.HAS_RAQM, reason="libraqm + FriBidi are not on this machine (the built-in shaper is the only path here)")
@pytest.mark.parametrize("key,weight", [("lalezar", 400), ("sahel", 800), ("vazirmatn", 700)])
def test_raqm_and_the_builtin_shaper_draw_nearly_the_same_picture(key, weight):
    for line in LINES[:5]:
        a, b = ink(line, key, weight, basic=False), ink(line, key, weight, basic=True)
        ba, bb = a.getbbox(), b.getbbox()
        assert ba and bb, (key, line)
        wa, wb = ba[2] - ba[0], bb[2] - bb[0]
        assert abs(wa - wb) / wa < 0.08, (key, line, wa, wb)                  # the same line width
        ia, ib = a.histogram()[255], b.histogram()[255]
        assert abs(ia - ib) / ia < 0.12, (key, line, ia, ib)                  # the same amount of ink: the same letters joined the same way


def test_the_cover_title_is_the_same_with_both_shapers():
    """The whole engine, not just one line: the title box of a rendered cover has the same size in both layouts."""
    from instai.covers.engine import fixtures
    from instai.covers.engine import render as R
    from instai.covers.engine.styles import STYLES

    inp = R.Inputs(brand_colors=list(fixtures.CHAGHER_COLORS))
    inp.subject, inp.subject_is_cutout = fixtures.person(), True
    sp = R.clean_spec({"format": "youtube", "style": "episode_card", "lang": "fa", "content": fixtures.sample_content("fa")}, STYLES)
    a = R.render(sp, inp, scale=0.5)
    with typo.basic_layout():
        b = R.render(sp, inp, scale=0.5)
    ta = next(t for t in a.texts if t["name"] == "title")
    tb = next(t for t in b.texts if t["name"] == "title")
    wa, wb = ta["bbox"][2] - ta["bbox"][0], tb["bbox"][2] - tb["bbox"][0]
    assert abs(wa - wb) / max(wa, wb) < 0.12, (wa, wb)
    assert abs(ta["lines"] - tb["lines"]) <= 1
