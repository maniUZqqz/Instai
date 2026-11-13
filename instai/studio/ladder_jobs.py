"""Ladder jobs: write one stage with the page's text model (or derive it), save it as a new version, let the automation level pass what may pass.
Loaded by StudioConfig.ready() (see jobs.py), so the worker, the server and the tests all see the handler."""
from __future__ import annotations

from instai.agents import llm
from instai.agents.pipeline_roles import ROLES
from instai.jobs import describe
from instai.jobs.registry import handler
from instai.pages.models import ContentPage
from instai.story.models import Episode, Series

from . import ladder, ladder_bridge
from .ladder_stages import BY_KEY

describe.KIND_TEXT.update({"studio.ladder": ("نوشتن یک مرحلهٔ استودیو", "Writing a studio stage")})


def _page_of(payload: dict) -> ContentPage | None:
    s = Series.objects.filter(pk=payload.get("series_id")).select_related("page").first()
    return s.page if s else None


def _resource(payload: dict) -> str:
    st = BY_KEY.get(payload.get("stage", ""))
    if not st or st["gen"] != "llm":
        return "cpu"
    return llm.resource_for(_page_of(payload), st["task"])


class _Llm:
    def __init__(self, ctx, page, task: str):
        self.ctx, self.provider, self.cm = ctx, llm.resolve(page, task), None

    def __enter__(self):
        if self.provider.resource == "gpu":
            from instai.gpu.arbiter import ARBITER

            self.cm = ARBITER.hold(self.ctx, "llm", llm.effective_model(self.provider))
            self.cm.__enter__()
        return self.provider

    def __exit__(self, *exc):
        return self.cm.__exit__(*exc) if self.cm else False


def _row_numbers(key: str, data: dict) -> dict:
    """Roles number shots/rows themselves; keep what they wrote but make sure every row list is a list of dicts."""
    return data


@handler("studio.ladder", resource=_resource, timeout=1800)
def ladder_stage(ctx):
    p = ctx.payload
    series = Series.objects.select_related("page").get(pk=p["series_id"])
    st = ladder.stage(p["stage"])
    ep = Episode.objects.select_related("series__page").get(pk=p["episode_id"]) if p.get("episode_id") else None
    lang = str(p.get("language") or "")[:2]
    lang = lang if lang in ("fa", "en") else series.page.language
    ctx.progress(0.2, st["key"])
    prov: dict = {"instruction": str(p.get("instruction") or "")[:300]}
    if st["gen"] == "derive":
        data = ladder_bridge.derive(st["key"], series, ep)
        author, note = "system", "derived from the other stages"
        prov["provider"] = "derived"
    elif st["gen"] == "llm":
        meta = ladder_bridge.context(st["key"], series, ep, lang, prov["instruction"])
        role = ROLES[st["task"]]
        with _Llm(ctx, series.page, st["task"]) as provider:
            res = role(meta, provider=provider)
        data, author, note = res.data, "ai", (prov["instruction"] or "written by the model")
        prov.update({"provider": res.provider, "model": res.model, "attempts": res.attempts})
    else:
        from instai.core.errors import DomainError

        raise DomainError("conflict", "این مرحله با هوش مصنوعی ساخته نمی‌شود.", message_en="This stage is not written by a model.")
    prov["job_id"] = ctx.job.pk
    v = ladder.save_version(series, ep, st["key"], data, author=author, note=note, provenance=prov)
    passed = ladder.auto_pass(series, ep)
    return {"stage": st["key"], "version": v.number, "auto_approved": passed, "provider": prov.get("provider")}
