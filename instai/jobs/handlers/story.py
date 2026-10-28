"""Story jobs: LLM-driven generation. Each handler builds a context from the DB, calls an agent role (validated JSON),
and persists through application services."""
from __future__ import annotations

from instai import research
from instai.agents import roles
from instai.jobs.registry import handler
from instai.pages import formats
from instai.providers.registry import get_text_provider
from instai.story import services, states
from instai.story.models import Episode, Series, Source


def _llm_resource(payload: dict) -> str:
    return get_text_provider().resource


def page_meta(page) -> dict:
    ident, prod = page.profile("identity"), page.profile("production")
    return {"page_name": page.name, "format": page.format, "language": page.language, "idea": page.idea, "niche": ident["niche"],
            "audience": ident["audience"], "tone": ident["tone"], "episodes_count": prod["episodes_per_series"],
            "episode_length_sec": prod["episode_length_sec"]}


def series_meta(series: Series) -> dict:
    page = series.page
    m = page_meta(page)
    m.update(title=series.title, premise=series.premise, branch_point=series.branch_point, alternative_timeline=series.alternative_timeline,
             content_rules=series.content_rules, is_fan_content=series.is_fan_content, episodes_count=series.target_episodes,
             characters=[c.name for c in page.characters.all()], memory=services.memory_digest(series))
    return m


def episode_meta(ep: Episode) -> dict:
    s = ep.series
    m = series_meta(s)
    m.update(series_title=s.title, memory=services.memory_digest(s, before_episode=ep.number), duration_sec=ep.duration_sec,
             episode={"number": ep.number, "title": ep.title, "logline": ep.logline, "goal": ep.goal, "cliffhanger": ep.cliffhanger},
             previous_summaries=services.memory_digest(s, before_episode=ep.number)["previous_summaries"])
    if ep.research:
        m["claims"] = [{"claim": c["claim"], "stance": c["stance"]} for c in ep.research.get("claims", [])]
    return m


@handler("story.strategy", resource=_llm_resource, timeout=900)
def strategy(ctx):
    """Idea -> strategy proposal. Nothing is saved: the owner edits it in the wizard first."""
    from instai.gpu.arbiter import ARBITER

    meta = ctx.payload
    ctx.progress(0.1, "strategy")
    with _gpu_if_needed(ctx, ARBITER):
        res = roles.strategist(meta)
    return {"strategy": res.data, "meta": res.meta()}


@handler("story.plan", resource=_llm_resource, timeout=1200)
def plan(ctx):
    """Series plan proposal (arcs + episodes). Saved only when the owner applies it."""
    from instai.gpu.arbiter import ARBITER

    series = Series.objects.get(pk=ctx.payload["series_id"])
    meta = series_meta(series)
    for k in ("episodes_count", "premise", "branch_point", "title"):
        if ctx.payload.get(k):
            meta[k] = ctx.payload[k]
    ctx.progress(0.1, "series plan")
    with _gpu_if_needed(ctx, ARBITER):
        res = roles.story_architect(meta)
    return {"plan": res.data, "meta": res.meta()}


@handler("story.script", resource=_llm_resource, timeout=1800)
def script(ctx):
    from instai.gpu.arbiter import ARBITER

    ep = Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"])
    prev = ep.state
    if ep.state not in (states.SCRIPTING,):
        services.transition(ep, states.SCRIPTING, reason="generate script", actor="system")
    try:
        ctx.progress(0.1, "script")
        with _gpu_if_needed(ctx, ARBITER):
            res = roles.scriptwriter(episode_meta(ep))
        for n in res.notes:
            ctx.log(n)
        services.save_script(ep, res.data, note="generated")
        services.transition(ep, states.SCRIPT_REVIEW, reason="script ready", actor="system")
    except BaseException:
        ep.refresh_from_db()
        if ep.state == states.SCRIPTING:
            services.transition(ep, prev if prev != states.SCRIPTING else states.PLANNED, reason="script generation failed", actor="system")
        raise
    return {"episode_id": ep.pk, "checks": ep.script_checks, "meta": res.meta()}


@handler("story.storyboard", resource=_llm_resource, timeout=1800)
def storyboard(ctx):
    from instai.gpu.arbiter import ARBITER

    ep = Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"])
    if not ep.script:
        from instai.core.errors import DomainError

        raise DomainError("not_ready", "ابتدا فیلم‌نامه را بسازید.")
    page = ep.series.page
    meta = episode_meta(ep)
    meta.update(script=ep.script, visual_style=_style(page), allowed_techniques=page.profile("production")["allowed_techniques"])
    ctx.progress(0.1, "storyboard")
    with _gpu_if_needed(ctx, ARBITER):
        res, info = roles.storyboarder(meta)
    for n in res.notes:
        ctx.log(n, "warning" if info["fallback"] else "info")
    services.save_storyboard(ep, res.data, note="generated" + (" (fallback)" if info["fallback"] else ""))
    return {"episode_id": ep.pk, "fallback": info["fallback"], "estimate": ep.estimate, "meta": res.meta()}


def _style(page) -> str:
    vis = page.profile("visual")
    base = next((s["prompt"] for s in formats.STYLES if s["key"] == vis["style_key"]), "")
    return ", ".join(x for x in (base, vis.get("style_notes", "")) if x)


@handler("story.research", resource=_llm_resource, timeout=1800)
def research_job(ctx):
    """Explainers: queries -> fetched sources (system-verified) + owner's sources -> sourced claims, stance-labelled."""
    from instai.gpu.arbiter import ARBITER

    ep = Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"])
    topic = ctx.payload.get("topic") or ep.title or ep.series.title
    meta = episode_meta(ep)
    meta["topic"] = topic
    lang = ep.series.page.language
    fetcher = research.get_fetcher(ctx.payload.get("fetcher"))
    with _gpu_if_needed(ctx, ARBITER):
        ctx.progress(0.1, "queries")
        q = roles.researcher_queries(meta)
        queries = q.data["queries"]
        fetched: list[dict] = []
        for i, query in enumerate(queries[:6]):
            ctx.check()
            ctx.progress(0.2 + 0.3 * i / max(1, len(queries)), f"fetch: {query}")
            for item in fetcher.search(query, lang, 2):
                if not any(f["url"] == item["url"] and item["url"] for f in fetched):
                    fetched.append({**item, "id": len(fetched) + 1})
        for s in Source.objects.filter(page=ep.series.page, added_by="user").filter(episode=ep) | Source.objects.filter(series=ep.series, added_by="user"):
            if s.extract and not any(f.get("pk") == s.pk for f in fetched):
                fetched.append({"id": len(fetched) + 1, "pk": s.pk, "title": s.title, "url": s.url, "extract": s.extract, "verified": s.verified})
        ctx.progress(0.6, "claims")
        meta["sources"] = [{"id": f["id"], "title": f["title"], "extract": f["extract"][:1200]} for f in fetched]
        c = roles.researcher_claims(meta)
    out = services.store_research(ep, topic, queries, fetched, c.data)
    return {"episode_id": ep.pk, "sources": len(fetched), "claims": len(out["claims"]), "unsupported": out["unsupported_count"], "fetcher": fetcher.name}


@handler("story.continuity", resource=_llm_resource, timeout=900)
def continuity(ctx):
    from instai.gpu.arbiter import ARBITER

    ep = Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"])
    meta = episode_meta(ep)
    meta["script"] = ep.script
    with _gpu_if_needed(ctx, ARBITER):
        res = roles.continuity_manager(meta)
    n = services.apply_continuity(ep, res.data)
    return {"episode_id": ep.pk, "entries": n, "meta": res.meta()}


class _gpu_if_needed:
    """Hold the GPU arbiter only when the active text provider runs locally on the GPU (Ollama)."""

    def __init__(self, ctx, arbiter):
        self.ctx, self.arbiter, self.cm = ctx, arbiter, None

    def __enter__(self):
        prov = get_text_provider()
        if prov.resource == "gpu":
            self.cm = self.arbiter.hold(self.ctx, "llm", prov.model)
            return self.cm.__enter__()
        return None

    def __exit__(self, *exc):
        if self.cm:
            return self.cm.__exit__(*exc)
        return False
