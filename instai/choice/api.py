"""Choice-story API: create, plan, edit the graph, review (validation, map, routes), approve, render, package."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.pages.models import ContentPage
from instai.render.stick import poses, scenes

from . import export, render, services, story_templates
from . import graph as G
from .models import ChoiceStory

STRUCTURES = ["spine"]


def _story(pk) -> ChoiceStory:
    return get_object_or_404(ChoiceStory.objects.select_related("page", "series"), pk=pk)


@api_view(["GET", "POST"])
def page_stories(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    if request.method == "POST":
        d = request.data if isinstance(request.data, dict) else {}
        s = services.create_from_template(page, str(d["template"]), d) if d.get("template") else services.create_story(page, d)
        return Response(services.story_dict(s), status=201)
    return Response([services.story_dict(s, full=False) for s in page.choice_stories.all()])


@api_view(["GET", "PATCH", "DELETE"])
def story_detail(request, pk):
    s = _story(pk)
    if request.method == "DELETE":
        s.delete()
        return Response(status=204)
    if request.method == "PATCH":
        d = request.data
        for f, n in (("title", 200), ("premise", 4000), ("genre", 60)):
            if f in d:
                setattr(s, f, str(d[f] or "")[:n])
        if d.get("aspect") in ("4:5", "1:1", "9:16"):
            s.aspect = d["aspect"]
        if d.get("renderer") in ("stick", "image"):
            s.renderer = d["renderer"]
        if d.get("language") in ("fa", "en"):
            s.language = d["language"]
        if isinstance(d.get("settings"), dict):
            s.settings = {**(s.settings or {}), **{k: v for k, v in d["settings"].items() if k in ("post_count", "allow_loops", "start", "per_day", "hour")}}
        s.save()
    return Response(services.story_dict(s))


@api_view(["GET"])
def story_report(request, pk):
    s = _story(pk)
    rep = services.report(s)
    rep["stale"] = render.stale_nodes(s)
    rep["unresolved"] = G.unresolved(s.graph)
    return Response(rep)


@api_view(["PUT"])
def story_graph(request, pk):
    s = _story(pk)
    g = request.data.get("graph") if isinstance(request.data, dict) else None
    if not isinstance(g, dict):
        raise DomainError("validation_error", "نمودار نامعتبر است.", http_status=400, message_en="Invalid graph.", details={"graph": ["required"]})
    services.save_graph(s, g, note=str(request.data.get("note") or "edit"), renumber=request.data.get("renumber", True) is not False)
    return Response(services.story_dict(s))


@api_view(["POST"])
def story_ops(request, pk):
    """One edit of the graph: add_node | remove_node | update_node | set_choice | remove_choice | renumber. Returns the story."""
    s = _story(pk)
    d = request.data if isinstance(request.data, dict) else {}
    g, op = s.graph, d.get("op")
    if op == "add_node":
        g, _nid = G.add_node(g, d.get("node") or {})
    elif op == "remove_node":
        g = G.remove_node(g, str(d.get("id") or ""))
    elif op == "update_node":
        nodes = G.by_id(g)
        n = nodes.get(str(d.get("id") or ""))
        if n is None:
            raise DomainError("not_found", http_status=404)
        for k in ("title", "text", "caption", "alt", "ending", "kind", "scene", "hashtags", "intended_dead_end"):
            if k in (d.get("fields") or {}):
                n[k] = d["fields"][k]
        g = G.normalize(g)
    elif op == "set_choice":
        if str(d.get("id")) not in G.by_id(g):
            raise DomainError("not_found", http_status=404)
        g = G.set_choice(g, str(d["id"]), int(d.get("index", 99)), str(d.get("label") or ""), str(d.get("to") or ""), loop=bool(d.get("loop")))
    elif op == "remove_choice":
        if str(d.get("id")) not in G.by_id(g):
            raise DomainError("not_found", http_status=404)
        g = G.remove_choice(g, str(d["id"]), int(d.get("index", 0)))
    elif op != "renumber":
        raise DomainError("validation_error", "عملیات ناشناخته است.", http_status=400, message_en="Unknown operation.", details={"op": ["unknown"]})
    services.save_graph(s, g, note=f"op {op}")
    return Response(services.story_dict(s))


@api_view(["POST"])
def story_plan(request, pk):
    s = _story(pk)
    return job_response(queue.enqueue("choice.plan", {"story_id": s.pk, "instruction": str(request.data.get("instruction") or "")[:1000]}, page=s.page_id, title=f"طراحی داستان «{s.title}»"))


@api_view(["POST"])
def story_template(request, pk):
    """Replace the story's graph with a ready-made story (the old graph stays as a version)."""
    s = _story(pk)
    services.load_template(s, str(request.data.get("key") or ""))
    return Response(services.story_dict(_story(pk)))


@api_view(["GET"])
def choice_templates(request):
    return Response({"templates": story_templates.listing()})


@api_view(["POST"])
def story_captions(request, pk):
    s = _story(pk)
    if not G.nodes_of(s.graph):
        raise DomainError("not_ready", "ابتدا نمودار داستان را بسازید.", message_en="Plan the graph first.")
    return job_response(queue.enqueue("choice.captions", {"story_id": s.pk}, page=s.page_id, title=f"کپشن‌های «{s.title}»"))


@api_view(["POST"])
def story_captions_reset(request, pk):
    s = _story(pk)
    services.reset_captions(s)
    return Response(services.story_dict(s))


@api_view(["POST"])
def story_approve(request, pk):
    return Response(services.story_dict(services.approve(_story(pk))))


@api_view(["POST"])
def story_revoke(request, pk):
    return Response(services.story_dict(services.revoke(_story(pk))))


@api_view(["GET"])
def story_versions(request, pk):
    s = _story(pk)
    return Response([{"number": v.number, "author": v.author, "note": v.note, "created_at": v.created_at, "posts": len(G.nodes_of(v.graph))} for v in s.versions.all()])


@api_view(["POST"])
def story_restore(request, pk):
    s = _story(pk)
    return Response(services.story_dict(services.restore(s, int(request.data.get("number") or 0))))


@api_view(["POST"])
def story_render(request, pk):
    s = _story(pk)
    if not G.nodes_of(s.graph):
        raise DomainError("not_ready", "ابتدا نمودار داستان را بسازید.", message_en="Plan the graph first.")
    nodes = [str(n) for n in (request.data.get("nodes") or [])] if isinstance(request.data, dict) else []
    return job_response(queue.enqueue("choice.render", {"story_id": s.pk, "nodes": nodes}, page=s.page_id, title=f"تصویر پست‌های «{s.title}»"))


@api_view(["POST"])
def story_package(request, pk):
    s = _story(pk)
    if s.status != "approved":
        raise DomainError("not_ready", "داستان باید پیش از ساخت بسته تأیید شود.", message_en="Approve the story before building the package.")
    return job_response(queue.enqueue("choice.package", {"story_id": s.pk}, page=s.page_id, title=f"بستهٔ انتشار «{s.title}»"))


@api_view(["GET"])
def story_schedule(request, pk):
    s = _story(pk)
    return Response({"posts": services.schedule(s, start=request.query_params.get("start") or None)})


@api_view(["GET"])
def story_captions_text(request, pk):
    return Response({"text": export.captions_text(_story(pk))})


@api_view(["GET"])
def story_post_preview(request, pk, nid):
    """The finished picture of ONE post, drawn now (stick renderer) or the latest rendered one (image renderer)."""
    s = _story(pk)
    node = G.by_id(s.graph).get(nid)
    if node is None:
        raise DomainError("not_found", http_status=404)
    h = render.node_hash(s, node, s.graph)
    if s.renderer == "image":
        from instai.assets.models import Asset

        a = Asset.objects.filter(pk=node.get("asset_id")).first() if node.get("asset_id") else None
        if a is None:
            raise DomainError("not_ready", "این پست هنوز ساخته نشده است؛ «ساخت تصویرها» را بزنید.", message_en="This post has not been rendered yet; press 'Render pictures'.")
        return Response({"url": a.url, "hash": node.get("image_hash"), "stale": node.get("image_hash") != h})
    rel = f"choice/{s.pk}/preview/{nid}-{h}.png"
    out = Path(settings.MEDIA_ROOT) / rel
    if not out.exists():
        render.render_post(s, node, out, Path(settings.MEDIA_ROOT) / "stickwork" / f"choice{s.pk}")
    return Response({"url": "/media/" + rel, "hash": h, "stale": False})


@api_view(["GET"])
def choice_options(request):
    return Response({"genres": services.GENRES, "poses": [{"key": k, "fa": v[0], "en": v[1]} for k, v in poses.POSE_LABELS.items()],
                     "expressions": ["neutral", "happy", "laugh", "sad", "angry", "scared", "surprised", "smirk"],
                     "backgrounds": [{"key": k, "fa": v["fa"], "en": v["en"]} for k, v in scenes.BACKGROUNDS.items()],
                     "limits": {"max_choices": G.MAX_CHOICES_HARD, "advised_choices": G.MAX_CHOICES_ADVISED, "label": G.MAX_LABEL, "text": G.MAX_TEXT},
                     "aspects": ["4:5", "1:1", "9:16"], "rules": ["forward_numbering", "no_dead_ends", "all_reachable", "placeholders_resolved", "endings"]})


urlpatterns = [
    path("pages/<int:pk>/choice-stories", page_stories),
    path("choice-stories/<int:pk>", story_detail),
    path("choice-stories/<int:pk>/report", story_report),
    path("choice-stories/<int:pk>/graph", story_graph),
    path("choice-stories/<int:pk>/ops", story_ops),
    path("choice-stories/<int:pk>/plan", story_plan),
    path("choice-stories/<int:pk>/template", story_template),
    path("choice-stories/<int:pk>/captions", story_captions),
    path("choice-stories/<int:pk>/captions/reset", story_captions_reset),
    path("choice-stories/<int:pk>/captions/text", story_captions_text),
    path("choice-stories/<int:pk>/approve", story_approve),
    path("choice-stories/<int:pk>/revoke", story_revoke),
    path("choice-stories/<int:pk>/versions", story_versions),
    path("choice-stories/<int:pk>/restore", story_restore),
    path("choice-stories/<int:pk>/render", story_render),
    path("choice-stories/<int:pk>/package", story_package),
    path("choice-stories/<int:pk>/schedule", story_schedule),
    path("choice-stories/<int:pk>/posts/<str:nid>/preview", story_post_preview),
    path("choice/options", choice_options),
    path("choice/templates", choice_templates),
]
