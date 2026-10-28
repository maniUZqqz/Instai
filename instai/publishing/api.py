"""Publishing centre (release 1): captions, hashtags, cover, schedule, status and a manual-export package. Nothing auto-publishes."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.pages.models import ContentPage
from instai.story import services, states
from instai.story.models import Episode

from .models import Publication, PublishTarget


def pub_dict(p: Publication) -> dict:
    return {"id": p.pk, "episode": p.episode_id, "episode_title": p.episode.title, "episode_number": p.episode.number, "target": p.target_id,
            "caption": p.caption, "hashtags": p.hashtags, "scheduled_at": p.scheduled_at, "status": p.status, "ai_label": p.ai_label,
            "package_url": p.package.url if p.package_id else None, "cover_url": p.cover.url if p.cover_id else None, "external_url": p.external_url,
            "created_at": p.created_at, "episode_state": p.episode.state}


@api_view(["GET", "POST"])
def page_publications(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    if request.method == "POST":
        ep = get_object_or_404(Episode, pk=request.data.get("episode"), series__page=page)
        tags = request.data.get("hashtags") or page.profile("publishing")["hashtags"]
        pub = Publication.objects.create(episode=ep, target=page.targets.first(), caption=request.data.get("caption") or ep.title, hashtags=tags)
        return Response(pub_dict(pub), status=201)
    return Response([pub_dict(p) for p in Publication.objects.filter(episode__series__page=page).select_related("episode", "package", "cover")])


@api_view(["PATCH", "DELETE"])
def publication_detail(request, pk):
    p = get_object_or_404(Publication.objects.select_related("episode", "package", "cover"), pk=pk)
    if request.method == "DELETE":
        p.delete()
        return Response(status=204)
    d = request.data
    for f in ("caption", "hashtags", "ai_label", "external_url"):
        if f in d:
            setattr(p, f, d[f])
    if "scheduled_at" in d:
        p.scheduled_at = parse_datetime(d["scheduled_at"]) if d["scheduled_at"] else None
        if p.scheduled_at and p.episode.state == states.APPROVED:
            services.transition(p.episode, states.SCHEDULED, reason="scheduled", actor="user")
            p.status = "scheduled"
    if d.get("status") == "published" and p.episode.state in (states.SCHEDULED, states.APPROVED):
        if p.episode.state == states.APPROVED:
            services.transition(p.episode, states.SCHEDULED, actor="user")
        services.transition(p.episode, states.PUBLISHED, reason="marked as published by the owner", actor="user")
        p.status = "published"
    p.save()
    return Response(pub_dict(p))


@api_view(["POST"])
def publication_export(request, pk):
    p = get_object_or_404(Publication, pk=pk)
    if p.episode.state not in (states.READY_FOR_APPROVAL, states.APPROVED, states.SCHEDULED, states.PUBLISHED):
        raise DomainError("not_ready", "فقط قسمتِ «آماده‌ی تأیید» یا تأییدشده را می‌توان برای انتشار بسته‌بندی کرد.")
    return job_response(queue.enqueue("publish.export", {"publication_id": p.pk}, episode=p.episode, page=p.episode.series.page_id,
                                      title=f"بسته‌ی انتشار قسمت {p.episode.number}", idempotency_key=f"export:{p.pk}:{p.updated_at.timestamp()}"))


@api_view(["GET", "POST"])
def page_targets(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    if request.method == "POST":
        t = PublishTarget.objects.create(page=page, platform=request.data.get("platform", "instagram"), handle=request.data.get("handle", ""), mode="manual")
        return Response({"id": t.pk, "platform": t.platform, "handle": t.handle, "mode": t.mode}, status=201)
    return Response([{"id": t.pk, "platform": t.platform, "handle": t.handle, "mode": t.mode, "enabled": t.enabled} for t in page.targets.all()])


urlpatterns = [
    path("pages/<int:pk>/publications", page_publications),
    path("pages/<int:pk>/targets", page_targets),
    path("publications/<int:pk>", publication_detail),
    path("publications/<int:pk>/export", publication_export),
]
