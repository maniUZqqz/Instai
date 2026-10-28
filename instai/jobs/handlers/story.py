"""Story jobs: LLM-driven generation. Each handler builds a context from the DB, calls an agent role (validated JSON) with the page's own text-model
choice (instai.agents.llm: per page and per task group, with fallback), and persists through application services.
(The development-room and pre-production jobs live in instai/studio/jobs.py.)"""
from __future__ import annotations

from instai import research
from instai.agents import llm, roles
from instai.core.errors import DomainError
from instai.jobs.registry import handler
from instai.pages import formats
from instai.pages.models import ContentPage
from instai.story import services, states
from instai.story.models import Episode, Series, Source


def _page_of(payload: dict) -> ContentPage | None:
    if payload.get("series_id"):
        s = Series.objects.filter(pk=payload["series_id"]).select_related("page").first()
        return s.page if s else None
    if payload.get("episode_id"):
        e = Episode.objects.filter(pk=payload["episode_id"]).select_related("series__page").first()
        return e.series.page if e else None
    if payload.get("page_id"):
        return ContentPage.objects.filter(pk=payload["page_id"]).first()
    return None


def _resource(task: str):
    return lambda payload: llm.resource_for(_page_of(payload), task)


class _Llm:
    """The page's provider for `task`; holds the GPU arbiter only while a local (Ollama) model runs."""

    def __init__(self, ctx, page, task: str):
        self.ctx, self.provider, self.cm = ctx, llm.resolve(page, task), None

    def __enter__(self):
        if self.provider.resource == "gpu":
            from instai.gpu.arbiter import ARBITER

            self.cm = ARBITER.hold(self.ctx, "llm", self.provider.model)
            self.cm.__enter__()
        return self.provider

    def __exit__(self, *exc):
        return self.cm.__exit__(*exc) if self.cm else False


def page_meta(page) -> dict:
    ident, prod = page.profile("identity"), page.profile("production")
    return {"page_name": page.name, "format": page.format, "language": page.language, "idea": page.idea, "niche": ident["niche"],
            "audience": ident["audience"], "tone": ident["tone"], "episodes_count": prod["episodes_per_series"],
            "episode_length_sec": prod["episode_length_sec"]}


def bible_digest(series: Series) -> dict:
    """The series bible (approved or draft), trimmed for prompts: tone, themes, world rules, characters, arcs."""
    from instai.studio import services as studio

    b = studio.bible_dict(series)
    if not b["exists"]:
        return {}
    d = b["data"]
    return {"status": b["status"], "logline": d["logline"], "tone": d["tone"], "themes": d["themes"], "world_rules": d["world_rules"][:10],
            "characters": [{k: c[k] for k in ("name", "role", "appearance", "personality", "motivations")} for c in d["characters"][:10]],
            "arcs": [{k: a[k] for k in ("title", "summary", "goal", "cliffhanger")} for a in d["arcs"][:10]], "visual_notes": d["visual_notes"]}


def series_meta(series: Series) -> dict:
    page = series.page
    m = page_meta(page)
    if series.languages:
        m["language"] = series.languages[0]
    m.update(title=series.title, premise=series.premise, branch_point=series.branch_point, alternative_timeline=series.alternative_timeline,
             content_rules=series.content_rules, is_fan_content=series.is_fan_content, episodes_count=series.target_episodes,
             characters=[c.name for c in page.characters.all()], memory=services.memory_digest(series))
    bible = bible_digest(series)
    if bible:
        m["bible"] = bible
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


@handler("story.strategy", resource=_resource("strategy"), timeout=900)
def strategy(ctx):
    """Idea -> strategy proposal. Nothing is saved: the owner edits it in the wizard first."""
    meta = ctx.payload
    ctx.progress(0.1, "strategy")
    with _Llm(ctx, _page_of(ctx.payload), "strategy") as prov:
        res = roles.strategist(meta, provider=prov)
    return {"strategy": res.data, "meta": res.meta()}


@handler("story.plan", resource=_resource("series_plan"), timeout=1200)
def plan(ctx):
    """Series plan proposal (arcs + episodes), built on the series bible when there is one. Saved only when the owner applies it."""
    series = Series.objects.select_related("page").get(pk=ctx.payload["series_id"])
    meta = series_meta(series)
    for k in ("episodes_count", "premise", "branch_point", "title"):
        if ctx.payload.get(k):
            meta[k] = ctx.payload[k]
    ctx.progress(0.1, "series plan")
    with _Llm(ctx, series.page, "series_plan") as prov:
        res = roles.story_architect(meta, provider=prov)
    return {"plan": res.data, "meta": res.meta()}


@handler("story.script", resource=_resource("script"), timeout=1800)
def script(ctx):
    ep = Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"])
    prev = ep.state
    if ep.state not in (states.SCRIPTING,):
        services.transition(ep, states.SCRIPTING, reason="generate script", actor="system")
    try:
        ctx.progress(0.1, "script")
        with _Llm(ctx, ep.series.page, "script") as prov:
            res = roles.scriptwriter(episode_meta(ep), provider=prov)
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


@handler("story.storyboard", resource=_resource("storyboard"), timeout=1800)
def storyboard(ctx):
    ep = Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"])
    if not ep.script:
        raise DomainError("not_ready", "ابتدا فیلم‌نامه را بسازید.")
    page = ep.series.page
    meta = episode_meta(ep)
    meta.update(script=ep.script, visual_style=_style(page), allowed_techniques=page.profile("production")["allowed_techniques"])
    ctx.progress(0.1, "storyboard")
    with _Llm(ctx, page, "storyboard") as prov:
        res, info = roles.storyboarder(meta, provider=prov)
    for n in res.notes:
        ctx.log(n, "warning" if info["fallback"] else "info")
    services.save_storyboard(ep, res.data, note="generated" + (" (fallback)" if info["fallback"] else ""))
    return {"episode_id": ep.pk, "fallback": info["fallback"], "estimate": ep.estimate, "meta": res.meta()}


def _style(page) -> str:
    """The page's visual style as one text: the style preset + theme + the owner's notes (the library composes them)."""
    from instai.styles import library

    vis = page.profile("visual")
    comp = library.compose(vis.get("style_key", ""), vis.get("theme_key", ""), vis.get("style_notes", ""))
    if comp["positive"]:
        return comp["positive"]
    base = next((s["prompt"] for s in formats.STYLES if s["key"] == vis["style_key"]), "")
    return ", ".join(x for x in (base, vis.get("style_notes", "")) if x)


@handler("story.research", resource=_resource("research_queries"), timeout=1800)
def research_job(ctx):
    """Explainers: queries -> fetched sources (system-verified) + owner's sources -> sourced claims, stance-labelled."""
    ep = Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"])
    topic = ctx.payload.get("topic") or ep.title or ep.series.title
    meta = episode_meta(ep)
    meta["topic"] = topic
    lang = ep.series.page.language
    fetcher = research.get_fetcher(ctx.payload.get("fetcher"))
    with _Llm(ctx, ep.series.page, "research_queries") as prov:
        ctx.progress(0.1, "queries")
        q = roles.researcher_queries(meta, provider=prov)
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
        c = roles.researcher_claims(meta, provider=prov)
    out = services.store_research(ep, topic, queries, fetched, c.data)
    return {"episode_id": ep.pk, "sources": len(fetched), "claims": len(out["claims"]), "unsupported": out["unsupported_count"], "fetcher": fetcher.name}


@handler("story.continuity", resource=_resource("continuity"), timeout=900)
def continuity(ctx):
    ep = Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"])
    meta = episode_meta(ep)
    meta["script"] = ep.script
    with _Llm(ctx, ep.series.page, "continuity") as prov:
        res = roles.continuity_manager(meta, provider=prov)
    n = services.apply_continuity(ep, res.data)
    return {"episode_id": ep.pk, "entries": n, "meta": res.meta()}
