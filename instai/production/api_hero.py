"""Phase 3 API: anime model candidates + comparison + vote, per-page production settings, character LoRA, shot renders (QC numbers)."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.assets.api import asset_dict
from instai.assets.models import Asset
from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.pages.models import Character, ContentPage
from instai.story.models import Episode, Shot

from . import anime
from .models import AnimeComparison, CharacterLora, ComparisonClip, PageProductionConfig, ShotRender

CONFIG_FIELDS = ("anime_model", "default_technique", "gpu_minutes_per_week", "api_usd_per_week", "render_windows", "utc_offset_minutes", "music_enabled")


def config_dict(cfg: PageProductionConfig) -> dict:
    return {"page": cfg.page_id, **{f: getattr(cfg, f) for f in CONFIG_FIELDS}, "auto_publish_enabled": cfg.auto_publish_enabled,
            "auto_publish_confirmed_at": cfg.auto_publish_confirmed_at}


@api_view(["GET"])
def anime_candidates(request):
    return Response(anime.describe())


def comparison_dict(c: AnimeComparison, detail: bool = True) -> dict:
    d = {"id": c.pk, "page": c.page_id, "name": c.name, "prompt": c.prompt, "seeds": c.seeds, "candidates": c.candidates, "status": c.status, "winner": c.winner,
         "counts": anime.tally(c), "created_at": c.created_at, "stills": []}
    if detail:
        d["stills"] = [asset_dict(a) for a in Asset.objects.filter(pk__in=c.stills)]
        d["stills"].sort(key=lambda a: c.stills.index(a["id"]))
        d["clips"] = [{"id": k.pk, "still_index": k.still_index, "seed": k.seed, "candidate": k.candidate, "status": k.status, "seconds": k.seconds, "device": k.device,
                       "error": k.error, "url": k.asset.url if k.asset_id else None} for k in c.clips.select_related("asset")]
    return d


@api_view(["GET", "POST"])
def comparisons(request):
    if request.method == "POST":
        d = request.data
        page = get_object_or_404(ContentPage, pk=d["page"]) if d.get("page") else None
        stills = [int(a) for a in (d.get("stills") or [])]
        if d.get("episode"):
            ep = get_object_or_404(Episode, pk=d["episode"])
            stills = list(Asset.objects.filter(episode=ep, role="keyframe", is_current=True).order_by("shot_id").values_list("pk", flat=True))[:3]
            page = page or ep.series.page
        if not stills or not Asset.objects.filter(pk__in=stills, kind="image").count():
            raise DomainError("validation_error", "حداقل یک تصویر ثابت لازم است (شناسهٔ دارایی یا یک قسمت دارای تصویر کلیدی).", http_status=400, details={"stills": ["required"]})
        cmp = anime.create(page, name=str(d.get("name") or ""), prompt=str(d.get("prompt") or ""), seeds=d.get("seeds") or [11, 12], still_assets=stills,
                           candidates=d.get("candidates") or ["wan22", "anisora", "animegen"])
        resp = job_response(queue.enqueue("compare.run", {"comparison_id": cmp.pk}, title=f"مقایسهٔ مدل‌های انیمه #{cmp.pk}", page=page.pk if page else None))
        resp.data["comparison"] = comparison_dict(cmp)
        return resp
    qs = AnimeComparison.objects.all()
    if request.query_params.get("page"):
        qs = qs.filter(page_id=request.query_params["page"])
    return Response([comparison_dict(c, detail=False) for c in qs[:30]])


@api_view(["GET"])
def comparison_detail(request, pk):
    return Response(comparison_dict(get_object_or_404(AnimeComparison, pk=pk)))


@api_view(["POST"])
def comparison_run(request, pk):
    c = get_object_or_404(AnimeComparison, pk=pk)
    ComparisonClip.objects.filter(comparison=c, status__in=("skipped", "failed")).update(status="queued", error="")
    return job_response(queue.enqueue("compare.run", {"comparison_id": c.pk}, title=f"مقایسهٔ مدل‌های انیمه #{c.pk}", page=c.page_id,
                                      idempotency_key=f"compare:{c.pk}:{ComparisonClip.objects.filter(comparison=c, status='done').count()}"))


@api_view(["POST"])
def comparison_vote(request, pk):
    c = get_object_or_404(AnimeComparison, pk=pk)
    r = anime.vote(c, str(request.data.get("candidate") or ""), request.data.get("still_index"))
    return Response({**r, "comparison": comparison_dict(c)})


@api_view(["GET", "PUT"])
def page_config(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    cfg, _ = PageProductionConfig.objects.get_or_create(page=page)
    if request.method == "PUT":
        d = request.data
        if "anime_model" in d and d["anime_model"] not in ("wan22", "anisora", "animegen"):
            raise DomainError("validation_error", "مدل انیمه نامعتبر است.", http_status=400, details={"anime_model": ["invalid"]})
        for f in CONFIG_FIELDS:
            if f in d and f != "render_windows":
                setattr(cfg, f, d[f])
        if "render_windows" in d:
            from . import scheduling

            cfg.render_windows = scheduling.validate_windows(d["render_windows"])
        cfg.save()
    return Response(config_dict(cfg))


def lora_dict(l: CharacterLora) -> dict:
    return {"id": l.pk, "character": l.character_id, "status": l.status, "lora_file": l.lora_file, "params": l.params, "before": l.before, "after": l.after,
            "seconds": l.seconds, "error": l.error, "approved": l.approved, "created_at": l.created_at}


@api_view(["GET", "POST"])
def character_loras(request, pk):
    ch = get_object_or_404(Character, pk=pk)
    if request.method == "POST":
        d = request.data
        lora = CharacterLora.objects.create(character=ch, params={"steps": int(d.get("steps") or 300), "rank": int(d.get("rank") or 16),
                                                                  "test_prompts": d.get("test_prompts") or []})
        resp = job_response(queue.enqueue("lora.train", {"lora_id": lora.pk}, title=f"آموزش LoRA «{ch.name}»", page=ch.page_id, max_attempts=1))
        resp.data["lora"] = lora_dict(lora)
        return resp
    return Response([lora_dict(l) for l in CharacterLora.objects.filter(character=ch)])


@api_view(["PATCH"])
def lora_detail(request, pk):
    l = get_object_or_404(CharacterLora, pk=pk)
    if "approved" in request.data:
        l.approved = bool(request.data["approved"])
        l.save(update_fields=["approved"])
    return Response(lora_dict(l))


def render_dict(r: ShotRender) -> dict:
    return {"id": r.pk, "shot": r.shot_id, "technique": r.technique, "status": r.status, "device": r.device, "seconds": r.seconds, "qc": r.qc, "params": r.params,
            "error": r.error, "asset": asset_dict(r.asset) if r.asset_id else None, "created_at": r.created_at}


@api_view(["GET"])
def episode_renders(request, pk):
    ep = get_object_or_404(Episode, pk=pk)
    return Response([render_dict(r) for r in ShotRender.objects.filter(shot__scene__episode=ep).select_related("asset")[:100]])


@api_view(["GET"])
def shot_renders(request, pk):
    shot = get_object_or_404(Shot, pk=pk)
    return Response([render_dict(r) for r in ShotRender.objects.filter(shot=shot).select_related("asset")[:30]])


urlpatterns = [
    path("anime/candidates", anime_candidates),
    path("comparisons", comparisons),
    path("comparisons/<int:pk>", comparison_detail),
    path("comparisons/<int:pk>/run", comparison_run),
    path("comparisons/<int:pk>/vote", comparison_vote),
    path("pages/<int:pk>/production-config", page_config),
    path("characters/<int:pk>/loras", character_loras),
    path("loras/<int:pk>", lora_detail),
    path("episodes/<int:pk>/renders", episode_renders),
    path("shots/<int:pk>/renders", shot_renders),
]
