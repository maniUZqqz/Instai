"""The colour palette of one design: from the colours of the page / series look plus the "mood" of the layout.

Deterministic, no AI. When the series (or the page) has brand colours every colour is built from them (darker, lighter, complementary);
otherwise the default colours of each mood are used. The main text always has enough contrast with the background (``ensure_contrast``).

SOURCE: ported from NMarketing:backend/apps/thumbs/palette.py @ v3.02 (c23f861), adapted for series/episode covers
(the store brand-colour helper is replaced by ``brand_colors_of`` for a page profile / series look and ``from_theme`` for the 6 roles of a colour theme).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import colorx

MOODS = ("vivid", "dark", "light", "cinema", "neon", "luxury", "warm", "cool")
MOOD_FA = {"vivid": "پرانرژی", "dark": "تیره", "light": "روشن و تمیز", "cinema": "سینمایی", "neon": "نئونی",
           "luxury": "لوکس", "warm": "گرم", "cool": "سرد و مدرن"}
MOOD_EN = {"vivid": "Vivid", "dark": "Dark", "light": "Light and clean", "cinema": "Cinematic", "neon": "Neon", "luxury": "Luxury", "warm": "Warm", "cool": "Cool and modern"}

#: base colours of each mood when there is no brand colour: (main, second)
DEFAULTS = {
    "vivid": ("#7c3aed", "#ec4899"),
    "dark": ("#1d4ed8", "#0ea5e9"),
    "light": ("#2563eb", "#f59e0b"),
    "cinema": ("#0f766e", "#ea580c"),
    "neon": ("#d946ef", "#22d3ee"),
    "luxury": ("#c9a24b", "#8a6d2b"),
    "warm": ("#ea580c", "#f59e0b"),
    "cool": ("#0ea5e9", "#6366f1"),
}


@dataclass
class Palette:
    bg1: str            # main background (darker)
    bg2: str            # second background (lighter or complementary)
    accent: str         # accent colour (key word, button, badge)
    accent2: str        # second accent colour
    text: str           # main text colour on the background
    ink: str            # dark colour (text outline, text on the accent)
    paper: str          # soft light colour (cards, paper)
    dark: bool          # is the background dark?
    primary: str        # the main brand colour (or the default)

    def public(self) -> dict:
        return asdict(self)


def _hsl(hex_color: str):
    return colorx.to_hsl(hex_color)


def _norm(c) -> str | None:
    c = str(c or "").strip().lower()
    return c if colorx.is_hex(c) else None


def clean_colors(values) -> list[str]:
    out: list[str] = []
    for v in values or []:
        n = _norm(v)
        if n and n not in out:
            out.append(n)
    return out[:5]


def brand_colors_of(page_palette=None, series_palette=None) -> list[str]:
    """Brand colours of a cover: the series' own look first, then the page's visual profile (both are lists of ``#rrggbb``).

    A colour theme lists its roles as background, primary, secondary, accent, shadow, highlight; the brand pair is (primary, secondary)."""
    for pal in (series_palette, page_palette):
        got = clean_colors(pal)
        if got:
            return got
    return []


def theme_roles(roles) -> dict | None:
    """The 6 roles of a colour theme (background, primary, secondary, accent, shadow, highlight) -> a dict, or None when it is not a valid list."""
    vals = [_norm(v) for v in (roles or [])]
    if len(vals) < 4 or not all(vals[:4]):
        return None
    names = ("background", "primary", "secondary", "accent", "shadow", "highlight")
    return {names[i]: vals[i] for i in range(min(6, len(vals))) if vals[i]}


def ensure_contrast(fg: str, bg: str, minimum: float = 3.0, *, light: str = "#ffffff", dark: str = "#0b1020") -> str:
    """If fg does not have enough contrast on bg it becomes the white / black that does."""
    if colorx.contrast(fg, bg) >= minimum:
        return fg
    return light if colorx.contrast(light, bg) >= colorx.contrast(dark, bg) else dark


def _rot(color: str, deg: float, s: float | None = None, l: float | None = None) -> str:
    h, ss, ll = _hsl(color)
    return colorx.from_hsl(h + deg, ss if s is None else s, ll if l is None else l)


def build(mood: str, brand: list[str] | None = None, overrides: dict | None = None, variation: int = 0) -> Palette:
    """The full palette. ``variation`` (0, 1, 2 ...) makes the A/B versions: the main / second colour swap and a gentle hue turn for the default colours."""
    mood = mood if mood in MOODS else "vivid"
    brand = clean_colors(brand)
    ov = overrides or {}
    base1, base2 = DEFAULTS[mood]
    primary = _norm(ov.get("primary")) or (brand[0] if brand else base1)
    secondary = _norm(ov.get("secondary")) or (brand[1] if len(brand) > 1 else None)
    if secondary is None:
        # no second colour: a near complement (30 to 40 degrees), or the mood's default second colour when there is no brand
        secondary = base2 if not brand else _rot(primary, 35)
    if variation % 2 == 1:
        primary, secondary = secondary, primary
    if variation >= 2 and not brand and not ov.get("primary"):
        primary, secondary = _rot(primary, 40 * (variation // 2)), _rot(secondary, 40 * (variation // 2))
    accent_in = _norm(ov.get("accent"))

    ph, ps, pl = _hsl(primary)
    sh, ss, sl = _hsl(secondary)
    if mood in ("vivid", "warm", "cool"):
        bg1 = colorx.from_hsl(ph, max(0.55, ps), 0.26 if pl > 0.3 else pl)
        bg2 = colorx.from_hsl(sh, max(0.6, ss), 0.5)
        accent = accent_in or "#ffd400"
        accent2 = colorx.from_hsl(sh + 25, 0.9, 0.62)
        dark = True
        text, ink, paper = "#ffffff", "#0b1020", "#fff7e6"
    elif mood == "dark":
        bg1 = colorx.from_hsl(ph, min(0.5, ps), 0.07)
        bg2 = colorx.from_hsl(ph, min(0.6, ps), 0.2)
        accent = accent_in or colorx.from_hsl(sh, max(0.7, ss), 0.62)
        accent2 = colorx.from_hsl(ph, max(0.7, ps), 0.58)
        dark = True
        text, ink, paper = "#f8fafc", "#05070d", "#e2e8f0"
    elif mood == "light":
        bg1 = colorx.from_hsl(ph, min(0.55, ps), 0.94)
        bg2 = colorx.from_hsl(sh, min(0.6, ss), 0.86)
        accent = accent_in or colorx.from_hsl(ph, max(0.65, ps), 0.42)
        accent2 = colorx.from_hsl(sh, max(0.65, ss), 0.5)
        dark = False
        text, ink, paper = "#0f172a", "#0f172a", "#ffffff"
    elif mood == "cinema":
        bg1 = colorx.from_hsl(ph, min(0.6, max(0.35, ps)), 0.08)
        bg2 = colorx.from_hsl(ph, min(0.6, max(0.4, ps)), 0.24)
        accent = accent_in or colorx.from_hsl(sh, 0.8, 0.55)
        accent2 = colorx.from_hsl(ph, 0.55, 0.6)
        dark = True
        text, ink, paper = "#f4efe6", "#05070d", "#e9dcc4"
    elif mood == "neon":
        bg1 = colorx.from_hsl(ph + 220, 0.5, 0.06)
        bg2 = colorx.from_hsl(ph + 240, 0.55, 0.14)
        accent = accent_in or colorx.from_hsl(ph, 1.0, 0.62)
        accent2 = colorx.from_hsl(sh + 40, 1.0, 0.6)
        dark = True
        text, ink, paper = "#ffffff", "#05010f", "#e9d5ff"
    else:  # luxury
        bg1 = colorx.from_hsl(ph, min(0.18, ps), 0.07)
        bg2 = colorx.from_hsl(ph, min(0.2, ps), 0.14)
        accent = accent_in or (colorx.with_lightness(primary, 0.66, 0.6) if brand else "#d4af37")
        accent2 = colorx.from_hsl(_hsl(accent)[0], 0.55, 0.72)
        dark = True
        text, ink, paper = "#f5efe0", "#0a0a0a", "#efe6d2"
    if colorx.contrast(accent, bg1) < 2.2:        # the accent got lost on the background -> make it lighter
        accent = colorx.with_lightness(accent, 0.65 if dark else 0.35)
    return Palette(bg1=bg1, bg2=bg2, accent=accent, accent2=accent2, text=text, ink=ink, paper=paper, dark=dark,
                   primary=primary)


def on(color: str, light: str = "#ffffff", dark: str = "#0b1020") -> str:
    """Readable text on any colour (white or dark, whichever has more contrast)."""
    return light if colorx.contrast(light, color) >= colorx.contrast(dark, color) else dark


def from_theme(roles, mood: str = "vivid", overrides: dict | None = None, variation: int = 0) -> Palette:
    """A palette from the 6 roles of a colour theme: primary and secondary drive the build, the theme's accent is kept when it reads on the
    background, ``shadow`` becomes the ink (outline / text on the accent) and ``highlight`` the paper, each only when it keeps enough contrast."""
    r = theme_roles(roles)
    if not r:
        return build(mood, [], overrides, variation)
    ov = dict(overrides or {})
    ov.setdefault("accent", r["accent"])
    p = build(mood, [r["primary"], r.get("secondary") or r["primary"]], ov, variation)
    if r.get("shadow") and colorx.contrast(r["shadow"], p.text) >= 4.0:
        p.ink = r["shadow"]
    if r.get("highlight") and colorx.contrast(r["highlight"], p.ink) >= 3.0:
        p.paper = r["highlight"]
    return p
