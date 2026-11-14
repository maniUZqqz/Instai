"""The few colour helpers the cover engine needs: hex checks, WCAG contrast, mixing and HSL moves. All colours are ``#rrggbb``.

SOURCE: ported from NMarketing:backend/apps/photoedit/designer/colorx.py @ v3.02 (c23f861), adapted for series/episode covers
(only the helpers palette.py and styles use: is_hex, contrast, mix, to_hsl, from_hsl, with_lightness; pure Python, no numpy).
"""
from __future__ import annotations

import colorsys
import re

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def is_hex(v) -> bool:
    return isinstance(v, str) and bool(_HEX.match(v))


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(round(float(v))))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    """WCAG relative luminance (0..1) of one colour."""
    r, g, b = (_lin(float(v)) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    """WCAG contrast ratio between two colours (1..21); a and b are hex strings or (r, g, b)."""
    ra = hex_to_rgb(a) if isinstance(a, str) else a
    rb = hex_to_rgb(b) if isinstance(b, str) else b
    la, lb = luminance(ra), luminance(rb)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: str, b: str, t: float) -> str:
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex([ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def to_hsl(h: str) -> tuple[float, float, float]:
    r, g, b = (v / 255.0 for v in hex_to_rgb(h))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return hh * 360.0, ss, ll


def from_hsl(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360.0) / 360.0, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return rgb_to_hex([r * 255, g * 255, b * 255])


def with_lightness(h: str, l: float, s: float | None = None) -> str:
    hh, ss, _ = to_hsl(h)
    return from_hsl(hh, ss if s is None else s, l)
