"""Colour contrast for text that must stay readable (WCAG relative luminance).

A Python twin of `readableOn` / `accentOn` / `mix` in remotion/src/kit/theme.ts (the code-to-video kit has the same rule: never a text colour without a check
against its own surface). The caption engine uses it so that whatever look a series has, the word being spoken, the plain words and the box behind them
always pass: 4.5:1 for text (the WCAG AA level for normal text; captions are read for a second or two, so large-text 3:1 is not good enough).
"""
from __future__ import annotations

import re

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_HEX3 = re.compile(r"^#[0-9a-fA-F]{3}$")
WHITE, BLACK = "#FFFFFF", "#000000"
TEXT_MIN = 4.5          # captions: normal-size text level
LARGE_MIN = 3.0         # decorations and large text


def norm(value, default: str) -> str:
    """'#RRGGBB' (upper-case) from '#rgb' / '#rrggbb'; `default` for anything else."""
    text = str(value or "").strip()
    if _HEX.match(text):
        return text.upper()
    if _HEX3.match(text):
        return "#" + "".join(ch * 2 for ch in text[1:]).upper()
    return default


def channels(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def luminance(c: str) -> float:
    """Relative luminance of a '#RRGGBB' colour, 0 (black) .. 1 (white)."""
    def f(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (f(v) for v in channels(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: str, b: str, t: float) -> str:
    """`a` moved the fraction `t` of the way to `b`."""
    (r1, g1, b1), (r2, g2, b2) = channels(a), channels(b)
    m = lambda x, y: f"{round(x + (y - x) * t):02X}"  # noqa: E731
    return f"#{m(r1, r2)}{m(g1, g2)}{m(b1, b2)}"


def best_plain(bg: str) -> str:
    """White or black, whichever reads better on `bg`."""
    return WHITE if contrast(WHITE, bg) >= contrast(BLACK, bg) else BLACK


def readable_on(bg: str, preferred: list[str] | tuple[str, ...] = (), minimum: float = TEXT_MIN) -> str:
    """The first preferred colour that has enough contrast on `bg`, else white or black."""
    for c in preferred:
        c = norm(c, "")
        if c and contrast(c, bg) >= minimum:
            return c
    return best_plain(bg)


def accent_on(bg: str, accent: str, minimum: float = LARGE_MIN) -> str:
    """The accent as it is when it reads on `bg`, else pulled toward the readable plain colour until it does."""
    accent = norm(accent, WHITE)
    if contrast(accent, bg) >= minimum:
        return accent
    text = best_plain(bg)
    for t in (0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0):
        c = mix(accent, text, t)
        if contrast(c, bg) >= minimum:
            return c
    return text


def distance(a: str, b: str) -> float:
    """A rough 0..1 distance between two colours (largest channel difference), to tell 'another colour' from 'the same colour'."""
    return max(abs(x - y) for x, y in zip(channels(a), channels(b))) / 255


def dark_of(bg: str, max_lum: float = 0.06) -> str:
    """A dark surface taken from `bg`: the look's own colour when it is dark enough, else pulled toward black until its luminance is at most `max_lum`
    (white text passes 4.5:1 up to a luminance of 0.18; 0.06 leaves room for the accent colours that sit next to it)."""
    bg = norm(bg, BLACK)
    for t in (0.0, 0.3, 0.5, 0.7, 0.85, 1.0):
        c = mix(bg, BLACK, t)
        if luminance(c) <= max_lum:
            return c
    return BLACK


def chroma(c: str) -> float:
    """How colourful a colour is, 0 (a grey) .. 1 (fully saturated): the spread of its channels. A pale blue next to white has little."""
    r, g, b = channels(c)
    return (max(r, g, b) - min(r, g, b)) / 255


def vivid_on(bg: str, color: str, minimum: float = TEXT_MIN) -> str | None:
    """`color` made lighter (on a dark surface) or darker (on a light one) while KEEPING its hue and its saturation, until it reads on `bg`; None when it cannot.
    Mixing toward white (`accent_on`) turns a teal into a washed-out grey; this keeps it a teal, only brighter - what a highlight should be."""
    import colorsys

    color = norm(color, WHITE)
    if contrast(color, bg) >= minimum:
        return color
    r, g, b = (v / 255 for v in channels(color))
    h, light, sat = colorsys.rgb_to_hls(r, g, b)
    sat = max(sat, 0.55)
    step = 0.02 if luminance(bg) < 0.4 else -0.02
    for i in range(0, 40):
        lt = light + step * i
        if not 0.12 <= lt <= 0.88:
            break
        rr, gg, bb = colorsys.hls_to_rgb(h, lt, sat)
        c = "#%02X%02X%02X" % (round(rr * 255), round(gg * 255), round(bb * 255))
        if contrast(c, bg) >= minimum:
            return c
    return None
