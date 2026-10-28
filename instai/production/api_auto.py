"""Phase 4 API: automation level + budgets + render windows, the publication schedule, notifications, publishing targets/adapters and the explicit publish action."""
from __future__ import annotations

from datetime import datetime, timezone

from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone as dj_tz
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.pages.models import ContentPage
from instai.publishing import adapters, notifications
from instai.publishing.models import Notification, Publication, PublishTarget

from . import automation, scheduling

LEVELS = ("manual", "assisted", "automatic")
TARGET_CONFIG_KEYS = ("ig_user_id", "facebook_page_linked", "public_base_url", "token_env", "api_version", "graph_base", "poll_seconds")
CONFIRM_TEXT = "I understand InstAI may post to my account"


def automation_dict(page: ContentPage) -> dict:
    cfg = automation.config(page)
    now = dj_tz.now()
    prof = page.profile("publishing")
    target = page.targets.first()
    slots = scheduling.publication_slots(prof["per_week"], prof["days"], prof["time"], now, 4, cfg.utc_offset_minutes)
    return {"page": page.pk, "level": page.automation_level, "levels": list(LEVELS), "usage": automation.usage(page, now), "gpu_minutes_per_week": cfg.gpu_minutes_per_week,
            "api_usd_per_week": cfg.api_usd_per_week, "render_windows": cfg.render_windows, "utc_offset_minutes": cfg.utc_offset_minutes,
            "window_open_now": scheduling.window_open(cfg.render_windows, now, cfg.utc_offset_minutes),
            "next_window": scheduling.next_window_open(cfg.render_windows, now, cfg.utc_offset_minutes),
            "publishing": {"per_week": prof["per_week"], "days": prof["days"], "time": prof["time"], "next_slots": slots},
            "auto_publish": {"enabled": cfg.auto_publish_enabled, "confirmed_at": cfg.auto_publish_confirmed_at, "confirm_text": CONFIRM_TEXT,
                             "can_post_now": adapters.can_auto_publish(page, target)[0], "why_not": adapters.can_auto_publish(page, target)[1],
                             "feature_flag": adapters.feature_enabled()},
            "explain": {"manual": "nothing runs by itself", "assisted": "previews run by themselves; costly steps ask you", "automatic": "script, final render and the publication package run within the budgets; you approve the episode"}}


@api_view(["GET", "PUT"])
def page_automation(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    if request.method == "PUT":
        d = request.data
        cfg = automation.config(page)
        if "level" in d:
            if d["level"] not in LEVELS:
                raise DomainError("validation_error", "سطح خودکارسازی نامعتبر است.", http_status=400, details={"level": ["invalid"]})
            page.automation_level = d["level"]
            page.save(update_fields=["automation_level", "updated_at"])
        for f, cast in (("gpu_minutes_per_week", int), ("api_usd_per_week", float), ("utc_offset_minutes", int)):
            if f in d:
                try:
                    setattr(cfg, f, max(0, cast(d[f])) if f != "utc_offset_minutes" else max(-720, min(840, int(d[f]))))
                except (TypeError, ValueError):
                    raise DomainError("validation_error", f"{f} نامعتبر است.", http_status=400, details={f: ["invalid"]})
        if "render_windows" in d:
            cfg.render_windows = scheduling.validate_windows(d["render_windows"])
        cfg.save()
    return Response(automation_dict(page))


@api_view(["POST"])
def auto_publish(request, pk):
    """Explicit, per-page enablement of automatic posting. Needs the exact confirmation sentence; disabling needs nothing."""
    page = get_object_or_404(ContentPage, pk=pk)
    cfg = automation.config(page)
    if request.data.get("enable"):
        if request.data.get("confirm") != CONFIRM_TEXT:
            raise DomainError("validation_error", "برای فعال‌کردنِ انتشار خودکار باید جملهٔ تأیید را دقیقاً بنویسید.", http_status=400, details={"confirm": ["required"]})
        cfg.auto_publish_enabled, cfg.auto_publish_confirmed_at = True, dj_tz.now()
    else:
        cfg.auto_publish_enabled, cfg.auto_publish_confirmed_at = False, None
    cfg.save()
    return Response(automation_dict(page))


@api_view(["POST"])
def automation_tick(request):
    """Run one automation pass now (the worker does it every 30 s)."""
    return Response({"actions": automation.tick()})


@api_view(["GET"])
def page_schedule(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    cfg = automation.config(page)
    prof = page.profile("publishing")
    n = max(1, min(20, int(request.query_params.get("n", 6))))
    return Response({"slots": scheduling.publication_slots(prof["per_week"], prof["days"], prof["time"], dj_tz.now(), n, cfg.utc_offset_minutes),
                     "scheduled": [{"id": p.pk, "episode": p.episode_id, "title": p.episode.title, "scheduled_at": p.scheduled_at, "status": p.status}
                                   for p in Publication.objects.filter(episode__series__page=page, status__in=("scheduled", "exported")).select_related("episode").order_by("scheduled_at")[:30]]})


# ------------------------------------------------------------------ notifications

@api_view(["GET"])
def notifications_list(request):
    qs = Notification.objects.all()
    if request.query_params.get("unread") == "1":
        qs = qs.filter(read=False)
    return Response({"unread": notifications.unread_count(), "items": [notifications.as_dict(n) for n in qs[: int(request.query_params.get("limit", 50))]]})


@api_view(["POST"])
def notifications_read(request):
    qs = Notification.objects.filter(read=False)
    if not request.data.get("all"):
        qs = qs.filter(pk__in=request.data.get("ids") or [])
    qs.update(read=True)
    return Response({"unread": notifications.unread_count()})


# ------------------------------------------------------------------ publishing targets / adapters / explicit publish

def target_dict(t: PublishTarget) -> dict:
    ad = adapters.adapter_for(t)
    return {"id": t.pk, "page": t.page_id, "platform": t.platform, "handle": t.handle, "mode": t.mode, "enabled": t.enabled, "config": {k: v for k, v in (t.config or {}).items() if k in TARGET_CONFIG_KEYS},
            "adapter": ad.name, "adapter_label": ad.label, "requirements": ad.requirements(t), "ready": ad.ready(t)}


@api_view(["GET", "PATCH"])
def target_detail(request, pk):
    t = get_object_or_404(PublishTarget, pk=pk)
    if request.method == "PATCH":
        d = request.data
        if "mode" in d:
            if d["mode"] not in ("manual", "api"):
                raise DomainError("validation_error", "حالت باید manual یا api باشد.", http_status=400, details={"mode": ["invalid"]})
            t.mode = d["mode"]
        if "enabled" in d:
            t.enabled = bool(d["enabled"])
        if "handle" in d:
            t.handle = str(d["handle"])[:120]
        if isinstance(d.get("config"), dict):
            t.config = {**(t.config or {}), **{k: v for k, v in d["config"].items() if k in TARGET_CONFIG_KEYS}}   # a token is never accepted here: it lives in .env
        t.save()
    return Response(target_dict(t))


@api_view(["GET"])
def adapters_list(request):
    return Response([{"name": n, "label": c().label, "requirements": c().requirements(None)} for n, c in adapters.ADAPTERS.items()])


@api_view(["POST"])
def publication_publish(request, pk):
    """The owner presses "publish now": the official API only when the target is an enabled API target and every requirement is met."""
    p = get_object_or_404(Publication.objects.select_related("episode__series__page", "target"), pk=pk)
    if not request.data.get("confirm"):
        raise DomainError("validation_error", "این کار پست را در حساب واقعی منتشر می‌کند؛ تأیید لازم است (confirm: true).", http_status=400, details={"confirm": ["required"]})
    ad = adapters.adapter_for(p.target)
    if ad.name != "manual" and not ad.ready(p.target):
        raise DomainError("not_ready", "پیش‌نیازهای انتشار با API کامل نیست: " + "؛ ".join(r["text"] for r in ad.requirements(p.target) if not r["ok"]), http_status=409)
    return job_response(queue.enqueue("publish.send", {"publication_id": p.pk}, episode=p.episode, page=p.episode.series.page_id, title=f"انتشار قسمت {p.episode.number}", max_attempts=1))


urlpatterns = [
    path("pages/<int:pk>/automation", page_automation),
    path("pages/<int:pk>/auto-publish", auto_publish),
    path("pages/<int:pk>/schedule", page_schedule),
    path("automation/tick", automation_tick),
    path("notifications", notifications_list),
    path("notifications/read", notifications_read),
    path("targets/<int:pk>", target_detail),
    path("publishing/adapters", adapters_list),
    path("publications/<int:pk>/publish", publication_publish),
]
