"""Mini-series channel API (one channel per series): settings and cast, the season slate, review, approval, writing the episodes."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.jobs import queue
from instai.jobs.api import job_response
from instai.story.models import Series

from . import conventions, season_templates, services


def _series(pk) -> Series:
    return get_object_or_404(Series.objects.select_related("page"), pk=pk)


def _payload(ch) -> dict:
    return {"channel": services.channel_dict(ch), **services.report(ch)}


@api_view(["GET", "PUT", "PATCH"])
def series_channel(request, pk):
    s = _series(pk)
    ch = services.get_channel(s)
    if request.method in ("PUT", "PATCH"):
        ch = services.update(ch, request.data if isinstance(request.data, dict) else {})
    return Response(_payload(ch))


@api_view(["POST"])
def channel_plan(request, pk):
    s = _series(pk)
    services.get_channel(s)
    return job_response(queue.enqueue("channel.season", {"series_id": s.pk, "instruction": str(request.data.get("instruction") or "")[:1000],
                                                          "language": str(request.data.get("language") or "")[:2]}, page=s.page_id, title=f"برنامهٔ فصل «{s.title}»"))


@api_view(["POST"])
def channel_template(request, pk):
    """Start the channel from a ready-made season (genre, cast with drawn identities, the whole season slate)."""
    ch = services.apply_template(services.get_channel(_series(pk)), str(request.data.get("key") or ""))
    return Response(_payload(ch))


@api_view(["GET"])
def channel_templates(request):
    return Response({"templates": season_templates.listing()})


@api_view(["POST"])
def channel_approve(request, pk):
    return Response(_payload(services.approve(services.get_channel(_series(pk)))))


@api_view(["POST"])
def channel_revoke(request, pk):
    return Response(_payload(services.revoke(services.get_channel(_series(pk)))))


@api_view(["POST"])
def channel_apply(request, pk):
    return Response(_payload(services.write_episodes(services.get_channel(_series(pk)))))


@api_view(["GET"])
def channel_conventions(request):
    return Response(conventions.public())


urlpatterns = [
    path("series/<int:pk>/channel", series_channel),
    path("series/<int:pk>/channel/plan", channel_plan),
    path("series/<int:pk>/channel/template", channel_template),
    path("series/<int:pk>/channel/approve", channel_approve),
    path("series/<int:pk>/channel/revoke", channel_revoke),
    path("series/<int:pk>/channel/apply", channel_apply),
    path("channel/conventions", channel_conventions),
    path("channel/templates", channel_templates),
]
