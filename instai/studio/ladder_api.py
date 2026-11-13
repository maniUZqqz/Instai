"""Studio ladder API: the review screen of a series (development stages) and of an episode (all stages): versions, edit, generate, approve, restore, compare."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.story.models import Episode, Series

from . import ladder
from .ladder_stages import public as catalogue


def _series(pk) -> Series:
    return get_object_or_404(Series.objects.select_related("page"), pk=pk)


def _ep(pk) -> Episode:
    return get_object_or_404(Episode.objects.select_related("series__page"), pk=pk)


def _target(request, series_pk=None, ep_pk=None):
    """(series, episode or None) of the URL; a stage must belong to the right scope."""
    if ep_pk is not None:
        e = _ep(ep_pk)
        return e.series, e
    return _series(series_pk), None


def _stage_check(key: str, ep) -> dict:
    st = ladder.stage(key)
    if st["scope"] == "episode" and ep is None:
        raise DomainError("validation_error", "این مرحله به قسمت تعلق دارد.", http_status=400, message_en="This stage belongs to an episode.")
    return st


@api_view(["GET"])
def series_ladder(request, pk):
    s = _series(pk)
    ladder.auto_pass(s, None)
    return Response(ladder.payload(s, None))


@api_view(["GET"])
def episode_ladder(request, pk):
    e = _ep(pk)
    ladder.auto_pass(e.series, e)
    return Response(ladder.payload(e.series, e))


@api_view(["GET"])
def ladder_catalogue(request):
    return Response(catalogue())


def _save(request, s, e, key):
    st = _stage_check(key, e)
    d = request.data if isinstance(request.data, dict) else {}
    if not isinstance(d.get("data"), dict):
        raise DomainError("validation_error", "داده لازم است.", http_status=400, message_en="Data is required.", details={"data": ["required"]})
    ladder.save_version(s, e, st["key"], d["data"], author="human", note=str(d.get("note") or "edited")[:300])
    return Response(ladder.payload(s, e))


@api_view(["PUT"])
def series_stage_save(request, pk, key):
    s, e = _target(request, series_pk=pk)
    return _save(request, s, e, key)


@api_view(["PUT"])
def episode_stage_save(request, pk, key):
    s, e = _target(request, ep_pk=pk)
    return _save(request, s, e, key)


def _generate(request, s, e, key):
    st = _stage_check(key, e)
    if st["gen"] is None:
        raise DomainError("conflict", "این مرحله با هوش مصنوعی ساخته نمی‌شود.", http_status=409, message_en="This stage is not written by a model.")
    lang = str(request.data.get("language") or request.headers.get("X-Lang") or "")[:2]
    payload = {"series_id": s.pk, "episode_id": e.pk if e else None, "stage": key, "instruction": str(request.data.get("instruction") or "")[:1000], "language": lang}
    return job_response(queue.enqueue("studio.ladder", payload, page=s.page_id, episode=e, title=f"{st['fa']}"))


@api_view(["POST"])
def series_stage_generate(request, pk, key):
    s, e = _target(request, series_pk=pk)
    return _generate(request, s, e, key)


@api_view(["POST"])
def episode_stage_generate(request, pk, key):
    s, e = _target(request, ep_pk=pk)
    return _generate(request, s, e, key)


def _approve(request, s, e, key, what):
    _stage_check(key, e)
    if what == "approve":
        num = request.data.get("version") if isinstance(request.data, dict) else None
        ladder.approve(s, e, key, int(num) if num else None)
        ladder.auto_pass(s, e)
    else:
        ladder.revoke(s, e, key)
    return Response(ladder.payload(s, e))


@api_view(["POST"])
def series_stage_approve(request, pk, key):
    s, e = _target(request, series_pk=pk)
    return _approve(request, s, e, key, "approve")


@api_view(["POST"])
def series_stage_revoke(request, pk, key):
    s, e = _target(request, series_pk=pk)
    return _approve(request, s, e, key, "revoke")


@api_view(["POST"])
def episode_stage_approve(request, pk, key):
    s, e = _target(request, ep_pk=pk)
    return _approve(request, s, e, key, "approve")


@api_view(["POST"])
def episode_stage_revoke(request, pk, key):
    s, e = _target(request, ep_pk=pk)
    return _approve(request, s, e, key, "revoke")


def _version(s, e, key, number):
    _stage_check(key, e)
    d = ladder.doc(s, e, key)
    v = ladder.version(d, int(number)) if d else None
    if v is None:
        raise DomainError("not_found", http_status=404)
    return v


@api_view(["GET"])
def series_stage_version(request, pk, key, number):
    s, e = _target(request, series_pk=pk)
    return Response(ladder.version_dict(_version(s, e, key, number), data=True))


@api_view(["GET"])
def episode_stage_version(request, pk, key, number):
    s, e = _target(request, ep_pk=pk)
    return Response(ladder.version_dict(_version(s, e, key, number), data=True))


def _diff(request, s, e, key):
    a, b = int(request.query_params.get("a") or 0), int(request.query_params.get("b") or 0)
    va, vb = _version(s, e, key, a), _version(s, e, key, b)
    return Response({"a": a, "b": b, "changes": ladder.diff(va.data, vb.data)})


@api_view(["GET"])
def series_stage_diff(request, pk, key):
    s, e = _target(request, series_pk=pk)
    return _diff(request, s, e, key)


@api_view(["GET"])
def episode_stage_diff(request, pk, key):
    s, e = _target(request, ep_pk=pk)
    return _diff(request, s, e, key)


def _restore(request, s, e, key):
    _stage_check(key, e)
    ladder.restore(s, e, key, int(request.data.get("version") or 0))
    return Response(ladder.payload(s, e))


@api_view(["POST"])
def series_stage_restore(request, pk, key):
    s, e = _target(request, series_pk=pk)
    return _restore(request, s, e, key)


@api_view(["POST"])
def episode_stage_restore(request, pk, key):
    s, e = _target(request, ep_pk=pk)
    return _restore(request, s, e, key)


urlpatterns = [
    path("ladder/catalogue", ladder_catalogue),
    path("series/<int:pk>/ladder", series_ladder),
    path("series/<int:pk>/ladder/<str:key>", series_stage_save),
    path("series/<int:pk>/ladder/<str:key>/generate", series_stage_generate),
    path("series/<int:pk>/ladder/<str:key>/approve", series_stage_approve),
    path("series/<int:pk>/ladder/<str:key>/revoke", series_stage_revoke),
    path("series/<int:pk>/ladder/<str:key>/restore", series_stage_restore),
    path("series/<int:pk>/ladder/<str:key>/diff", series_stage_diff),
    path("series/<int:pk>/ladder/<str:key>/versions/<int:number>", series_stage_version),
    path("episodes/<int:pk>/ladder", episode_ladder),
    path("episodes/<int:pk>/ladder/<str:key>", episode_stage_save),
    path("episodes/<int:pk>/ladder/<str:key>/generate", episode_stage_generate),
    path("episodes/<int:pk>/ladder/<str:key>/approve", episode_stage_approve),
    path("episodes/<int:pk>/ladder/<str:key>/revoke", episode_stage_revoke),
    path("episodes/<int:pk>/ladder/<str:key>/restore", episode_stage_restore),
    path("episodes/<int:pk>/ladder/<str:key>/diff", episode_stage_diff),
    path("episodes/<int:pk>/ladder/<str:key>/versions/<int:number>", episode_stage_version),
]
