"""Text-model choice per page and per task group, with fallback.

A page's `production.llm` profile says, for each task group (brainstorm, research, bible, script, translate, strategy), which provider
(Ollama / OpenAI-compatible API / fake) and which model to use; an empty choice means "the global default from Settings". A fallback
choice is tried when the primary one raises a provider error (offline, quota, model missing). Keys stay in `.env`; only provider and
model NAMES are stored on the page.
"""
from __future__ import annotations

import logging

from instai.core import settings_store
from instai.providers import registry
from instai.providers.base import LLMResult, ProviderError, TextProvider
from instai.providers.fake import FakeProvider
from instai.providers.ollama import OllamaProvider
from instai.providers.openai_compat import OpenAICompatProvider

log = logging.getLogger("instai.llm")

# task (the `task` name passed to call_json / the fake provider) -> group shown in the UI
TASK_GROUP = {
    "strategy": "strategy",
    "ideas": "brainstorm", "idea_refine": "brainstorm", "idea_merge": "brainstorm", "consequence_map": "brainstorm", "timeline": "brainstorm",
    "character_bible": "brainstorm",
    "canon": "research", "research_queries": "research", "research_claims": "research",
    "bible": "bible", "series_plan": "bible",
    "script": "script", "storyboard": "script", "continuity": "script", "design": "script", "casting": "script",
    "translate": "translate", "translate_shots": "translate",
}
GROUPS = [
    {"key": "strategy", "label_fa": "استراتژی صفحه", "label_en": "Page strategy"},
    {"key": "brainstorm", "label_fa": "ایده‌پردازی، نقشهٔ پیامدها و خط زمانی", "label_en": "Brainstorm, consequence map & timeline"},
    {"key": "research", "label_fa": "پژوهش و راستی‌آزمایی", "label_en": "Research & fact-check"},
    {"key": "bible", "label_fa": "کتاب سریال و ساختار قسمت‌ها", "label_en": "Series bible & composition"},
    {"key": "script", "label_fa": "فیلم‌نامه، استوری‌بورد، طراحی و انتخاب صدا", "label_en": "Scripts, storyboard, design & casting"},
    {"key": "translate", "label_fa": "ترجمهٔ قسمت", "label_en": "Episode translation"},
]


def group_of(task: str) -> str:
    return TASK_GROUP.get(task, "script")


class FallbackProvider(TextProvider):
    """Tries each provider in order; the first that does not raise ProviderError wins. `used` records which one answered."""

    def __init__(self, providers: list[TextProvider]):
        self.providers = providers
        self.used: TextProvider = providers[0]

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.providers[0].name

    @property
    def resource(self) -> str:  # type: ignore[override]
        return self.providers[0].resource

    @property
    def model(self) -> str:
        return self.providers[0].model

    def health(self) -> dict:
        return self.providers[0].health()

    def unload(self) -> None:
        for p in self.providers:
            try:
                p.unload()
            except Exception:  # noqa: BLE001
                pass

    def generate(self, messages, **kw) -> LLMResult:
        last: ProviderError | None = None
        for p in self.providers:
            try:
                res = p.generate(messages, **kw)
                self.used = p
                return res
            except ProviderError as e:
                last = e
                log.warning("text provider %s failed (%s); trying the fallback", p.name, e)
        assert last is not None
        raise last


def _build(provider: str, model: str, task: str) -> TextProvider:
    provider = provider or registry.active_provider_name()
    if provider == "fake":
        return FakeProvider()
    if provider == "openai":
        return OpenAICompatProvider(settings_store.effective("openai_base_url"), model or settings_store.effective("openai_model"),
                                    settings_store.effective("openai_json_mode"))
    url = settings_store.effective("ollama_url")
    model = model or _default_ollama_model(url, task)
    return OllamaProvider(url, model)


def _default_ollama_model(url: str, task: str) -> str:
    """Translation prefers an installed translategemma model when no model was chosen."""
    chosen = settings_store.effective("ollama_model")
    if group_of(task) != "translate":
        return chosen
    try:
        models = OllamaProvider(url, chosen).list_models()
    except Exception:  # noqa: BLE001
        return chosen
    for m in models:
        if m.lower().startswith("translategemma"):
            return m
    return chosen


def llm_spec(page, task: str) -> dict:
    """{'primary': {provider, model}, 'fallback': {provider, model}} as stored on the page (empty = global default)."""
    cfg = page.profile("production").get("llm") if page is not None else None
    cfg = cfg or {}
    primary = (cfg.get("groups") or {}).get(group_of(task)) or cfg.get("default") or {}
    return {"primary": {"provider": primary.get("provider", ""), "model": primary.get("model", "")}, "fallback": cfg.get("fallback") or {}}


def resolve(page, task: str) -> TextProvider:
    """The provider to use for `task` on `page`. Tests that force a provider (registry.use_provider) win over everything."""
    forced = registry._OVERRIDE
    if forced is not None:
        return forced
    spec = llm_spec(page, task)
    primary = _build(spec["primary"]["provider"], spec["primary"]["model"], task)
    fb = spec["fallback"]
    if fb.get("provider") or fb.get("model"):
        second = _build(fb.get("provider", ""), fb.get("model", ""), task)
        if (second.name, second.model) != (primary.name, primary.model):
            return FallbackProvider([primary, second])
    return primary


def resource_for(page, task: str) -> str:
    """cpu | gpu | net for the primary provider of `task`, without building it (used when a job is queued: no network calls)."""
    forced = registry._OVERRIDE
    if forced is not None:
        return forced.resource
    prov = llm_spec(page, task)["primary"]["provider"] or registry.active_provider_name()
    return {"ollama": "gpu", "openai": "net", "fake": "cpu"}.get(prov, "gpu")


def describe(page) -> dict:
    """What would be used right now for each task group (for the settings screen)."""
    out = {}
    for g in GROUPS:
        spec = llm_spec(page, {"strategy": "strategy", "brainstorm": "ideas", "research": "canon", "bible": "bible", "script": "script",
                               "translate": "translate"}[g["key"]])
        prov = spec["primary"]["provider"] or registry.active_provider_name()
        out[g["key"]] = {"provider": prov, "model": spec["primary"]["model"], "explicit": bool(spec["primary"]["provider"] or spec["primary"]["model"])}
    return out
