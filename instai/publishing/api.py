"""Publishing centre (release 1): captions, hashtags, cover, schedule, status and a manual-export package. Nothing auto-publishes."""
from __future__ import annotations

from instai.core.fa_digits import fa_digits

from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.pages.models import ContentPage
from instai.render import delivery, loudness
from instai.story import services, states
from instai.story.models import Episode

from . import hashtags as hashtags_mod
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
                                      title=f"بسته‌ی انتشار قسمت {fa_digits(p.episode.number)}", idempotency_key=f"export:{p.pk}:{p.updated_at.timestamp()}"))


def _network_info(platform: str) -> dict:
    key = delivery.network_for(platform)
    n = delivery.NETWORKS.get(key or "")
    return {"network": key, "network_fa": n["fa"] if n else platform, "network_en": n["en"] if n else platform}


@api_view(["GET", "POST"])
def page_targets(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    if request.method == "POST":
        platform = str(request.data.get("platform", "instagram") or "instagram").strip().lower()
        if delivery.network_for(platform) is None:
            raise DomainError("validation_error", "این شبکه را نمی‌شناسم: " + platform, http_status=400, details={"platform": ["unknown"]},
                              message_en="Unknown network: " + platform)
        t = PublishTarget.objects.create(page=page, platform=platform, handle=request.data.get("handle", ""), mode="manual")
        return Response({"id": t.pk, "platform": t.platform, "handle": t.handle, "mode": t.mode, **_network_info(t.platform)}, status=201)
    return Response([{"id": t.pk, "platform": t.platform, "handle": t.handle, "mode": t.mode, "enabled": t.enabled, "fit": (t.config or {}).get("fit", ""),
                     **_network_info(t.platform)} for t in page.targets.all()])


@api_view(["GET"])
def delivery_networks(request):
    """The nine networks (size, frame rate, quality, length limit, safe zone, loudness: all approximate), the loudness profiles and the shapes the assembly can render."""
    return Response({"networks": delivery.catalogue(), "loudness_profiles": loudness.catalogue(), "rerender_aspects": list(delivery.RERENDER_ASPECTS),
                     "legacy": delivery.LEGACY_PLATFORM})


@api_view(["GET", "POST"])
def publication_delivery(request, pk):
    """What the package of this publication will hold (the networks of the page's targets with their status and the reason for any missing file) and the caption check.
    POST {caption, hashtags} checks a DRAFT text (what is typed in the box, not yet saved)."""
    from . import delivery_package as dp

    pub = get_object_or_404(Publication.objects.select_related("episode__series__page", "cover"), pk=pk)
    plan = dp.plan_for(pub)
    if request.method == "POST" and ("caption" in request.data or "hashtags" in request.data):
        cap = request.data.get("caption", pub.caption)
        tags = request.data.get("hashtags", pub.hashtags)
        tags = tags if isinstance(tags, list) else []
        plan["lint"] = dp.lint_for(pub, str(cap or ""), tags, [n["key"] for n in plan["networks"]])
        vocab = hashtags_mod.page_vocabulary(pub.episode.series.page, pub.episode.series, pub.episode)
        rep = [hashtags_mod.clean(hashtags_mod.repair(h, vocab)) for h in tags if isinstance(h, str)]
        plan["hashtags"] = {"given": [h for h in tags if isinstance(h, str)], "repaired": rep, "changed": [h for h, r in zip(tags, rep) if hashtags_mod.clean(h) != r]}
    return Response(plan)


urlpatterns = [
    path("pages/<int:pk>/publications", page_publications),
    path("pages/<int:pk>/targets", page_targets),
    path("publications/<int:pk>", publication_detail),
    path("publications/<int:pk>/export", publication_export),
    path("publications/<int:pk>/delivery", publication_delivery),
    path("delivery/networks", delivery_networks),
]
