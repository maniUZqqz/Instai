"""Style & theme library: shared vocabulary and normalisers.

A *style preset* describes a LOOK (realism level + concrete animation style + prompt fragments for image and video models).
A *theme* describes colour palette, lighting, mood and title/subtitle typography. A page picks one of each; both can be
duplicated, edited, added, exported and imported. Built-in entries live in code (read-only); user entries live in the database.

Licence note: prompt fragments never contain studio, artist, franchise or character names. Styles are described by generic
visual traits (line weight, shading, palette, motion) so that the output cannot be mistaken for a specific rights-holder's work.
"""
from __future__ import annotations

import re
from typing import Any

# The realism ladder, from photographic to abstract. `anime_like` = semi-real with anime traits (large eyes, painted shading).
REALISM = {
    "realistic": {"fa": "واقع‌گرا", "en": "Realistic", "order": 1},
    "semi_realistic": {"fa": "نیمه‌واقع‌گرا", "en": "Semi-realistic", "order": 2},
    "anime_like": {"fa": "شبیه انیمه", "en": "Anime-like", "order": 3},
    "anime": {"fa": "انیمه", "en": "Anime", "order": 4},
    "cartoon": {"fa": "کارتون ۲بعدی", "en": "2D cartoon", "order": 5},
    "cartoon_3d": {"fa": "سه‌بعدی / عروسکی", "en": "3D / puppet", "order": 6},
    "graphic": {"fa": "گرافیکی و ساده", "en": "Graphic & flat", "order": 7},
    "stylized_art": {"fa": "هنری و دست‌ساز", "en": "Stylised handmade", "order": 8},
}

FAMILIES = {
    "live_like": {"fa": "نمای زنده", "en": "Live-action look"},
    "illustration": {"fa": "تصویرسازی", "en": "Illustration"},
    "anime": {"fa": "انیمه", "en": "Anime"},
    "western_2d": {"fa": "کارتون غربی", "en": "Western 2D"},
    "cg_3d": {"fa": "سه‌بعدی (CG)", "en": "3D (CG)"},
    "stop_motion": {"fa": "استاپ‌موشن", "en": "Stop-motion"},
    "graphic": {"fa": "گرافیک متحرک", "en": "Motion graphics"},
    "handmade": {"fa": "دست‌ساز و هنری", "en": "Handmade / art"},
}

# Animation approach = how it MOVES (the owner asked "which animation style exactly").
ANIMATIONS = {
    "live_camera": {"fa": "حرکت دوربین سینمایی", "en": "Cinematic camera moves"},
    "limited_2d": {"fa": "انیمیشن محدود ۲بعدی (روی ۲ و ۳)", "en": "Limited 2D (on twos/threes)"},
    "full_2d": {"fa": "انیمیشن کامل و روان ۲بعدی", "en": "Full 2D (fluid)"},
    "rubber_hose": {"fa": "کش‌وقوسیِ قدیمی (rubber hose)", "en": "Rubber-hose bounce"},
    "cutout": {"fa": "برش کاغذی / عروسک لایه‌ای", "en": "Cut-out / layered puppet"},
    "motion_graphics": {"fa": "موشن‌گرافیک", "en": "Motion graphics"},
    "stop_motion": {"fa": "استاپ‌موشن (روی ۲ و ۴)", "en": "Stop-motion (on twos/fours)"},
    "cg_3d": {"fa": "سه‌بعدی کامپیوتری", "en": "3D CG"},
    "toon_3d": {"fa": "سه‌بعدی با سایه‌ی کارتونی", "en": "Toon-shaded 3D"},
    "painted_parallax": {"fa": "نقاشی متحرک با پارالاکس", "en": "Painted art with parallax"},
}

TECHNIQUES = ["still_kenburns", "parallax_25d", "puppet_2d", "motion_graphics", "wan_i2v", "wan_flf", "talking_video", "three_d"]

STYLE_FIELDS = {
    "name_fa": "", "name_en": "", "description_fa": "", "description_en": "", "realism": "anime", "family": "anime", "animation": "limited_2d",
    "fps_feel": 12, "image_positive": "", "image_negative": "", "video_positive": "", "video_negative": "", "palette": [], "lighting": "",
    "mood": "", "techniques": ["still_kenburns", "parallax_25d"], "sample_prompt": "", "theme_key": "", "tags": [], "thumbnail_asset": None,
    "notes": "",
}
THEME_FIELDS = {
    "name_fa": "", "name_en": "", "description_fa": "", "description_en": "",
    # palette order: background, primary, secondary, accent, shadow, highlight
    "palette": [], "lighting": "", "mood": "", "prompt_fragment": "", "negative_fragment": "", "tags": [],
    "typography": {"title_weight": "bold", "title_case": "normal", "title_animation": "fade", "subtitle_color": "#FFFFFF",
                   "subtitle_outline": "#000000", "subtitle_position": "bottom", "subtitle_box_opacity": 0.0, "subtitle_size": 64},
    "notes": "",
}
PALETTE_ROLES = ["background", "primary", "secondary", "accent", "shadow", "highlight"]
TITLE_WEIGHTS = ["regular", "bold", "black"]
TITLE_CASES = ["normal", "upper", "lower"]
TITLE_ANIMATIONS = ["none", "fade", "pop", "slide", "typewriter"]
SUB_POSITIONS = ["bottom", "middle", "top"]

_KEY = re.compile(r"[^a-z0-9_]+")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def slug(text: str, fallback: str = "preset") -> str:
    s = _KEY.sub("_", (text or "").lower().strip()).strip("_")
    return (s or fallback)[:60]


def _str(v: Any, default: str = "") -> str:
    return default if v is None else str(v).strip()


def _str_list(v: Any, limit: int = 40) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[,\n،]", v)
    return [str(x).strip() for x in (v or []) if str(x).strip()][:limit]


def _palette(v: Any) -> list[str]:
    out = []
    for c in v or []:
        c = str(c).strip()
        if _HEX.match(c):
            out.append(c.upper())
    return out[:8]


def normalize_style(data: dict | None) -> dict:
    """Complete, safe style dict: unknown keys dropped, enums clamped, palette limited to valid hex colours."""
    d = data or {}
    out: dict[str, Any] = {}
    for k, default in STYLE_FIELDS.items():
        v = d.get(k, default)
        if k == "palette":
            v = _palette(v)
        elif k == "tags":
            v = _str_list(v)
        elif k == "techniques":
            v = [t for t in _str_list(v) if t in TECHNIQUES] or list(default)
        elif k == "fps_feel":
            try:
                v = max(4, min(60, int(v)))
            except (TypeError, ValueError):
                v = default
        elif k == "thumbnail_asset":
            v = int(v) if isinstance(v, (int, str)) and str(v).isdigit() else None
        else:
            v = _str(v, default if isinstance(default, str) else "")
        out[k] = v
    if out["realism"] not in REALISM:
        out["realism"] = "anime"
    if out["family"] not in FAMILIES:
        out["family"] = "anime"
    if out["animation"] not in ANIMATIONS:
        out["animation"] = "limited_2d"
    return out


def normalize_theme(data: dict | None) -> dict:
    d = data or {}
    out: dict[str, Any] = {}
    for k, default in THEME_FIELDS.items():
        v = d.get(k, default)
        if k == "palette":
            v = _palette(v)
        elif k == "tags":
            v = _str_list(v)
        elif k == "typography":
            base = dict(default)
            if isinstance(v, dict):
                base.update({kk: vv for kk, vv in v.items() if kk in default})
            for ck in ("subtitle_color", "subtitle_outline"):
                if not _HEX.match(str(base[ck])):
                    base[ck] = default[ck]
            if base["title_weight"] not in TITLE_WEIGHTS:
                base["title_weight"] = "bold"
            if base["title_case"] not in TITLE_CASES:
                base["title_case"] = "normal"
            if base["title_animation"] not in TITLE_ANIMATIONS:
                base["title_animation"] = "fade"
            if base["subtitle_position"] not in SUB_POSITIONS:
                base["subtitle_position"] = "bottom"
            try:
                base["subtitle_box_opacity"] = max(0.0, min(1.0, float(base["subtitle_box_opacity"])))
                base["subtitle_size"] = max(24, min(120, int(base["subtitle_size"])))
            except (TypeError, ValueError):
                base["subtitle_box_opacity"], base["subtitle_size"] = 0.0, 64
            v = base
        else:
            v = _str(v)
        out[k] = v
    return out


def subtitle_profile(theme: dict) -> dict:
    """The part of a theme that the render path already understands: the `visual.subtitle` profile dict."""
    t = (theme or {}).get("typography") or {}
    return {"font": "Vazirmatn", "size": t.get("subtitle_size", 64), "color": t.get("subtitle_color", "#FFFFFF"),
            "outline": t.get("subtitle_outline", "#000000"), "position": t.get("subtitle_position", "bottom")}
