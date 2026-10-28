"""Read/write AppSetting rows with a small TTL cache (the worker is a separate process, so keep the TTL short)."""
from __future__ import annotations

import os
import time
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}
TTL = 3.0

# key -> (env var that supplies the default, built-in default)
DEFAULTS: dict[str, tuple[str, Any]] = {
    "llm_provider": ("INSTAI_LLM_PROVIDER", "ollama"),
    "ollama_url": ("INSTAI_OLLAMA_URL", "http://127.0.0.1:11434"),
    "ollama_model": ("INSTAI_OLLAMA_MODEL", ""),
    "openai_base_url": ("INSTAI_OPENAI_BASE_URL", ""),
    "openai_model": ("INSTAI_OPENAI_MODEL", ""),
    "openai_json_mode": ("INSTAI_OPENAI_JSON_MODE", "json_object"),
    "comfyui_url": ("INSTAI_COMFYUI_URL", "http://127.0.0.1:8188"),
    "moss_tts_url": ("INSTAI_MOSS_TTS_URL", ""),
    "moss_sfx_url": ("INSTAI_MOSS_SFX_URL", ""),
    "acestep_url": ("INSTAI_ACESTEP_URL", ""),
    "pocket_url": ("INSTAI_POCKET_URL", "http://127.0.0.1:5620"),
    "piper_voice": ("INSTAI_PIPER_VOICE", "fa_IR-gyro-medium"),
    "tts_engine": ("INSTAI_TTS_ENGINE", "auto"),
    "openai_price_in_per_1k": ("INSTAI_OPENAI_PRICE_IN", "0"),
    "openai_price_out_per_1k": ("INSTAI_OPENAI_PRICE_OUT", "0"),
    "sfx_engine": ("INSTAI_SFX_ENGINE", "auto"),
    "music_engine": ("INSTAI_MUSIC_ENGINE", "auto"),
    "image_workflow": ("INSTAI_IMAGE_WORKFLOW", "flux_dev_fp8_t2i"),
    "image_engine": ("INSTAI_IMAGE_ENGINE", "auto"),
    "research_fetch": ("INSTAI_RESEARCH_FETCH", "off"),
    "comfyui_dir": ("COMFYUI_DIR", ""),
    "ui_language": ("INSTAI_UI_LANGUAGE", "fa"),
}
PUBLIC_KEYS = tuple(DEFAULTS)


def get_setting(key: str, default: Any = None) -> Any:
    if os.environ.get("INSTAI_WORKER_MODE"):      # a worker PC has no database: its settings come from .env
        return default
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < TTL:
        return hit[1] if hit[1] is not None else default
    from django.db import DatabaseError

    from .models import AppSetting

    try:
        row = AppSetting.objects.filter(key=key).first()
    except DatabaseError:  # database not created/migrated yet: fall back to .env / defaults
        return default
    val = row.value if row else None
    _CACHE[key] = (now, val)
    return val if val is not None else default


def effective(key: str) -> Any:
    """DB value -> environment/.env -> built-in default."""
    v = get_setting(key)
    if v not in (None, ""):
        return v
    env, default = DEFAULTS.get(key, ("", None))
    return (os.environ.get(env, "").strip() if env else "") or default


def set_setting(key: str, value: Any) -> None:
    from .models import AppSetting

    AppSetting.objects.update_or_create(key=key, defaults={"value": value})
    _CACHE.pop(key, None)


def clear_cache() -> None:
    _CACHE.clear()


def all_effective() -> dict[str, Any]:
    return {k: effective(k) for k in PUBLIC_KEYS}
