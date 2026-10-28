"""Automation levels that really drive the pipeline, the weekly budgets, the render windows and the publication schedule.

`tick()` runs every ~30 s inside the worker. For every active page it looks at its episodes and decides, by the page's automation level:

  manual     nothing happens by itself.
  assisted   cheap steps run by themselves (a preview render once the storyboard and the pre-production gate are fine); every decision that costs
             real GPU time or commits content (approve the script, make the final render, approve the episode) becomes a NOTIFICATION.
  automatic  also approves the script, makes the final render (inside the weekly GPU-minute budget and the render windows, e.g. "nights only")
             and prepares the publication package. The owner still approves the finished episode; nothing is published without explicit,
             per-page enablement (publishing/adapters.can_auto_publish) - otherwise the due time only produces a reminder + the manual package.

Budgets: GPU minutes (Job.gpu_seconds of the page's jobs this week, including time spent on worker PCs) and API dollars (token counts of
LLM jobs x the prices set in Settings). A render that would exceed the budget does not start; a notification says so once per week.
Everything here is idempotent: running tick twice does the same as once.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from django.utils import timezone as dj_tz

from instai.core import settings_store
from instai.jobs import queue
from instai.jobs.models import Job
from instai.pages.models import ContentPage
from instai.publishing import adapters
from instai.publishing.models import Publication
from instai.publishing.notifications import notify
from instai.story import costs, services, states
from instai.story.models import Episode

from . import scheduling
from .models import PageProductionConfig

log = logging.getLogger("instai.automation")
BUFFER = 2                 # episodes kept in the pipeline ahead of publishing by `automatic`
PROD_KINDS = ("prod.keyframes", "prod.tts", "prod.clips", "prod.assemble")


def config(page) -> PageProductionConfig:
    cfg, _ = PageProductionConfig.objects.get_or_create(page=page)
    return cfg


# ------------------------------------------------------------------ budgets

def usage(page, now: datetime | None = None) -> dict:
    """GPU minutes and API dollars spent by this page's jobs in the owner's current week."""
    now = now or dj_tz.now()
    cfg = config(page)
    start = scheduling.week_start(now, cfg.utc_offset_minutes)
    gpu = api = 0.0
    p_in, p_out = float(settings_store.effective("openai_price_in_per_1k") or 0), float(settings_store.effective("openai_price_out_per_1k") or 0)
    for j in Job.objects.filter(page=page, created_at__gte=start).only("gpu_seconds", "result", "kind"):
        gpu += j.gpu_seconds or 0.0
        meta = (j.result or {}).get("meta") or {}
        if meta.get("provider") == "openai":
            api += (meta.get("prompt_tokens") or 0) / 1000 * p_in + (meta.get("completion_tokens") or 0) / 1000 * p_out
    return {"week_start": start, "gpu_minutes": round(gpu / 60, 1), "api_usd": round(api, 4), "gpu_budget": cfg.gpu_minutes_per_week, "api_budget": cfg.api_usd_per_week}


def final_estimate_minutes(ep: Episode) -> float:
    est = costs.episode_estimate(services.all_shots(ep), ("final",))
    return est["modes"]["final"]["gpu_minutes"]


def gpu_budget_allows(page, ep: Episode, now) -> tuple[bool, str]:
    u = usage(page, now)
    need = final_estimate_minutes(ep)
    if u["gpu_budget"] and u["gpu_minutes"] + need > u["gpu_budget"]:
        return False, f"{u['gpu_minutes']:.0f} + about {need:.0f} min would exceed the weekly budget of {u['gpu_budget']} min"
    return True, ""


def api_budget_allows(page, now) -> tuple[bool, str]:
    u = usage(page, now)
    if u["api_budget"] and u["api_usd"] >= u["api_budget"]:
        return False, f"${u['api_usd']:.2f} of the weekly ${u['api_budget']:.2f} API budget is used"
    return True, ""


# ------------------------------------------------------------------ helpers

def _busy(ep: Episode) -> bool:
    return Job.objects.filter(episode=ep, status__in=(Job.QUEUED, Job.RUNNING)).exists()


def _has_video(ep: Episode, role: str) -> bool:
    from instai.assets.models import Asset

    return Asset.objects.filter(episode=ep, role=role, is_current=True, kind="video").exists()


def _gate_ok(ep: Episode) -> bool:
    try:
        from instai.studio import preprod

        preprod.assert_gate(ep)
        return True
    except Exception:  # noqa: BLE001 - DomainError: pre-production not approved yet
        return False


def _link(ep: Episode) -> str:
    return f"/episodes/{ep.pk}"


def _label(ep: Episode) -> str:
    return f"{ep.series.page.name} - قسمت {ep.number}"


# ------------------------------------------------------------------ one episode

def step_episode(page, ep: Episode, level: str, now: datetime) -> list[dict]:
    """Decide and do the next automatic step of one episode. Returns what was done: [{episode, action, ...}]."""
    acts: list[dict] = []
    cfg = config(page)
    wk = scheduling.week_start(now, cfg.utc_offset_minutes).strftime("%Y%m%d")
    ep.refresh_from_db()
    if _busy(ep) or ep.state in (states.FAILED, states.CANCELLED, states.PUBLISHED, states.SCHEDULED):
        return acts
    st = ep.state

    if st in (states.DRAFT, states.PLANNED) and level == "automatic":
        active = Episode.objects.filter(series__page=page, state__in=[states.SCRIPTING, states.SCRIPT_REVIEW, states.STORYBOARDING, states.ASSET_GENERATION, states.ANIMATION,
                                                                    states.ASSEMBLY, states.QUALITY_REVIEW, states.READY_FOR_APPROVAL, states.APPROVED]).count()
        first = Episode.objects.filter(series__page=page, state__in=[states.DRAFT, states.PLANNED]).order_by("series_id", "number").first()
        if active < BUFFER and first and first.pk == ep.pk:
            ok, why = api_budget_allows(page, now)
            if not ok:
                notify("budget", f"بودجهٔ API تمام شد؛ فیلم‌نامهٔ {_label(ep)} ساخته نشد", body=why, level="warn", page=page, episode=ep, key=f"api-budget:{page.pk}:{wk}")
                return acts
            if ep.state == states.DRAFT:
                services.transition(ep, states.PLANNED, actor="system", reason="automatic: next episode")
            queue.enqueue("story.script", {"episode_id": ep.pk}, episode=ep, page=page.pk, title=f"فیلم‌نامه‌ی قسمت {ep.number} (خودکار)",
                          idempotency_key=f"auto-script:{ep.pk}")
            acts.append({"episode": ep.pk, "action": "script_started"})

    elif st == states.SCRIPT_REVIEW:
        if level == "automatic":
            services.transition(ep, states.STORYBOARDING, actor="system", reason="automatic: script approved")
            queue.enqueue("story.continuity", {"episode_id": ep.pk}, episode=ep, page=page.pk, title=f"حافظهٔ داستان (قسمت {ep.number})", idempotency_key=f"auto-cont:{ep.pk}")
            queue.enqueue("story.storyboard", {"episode_id": ep.pk}, episode=ep, page=page.pk, title=f"استوری‌بورد قسمت {ep.number} (خودکار)",
                          idempotency_key=f"auto-board:{ep.pk}")
            acts.append({"episode": ep.pk, "action": "script_approved"})
        else:
            notify("decision", f"فیلم‌نامهٔ {_label(ep)} آمادهٔ تأیید است", level="info", link=_link(ep), page=page, episode=ep, key=f"script:{ep.pk}", once=True)

    elif st == states.STORYBOARDING and services.all_shots(ep):
        if not _gate_ok(ep):
            notify("decision", f"پیش‌تولیدِ {_label(ep)} منتظر تأیید شماست", level="info", link=_link(ep), page=page, episode=ep, key=f"gate:{ep.pk}", once=True)
        else:
            from . import pipeline

            pipeline.start(ep, "preview", actor="system")
            acts.append({"episode": ep.pk, "action": "preview_started"})

    elif st == states.READY_FOR_APPROVAL:
        if _has_video(ep, "final"):
            notify("decision", f"قسمتِ {_label(ep)} برای تأیید آماده است", body="نسخهٔ نهایی ساخته و بررسی شد.", level="ok", link=_link(ep), page=page, episode=ep,
                   key=f"ready:{ep.pk}", once=True)
        elif _has_video(ep, "preview"):
            if level == "automatic":
                ok, why = gpu_budget_allows(page, ep, now)
                if not ok:
                    notify("budget", f"بودجهٔ GPU اجازهٔ ساخت نسخهٔ نهایی {_label(ep)} را نمی‌دهد", body=why, level="warn", link=_link(ep), page=page, episode=ep,
                           key=f"gpu-budget:{ep.pk}:{wk}")
                    return acts
                if not scheduling.window_open(cfg.render_windows, now, cfg.utc_offset_minutes):
                    nxt = scheduling.next_window_open(cfg.render_windows, now, cfg.utc_offset_minutes)
                    notify("schedule", f"ساخت نسخهٔ نهایی {_label(ep)} تا بازهٔ رندر منتظر می‌ماند", body=f"بازهٔ بعدی: {nxt.isoformat()}", level="info", link=_link(ep),
                           page=page, episode=ep, key=f"window:{ep.pk}:{nxt.strftime('%Y%m%d%H')}")
                    return acts
                from . import pipeline

                pipeline.start(ep, "final", actor="system")
                acts.append({"episode": ep.pk, "action": "final_started"})
            else:
                notify("decision", f"پیش‌نمایشِ {_label(ep)} آماده است", body="برای ساخت نسخهٔ نهایی (زمان GPU) تأیید کنید.", level="info", link=_link(ep), page=page, episode=ep,
                       key=f"preview:{ep.pk}", once=True)

    elif st == states.APPROVED and level == "automatic":
        acts += plan_publication(page, ep, now)
    return acts


# ------------------------------------------------------------------ publishing schedule

def plan_publication(page, ep: Episode, now: datetime) -> list[dict]:
    """An approved episode gets the page's next free publication slot (Publication + state `scheduled`)."""
    if Publication.objects.filter(episode=ep, status__in=("scheduled", "published")).exists():
        return []
    prof = page.profile("publishing")
    cfg = config(page)
    taken = list(Publication.objects.filter(episode__series__page=page, status="scheduled", scheduled_at__isnull=False).values_list("scheduled_at", flat=True))
    after = max([now] + taken) if taken else now
    slot = scheduling.publication_slots(prof["per_week"], prof["days"], prof["time"], after, 1, cfg.utc_offset_minutes)[0]
    pub = Publication.objects.filter(episode=ep).exclude(status="published").first() or Publication.objects.create(
        episode=ep, target=page.targets.first(), caption=ep.title, hashtags=prof["hashtags"])
    pub.scheduled_at, pub.status = slot, "scheduled"
    pub.save(update_fields=["scheduled_at", "status", "updated_at"])
    services.transition(ep, states.SCHEDULED, actor="system", reason="automatic: publication slot")
    notify("schedule", f"{_label(ep)} برای انتشار زمان‌بندی شد", body=slot.isoformat(), level="info", link=_link(ep), page=page, episode=ep, key=f"slot:{ep.pk}:{slot:%Y%m%d%H%M}")
    return [{"episode": ep.pk, "action": "scheduled", "at": slot.isoformat()}]


def process_due_publications(now: datetime) -> list[dict]:
    """Scheduled publications whose time has come: post through the official API ONLY with explicit enablement, else prepare the manual package
    and remind the owner. Nothing here ever posts by default."""
    out = []
    for pub in Publication.objects.filter(status="scheduled", scheduled_at__lte=now).select_related("episode__series__page", "target"):
        ep, page = pub.episode, pub.episode.series.page
        ok, why = adapters.can_auto_publish(page, pub.target)
        if ok:
            try:
                res = adapters.InstagramGraph().publish(pub)
            except Exception as e:  # noqa: BLE001 - the owner is told; nothing is retried blindly
                Publication.objects.filter(pk=pub.pk).update(status="failed")
                notify("publish", f"انتشار {_label(ep)} ناموفق بود", body=str(e)[:300], level="error", link=_link(ep), page=page, episode=ep, key=f"pubfail:{pub.pk}", once=True)
                out.append({"publication": pub.pk, "action": "failed"})
                continue
            Publication.objects.filter(pk=pub.pk).update(status="published", external_url=str(res.get("external_id") or ""))
            services.transition(ep, states.PUBLISHED, actor="system", reason="published through the official API (explicitly enabled)")
            notify("publish", f"{_label(ep)} منتشر شد", level="ok", link=_link(ep), page=page, episode=ep, key=f"pub:{pub.pk}", once=True)
            out.append({"publication": pub.pk, "action": "published"})
        else:
            try:
                adapters.ManualExport().publish(pub)
            except Exception as e:  # noqa: BLE001
                log.warning("export for %s failed: %s", pub.pk, e)
            Publication.objects.filter(pk=pub.pk).update(status="exported")
            notify("publish", f"زمان انتشار {_label(ep)} رسید", body="بستهٔ انتشار آماده است؛ آن را دستی بارگذاری کنید. (انتشار خودکار فعال نیست)", level="info",
                   link=f"/pages/{page.pk}/publishing", page=page, episode=ep, key=f"due:{pub.pk}", once=True)
            out.append({"publication": pub.pk, "action": "reminder", "auto_publish": why})
    return out


# ------------------------------------------------------------------ the tick

def tick(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    done: list[dict] = []
    for page in ContentPage.objects.filter(status="active"):
        level = page.automation_level
        if level == "manual":
            continue
        for ep in Episode.objects.filter(series__page=page).select_related("series__page").order_by("series_id", "number"):
            try:
                done += step_episode(page, ep, level, now)
            except Exception as e:  # noqa: BLE001 - one bad episode must not stop the others
                log.exception("automation failed for episode %s", ep.pk)
                notify("automation", f"خطا در خودکارسازی {_label(ep)}", body=str(e)[:300], level="error", link=_link(ep), page=page, episode=ep, key=f"autoerr:{ep.pk}:{type(e).__name__}")
    done += process_due_publications(now)
    return done


def check_worker_health() -> None:
    """Tell the owner when a paired worker PC went offline while it still had work."""
    from datetime import timedelta as td

    from instai.jobs.models import RemoteTask, WorkerNode

    for w in WorkerNode.objects.filter(enabled=True):
        if w.last_seen and dj_tz.now() - w.last_seen > td(minutes=3) and RemoteTask.objects.filter(target_worker=w, status__in=("queued", "running")).exists():
            notify("worker", f"رایانهٔ کارگر «{w.name}» پاسخ نمی‌دهد", level="warn", link="/lab/workers", key=f"worker-off:{w.pk}")
