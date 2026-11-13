"""Choice stories: create, plan (model or skeleton), edit the graph with versions, approve, schedule. The ONLY place where a graph is written to the database."""
from __future__ import annotations

import copy
import datetime as dt

from django.db import transaction
from django.utils import timezone

from instai.core.errors import DomainError
from instai.pages.models import ContentPage

from . import graph as G
from . import story_templates
from .models import ChoiceStory, ChoiceVersion

GENRES = ["prison_escape", "zombie_survival", "haunted_house", "detective", "space_station", "custom"]


def _bad(code: str, fa: str, en: str, status: int = 409, **details) -> DomainError:
    return DomainError(code, fa, http_status=status, message_en=en, details=details or None)


def create_story(page: ContentPage, data: dict) -> ChoiceStory:
    title = str(data.get("title") or "").strip()
    if not title:
        raise _bad("validation_error", "عنوان داستان لازم است.", "The story needs a title.", 400, title=["required"])
    lang = str(data.get("language") or page.language or "fa")[:2]
    aspect = data.get("aspect") if data.get("aspect") in ("4:5", "1:1", "9:16") else "4:5"
    renderer = data.get("renderer") if data.get("renderer") in ("stick", "image") else "stick"
    settings = {"post_count": max(6, min(60, int(data.get("post_count") or 14))), "allow_loops": bool(data.get("allow_loops")),
                "hour": str(data.get("hour") or "20:00")[:5], "per_day": max(1, min(10, int(data.get("per_day") or 1)))}
    return ChoiceStory.objects.create(page=page, series_id=data.get("series") or None, title=title[:200], premise=str(data.get("premise") or ""), genre=str(data.get("genre") or "")[:60],
                                      language=lang if lang in ("fa", "en") else "fa", aspect=aspect, renderer=renderer, settings=settings, graph={"nodes": [], "meta": {}})


# ------------------------------------------------------------------ ready-made stories

def create_from_template(page: ContentPage, key: str, data: dict | None = None) -> ChoiceStory:
    """A new story that starts from a ready-made, hand-written one: its characters are created on the page (stick identity drawn and locked), its posts are the graph."""
    data = data or {}
    tpl = story_templates.get(key)
    if tpl is None:
        raise _bad("not_found", "این داستان آماده پیدا نشد.", "That ready-made story does not exist.", 404)
    story = create_story(page, {"title": str(data.get("title") or tpl["title_fa"]), "premise": tpl["blurb_fa"], "genre": tpl["genre"], "language": "fa", "post_count": len(tpl["posts"]),
                                "aspect": data.get("aspect"), "renderer": "stick", "hour": data.get("hour"), "per_day": data.get("per_day"), "allow_loops": False})
    load_template(story, key)
    story.refresh_from_db()
    return story


def load_template(story: ChoiceStory, key: str) -> ChoiceStory:
    """Replace the story's graph with a ready-made one (the old graph is kept as a version). Creates the template's characters on the page first."""
    from instai.identity import cast

    tpl = story_templates.get(key)
    if tpl is None:
        raise _bad("not_found", "این داستان آماده پیدا نشد.", "That ready-made story does not exist.", 404)
    cast.ensure_cast(story.page, tpl["cast"])
    story.language = "fa"
    story.genre = tpl["genre"]
    st = dict(story.settings or {})
    st["post_count"] = len(tpl["posts"])
    story.settings = st
    story.save(update_fields=["language", "genre", "settings", "updated_at"])
    return apply_plan(story, story_templates.plan_of(tpl), author="system")


def _snapshot(story: ChoiceStory, author: str, note: str) -> None:
    if G.nodes_of(story.graph):
        ChoiceVersion.objects.create(story=story, number=story.version, graph=copy.deepcopy(story.graph), author=author, note=note[:300])
        story.version += 1


@transaction.atomic
def save_graph(story: ChoiceStory, graph: dict, *, author: str = "human", note: str = "", renumber: bool = True) -> ChoiceStory:
    """Replace the graph (the old one is kept as a version). The result is normalised and numbered in posting order; approval is cleared."""
    g = G.normalize(graph)
    if renumber:
        g, _ = G.renumber(g)
    _snapshot(story, author, note or "before replace")
    story.graph = g
    if G.nodes_of(g) and story.status == "draft":
        story.status = "planned"
    if story.status == "approved":
        story.status, story.approved_at = "planned", None
    story.save()
    return story


def apply_plan(story: ChoiceStory, plan: dict, *, author: str = "ai") -> ChoiceStory:
    """Turn a planner answer ({title, posts[...]}) into the graph: scene fields, characters (page characters by name), default captions."""
    page_chars = [c.name for c in story.page.characters.all()]
    nodes = []
    for p in plan.get("posts") or []:
        node = G.new_node(str(p["id"]), title=str(p.get("title") or ""), text=str(p.get("text") or ""), kind=str(p.get("kind") or "story"), ending=str(p.get("ending") or ""),
                          choices=[{"label": c.get("label", ""), "to": c.get("to", "")} for c in p.get("choices") or []],
                          scene={k: p.get(k) for k in ("location", "pose", "expression") if p.get(k)})
        chars = [c for c in (p.get("characters") or []) if c in page_chars] or page_chars[:1]
        if chars:
            node["scene"]["characters"] = chars[:2]
        nodes.append(node)
    g = G.normalize({"nodes": nodes, "meta": {"planned_by": author}})
    g, _ = G.renumber(g)
    for n in g["nodes"]:
        n["caption"] = G.default_caption(n, g, fa=story.language == "fa")
    if plan.get("title") and not story.title:
        story.title = plan["title"][:200]
    return save_graph(story, g, author=author, note="planned", renumber=False)


def apply_captions(story: ChoiceStory, captions: dict) -> ChoiceStory:
    rows = {str(c["id"]): c for c in captions.get("posts") or []}
    g = copy.deepcopy(story.graph)
    for n in g["nodes"]:
        row = rows.get(n["id"])
        if row and str(row.get("caption") or "").strip():
            n["caption"] = row["caption"]
            n["hashtags"] = [str(h) for h in (row.get("hashtags") or [])][:12]
            n["alt"] = str(row.get("alt") or "")[:300]
    return save_graph(story, g, author="ai", note="captions", renumber=False)


def reset_captions(story: ChoiceStory) -> ChoiceStory:
    g = copy.deepcopy(story.graph)
    for n in g["nodes"]:
        n["caption"] = G.default_caption(n, g, fa=story.language == "fa")
    return save_graph(story, g, author="system", note="default captions", renumber=False)


def report(story: ChoiceStory) -> dict:
    """The review screen: validation (errors block approval), stats, the SVG layout, every route, unresolved caption placeholders."""
    g = story.graph
    v = G.validate(g, allow_back_edges=bool((story.settings or {}).get("allow_loops")))
    un = G.unresolved(g)
    v["errors"] = v["errors"] + un
    v["ok"] = not v["errors"]
    return {"validation": v, "layout": G.layout(g), "paths": G.enumerate_paths(g, 40), "stats": v["stats"], "story_status": story.status}


def approve(story: ChoiceStory) -> ChoiceStory:
    rep = report(story)
    if not rep["validation"]["ok"]:
        raise _bad("not_ready", "نمودار هنوز اشکال دارد؛ اول خطاها را رفع کنید.", "The graph still has errors; fix them first.", errors=[e["code"] for e in rep["validation"]["errors"]][:20])
    story.status, story.approved_at = "approved", timezone.now()
    story.save(update_fields=["status", "approved_at", "updated_at"])
    return story


def revoke(story: ChoiceStory) -> ChoiceStory:
    story.status, story.approved_at = "planned" if G.nodes_of(story.graph) else "draft", None
    story.save(update_fields=["status", "approved_at", "updated_at"])
    return story


def restore(story: ChoiceStory, number: int) -> ChoiceStory:
    v = story.versions.filter(number=number).first()
    if not v:
        raise DomainError("not_found", http_status=404)
    return save_graph(story, v.graph, author="human", note=f"restored version {number}", renumber=False)


def schedule(story: ChoiceStory, *, start: str | None = None, utc_offset_minutes: int = 210) -> list[dict]:
    """Posting plan in NUMBER order: post k goes out `per_day` posts per day from the start date at the chosen hour (local time of the page).
    Choice stories must be released in order, because every caption points forward to posts that are already numbered."""
    st = story.settings or {}
    per_day = max(1, int(st.get("per_day") or 1))
    hh, mm = (str(st.get("hour") or "20:00") + ":00").split(":")[:2]
    day0 = dt.date.fromisoformat(start or st.get("start") or (timezone.now() + dt.timedelta(days=1)).date().isoformat())
    out = []
    for n in sorted(G.nodes_of(story.graph), key=lambda n: n.get("number") or 0):
        k = (n.get("number") or 1) - 1
        slot = k % per_day
        minutes = int(hh) * 60 + int(mm) + slot * 90
        local = dt.datetime.combine(day0 + dt.timedelta(days=k // per_day), dt.time(0, 0)) + dt.timedelta(minutes=minutes)
        utc = local - dt.timedelta(minutes=utc_offset_minutes)
        out.append({"id": n["id"], "number": n["number"], "local": local.isoformat(timespec="minutes"), "utc": utc.replace(tzinfo=dt.timezone.utc).isoformat(timespec="minutes")})
    return out


def story_dict(s: ChoiceStory, *, full: bool = True) -> dict:
    out = {"id": s.pk, "page": s.page_id, "series": s.series_id, "title": s.title, "premise": s.premise, "genre": s.genre, "language": s.language, "aspect": s.aspect,
           "renderer": s.renderer, "status": s.status, "settings": s.settings, "version": s.version, "approved_at": s.approved_at, "created_at": s.created_at,
           "updated_at": s.updated_at, "posts": len(G.nodes_of(s.graph))}
    if full:
        out["graph"] = s.graph
    return out
