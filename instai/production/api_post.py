"""Post-production API: time-range video retakes (with audio replace / mute / cut and revert) and the episode's music / ambience / SFX mix."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.assets.api import asset_dict
from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.story.models import Episode, Shot

from . import mixing, retakes
from .models import MixTrack, Retake


def retake_dict(r: Retake) -> dict:
    return {"id": r.pk, "episode": r.episode_id, "source_asset": r.source_asset_id, "start_sec": r.start_sec, "end_sec": r.end_sec, "prompt": r.prompt,
            "audio_mode": r.audio_mode, "status": r.status, "result": asset_dict(r.result_asset) if r.result_asset_id else None, "seam": r.seam, "error": r.error,
            "created_at": r.created_at}


@api_view(["GET", "POST"])
def episode_video_retakes(request, pk):
    ep = get_object_or_404(Episode, pk=pk)
    if request.method == "POST":
        d = request.data
        try:
            start, end = float(d.get("start_sec")), float(d.get("end_sec"))
        except (TypeError, ValueError):
            raise DomainError("validation_error", "ثانیهٔ شروع و پایان لازم است.", http_status=400, details={"start_sec": ["required"]})
        r = retakes.create(ep, start_sec=start, end_sec=end, prompt=str(d.get("prompt") or ""), audio_mode=str(d.get("audio_mode") or "keep"),
                           audio_asset=d.get("audio_asset"), source_asset=d.get("source_asset"))
        resp = job_response(queue.enqueue("retake.run", {"retake_id": r.pk, "audio_mode": r.audio_mode}, episode=ep, page=ep.series.page_id,
                                          title=f"بازسازی بازه {r.start_sec:.1f}–{r.end_sec:.1f} ثانیه", max_attempts=1))
        resp.data["retake"] = retake_dict(r)
        return resp
    return Response([retake_dict(r) for r in ep.retakes.select_related("result_asset")[:30]])


@api_view(["GET"])
def video_retake_detail(request, pk):
    return Response(retake_dict(get_object_or_404(Retake, pk=pk)))


@api_view(["POST"])
def video_retake_revert(request, pk):
    r = get_object_or_404(Retake, pk=pk)
    retakes.revert(r)
    return Response(retake_dict(r))


def track_dict(t: MixTrack) -> dict:
    return {"id": t.pk, "episode": t.episode_id, "shot": t.shot_id, "kind": t.kind, "label": t.label, "prompt": t.prompt, "start_sec": t.start_sec, "end_sec": t.end_sec,
            "gain_db": t.gain_db, "duck": t.duck, "fade_in": t.fade_in, "fade_out": t.fade_out, "status": t.status, "error": t.error,
            "asset": asset_dict(t.asset) if t.asset_id else None}


@api_view(["GET", "POST"])
def episode_mix(request, pk):
    ep = get_object_or_404(Episode, pk=pk)
    if request.method == "POST":
        d = request.data
        if d.get("kind") not in ("music", "sfx", "ambience"):
            raise DomainError("validation_error", "نوع باید music، sfx یا ambience باشد.", http_status=400, details={"kind": ["invalid"]})
        shot = get_object_or_404(Shot, pk=d["shot"], scene__episode=ep) if d.get("shot") else None
        t = MixTrack.objects.create(episode=ep, shot=shot, kind=d["kind"], label=str(d.get("label") or d.get("prompt") or d["kind"])[:160], prompt=str(d.get("prompt") or ""),
                                    start_sec=float(d.get("start_sec") or 0), gain_db=float(d.get("gain_db", -18 if d["kind"] != "sfx" else -12)),
                                    duck=bool(d.get("duck", d["kind"] != "sfx")))
        return Response(track_dict(t), status=201)
    return Response({"tracks": [track_dict(t) for t in ep.mix_tracks.select_related("asset")], "engines": {"music": "ACE-Step 1.5 (MIT)", "sfx": "MOSS-SoundEffect v2.0 (Apache-2.0)"}})


@api_view(["POST"])
def episode_mix_plan(request, pk):
    ep = get_object_or_404(Episode, pk=pk)
    mixing.plan(ep)
    return Response({"tracks": [track_dict(t) for t in ep.mix_tracks.select_related("asset")]})


@api_view(["POST"])
def episode_mix_generate(request, pk):
    ep = get_object_or_404(Episode, pk=pk)
    ids = [t.pk for t in ep.mix_tracks.filter(status__in=("planned", "failed"))]
    if request.data.get("track_ids"):
        ids = [i for i in request.data["track_ids"] if ep.mix_tracks.filter(pk=i).exists()]
    if not ids:
        raise DomainError("conflict", "همهٔ ترک‌ها آماده‌اند یا ترکی برنامه‌ریزی نشده است.", http_status=409)
    return job_response(queue.enqueue("audio.generate", {"track_ids": ids}, episode=ep, page=ep.series.page_id, title=f"ساخت صدا ({len(ids)} ترک)"))


@api_view(["PATCH", "DELETE"])
def mix_track_detail(request, pk):
    t = get_object_or_404(MixTrack, pk=pk)
    if request.method == "DELETE":
        t.delete()
        return Response(status=204)
    d = request.data
    regenerate = False
    for f in ("label", "prompt"):
        if f in d:
            regenerate = regenerate or (f == "prompt" and d[f] != t.prompt)
            setattr(t, f, str(d[f])[:400] if f == "label" else str(d[f]))
    for f in ("start_sec", "end_sec", "gain_db", "fade_in", "fade_out"):
        if f in d:
            setattr(t, f, None if d[f] in (None, "") and f == "end_sec" else float(d[f]))
    if "duck" in d:
        t.duck = bool(d["duck"])
    if regenerate and t.asset_id:
        t.status, t.asset = "planned", None            # a new prompt needs new audio
    t.save()
    return Response(track_dict(t))


urlpatterns = [
    path("episodes/<int:pk>/video-retakes", episode_video_retakes),
    path("video-retakes/<int:pk>", video_retake_detail),
    path("video-retakes/<int:pk>/revert", video_retake_revert),
    path("episodes/<int:pk>/mix", episode_mix),
    path("episodes/<int:pk>/mix/plan", episode_mix_plan),
    path("episodes/<int:pk>/mix/generate", episode_mix_generate),
    path("mix-tracks/<int:pk>", mix_track_detail),
]
