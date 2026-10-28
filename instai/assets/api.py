from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Asset


def asset_dict(a: Asset) -> dict:
    return {"id": a.pk, "kind": a.kind, "role": a.role, "url": a.url, "mime": a.mime, "size_bytes": a.size_bytes, "duration_sec": a.duration_sec,
            "fps": a.fps, "width": a.width, "height": a.height, "codec": a.codec, "loudness_lufs": a.loudness_lufs, "version": a.version,
            "is_current": a.is_current, "approved": a.approved, "provenance": a.provenance, "episode": a.episode_id, "shot": a.shot_id,
            "created_at": a.created_at}


@api_view(["GET"])
def assets(request):
    qs = Asset.objects.all()
    q = request.query_params
    for f in ("episode", "shot", "role", "kind", "page"):
        if q.get(f):
            qs = qs.filter(**{f"{f}_id" if f in ("episode", "shot", "page") else f: q[f]})
    if q.get("current") == "1":
        qs = qs.filter(is_current=True)
    return Response([asset_dict(a) for a in qs[:200]])


@api_view(["GET", "PATCH"])
def asset_detail(request, pk):
    a = get_object_or_404(Asset, pk=pk)
    if request.method == "PATCH" and "approved" in request.data:
        a.approved = bool(request.data["approved"])
        a.save(update_fields=["approved"])
    return Response(asset_dict(a))


urlpatterns = [path("assets", assets), path("assets/<int:pk>", asset_detail)]
