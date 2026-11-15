"""The cover text: layout, automatic fitting, outline / shadow / glow / extrusion and the highlighted word, in Persian (right to left) and English.

Pillow draws it. Persian is shaped by libraqm when it works; when it does not (the owner's Windows Pillow has no FriBidi) the built-in shaper of
``instai.render.fa_text`` (contextual forms + a simplified bidi order, drawn with Pillow's basic layout) is used, and both give the same picture for ordinary
sentences (tests/test_covers_text.py compares them). Fonts are bundled in ``instai/covers/fonts`` (all SIL OFL 1.1; Estedad was left out because its Persian letters exist only as OpenType rules, which the built-in shaper cannot use) plus the Vazirmatn of ``instai/render/fonts``.

``render_text`` returns a "text block" (RGBA + a nominal size); ``place`` puts it. The highlighted word: write ``*word*`` in the text (or automatically the last
word). ``|`` means "break the line here".

SOURCE: ported from NMarketing:backend/apps/thumbs/typo.py @ v3.02 (c23f861), adapted for series/episode covers
(shaping goes through instai.render.fa_text; the bundled fonts are Lalezar, Sahel and Vazirmatn).
"""
from __future__ import annotations

import math
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from instai.render import fa_text

from . import primitives as P

FONT_DIR = Path(__file__).resolve().parents[1] / "fonts"
FALLBACK_DIR = Path(fa_text.FONT_DIR)

#: font key -> {label (fa, en), default weight of a headline, files {weight: (folder, file name)}}. Lalezar has a single weight.
FONTS: dict[str, dict] = {
    "lalezar": {"label": ("لاله‌زار — درشت و پرجلوه", "Lalezar - bold and showy"), "weight": 400,
                "files": {400: (FONT_DIR, "Lalezar-Regular.ttf")}},
    "sahel": {"label": ("ساحل — گرم و گرد", "Sahel - warm and round"), "weight": 800,
              "files": {300: (FONT_DIR, "Sahel-Light.ttf"), 400: (FONT_DIR, "Sahel-Regular.ttf"), 600: (FONT_DIR, "Sahel-SemiBold.ttf"),
                        700: (FONT_DIR, "Sahel-Bold.ttf"), 800: (FONT_DIR, "Sahel-Black.ttf")}},
    "vazirmatn": {"label": ("وزیرمتن — خوانا", "Vazirmatn - readable"), "weight": 700,
                  "files": {400: (FALLBACK_DIR, "Vazirmatn-Regular.ttf"), 700: (FALLBACK_DIR, "Vazirmatn-Bold.ttf")}},
}
#: key -> (label, headline weight): the shape the styles read
FONT_CHOICES = {k: (v["label"][0], v["weight"]) for k, v in FONTS.items()}
AUTO_FONT = "auto"

_RTL_RE = re.compile("[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_HL_RE = re.compile(r"\*([^*]+)\*")

_INVISIBLE = {0x200C: None, 0x200D: None, 0x200E: None, 0x200F: None, 0xFEFF: None}

# which layout engine draws Persian: libraqm when it really works (RAQM + FriBidi), otherwise the built-in shaper.
# ``basic_layout()`` forces the built-in shaper (the tests compare the two; the owner's Windows PC always takes it).
HAS_RAQM = bool(fa_text.RAQM_OK)
_FORCE = threading.local()


def use_raqm() -> bool:
    return HAS_RAQM and not getattr(_FORCE, "basic", False)


@contextmanager
def basic_layout(on: bool = True):
    """Draw with the built-in Persian shaper (as on a PC without FriBidi) inside the ``with`` block."""
    old = getattr(_FORCE, "basic", False)
    _FORCE.basic = bool(on)
    try:
        yield
    finally:
        _FORCE.basic = old


def is_rtl(text: str) -> bool:
    return bool(_RTL_RE.search(text or ""))


def font_path(key: str, weight: int) -> str:
    """The file of font ``key`` at the weight nearest to ``weight`` (an unknown key -> Vazirmatn)."""
    fam = FONTS.get(key) or FONTS["vazirmatn"]
    files = fam["files"]
    w = min(files, key=lambda x: (abs(x - int(weight)), x))
    folder, name = files[w]
    return str(Path(folder) / name)


@lru_cache(maxsize=96)
def _font_cached(path: str, px: int, raqm: bool):
    return ImageFont.truetype(path, px, layout_engine=ImageFont.Layout.RAQM if raqm else ImageFont.Layout.BASIC)


def _font(path: str, px: int):
    return _font_cached(path, int(px), use_raqm())


def _kw(rtl: bool) -> dict:
    return {"direction": "rtl", "language": "fa"} if (rtl and use_raqm()) else {}


def _shape(text: str, rtl: bool) -> str:
    """Without raqm: the built-in shaper (joined letters + right-to-left order); with raqm the string goes to Pillow unchanged."""
    if use_raqm() or not rtl:
        return text
    # Pillow's basic layout cannot place a vowel mark (kasra, fatha ...) under / over its letter: it would sit beside it as a stray dash, so the marks are left out here
    # (libraqm draws them correctly). The zero-width joiners only steer the joining (already done by ``shape``); a font without a glyph for them would draw an empty box.
    return fa_text.shape("".join(ch for ch in text if ch not in fa_text.HARAKAT)).translate(_INVISIBLE)



def to_fa_digits(text: str) -> str:
    """Latin digits -> Persian; a comma between digits -> "٬". Pure Latin text ("HIIT", "3D", "Wi-Fi 6") is left alone,
    but a digits-only string ("7", "20%", "10:30") with no Latin letter becomes Persian too (the "number" box of the list layout)."""
    if not text:
        return text
    if not is_rtl(text) and (re.search(r"[A-Za-z]", text) or not re.search(r"[0-9]", text)):
        return text
    out = text.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    return re.sub(r"(?<=[۰-۹]),(?=[۰-۹])", "٬", out)


def clean(text) -> str:
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]+", " ", str(text or ""))
    return re.sub(r"[ \t]+", " ", t).strip()


@dataclass
class TextStyle:
    fill: str = "#ffffff"
    fill2: str | None = None          # bottom of the vertical fill gradient
    hl: str | None = None             # colour of the highlighted word
    stroke: str | None = None
    stroke_w: float = 0.0             # relative to the font size
    shadow: tuple[float, float, float, str, float] | None = None   # (dx, dy, blur) relative to the font, colour, opacity
    glow: tuple[str, float, float] | None = None                   # (colour, radius relative to the font, strength)
    extrude: tuple[str, float] | None = None                       # (colour, depth relative to the font) - a 3D extrusion
    align: str = "auto"               # auto | right | center | left
    line_gap: float = 1.1
    weight: int = 800
    font_key: str = "lalezar"
    rotate: float = 0.0
    #: a "label" behind the text: (colour, relative padding, relative radius)
    plate: tuple[str, float, float] | None = None
    auto_hl: bool = False


@dataclass
class TextBlock:
    img: Image.Image                  # RGBA (including the edges of the effects)
    nominal: tuple[int, int]          # size of the nominal box of the text (without effects)
    origin: tuple[int, int]           # offset of the nominal box's corner inside img
    lines: int
    px: int
    ink: tuple[int, int, int, int] | None = None     # the real box of the ink inside img

    @property
    def size(self) -> tuple[int, int]:
        return self.img.size


def parse_marked(text: str) -> tuple[list[list[tuple[str, bool]]], bool]:
    """"A *B* C|D" -> [[(word, highlighted?) ...] for each forced line], and whether there was a marker."""
    text = clean(text)
    forced = [seg.strip() for seg in text.split("|")] if "|" in text else [text]
    marked = bool(_HL_RE.search(text))
    out: list[list[tuple[str, bool]]] = []
    for seg in forced:
        words: list[tuple[str, bool]] = []
        # runs: plain text and "*highlighted*"; text glued to a star ("*one minute*?", "*Name*,") sticks to that word and does not become a separate word
        runs: list[tuple[str, bool]] = []
        pos = 0
        for m in _HL_RE.finditer(seg):
            runs.append((seg[pos:m.start()], False))
            runs.append((m.group(1), True))
            pos = m.end()
        runs.append((seg[pos:], False))
        glue = False                       # the previous run ended with a character that is not a space
        for text, flag in runs:
            if not text:
                continue
            toks = text.split()
            if toks:
                if glue and not text[0].isspace() and words:
                    pw, pf = words[-1]
                    words[-1] = (pw + toks[0], pf or flag)
                    toks = toks[1:]
                words.extend((w, flag) for w in toks)
            glue = not text[-1].isspace()
        out.append(words)
    return [ln for ln in out if ln], marked


def plain(text: str) -> str:
    """The text without the markers (for counting / showing)."""
    return re.sub(r"\s+", " ", _HL_RE.sub(r"\1", clean(text)).replace("|", " ")).strip()


def _wrap(words: list[tuple[str, bool]], widths: list[float], space: float, avail: float) -> list[list[int]] | None:
    """Greedy wrapping; None when a word is wider than the allowed width."""
    if any(w > avail for w in widths):
        return None
    lines: list[list[int]] = []
    cur: list[int] = []
    cur_w = 0.0
    for i, w in enumerate(widths):
        add = w if not cur else space + w
        if cur and cur_w + add > avail:
            lines.append(cur)
            cur, cur_w = [i], w
        else:
            cur.append(i)
            cur_w += add
    if cur:
        lines.append(cur)
    return lines


def _balance(words, widths, space, avail, n_lines) -> list[list[int]]:
    """Balance the lines: the smallest width that still gives the same number of lines."""
    lo, hi = max(widths), avail
    best = _wrap(words, widths, space, hi) or []
    for _ in range(14):
        mid = (lo + hi) / 2
        got = _wrap(words, widths, space, mid)
        if got is not None and len(got) <= n_lines:
            best, hi = got, mid
        else:
            lo = mid
    return best


def _line_width(idx: list[int], widths: list[float], space: float) -> float:
    return sum(widths[i] for i in idx) + space * max(0, len(idx) - 1)


def _layout(groups, path: str, px: int, box_w: float, style: TextStyle, rtl: bool, force: bool = False):
    """Lay out every group at one font size -> (word space, [(words, widths, lines)]) or None when a word does not fit."""
    f = _font(path, px)
    kw = _kw(rtl)
    sw = style.stroke_w * px
    avail = 1e9 if force else box_w - 2 * sw
    space = max(f.getlength(_shape(" ", rtl), **kw), px * 0.24)
    rows = []
    for words in groups:
        widths = [f.getlength(_shape(w, rtl), **kw) for w, _ in words]
        got = _wrap(words, widths, space, avail)
        if got is None:
            return None
        if len(groups) == 1 and len(got) > 1:
            got = _balance(words, widths, space, avail, len(got))
        rows.append((words, widths, got))
    return space, rows


def fit(text: str, path: str, box_w: float, box_h: float, style: TextStyle, *, max_lines: int = 3, min_px: int = 18,
        max_px: int = 400, rtl: bool | None = None):
    """The largest font size at which the text fits the box. -> (px, lines [(word, highlighted?) ...], width of each line, word space, rtl)."""
    groups, marked = parse_marked(text)
    if not groups:
        return None
    rtl = is_rtl(text) if rtl is None else rtl
    max_lines = max(max_lines, min(len(groups), 5))     # "A|B|C" = three forced lines; the line cap must not turn it into tiny text
    px = int(max_px)
    floor = max(8, int(min_px * 0.45))
    res = None
    while True:
        res = _layout(groups, path, px, box_w, style, rtl)
        if res is not None:
            total_lines = sum(len(r[2]) for r in res[1])
            sw = style.stroke_w * px
            asc, desc = _font(path, px).getmetrics()
            height = px * style.line_gap * (total_lines - 1) + asc + desc + 2 * sw
            if total_lines <= max_lines and height <= box_h:
                break
        if px <= floor:
            break
        px = max(floor, int(px * 0.94) if px > 40 else px - 2)
    if res is None:                      # even at the smallest size one word is wider than the box -> do not break it
        res = _layout(groups, path, px, box_w, style, rtl, force=True)
    space, rows = res
    lines: list[list[tuple[str, bool]]] = []
    widths_out: list[float] = []
    for words, widths, got in rows:
        for idx in got:
            lines.append([words[i] for i in idx])
            widths_out.append(_line_width(idx, widths, space))
    if style.auto_hl and not marked and lines and sum(len(ln) for ln in lines) >= 3:
        last = lines[-1][-1]
        lines[-1][-1] = (last[0], True)
    return px, lines, widths_out, space, rtl


def render_text(text: str, box_w: float, box_h: float, style: TextStyle, *, max_lines: int = 3, min_px: int = 18,
                max_px: int = 400) -> TextBlock | None:
    """Fit the text in the box_w x box_h box and build an RGBA block with all effects. Empty text -> None."""
    text = clean(text)
    if not plain(text):
        return None
    path = font_path(style.font_key, style.weight)
    got = fit(text, path, box_w, box_h, style, max_lines=max_lines, min_px=min_px, max_px=max_px)
    if got is None:
        return None
    px, lines, widths, space, rtl = got
    f = _font(path, px)
    kw = _kw(rtl)
    ascent, descent = f.getmetrics()
    sw = int(round(style.stroke_w * px))
    line_h = px * style.line_gap
    nominal_w = int(math.ceil(max(widths) + 2 * sw)) if widths else int(box_w)
    nominal_w = max(nominal_w, 1)
    nominal_h = int(math.ceil(line_h * (len(lines) - 1) + ascent + descent + 2 * sw))

    # edge padding for the effects
    pad = sw + 4
    if style.shadow:
        pad = max(pad, int(abs(style.shadow[0]) * px + abs(style.shadow[1]) * px + style.shadow[2] * px * 2.5) + 4)
    if style.glow:
        pad = max(pad, int(style.glow[1] * px * 2.6) + 4)
    if style.extrude:
        pad = max(pad, int(style.extrude[1] * px) + sw + 4)
    if style.plate:
        pad = max(pad, int(style.plate[1] * px) + 4)
    W, H = nominal_w + 2 * pad, nominal_h + 2 * pad

    align = style.align if style.align != "auto" else ("right" if rtl else "left")
    m_fill = Image.new("L", (W, H), 0)
    m_hl = Image.new("L", (W, H), 0)
    m_stroke = Image.new("L", (W, H), 0)
    d_fill, d_hl, d_stroke = ImageDraw.Draw(m_fill), ImageDraw.Draw(m_hl), ImageDraw.Draw(m_stroke)

    def draw_to(draw, xy, s, anchor, stroke):
        if stroke:
            draw.text(xy, s, font=f, fill=255, anchor=anchor, stroke_width=sw, stroke_fill=255, **kw)
        else:
            draw.text(xy, s, font=f, fill=255, anchor=anchor, **kw)

    inner_left, inner_right = pad + sw, pad + sw + (nominal_w - 2 * sw)
    inner_w = inner_right - inner_left
    for li, (line, lw) in enumerate(zip(lines, widths)):
        base = pad + sw + ascent + li * line_h
        if align == "center":
            right = inner_left + inner_w / 2 + lw / 2
            left = inner_left + inner_w / 2 - lw / 2
        elif align == "right":
            right, left = inner_right, inner_right - lw
        else:
            left, right = inner_left, inner_left + lw
        has_hl = any(h for _, h in line)
        if not has_hl:
            s = " ".join(w for w, _ in line)
            if rtl:
                draw_to(d_fill, (right, base), _shape(s, rtl), "rs", False)
                draw_to(d_stroke, (right, base), _shape(s, rtl), "rs", sw > 0)
            else:
                draw_to(d_fill, (left, base), s, "ls", False)
                draw_to(d_stroke, (left, base), s, "ls", sw > 0)
            continue
        cursor = right if rtl else left
        for w, hl in line:
            wd = f.getlength(_shape(w, rtl), **kw)
            tgt_fill = d_hl if hl else d_fill
            if rtl:
                draw_to(tgt_fill, (cursor, base), _shape(w, rtl), "rs", False)
                draw_to(d_stroke, (cursor, base), _shape(w, rtl), "rs", sw > 0)
                cursor -= wd + space
            else:
                draw_to(tgt_fill, (cursor, base), w, "ls", False)
                draw_to(d_stroke, (cursor, base), w, "ls", sw > 0)
                cursor += wd + space

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if style.plate:
        pc, pp, pr = style.plate
        ink = ImageChops.lighter(m_stroke, ImageChops.lighter(m_fill, m_hl)).getbbox()
        if ink:
            pd = int(pp * px)
            bx = (max(0, ink[0] - pd), max(0, ink[1] - pd), min(W, ink[2] + pd), min(H, ink[3] + pd))
            plate_m = P.rounded_mask((bx[2] - bx[0], bx[3] - bx[1]), pr * px)
            full = Image.new("L", (W, H), 0)
            full.paste(plate_m, (bx[0], bx[1]))
            out = Image.alpha_composite(out, P.solid((W, H), pc, full))
    if style.shadow:
        sdx, sdy, sbl, scol, sop = style.shadow
        base = m_stroke if sw else ImageChops.lighter(m_fill, m_hl)
        sh = ImageChops.offset(base, int(round(sdx * px)), int(round(sdy * px)))
        sh = sh.filter(ImageFilter.GaussianBlur(max(0.1, sbl * px)))
        out = Image.alpha_composite(out, P.solid((W, H), scol, sh, sop))
    if style.glow:
        gc, gr, gs = style.glow
        base = m_stroke if sw else ImageChops.lighter(m_fill, m_hl)
        gl = base.filter(ImageFilter.GaussianBlur(max(0.1, gr * px)))
        out = Image.alpha_composite(out, P.solid((W, H), gc, gl, min(1.0, gs)))
        out = Image.alpha_composite(out, P.solid((W, H), gc, base.filter(ImageFilter.GaussianBlur(max(0.1, gr * px * 0.35))), min(1.0, gs)))
    if style.extrude:
        ec, ed = style.extrude
        depth = max(1, int(ed * px))
        base = m_stroke if sw else ImageChops.lighter(m_fill, m_hl)
        for k in range(depth, 0, -1):
            out = Image.alpha_composite(out, P.solid((W, H), ec, ImageChops.offset(base, k // 2 + 1, k), 1.0))
    if sw and style.stroke:
        out = Image.alpha_composite(out, P.solid((W, H), style.stroke, m_stroke))
    fill_img: Image.Image | str = style.fill
    if style.fill2:
        fill_img = P.gradient((W, H), [(0.0, style.fill), (1.0, style.fill2)], 90).convert("RGBA")
    if isinstance(fill_img, str):
        out = Image.alpha_composite(out, P.solid((W, H), fill_img, m_fill))
    else:
        layer = fill_img.copy()
        layer.putalpha(m_fill)
        out = Image.alpha_composite(out, layer)
    if style.hl:
        out = Image.alpha_composite(out, P.solid((W, H), style.hl, m_hl))
    elif m_hl.getbbox():
        out = Image.alpha_composite(out, P.solid((W, H), style.fill, m_hl))

    origin = (pad, pad)
    if abs(style.rotate) > 0.01:
        out = out.rotate(style.rotate, resample=Image.Resampling.BICUBIC, expand=True)
        # the centre of the nominal box moves after the rotation; the new origin = the centre of the box
        ox = out.width / 2 - nominal_w / 2
        oy = out.height / 2 - nominal_h / 2
        origin = (int(round(ox)), int(round(oy)))
    ink = out.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    return TextBlock(img=out, nominal=(nominal_w, nominal_h), origin=origin, lines=len(lines), px=px, ink=ink)


def place(block: TextBlock, rect: tuple[float, float, float, float], ax: str = "center", ay: str = "middle"
          ) -> tuple[int, int]:
    """Position of the top-left corner of ``block.img`` so that the nominal text box sits in rect with the alignment (ax: right/center/left, ay: top/middle/bottom)."""
    x0, y0, x1, y1 = rect
    nw, nh = block.nominal
    if ax == "right":
        nx = x1 - nw
    elif ax == "left":
        nx = x0
    else:
        nx = (x0 + x1) / 2 - nw / 2
    if ay == "top":
        ny = y0
    elif ay == "bottom":
        ny = y1 - nh
    else:
        ny = (y0 + y1) / 2 - nh / 2
    return int(round(nx - block.origin[0])), int(round(ny - block.origin[1]))


def label(text: str, px: int, *, font_key: str = "sahel", weight: int = 800, fill: str = "#ffffff", bg: str = "#000000",
          pad_x: float = 0.7, pad_y: float = 0.32, radius: float = 0.5, border: str | None = None, border_w: float = 0.0,
          shadow: bool = True, slant: float = 0.0) -> Image.Image | None:
    """A capsule label (short text on a coloured background) -> RGBA. ``slant`` > 0 slants the edges."""
    text = plain(text)
    if not text:
        return None
    rtl = is_rtl(text)
    f = _font(font_path(font_key, weight), max(8, int(px)))
    kw = _kw(rtl)
    tw = f.getlength(_shape(text, rtl), **kw)
    asc, desc = f.getmetrics()
    px_i, py_i = int(px * pad_x), int(px * pad_y)
    w, h = int(math.ceil(tw)) + 2 * px_i, asc + desc + 2 * py_i
    shadow_pad = int(px * 0.35) if shadow else 0
    bw = int(round(border_w * px))
    pad = shadow_pad + bw + 2
    base = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    if slant:
        sk = int(h * slant)
        pts = [(sk, 0), (w, 0), (w - sk, h), (0, h)]
        m = P.polygon_mask((w, h), pts)
    else:
        m = P.rounded_mask((w, h), min(h / 2, radius * h))
    big = Image.new("L", base.size, 0)
    big.paste(m, (pad, pad))
    if shadow:
        sh = ImageChops.offset(big, 0, int(px * 0.12)).filter(ImageFilter.GaussianBlur(px * 0.12))
        base = Image.alpha_composite(base, P.solid(base.size, "#000000", sh, 0.35))
    if border and bw:
        base = Image.alpha_composite(base, P.solid(base.size, border, P.dilate(big, bw)))
    base = Image.alpha_composite(base, P.solid(base.size, bg, big))
    d = ImageDraw.Draw(base)
    d.text((pad + w / 2, pad + py_i + asc), _shape(text, rtl), font=f, fill=P.rgba(fill), anchor="ms", **kw)
    return base
