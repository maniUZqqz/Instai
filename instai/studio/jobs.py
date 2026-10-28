"""Studio jobs: every long or model-driven action of the development room and of pre-production.

Handlers build a context from the database, call an agent role (validated JSON) with the page's own text-model choice, and persist through
instai/studio/services.py. Loaded by StudioConfig.ready(), so the worker, the server and the tests all see them.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from instai import research, research_series
from instai.agents import llm, studio_roles as roles
from instai.agents import roles as story_roles
from instai.assets import storage as asset_storage
from instai.core import settings_store
from instai.core.errors import DomainError
from instai.jobs.registry import handler
from instai.pages.models import ContentPage
from instai.story import services as story_services
from instai.story.models import Episode, Series, Source
from instai.styles import library

from . import animatic as animatic_mod
from . import preprod, services
from .models import Idea, ResearchDoc, SeriesBible

LANGS = ("fa", "en")


# ------------------------------------------------------------------ plumbing

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
    """Resolve the page's provider for `task` and hold the GPU while it runs when the provider is local."""

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


def _lang(payload: dict, page: ContentPage) -> str:
    """The language the human works in (the UI language when the job was started); defaults to the page's primary language."""
    v = str(payload.get("language") or "")[:2]
    return v if v in LANGS else page.language


def look_summary(series: Series) -> dict:
    vis = series.page.profile("visual")
    look = {**{k: vis.get(k, "") for k in ("style_key", "realism", "theme_key")}, **(series.look or {})}
    st = library.get_style(look["style_key"]) or {}
    th = library.get_theme(look.get("theme_key") or st.get("theme_key", "")) or {}
    return {"realism": look.get("realism") or st.get("realism", ""), "style": st.get("name_en", look["style_key"]), "animation": st.get("animation", ""),
            "mood": th.get("mood") or st.get("mood", ""), "palette": th.get("palette") or st.get("palette") or []}


def canon_brief(doc: ResearchDoc | None) -> dict:
    if not doc or not doc.content:
        return {}
    c = doc.content
    return {"summary": c.get("summary", ""), "characters": [{k: x.get(k, "") for k in ("name", "role", "abilities", "arc")} for x in (c.get("characters") or [])[:14]],
            "arcs": [{"title": a.get("title"), "summary": a.get("summary")} for a in (c.get("arcs") or [])[:10]],
            "key_events": [{"when": e.get("when", ""), "event": e.get("event", "")} for e in (c.get("key_events") or [])[:25]],
            "world_rules": [r.get("rule", "") for r in (c.get("world_rules") or [])[:10]], "themes": c.get("themes", [])}


def idea_card(i: Idea) -> dict:
    return {"title": i.title, "logline": i.logline, "why_it_works": i.why, "details": i.details or {}}


def dev_meta(series: Series, language: str) -> dict:
    from instai.jobs.handlers.story import series_meta

    m = series_meta(series)
    m.update(language=language, look=look_summary(series), source=series.source or {}, is_fan_content=series.is_fan_content,
             canon=canon_brief(series.research_docs.filter(kind="canon").first()))
    approved = [{"board": i.board, **idea_card(i)} for i in services.approved_ideas(series)]
    if approved:
        m["approved_ideas"] = approved
    steps = {s.kind: s for s in series.dev_steps.all()}
    if "map" in steps and (steps["map"].data or {}).get("nodes"):
        m["map"] = steps["map"].data["nodes"]
    if "timeline" in steps and (steps["timeline"].data or {}).get("rows"):
        m["timeline"] = steps["timeline"].data["rows"]
    topic = series.research_docs.filter(kind="topic").first()
    if topic and (topic.content or {}).get("claims"):
        m["claims"] = [{"claim": c["claim"], "stance": c["stance"]} for c in topic.content["claims"]][:30]
    m["characters"] = [c.name for c in series.page.characters.all()]
    return m


def _step_key(series: Series, payload: dict, kind: str) -> str:
    return payload.get("step_key") or services._first_key(series, kind)


def _meta(res) -> dict:
    return res.meta()


# ------------------------------------------------------------------ source lookup (network only)

@handler("studio.source_search", resource="net", timeout=120)
def source_search(ctx):
    p = ctx.payload
    providers = p.get("providers") or (["fake"] if str(settings_store.effective("research_fetch")) == "fake" else None)
    ctx.progress(0.2, "search")
    return research_series.search_series(p.get("query", ""), providers, str(p.get("language") or "en"), str(p.get("fandom_wiki") or ""))


# ------------------------------------------------------------------ brainstorm boards

@handler("studio.ideas", resource=_resource("ideas"), timeout=900)
def ideas_job(ctx):
    p = ctx.payload
    series = Series.objects.select_related("page").get(pk=p["series_id"])
    board = p["board"]
    sdef = next((s for s in services.template_of(series)["steps"] if s["kind"] == "brainstorm" and s["params"].get("board", s["key"]) == board), None)
    lens = (sdef or {}).get("params", {}).get("lens", "series_concept")
    lang = _lang(p, series.page)
    meta = dev_meta(series, lang)
    existing = list(series.ideas.filter(board=board))
    meta.update(lens=lens, board=board, count=int(p.get("count") or (sdef or {}).get("params", {}).get("count") or 6), instruction=str(p.get("instruction") or ""),
                existing_ideas=[i.title for i in existing if i.status != "rejected"], rejected=[i.title for i in existing if i.status == "rejected"][:20],
                liked_ideas=[idea_card(i) for i in existing if i.pk in (p.get("more_like") or [])])
    ctx.progress(0.1, "brainstorm")
    with _Llm(ctx, series.page, "ideas") as prov:
        res = roles.brainstormer(meta, provider=prov)
    parent = Idea.objects.filter(pk=(p.get("more_like") or [None])[0], series=series).first() if p.get("more_like") else None
    rows = services.save_ai_ideas(series, board, [{**i, "why": i.get("why_it_works", "")} for i in res.data["ideas"]], language=lang, parent=parent)
    return {"ideas": [r.pk for r in rows], "board": board, "meta": _meta(res)}


@handler("studio.idea_refine", resource=_resource("idea_refine"), timeout=600)
def idea_refine_job(ctx):
    p = ctx.payload
    idea = Idea.objects.select_related("series__page").get(pk=p["idea_id"])
    series, lang = idea.series, _lang(p, idea.series.page)
    meta = dev_meta(series, lang)
    meta.update(idea=idea_card(idea), instruction=str(p.get("instruction") or ""))
    with _Llm(ctx, series.page, "idea_refine") as prov:
        res = roles.idea_editor(meta, provider=prov)
    card = services.add_idea(series, idea.board, {**res.data, "why": res.data.get("why_it_works", "")}, author="refined", parent=idea, language=lang)
    return {"idea": card.pk, "meta": _meta(res)}


@handler("studio.idea_merge", resource=_resource("idea_merge"), timeout=600)
def idea_merge_job(ctx):
    p = ctx.payload
    series = Series.objects.select_related("page").get(pk=p["series_id"])
    cards = list(Idea.objects.filter(series=series, pk__in=p["ids"]))
    if len(cards) < 2:
        raise DomainError("validation_error", "برای ادغام حداقل دو ایده لازم است.", message_en="Merging needs at least two ideas.", http_status=400)
    lang = _lang(p, series.page)
    meta = dev_meta(series, lang)
    meta.update(ideas=[idea_card(c) for c in cards], instruction=str(p.get("instruction") or ""))
    with _Llm(ctx, series.page, "idea_merge") as prov:
        res = roles.idea_merger(meta, provider=prov)
    card = services.merge_ideas(series, [c.pk for c in cards], {**res.data, "why": res.data.get("why_it_works", "")}, language=lang)
    return {"idea": card.pk, "meta": _meta(res)}


# ------------------------------------------------------------------ research

@handler("studio.research", resource=_resource("canon"), timeout=1800)
def research_job(ctx):
    p = ctx.payload
    series = Series.objects.select_related("page").get(pk=p["series_id"])
    mode = p.get("mode") if p.get("mode") in ("canon", "topic") else "topic"
    lang = _lang(p, series.page)
    key = _step_key(series, p, "research")
    manual = [s for s in Source.objects.filter(series=series, added_by="user", episode__isnull=True) if s.extract]
    if mode == "canon":
        return _canon(ctx, series, lang, key, manual, p)
    return _topic(ctx, series, lang, key, manual, p)


def _numbered(fetched: list[dict]) -> list[dict]:
    return [{"id": f["id"], "title": f["title"], "extract": f["extract"][:3200]} for f in fetched]


def _canon(ctx, series: Series, lang: str, key: str, manual: list[Source], p: dict) -> dict:
    src = series.source or {}
    errors: list[str] = []
    fetched: list[dict] = []
    if src.get("provider"):
        ctx.progress(0.1, "collecting canon material")
        got = research_series.fetch_material(src, language=lang, extra_wikipedia=bool(p.get("wikipedia", True)), fandom_wiki=str(src.get("fandom_wiki") or p.get("fandom_wiki") or ""))
        errors += got["errors"]
        fetched += [{**m, "id": len(fetched) + i + 1} for i, m in enumerate(got["material"])]
    for s in manual:
        fetched.append({"id": len(fetched) + 1, "pk": s.pk, "title": s.title, "url": s.url, "publisher": s.publisher, "extract": s.extract, "verified": s.verified})
    if src.get("notes") and not any(f.get("title") == "Owner notes" for f in fetched):
        fetched.append({"id": len(fetched) + 1, "title": "Owner notes", "url": "", "publisher": "owner", "extract": src["notes"], "verified": False})
    if not fetched:
        raise DomainError("not_ready", "هیچ منبعی به دست نیامد (اینترنت کند یا مسدود است؟). متنِ منبع را دستی در بخش «منبع‌ها» اضافه کنید یا یادداشت بنویسید؛ سپس دوباره اجرا کنید.", message_en="No source could be collected (is the internet slow or blocked?). Add source text by hand in the Sources panel or write a note, then run it again.")
    ctx.progress(0.45, "analysing the canon")
    meta = dev_meta(series, lang)
    meta["sources"] = _numbered(fetched)
    with _Llm(ctx, series.page, "canon") as prov:
        res = roles.canon_researcher(meta, provider=prov)
    doc = services.store_research_doc(series, "canon", fetched, res.data, language=lang,
                                      title=src.get("title", ""), meta={**_meta(res), "fetch_errors": errors, "sources": len(fetched)})
    services.step_touched(series, key)
    return {"doc": doc.pk, "sources": len(fetched), "fetch_errors": errors, "characters": len(res.data["characters"]), "meta": _meta(res)}


def _topic(ctx, series: Series, lang: str, key: str, manual: list[Source], p: dict) -> dict:
    topic = str(p.get("topic") or "").strip() or series.title
    meta = dev_meta(series, lang)
    meta["topic"] = topic
    fetcher = research.get_fetcher(p.get("fetcher"))
    fetched: list[dict] = []
    with _Llm(ctx, series.page, "research_queries") as prov:
        ctx.progress(0.1, "queries")
        q = story_roles.researcher_queries(meta, provider=prov)
        for i, query in enumerate(q.data["queries"][:6]):
            ctx.check()
            ctx.progress(0.2 + 0.3 * i / max(1, len(q.data["queries"])), f"fetch: {query}")
            for item in fetcher.search(query, lang, 2):
                if not any(f["url"] == item["url"] and item["url"] for f in fetched):
                    fetched.append({**item, "id": len(fetched) + 1})
        for s in manual:
            fetched.append({"id": len(fetched) + 1, "pk": s.pk, "title": s.title, "url": s.url, "extract": s.extract, "verified": s.verified})
        ctx.progress(0.6, "claims")
        meta["sources"] = _numbered(fetched)
        c = story_roles.researcher_claims(meta, provider=prov)
    content = services.normalize_topic_content({"topic": topic, "queries": q.data["queries"], **c.data})
    doc = services.store_research_doc(series, "topic", fetched, content, language=lang, title=topic, meta={**_meta(c), "fetcher": fetcher.name, "sources": len(fetched)})
    # normalising again after the id remap keeps the unsupported flags right
    doc.content = services.normalize_topic_content(doc.content)
    doc.save(update_fields=["content", "updated_at"])
    services.step_touched(series, key)
    return {"doc": doc.pk, "sources": len(fetched), "claims": len(doc.content["claims"]), "unsupported": doc.content["unsupported_count"], "fetcher": fetcher.name}


# ------------------------------------------------------------------ consequence map, timeline, character bible

def _divergence(series: Series) -> dict:
    ideas = services.approved_ideas(series, "divergence") or services.approved_ideas(series)
    return idea_card(ideas[0]) if ideas else {}


@handler("studio.map", resource=_resource("consequence_map"), timeout=900)
def map_job(ctx):
    p = ctx.payload
    series = Series.objects.select_related("page").get(pk=p["series_id"])
    key = _step_key(series, p, "map")
    div = _divergence(series)
    if not div:
        raise DomainError("not_ready", "ابتدا یک ایدهٔ نقطهٔ انشعاب را تأیید کنید.", message_en="Approve a divergence-point idea first.")
    lang = _lang(p, series.page)
    meta = dev_meta(series, lang)
    meta.update(divergence=div, instruction=str(p.get("instruction") or ""), episodes_count=series.target_episodes)
    meta.pop("map", None)
    with _Llm(ctx, series.page, "consequence_map") as prov:
        res = roles.consequence_mapper(meta, provider=prov)
    services.save_step_data(series, key, {"nodes": res.data["nodes"], "instruction": meta["instruction"]})
    services.step_touched(series, key)
    return {"nodes": len(res.data["nodes"]), "meta": _meta(res)}


@handler("studio.timeline", resource=_resource("timeline"), timeout=900)
def timeline_job(ctx):
    p = ctx.payload
    series = Series.objects.select_related("page").get(pk=p["series_id"])
    key = _step_key(series, p, "timeline")
    lang = _lang(p, series.page)
    meta = dev_meta(series, lang)
    meta.update(divergence=_divergence(series), instruction=str(p.get("instruction") or ""), canon_events=(meta.get("canon") or {}).get("key_events", []))
    with _Llm(ctx, series.page, "timeline") as prov:
        res = roles.timeline_builder(meta, provider=prov)
    services.save_step_data(series, key, {"rows": res.data["rows"], "summary": res.data.get("summary", "")})
    services.step_touched(series, key)
    return {"rows": len(res.data["rows"]), "meta": _meta(res)}


@handler("studio.profile", resource=_resource("character_bible"), timeout=900)
def profile_job(ctx):
    p = ctx.payload
    series = Series.objects.select_related("page").get(pk=p["series_id"])
    key = _step_key(series, p, "profile")
    step = services.get_step(series, key)
    brief = str(p.get("brief") or (step.data or {}).get("brief") or series.page.idea or "").strip()
    if not brief:
        raise DomainError("not_ready", "ابتدا یادداشت طراحی شخصیت را بنویسید.", message_en="Write the character design brief first.")
    lang = _lang(p, series.page)
    meta = dev_meta(series, lang)
    meta["brief"] = brief
    with _Llm(ctx, series.page, "character_bible") as prov:
        res = roles.character_designer(meta, provider=prov)
    services.save_step_data(series, key, {"brief": brief, "characters": res.data["characters"]})
    services.step_touched(series, key)
    return {"characters": len(res.data["characters"]), "meta": _meta(res)}


# ------------------------------------------------------------------ series bible

@handler("studio.bible", resource=_resource("bible"), timeout=1200)
def bible_job(ctx):
    p = ctx.payload
    series = Series.objects.select_related("page").get(pk=p["series_id"])
    lang = _lang(p, series.page)
    meta = dev_meta(series, lang)
    meta.update(instruction=str(p.get("instruction") or ""), episodes_count=series.target_episodes)
    existing = services.bible_dict(series)
    if existing["exists"] and p.get("keep_existing"):
        meta["existing_bible"] = existing["data"]
    for st in series.dev_steps.filter(kind="profile"):
        if (st.data or {}).get("characters"):
            meta["characters_detail"] = st.data["characters"]
    with _Llm(ctx, series.page, "bible") as prov:
        res = roles.bible_writer(meta, provider=prov)
    services.save_bible(series, res.data, by_ai=True)
    return {"bible": True, "meta": _meta(res)}


# ------------------------------------------------------------------ pre-production

def _scenes_meta(ep: Episode) -> list[dict]:
    return [{"title": sc.title, "summary": sc.summary, "location": sc.location, "characters": [c.name for c in sc.characters.all()]}
            for sc in ep.scenes.prefetch_related("characters")]


@handler("studio.design", resource=_resource("design"), timeout=1200)
def design_job(ctx):
    p = ctx.payload
    ep = Episode.objects.select_related("series__page").get(pk=p["episode_id"])
    page = ep.series.page
    lang = _lang(p, page)
    chars = preprod.episode_characters(ep) or list(page.characters.all())[:4]
    comp = library.compose_for_page(page)
    meta = {"language": lang, "format": page.format, "page_name": page.name, "title": ep.title, "visual_style": comp["positive"], "negative": comp["negative"],
            "look": look_summary(ep.series), "episode": {"number": ep.number, "title": ep.title, "logline": ep.logline}, "scenes": _scenes_meta(ep),
            "characters_detail": [{"name": c.name, "role": c.role, "appearance": c.appearance, "personality": c.personality} for c in chars]}
    with _Llm(ctx, page, "design") as prov:
        res = roles.design_director(meta, provider=prov)
    made = preprod.save_ai_sheets(ep, res.data["sheets"])
    return {"sheets": [s.pk for s in made], "meta": _meta(res)}


@handler("studio.casting", resource=_resource("casting"), timeout=600)
def casting_job(ctx):
    p = ctx.payload
    ep = Episode.objects.select_related("series__page").get(pk=p["episode_id"])
    page = ep.series.page
    lang = _lang(p, page)
    voices = [{"id": v["id"], "label": v["label"], "language": v["language"], "tags": v["tags"]} for v in preprod.voice_options(page.language) if v["installed"]]
    if not voices:
        raise DomainError("not_ready", "هیچ صدایی در این رایانه آماده نیست؛ در «سیستم» موتور صدا را آماده کنید یا حالت آزمایشی را روشن کنید.", message_en="No voice is ready on this computer; prepare a speech engine in System or turn on demo mode.")
    chars = preprod.episode_characters(ep)
    meta = {"language": lang, "format": page.format, "voices": voices,
            "characters_detail": [{"name": c.name, "role": c.role, "personality": c.personality, "appearance": c.appearance} for c in chars]}
    if not chars:
        raise DomainError("not_ready", "در این قسمت شخصیتی با دیالوگ نیست؛ راوی از صدای پیش‌فرض صفحه استفاده می‌کند.", message_en="No character speaks in this episode; the narrator uses the page's default voice.")
    with _Llm(ctx, page, "casting") as prov:
        res = roles.voice_caster(meta, provider=prov)
    by_name = {c.name: c for c in chars}
    applied = []
    for row in res.data["casting"]:
        c = by_name.get(row["character"])
        if c:
            preprod.set_voice(c, row["voice_id"])
            applied.append({"character": c.name, "voice_id": row["voice_id"], "reason": row.get("reason", "")})
    preprod.clear_approval(ep, "casting")
    return {"casting": applied, "meta": _meta(res)}


@handler("studio.translate", resource=_resource("translate"), timeout=1800)
def translate_job(ctx):
    p = ctx.payload
    ep = Episode.objects.select_related("series__page").get(pk=p["episode_id"])
    page = ep.series.page
    target = str(p.get("language") or "")[:2]
    if target not in LANGS:
        raise DomainError("validation_error", "زبان مقصد نامعتبر است.", message_en="Invalid target language.", http_status=400)
    source_lang = (ep.script or {}).get("language") or page.language
    if target == source_lang[:2]:
        raise DomainError("validation_error", "زبان مقصد با زبان فیلم‌نامه یکی است.", message_en="The target language is the script's own language.", http_status=400)
    if not ep.script:
        raise DomainError("not_ready", "ابتدا فیلم‌نامه را بسازید.", message_en="Build the script first.")
    base = {"language": target, "target_language": target, "format": page.format}
    ctx.progress(0.1, "script")
    with _Llm(ctx, page, "translate") as prov:
        res = roles.translator({**base, "script": ep.script}, provider=prov)
        lines = [{"id": str(s.pk), "text": s.narration} for s in story_services.all_shots(ep) if s.narration.strip()]
        shots: dict[str, str] = {}
        meta2 = res.meta()
        for i in range(0, len(lines), 40):
            ctx.check()
            ctx.progress(0.4 + 0.5 * i / max(1, len(lines)), "shot narration")
            r2 = roles.shot_translator({**base, "lines": lines[i:i + 40]}, provider=prov)
            shots.update({str(x["id"]): x["text"] for x in r2.data["lines"]})
    script = {"title": res.data.get("title") or ep.script.get("title", ""), "hook": res.data.get("hook") or "", "cta": res.data.get("cta") or "", "language": target,
              "blocks": [{"id": i + 1, "speaker": b.get("speaker") or ep.script["blocks"][i].get("speaker", ""), "text": b["text"],
                          "emotion": b.get("emotion") or ep.script["blocks"][i].get("emotion", "")} for i, b in enumerate(res.data["blocks"])
                         if i < len(ep.script["blocks"])]}
    tr = dict(ep.translations or {})
    tr[target] = {"script": script, "shots": shots, "at": timezone.now().isoformat(), "provider": meta2.get("provider"), "model": meta2.get("model"), "from": source_lang[:2]}
    ep.translations = tr
    ep.save(update_fields=["translations", "updated_at"])
    return {"language": target, "blocks": len(script["blocks"]), "shots": len(shots), "meta": meta2}


@handler("studio.animatic", resource="cpu", timeout=1800)
def animatic_job(ctx):
    ep = Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"])
    return animatic_mod.build(ctx, ep)


@handler("studio.design_image", resource=lambda payload: "cpu" if str(settings_store.effective("image_engine")) == "placeholder" else "gpu", timeout=1800)
def design_image_job(ctx):
    """Render one design sheet. Uses the same image engine as keyframes (ComfyUI), or a labelled placeholder in demo mode."""
    from instai.core.errors import DomainError as DE
    from instai.providers.base import ProviderError
    from instai.render.placeholders import make_placeholder

    from .models import DesignSheet

    sheet = DesignSheet.objects.select_related("episode__series__page", "page").get(pk=ctx.payload["sheet_id"])
    page = sheet.page
    comp = library.compose_for_page(page)
    w, h = (1024, 704) if sheet.kind in ("character", "expression", "prop") else (576, 1024)
    sheet.status, sheet.last_error = "generating", ""
    sheet.save(update_fields=["status", "last_error", "updated_at"])
    seed = int(ctx.payload.get("seed") or (sheet.pk * 7919) % (2 ** 31))
    tmpdir = Path(tempfile.mkdtemp(prefix="design-", dir=settings.MEDIA_ROOT))
    tmp = tmpdir / "sheet.png"
    try:
        engine = str(settings_store.effective("image_engine") or "auto")
        prov: dict
        if engine == "placeholder":
            make_placeholder(tmp, w, h, f"{sheet.kind}: {sheet.subject[:18]}", seed=f"design-{sheet.pk}")
            prov = {"provider": "placeholder", "note": "demo mode: generated placeholder, not an AI image"}
        else:
            from instai.production import pipeline

            client, spec = pipeline._comfy_ready()  # same readiness check and error text as keyframes
            from instai.gpu.arbiter import ARBITER

            with ARBITER.hold(ctx, "comfy"):
                prompt = ", ".join(x for x in (sheet.prompt, comp["positive"]) if x)
                inputs = {"prompt": prompt, "negative_prompt": ", ".join(x for x in (sheet.negative, comp["negative"]) if x), "width": w, "height": h, "seed": seed, "steps": 20}
                _, files = client.run(spec.build(inputs), timeout=1800, on_tick=lambda s: ctx.progress(0.5, f"image ({int(s)}s)"), cancel=lambda: ctx.check() or False)
                if not files:
                    raise ProviderError("ComfyUI returned no image", retryable=True)
                client.download(files[0], tmp)
            prov = {**spec.provenance(inputs), "provider": "comfyui"}
        asset = asset_storage.register(tmp, f"design/{sheet.pk}/{sheet.kind}-{seed}.png", kind="image", role="reference", page=page,
                                       provenance={**prov, "design_sheet": sheet.pk, "job_id": ctx.job.pk, "seed": seed, "prompt": sheet.prompt})
        sheet.asset, sheet.status = asset, "done"
        sheet.approved = False
        sheet.save(update_fields=["asset", "status", "approved", "updated_at"])
        if sheet.episode_id:
            preprod.clear_approval(sheet.episode, "design")
    except (ProviderError, DE) as e:
        sheet.status, sheet.last_error = "failed", str(e)[:500]
        sheet.save(update_fields=["status", "last_error", "updated_at"])
        raise
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
    return {"asset_id": asset.pk, "sheet": sheet.pk}
