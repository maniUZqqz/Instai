"""Which providers exist and which one is active. Availability is detected at call time, never hard-coded."""
from __future__ import annotations

import contextlib
import os

from instai.core import settings_store

from .base import TextProvider
from .fake import FakeProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

_OVERRIDE: TextProvider | None = None

PROVIDER_INFO = {
    "fake": {"label": "نمونه‌ی آزمایشی (Fake)", "resource": "cpu", "licence": "—",
             "note": "خروجی ساختگی برای آزمایش و نمایش؛ برای تولید واقعی نیست."},
    "ollama": {"label": "Ollama (محلی)", "resource": "gpu", "licence": "بسته به مدل",
               "note": "مدل‌ها روی کارت گرافیک اجرا می‌شوند."},
    "openai": {"label": "API سازگار با OpenAI (مثلاً MetisAI)", "resource": "net", "licence": "شرایط سرویس‌دهنده",
               "note": "نشانی و مدل در تنظیمات؛ کلید فقط در پرونده‌ی .env ذخیره می‌شود."},
}


def build_provider(name: str) -> TextProvider:
    if name == "fake":
        return FakeProvider()
    if name == "openai":
        return OpenAICompatProvider(settings_store.effective("openai_base_url"), settings_store.effective("openai_model"),
                                    settings_store.effective("openai_json_mode"))
    return OllamaProvider(settings_store.effective("ollama_url"), settings_store.effective("ollama_model"))


def active_provider_name() -> str:
    if _OVERRIDE is not None:
        return _OVERRIDE.name
    name = str(settings_store.effective("llm_provider") or "ollama")
    return name if name in PROVIDER_INFO else "ollama"


def get_text_provider(name: str | None = None) -> TextProvider:
    if _OVERRIDE is not None and name is None:
        return _OVERRIDE
    return build_provider(name or active_provider_name())


@contextlib.contextmanager
def use_provider(provider: TextProvider):
    """Tests: force one provider instance (e.g. FakeProvider(fail_first=2)) for everything in the block."""
    global _OVERRIDE
    prev, _OVERRIDE = _OVERRIDE, provider
    try:
        yield provider
    finally:
        _OVERRIDE = prev


def set_provider_for_tests(provider: TextProvider | None) -> None:
    global _OVERRIDE
    _OVERRIDE = provider


_DESCRIBE_CACHE: dict = {"at": 0.0, "key": None, "value": None}


def describe_text_providers() -> list[dict]:
    """Provider list with live health (cached 8 s: health checks of a missing local service are slow to fail)."""
    import time

    key = (active_provider_name(), settings_store.effective("ollama_url"), settings_store.effective("openai_base_url"),
           settings_store.effective("ollama_model"), settings_store.effective("openai_model"), api_key_state()["set"])
    if _DESCRIBE_CACHE["key"] == key and time.time() - _DESCRIBE_CACHE["at"] < 8 and _OVERRIDE is None:
        return _DESCRIBE_CACHE["value"]
    active = active_provider_name()
    out = []
    for name, info in PROVIDER_INFO.items():
        p = build_provider(name) if not (_OVERRIDE and _OVERRIDE.name == name) else _OVERRIDE
        h = p.health()
        out.append({"id": name, **info, "active": name == active, "ok": h["ok"], "detail": h["detail"], "models": h["models"],
                    "model": p.model})
    _DESCRIBE_CACHE.update(at=time.time(), key=key, value=out)
    return out


def api_key_state() -> dict:
    key = os.environ.get("INSTAI_OPENAI_API_KEY", "")
    return {"set": bool(key), "hint": ("…" + key[-4:]) if len(key) >= 8 else ""}
