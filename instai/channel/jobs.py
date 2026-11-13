"""Channel jobs: plan a season (model, with the skeleton as the fallback)."""
from __future__ import annotations

from instai.agents import llm
from instai.agents import pipeline_roles as roles
from instai.agents.runner import AgentError
from instai.jobs import describe
from instai.jobs.registry import handler
from instai.story.models import Series

from . import conventions, planner, services

describe.KIND_TEXT.update({"channel.season": ("برنامه‌ریزی فصل مینی‌سریال", "Planning the mini-series season")})


def _page(payload: dict):
    s = Series.objects.filter(pk=payload.get("series_id")).select_related("page").first()
    return s.page if s else None


@handler("channel.season", resource=lambda payload: llm.resource_for(_page(payload), "season_plan"), timeout=1800)
def season(ctx):
    series = Series.objects.select_related("page").get(pk=ctx.payload["series_id"])
    ch = services.get_channel(series)
    lang = (ctx.payload.get("language") or series.languages or [series.page.language])
    lang = lang if isinstance(lang, str) and lang else (lang[0] if lang else series.page.language)
    lang = lang if lang in ("fa", "en") else "fa"
    g = conventions.genre(ch.genre)
    meta = {"language": lang, "format": series.page.format, "title": series.title, "premise": series.premise, "episodes_count": ch.episodes_per_season, "runtime_sec": ch.runtime_sec,
            "characters": [{"name": c["name"], "role": c["role"], "marker": c.get("marker", ""), "catchphrase": c.get("catchphrase", "")} for c in ch.cast],
            "genre_notes": {"genre": ch.genre, "summary": g["summary_en"], "beats": conventions.beat_plan(ch.genre, ch.runtime_sec), "conventions": [c["en"] for c in conventions.CONVENTIONS][:8]},
            "instruction": ctx.payload.get("instruction", "")}
    ctx.progress(0.2, "planning")
    fallback = False
    try:
        res = roles.season_planner(meta, provider=llm.resolve(series.page, "season_plan"))
        plan, info = res.data, {"provider": res.provider, "model": res.model}
    except AgentError as e:        # a weak model never stalls the season: the deterministic skeleton is used and flagged
        plan = planner.skeleton_season(ch.episodes_per_season, ch.runtime_sec, fa=lang == "fa", characters=[c["name"] for c in ch.cast], title=series.title)
        info, fallback = {"provider": "skeleton", "errors": e.errors[:3]}, True
    services.apply_season_plan(ch, plan)
    rep = services.report(ch)
    return {"episodes": len(ch.slate), "fallback": fallback, "ok": rep["validation"]["ok"], "errors": [e["code"] for e in rep["validation"]["errors"]][:10], **info}
