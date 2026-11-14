"""Colour maths of the motion plan (WCAG contrast), written to give the same answers as remotion/src/kit/theme.ts (luminance, contrast, readableOn,
accentOn, mix) and remotion/src/components/ctx.tsx (paletteFromKit): the QA judges the colours the renderer will really draw.

InstAI's rule, kept: a colour is never used without readableOn / accentOn against its own surface.
"""
from __future__ import annotations

import re


def parse(c: str):
    """'#rrggbb' / 'rgb(r, g, b)' / 'rgba(r, g, b, a)' => (r, g, b, a) or None."""
    if not c:
        return None
    c = c.strip().lower()
    m = re.match(r"rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:[ ,/]+([\d.]+))?", c)
    if m:
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return (round(float(m.group(1))), round(float(m.group(2))), round(float(m.group(3))), a)
    m = re.match(r"^#?([0-9a-f]{6})$", c)
    if m:
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    return None


def _lin(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a, b, t: float) -> tuple:
    return tuple(int(a[k] + (b[k] - a[k]) * t + 0.5) for k in range(3))


def hexof(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(x) for x in rgb[:3])


def _rgb(c):
    p = parse(c) if isinstance(c, str) else c
    return tuple(p[:3]) if p else (0, 0, 0)


def readable_on(bg, preferred=()) -> str:
    """The text colour that reads on `bg`: the first preferred colour with contrast >= 4.5, else white or black."""
    b = _rgb(bg)
    for c in preferred:
        if contrast(_rgb(c), b) >= 4.5:
            return hexof(_rgb(c))
    return "#ffffff" if contrast((255, 255, 255), b) >= contrast((0, 0, 0), b) else "#000000"


def accent_on(bg, accent, minimum: float = 3.0) -> str:
    """The accent as it is when it reads on `bg` (contrast >= minimum), else the accent pulled toward the readable text colour until it does."""
    b, a = _rgb(bg), _rgb(accent)
    if contrast(a, b) >= minimum:
        return hexof(a)
    text = (255, 255, 255) if contrast((255, 255, 255), b) >= contrast((0, 0, 0), b) else (0, 0, 0)
    for t in (0.35, 0.5, 0.65, 0.8, 1):
        c = mix(a, text, t)
        if contrast(c, b) >= minimum:
            return hexof(c)
    return hexof(text)


def best_text_color(bg, candidates=("#ffffff", "#111111")) -> tuple:
    """The most readable colour on `bg` => (hex, contrast ratio)."""
    b = _rgb(bg)
    best = max(candidates, key=lambda h: contrast(_rgb(h), b))
    return best, contrast(_rgb(best), b)


def palette_from_kit(kit: dict) -> dict:
    """The eight colour roles the components draw with, from the kit's six (the mirror of ctx.tsx `paletteFromKit`)."""
    p = (kit or {}).get("palette") or {}
    bg = p.get("background", "#14181F")
    ink = readable_on(bg, [p.get("highlight", "#F3E9D8"), "#FFFFFF"])
    primary = p.get("primary", "#3B4A5C")
    return {
        "bg": bg, "bg2": hexof(mix(_rgb(bg), _rgb(primary), 0.35)), "ink": ink, "paper": hexof(mix(_rgb(bg), _rgb(primary), 0.55)),
        "accent": accent_on(bg, p.get("accent", "#E8C98F"), 4.5), "accent2": accent_on(bg, p.get("secondary", "#B9824B"), 4.5),
        "accent3": accent_on(bg, hexof(mix(_rgb(primary), _rgb(p.get("highlight", "#F3E9D8")), 0.4)), 4.5),
        "muted": hexof(mix(_rgb(ink), _rgb(bg), 0.5)),
    }
