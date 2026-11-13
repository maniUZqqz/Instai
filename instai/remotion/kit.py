"""The "style kit" a Remotion composition reads (remotion/src/kit/theme.ts `StyleKit`): one InstAI art style + its theme, reduced to what a
title, an explainer or a kinetic text needs: the palette, how the style MOVES, how fast its poses change, and the title typography.

The kit is built here, from the style library (instai/styles), and only here: the preview in the page and the rendered video receive the same JSON."""
from __future__ import annotations

from instai.styles import library, schema

DEFAULT_KEY = "cinematic_realistic"


def _palette(style: dict, theme: dict | None) -> dict:
    """background, primary, secondary, accent, shadow, highlight: the style's own colours, else its theme's, else the schema default."""
    for src in (style.get("palette"), (theme or {}).get("palette")):
        if isinstance(src, list) and len(src) >= 6:
            return dict(zip(schema.PALETTE_ROLES, src[:6]))
    return dict(zip(schema.PALETTE_ROLES, ["#14181F", "#3B4A5C", "#B9824B", "#E8C98F", "#05070A", "#F3E9D8"]))


def style_kit(style_key: str | None = None, theme_key: str | None = None) -> dict:
    """{key, theme_key, name, name_fa, name_en, animation, animation_fa, animation_en, family, realism, fps_feel, palette, typography, mood}.
    An unknown style falls back to the first built-in one; `theme_key` (else the style's own `theme_key`) picks the typography."""
    style = library.get_style(style_key or "") or library.get_style(DEFAULT_KEY) or next(iter(library.list_presets("style")))
    theme = library.get_theme(theme_key or style.get("theme_key") or "")
    typo = {**schema.THEME_FIELDS["typography"], **((theme or {}).get("typography") or {})}
    anim = schema.ANIMATIONS.get(style.get("animation"), {})
    return {
        "key": style["key"], "theme_key": (theme or {}).get("key", ""),
        "name": style.get("name_en") or style.get("name_fa") or style["key"], "name_fa": style.get("name_fa", ""), "name_en": style.get("name_en", ""),
        "animation": style.get("animation", "motion_graphics"), "animation_fa": anim.get("fa", ""), "animation_en": anim.get("en", ""),
        "family": style.get("family", "graphic"), "realism": style.get("realism", "graphic"), "fps_feel": int(style.get("fps_feel") or 12),
        "palette": _palette(style, theme),
        "typography": {"title_weight": typo.get("title_weight", "bold"), "title_case": typo.get("title_case", "normal"),
                       "title_animation": typo.get("title_animation", "fade"), "subtitle_color": typo.get("subtitle_color", "#FFFFFF")},
        "mood": style.get("mood") or (theme or {}).get("mood", ""), "group": style.get("group", ""),
    }


def all_kits() -> list[dict]:
    """The kit of every style of the library (built-in and the owner's own), in the library's order: the style picker and its colour chips."""
    out = []
    for s in library.list_presets("style"):
        k = style_kit(s["key"])
        out.append({**k, "builtin": bool(s.get("builtin"))})
    return out
