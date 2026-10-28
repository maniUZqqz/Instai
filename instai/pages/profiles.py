"""Settings profiles: six reusable kinds. Data is normalised against these defaults (unknown keys dropped, types coerced),
so a profile is always complete and safe to copy to another page."""
from __future__ import annotations

import copy
from typing import Any

KINDS = ["identity", "strategy", "visual", "audio", "production", "publishing"]

DEFAULTS: dict[str, dict[str, Any]] = {
    "identity": {"display_name": "", "handle": "", "bio": "", "niche": "", "theme": "", "audience": "", "tone": "",
                 "languages": ["fa"], "content_rules": []},
    "strategy": {"positioning": "", "audience_insight": "", "tone_guidelines": "", "pillars": [], "hashtags": [], "risks": [],
                 "posting_goal": ""},
    "visual": {"style_key": "modern_tv_anime", "realism": "anime", "theme_key": "", "style_notes": "", "aspect_ratio": "9:16", "palette": [],
               "negative_prompt": "",
               "subtitle": {"font": "Tahoma", "size": 64, "color": "#FFFFFF", "outline": "#000000", "position": "bottom"}},
    "audio": {"narration_engine": "auto", "narration_voice": "", "language": "fa", "music_enabled": False, "music_mood": "calm",
              "music_volume_db": -22, "sfx_enabled": False, "target_lufs": -16},
    "production": {"preset": "balanced", "episodes_per_series": 5, "episode_length_sec": 45, "preview_default": True,
                   "allowed_techniques": ["still_kenburns", "parallax_25d"], "max_gpu_minutes_per_episode": 60, "fps": 30,
                   "preview_height": 640, "final_height": 1920,
                   # studio gates: animatic / design / casting must be approved before an episode goes to production (off = old behaviour)
                   "studio_mode": False,
                   # text model choice per task group: {"default": {provider, model}, "fallback": {...}, "groups": {group: {provider, model}}}
                   "llm": {"default": {"provider": "", "model": ""}, "fallback": {"provider": "", "model": ""}, "groups": {}}},
    "publishing": {"platform": "instagram", "per_week": 3, "days": ["sat", "mon", "wed"], "time": "20:00", "caption_style": "",
                   "hashtags": [], "auto_publish": False},
}

LLM_PROVIDERS = ["", "fake", "ollama", "openai"]
LLM_GROUPS = ["strategy", "brainstorm", "research", "bible", "script", "translate"]
ENUMS = {
    ("visual", "aspect_ratio"): ["9:16", "1:1", "16:9", "4:5"],
    ("visual", "realism"): ["realistic", "semi_realistic", "anime_like", "anime", "cartoon", "cartoon_3d", "graphic", "stylized_art"],
    ("production", "preset"): ["preview", "balanced", "quality", "overnight"],
    ("audio", "narration_engine"): ["auto", "moss", "piper", "fake"],
}
INT_RANGES = {
    ("production", "episodes_per_series"): (1, 60), ("production", "episode_length_sec"): (10, 180),
    ("production", "max_gpu_minutes_per_episode"): (1, 1440), ("production", "fps"): (12, 60),
    ("production", "preview_height"): (240, 1280), ("production", "final_height"): (480, 2560),
    ("publishing", "per_week"): (1, 21), ("audio", "target_lufs"): (-30, -8), ("audio", "music_volume_db"): (-60, 0),
}


def default_data(kind: str) -> dict:
    return copy.deepcopy(DEFAULTS[kind])


def _coerce(value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        return bool(value) if not isinstance(value, str) else value.strip().lower() in ("1", "true", "yes")
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, str):
        return "" if value is None else str(value)
    if isinstance(default, list):
        if isinstance(value, list):
            return value
        return [] if value in (None, "") else [value]
    if isinstance(default, dict):
        return value if isinstance(value, dict) else copy.deepcopy(default)
    return value


def normalize_llm(v: Any) -> dict:
    """Keep only known providers and task groups; models are free text (names of installed Ollama models / API models)."""
    def spec(x: Any) -> dict:
        x = x if isinstance(x, dict) else {}
        prov = str(x.get("provider") or "").strip()
        return {"provider": prov if prov in LLM_PROVIDERS else "", "model": str(x.get("model") or "").strip()[:120]}
    v = v if isinstance(v, dict) else {}
    groups = v.get("groups") if isinstance(v.get("groups"), dict) else {}
    return {"default": spec(v.get("default")), "fallback": spec(v.get("fallback")),
            "groups": {g: spec(groups[g]) for g in LLM_GROUPS if g in groups and (spec(groups[g])["provider"] or spec(groups[g])["model"])}}


def normalize(kind: str, data: dict | None) -> dict:
    """Merge into the defaults. Nested dicts (e.g. visual.subtitle) are merged one level deep."""
    if kind not in DEFAULTS:
        raise ValueError(f"unknown profile kind: {kind}")
    base = default_data(kind)
    data = data or {}
    out: dict[str, Any] = {}
    for k, d in base.items():
        v = _coerce(data.get(k, d), d)
        if isinstance(d, dict) and isinstance(v, dict):
            v = {**d, **{kk: vv for kk, vv in v.items() if kk in d}}
        if (kind, k) == ("production", "llm"):
            v = normalize_llm(v)
        if (kind, k) in ENUMS and v not in ENUMS[(kind, k)]:
            v = d
        if (kind, k) in INT_RANGES:
            lo, hi = INT_RANGES[(kind, k)]
            v = max(lo, min(hi, int(v)))
        out[k] = v
    return out


def validate_techniques(data: dict) -> list[str]:
    from instai.agents.schemas import TECHNIQUES

    return [t for t in data.get("allowed_techniques", []) if t not in TECHNIQUES]
