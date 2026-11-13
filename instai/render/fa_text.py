"""Persian / Arabic-script text drawn with Pillow (posts, covers, model sheets, speech bubbles).

Why this exists: subtitles go through ffmpeg's libass (HarfBuzz + FriBidi), but a still picture is drawn with Pillow, and Pillow shapes
Persian only when libraqm (+ FriBidi) is present. That is true on Linux, but the Windows wheels need a separate fribidi DLL, so on the
owner's PC the letters would come out disconnected and reversed. `draw_text` therefore uses libraqm when it works and otherwise a small
built-in shaper (contextual forms from the Arabic Presentation Forms block + a simplified bidi reorder) that Vazirmatn can draw with
Pillow's basic layout. Both paths give the same picture for ordinary sentences (tests/test_stick.py compares them).

Public helpers: `shape`, `font`, `text_width`, `wrap`, `draw_text`, `draw_paragraph`, `digits_fa`.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

from PIL import ImageDraw, ImageFont, features

FONT_DIR = Path(__file__).parent / "fonts"
RTL_RANGE = re.compile(r"[֐-ࣿיִ-﷿ﹰ-﻿]")
HARAKAT = set("ًٌٍَُِّْٰٕٓٔ")

# letter -> (isolated, final, initial, medial); right-joining letters have only the first two
_FORMS: dict[str, tuple[str, ...]] = {
    "ء": ("ﺀ",),
    "آ": ("ﺁ", "ﺂ"), "أ": ("ﺃ", "ﺄ"), "ؤ": ("ﺅ", "ﺆ"), "إ": ("ﺇ", "ﺈ"),
    "ئ": ("ﺉ", "ﺊ", "ﺋ", "ﺌ"), "ا": ("ﺍ", "ﺎ"),
    "ب": ("ﺏ", "ﺐ", "ﺑ", "ﺒ"), "ة": ("ﺓ", "ﺔ"),
    "ت": ("ﺕ", "ﺖ", "ﺗ", "ﺘ"), "ث": ("ﺙ", "ﺚ", "ﺛ", "ﺜ"),
    "ج": ("ﺝ", "ﺞ", "ﺟ", "ﺠ"), "ح": ("ﺡ", "ﺢ", "ﺣ", "ﺤ"),
    "خ": ("ﺥ", "ﺦ", "ﺧ", "ﺨ"), "د": ("ﺩ", "ﺪ"), "ذ": ("ﺫ", "ﺬ"),
    "ر": ("ﺭ", "ﺮ"), "ز": ("ﺯ", "ﺰ"),
    "س": ("ﺱ", "ﺲ", "ﺳ", "ﺴ"), "ش": ("ﺵ", "ﺶ", "ﺷ", "ﺸ"),
    "ص": ("ﺹ", "ﺺ", "ﺻ", "ﺼ"), "ض": ("ﺽ", "ﺾ", "ﺿ", "ﻀ"),
    "ط": ("ﻁ", "ﻂ", "ﻃ", "ﻄ"), "ظ": ("ﻅ", "ﻆ", "ﻇ", "ﻈ"),
    "ع": ("ﻉ", "ﻊ", "ﻋ", "ﻌ"), "غ": ("ﻍ", "ﻎ", "ﻏ", "ﻐ"),
    "ف": ("ﻑ", "ﻒ", "ﻓ", "ﻔ"), "ق": ("ﻕ", "ﻖ", "ﻗ", "ﻘ"),
    "ك": ("ﻙ", "ﻚ", "ﻛ", "ﻜ"), "ل": ("ﻝ", "ﻞ", "ﻟ", "ﻠ"),
    "م": ("ﻡ", "ﻢ", "ﻣ", "ﻤ"), "ن": ("ﻥ", "ﻦ", "ﻧ", "ﻨ"),
    "ه": ("ﻩ", "ﻪ", "ﻫ", "ﻬ"), "و": ("ﻭ", "ﻮ"),
    "ى": ("ﻯ", "ﻰ"), "ي": ("ﻱ", "ﻲ", "ﻳ", "ﻴ"),
    "پ": ("ﭖ", "ﭗ", "ﭘ", "ﭙ"),                      # pe
    "چ": ("ﭺ", "ﭻ", "ﭼ", "ﭽ"),                      # che
    "ژ": ("ﮊ", "ﮋ"),                                           # zhe
    "ک": ("ﮎ", "ﮏ", "ﮐ", "ﮑ"),                      # keheh (Persian kaf)
    "گ": ("ﮒ", "ﮓ", "ﮔ", "ﮕ"),                      # gaf
    "ی": ("ﯼ", "ﯽ", "ﯾ", "ﯿ"),                      # Persian yeh
}
# lam + alef ligatures: alef variant -> (isolated, final)
_LAM_ALEF = {"ا": ("ﻻ", "ﻼ"), "آ": ("ﻵ", "ﻶ"), "أ": ("ﻷ", "ﻸ"), "إ": ("ﻹ", "ﻺ")}
_MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<", "«": "»", "»": "«"}
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_PRES = {v for forms in _FORMS.values() for v in forms} | {x for v in _LAM_ALEF.values() for x in v}


def digits_fa(text: str) -> str:
    """ASCII digits -> Persian digits (for captions that should read as Persian)."""
    return str(text).translate(_FA_DIGITS)


def has_rtl(text: str) -> bool:
    return bool(RTL_RANGE.search(text or ""))


def _joins_next(ch: str) -> bool:
    f = _FORMS.get(ch)
    return bool(f and len(f) == 4)


def _is_letter(ch: str) -> bool:
    return ch in _FORMS


def _contextual(text: str) -> str:
    """Logical order -> logical order with each letter replaced by its contextual presentation form."""
    chars = list(text)
    n = len(chars)
    out: list[str] = []
    i = 0

    def prev_base(k: int) -> str:
        k -= 1
        while k >= 0 and chars[k] in HARAKAT:
            k -= 1
        return chars[k] if k >= 0 else ""

    def next_base(k: int) -> str:
        k += 1
        while k < n and chars[k] in HARAKAT:
            k += 1
        return chars[k] if k < n else ""

    while i < n:
        ch = chars[i]
        if not _is_letter(ch):
            out.append(ch)
            i += 1
            continue
        p, nx = prev_base(i), next_base(i)
        join_prev = bool(p) and _joins_next(p)
        # a "lam" + alef pair becomes one ligature glyph
        if ch == "ل" and nx in _LAM_ALEF:
            iso, fin = _LAM_ALEF[nx]
            out.append(fin if join_prev else iso)
            j = i + 1
            while j < n and chars[j] != nx:       # keep marks that sat between lam and alef
                out.append(chars[j])
                j += 1
            i = j + 1
            continue
        forms = _FORMS[ch]
        join_next = _joins_next(ch) and nx != "" and _is_letter(nx) and nx != "ء"
        if len(forms) == 1:
            out.append(forms[0])
        elif len(forms) == 2:                  # right-joining: isolated or final
            out.append(forms[1] if join_prev else forms[0])
        else:
            if join_prev and join_next:
                out.append(forms[3])
            elif join_prev:
                out.append(forms[1])
            elif join_next:
                out.append(forms[2])
            else:
                out.append(forms[0])
        i += 1
    return "".join(out)


def _kind(ch: str) -> str:
    """R (right-to-left letter), L (left-to-right letter or digit), N (neutral)."""
    if ch in HARAKAT or RTL_RANGE.match(ch):
        if "۰" <= ch <= "۹" or "٠" <= ch <= "٩":
            return "L"           # numbers keep their own left-to-right order inside right-to-left text
        return "R"
    if ch.isdigit() or (ch.isalpha() and ord(ch) < 0x590):
        return "L"
    return "N"


def _reorder(text: str) -> str:
    """Logical -> visual order for a right-to-left paragraph (simplified: runs of letters/numbers, neutrals take the side of their
    neighbours or the paragraph direction)."""
    if not text:
        return text
    kinds = [_kind(c) for c in text]
    # neutrals between two runs of the same kind take that kind; everything else follows the paragraph (R)
    resolved = kinds[:]
    i, n = 0, len(text)
    while i < n:
        if kinds[i] != "N":
            i += 1
            continue
        j = i
        while j < n and kinds[j] == "N":
            j += 1
        left = kinds[i - 1] if i > 0 else "R"
        right = kinds[j] if j < n else "R"
        # a space or punctuation between two LTR runs stays inside the LTR run only if both sides are L
        k = left if left == right else "R"
        for t in range(i, j):
            resolved[t] = k
        i = j
    runs: list[tuple[str, str]] = []
    for ch, k in zip(text, resolved):
        if runs and runs[-1][0] == k:
            runs[-1] = (k, runs[-1][1] + ch)
        else:
            runs.append((k, ch))
    out = []
    for k, s in reversed(runs):
        out.append("".join(_MIRROR.get(c, c) for c in reversed(s)) if k == "R" else s)
    return "".join(out)


def shape(text: str) -> str:
    """The string to hand to Pillow's BASIC layout: contextual forms, then visual (left-to-right) order."""
    if not has_rtl(text):
        return text
    return _reorder(_contextual(text))


# ------------------------------------------------------------------ fonts and drawing

RAQM_OK = bool(features.check("raqm")) and bool(features.check("fribidi"))


@functools.lru_cache(maxsize=64)
def _font(size: int, bold: bool, raqm: bool):
    name = "Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf"
    engine = ImageFont.Layout.RAQM if raqm else ImageFont.Layout.BASIC
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size, layout_engine=engine)
    except OSError:
        return ImageFont.load_default()


def font(size: int, bold: bool = False, *, force_basic: bool = False):
    return _font(int(size), bool(bold), RAQM_OK and not force_basic)


def _use_raqm(fnt) -> bool:
    return RAQM_OK and getattr(fnt, "layout_engine", None) == ImageFont.Layout.RAQM


def text_width(text: str, fnt) -> float:
    if _use_raqm(fnt):
        return fnt.getlength(text, direction="rtl" if has_rtl(text) else None, language="fa" if has_rtl(text) else None)
    return fnt.getlength(shape(text))


def wrap(text: str, fnt, max_width: float) -> list[str]:
    """Greedy word wrap of logical text; explicit newlines are kept."""
    lines: list[str] = []
    for para in str(text or "").split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            trial = f"{cur} {w}"
            if text_width(trial, fnt) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fnt, fill, *, anchor: str = "la", stroke_width: int = 0, stroke_fill=None) -> None:
    """Draw one line. `anchor` is Pillow's (horizontal l/m/r + vertical a/m/s) in VISUAL terms: 'ra' puts the right edge at x."""
    if _use_raqm(fnt):
        rtl = has_rtl(text)
        draw.text(xy, text, font=fnt, fill=fill, anchor=anchor, direction="rtl" if rtl else None, language="fa" if rtl else None,
                  stroke_width=stroke_width, stroke_fill=stroke_fill)
    else:
        draw.text(xy, shape(text), font=fnt, fill=fill, anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill)


def line_height(fnt, spacing: float = 1.35) -> int:
    asc, desc = fnt.getmetrics()
    return int((asc + desc) * spacing)


def draw_paragraph(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], text: str, fnt, fill, *, align: str = "auto",
                   spacing: float = 1.35, valign: str = "top", stroke_width: int = 0, stroke_fill=None) -> tuple[float, float]:
    """Wrap `text` inside `box` (x0, y0, x1, y1) and draw it. align: auto (right for Persian, left otherwise) | right | left | center.
    Returns (width, height) actually used. Lines beyond the box height are dropped with an ellipsis on the last one."""
    x0, y0, x1, y1 = box
    lines = wrap(text, fnt, x1 - x0)
    lh = line_height(fnt, spacing)
    maxl = max(1, int((y1 - y0) // lh))
    if len(lines) > maxl:
        lines = lines[:maxl]
        lines[-1] = lines[-1].rstrip() + "…"
    total = lh * len(lines)
    y = y0 + ((y1 - y0 - total) / 2 if valign == "middle" else 0)
    used_w = 0.0
    for ln in lines:
        w = text_width(ln, fnt)
        used_w = max(used_w, w)
        al = align if align != "auto" else ("right" if has_rtl(ln) else "left")
        if al == "right":
            draw_text(draw, (x1, y), ln, fnt, fill, anchor="ra", stroke_width=stroke_width, stroke_fill=stroke_fill)
        elif al == "center":
            draw_text(draw, ((x0 + x1) / 2, y), ln, fnt, fill, anchor="ma", stroke_width=stroke_width, stroke_fill=stroke_fill)
        else:
            draw_text(draw, (x0, y), ln, fnt, fill, anchor="la", stroke_width=stroke_width, stroke_fill=stroke_fill)
        y += lh
    return used_w, total
