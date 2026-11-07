"""The queue page and the header counter: for every job a plain state (running, waiting for a computer, waiting for its turn, scheduled
download, night window ...), in Persian and English, with its place in the line. Pure functions of the job row and the clock."""
from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from instai.jobs import schedule
from instai.jobs.models import Job, WorkerNode

from . import report

WAIT_CODES_NODE = ("worker_offline", "worker_lost")
WAIT_CODES_SERVICE = ("ollama_down", "comfy_down")

from instai.jobs.queue import WAIT_TEXT_EN as STATE_EN  # noqa: E402


def _ago_fa(since: datetime | None, now: datetime) -> str:
    if not since:
        return ""
    s = max(0, int((now - since).total_seconds()))
    if s < 90:
        return "از چند ثانیه پیش"
    if s < 3600:
        return f"از {schedule.fa_num(s // 60)} دقیقه پیش"
    if s < 86400:
        return f"از {schedule.fa_num(s // 3600)} ساعت پیش"
    return f"از {schedule.fa_num(s // 86400)} روز پیش"


def _ago_en(since: datetime | None, now: datetime) -> str:
    if not since:
        return ""
    s = max(0, int((now - since).total_seconds()))
    if s < 90:
        return "since a few seconds ago"
    if s < 3600:
        return f"for {s // 60} min"
    if s < 86400:
        return f"for {s // 3600} h"
    return f"for {s // 86400} days"


def job_state(job: Job, now: datetime | None = None, position: int | None = None) -> dict:
    """{"state", "fa", "en"}. States: running, waiting_node, waiting_service, waiting_gpu, window, scheduled, retry, waiting_turn,
    succeeded, failed, cancelled."""
    now = now or timezone.now()
    st = job.status
    if st == Job.SUCCEEDED:
        return {"state": "succeeded", "fa": "انجام شد", "en": "Done"}
    if st == Job.FAILED:
        return {"state": "failed", "fa": "ناموفق (خطای واقعی)", "en": "Failed (a real error)"}
    if st == Job.CANCELLED:
        return {"state": "cancelled", "fa": "لغو شد", "en": "Cancelled"}
    node = report._node_of(job)
    where_fa = "روی کامپیوتر اصلی (A)" if node == report.LOCAL else f"روی کامپیوتر {node}"
    where_en = "on the main PC (A)" if node == report.LOCAL else f"on computer {node}"
    if st == Job.RUNNING:
        if job.cancel_requested:
            return {"state": "running", "fa": "در حال توقف (لغو شد)…", "en": "Stopping (cancelled)…"}
        pct = f" — {schedule.fa_num(int(round(job.progress * 100)))}٪" if job.progress > 0 else ""
        pct_en = f" — {int(round(job.progress * 100))}%" if job.progress > 0 else ""
        if job.waiting_reason:
            return {"state": "waiting_gpu", "fa": f"در حال اجرا، ولی منتظر: {job.waiting_reason}", "en": f"Running, but waiting: {job.waiting_reason}"}
        return {"state": "running", "fa": f"در حال اجرا {where_fa}{pct}", "en": f"Running {where_en}{pct_en}"}
    # queued
    code = job.wait_code
    if code in WAIT_CODES_NODE:
        who = _waiting_names(job)
        return {"state": "waiting_node", "fa": f"منتظر روشن شدن {who} — {_ago_fa(job.waiting_since, now)}",
                "en": f"Waiting for {who} to come online — {_ago_en(job.waiting_since, now)}"}
    if code in WAIT_CODES_SERVICE:
        name = "Ollama" if code == "ollama_down" else "ComfyUI"
        return {"state": "waiting_service", "fa": f"منتظر روشن شدن {name} — {_ago_fa(job.waiting_since, now)}", "en": f"Waiting for {name} to start — {_ago_en(job.waiting_since, now)}"}
    if code == "gpu_busy":
        return {"state": "waiting_gpu", "fa": f"منتظر آزاد شدن کارت گرافیک — {_ago_fa(job.waiting_since, now)}", "en": f"Waiting for the graphics card — {_ago_en(job.waiting_since, now)}"}
    if job.window and (code == "window" or not schedule.in_window(job.window, now)):
        opens = schedule.next_window_start(job.window, now)
        return {"state": "window", "fa": f"منتظر بازهٔ شبانه {schedule.fa_num(job.window)} — شروع {schedule.clock_text(opens, now)}",
                "en": f"Waiting for the night window {job.window} — starts {schedule.clock_text_en(opens, now)}"}
    if job.run_after and job.run_after > now and job.attempts and job.error:
        secs = int((job.run_after - now).total_seconds())
        return {"state": "retry", "fa": f"تلاش {schedule.fa_num(job.attempts)} از {schedule.fa_num(job.max_attempts)} ناموفق بود؛ {schedule.fa_num(max(1, secs))} ثانیهٔ دیگر دوباره",
                "en": f"Try {job.attempts} of {job.max_attempts} failed; again in {max(1, secs)} s"}
    if job.run_after and job.run_after > now and (job.ready_at is None or job.ready_at > now):
        return {"state": "scheduled", "fa": f"زمان‌بندی‌شده — شروع {schedule.clock_text(job.run_after, now)}", "en": f"Scheduled — starts {schedule.clock_text_en(job.run_after, now)}"}
    pos_fa = f"نفر {schedule.fa_num(position)}ام در صف" if position else "در صف؛ منتظر نوبت"
    pos_en = f"Number {position} in line" if position else "Queued; waiting for its turn"
    return {"state": "waiting_turn", "fa": pos_fa, "en": pos_en}


def _waiting_names(job: Job) -> str:
    """"رایانهٔ B" (or the names of the paired computers when there are several): what the waiting job is waiting for."""
    names = list(WorkerNode.objects.filter(enabled=True).values_list("name", flat=True)[:3])
    return ("رایانهٔ " + "، ".join(names)) if names else "رایانهٔ دوم"


def wait_text_en(job: Job) -> str:
    return STATE_EN.get(job.wait_code, "")


def job_row(job: Job, now: datetime, position: int | None, activity: dict | None = None) -> dict:
    s = job_state(job, now, position)
    ex = report.job_error(job)
    fa, en = report.kind_titles(job.kind)
    if job.kind.startswith("downloads."):
        from .downloads import titles

        fa, en = titles(job)
        activity = {**(activity or {}), "title_fa": fa, "title_en": en}
    return {
        "id": job.pk, "kind": job.kind, "title_fa": (activity or {}).get("title_fa") or fa, "title_en": (activity or {}).get("title_en") or en,
        "for_fa": (activity or {}).get("for_fa", ""), "for_en": (activity or {}).get("for_en", ""),
        "status": job.status, "state": s["state"], "state_fa": s["fa"], "state_en": s["en"], "waiting_reason": job.waiting_reason, "wait_code": job.wait_code,
        "waiting_since": job.waiting_since.isoformat() if job.waiting_since else None, "position": position, "node": report._node_of(job),
        "attempts": job.attempts, "max_attempts": job.max_attempts, "deferrals": job.deferrals, "progress": job.progress, "resource": job.resource,
        "created_at": job.created_at.isoformat(), "run_after": job.run_after.isoformat() if job.run_after else None, "window": job.window,
        "started_at": job.started_at.isoformat() if job.started_at else None, "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "duration_sec": job.duration_sec, "queue_wait_sec": report.queue_wait(job), "error": (job.error or "")[:400], "explain": ex,
        "can_cancel": job.status in (Job.QUEUED, Job.RUNNING) and not job.cancel_requested, "can_retry": job.status in (Job.FAILED, Job.CANCELLED),
        "can_run_now": job.status == Job.QUEUED and (bool(job.window) or (job.run_after and job.run_after > now and not job.wait_code)) and job.kind.startswith("downloads."),
        "is_download": job.kind.startswith("downloads."),
    }


def positions(queued: list[Job], now: datetime) -> dict[int, int]:
    """Place in line of every queued job that is ready and not waiting for a thing: GPU jobs one line, CPU/net jobs another."""
    out: dict[int, int] = {}
    count = {"gpu": 0, "other": 0}
    for j in sorted(queued, key=lambda j: (-j.priority, j.pk)):
        if j.wait_code or (j.run_after and j.run_after > now) or (j.window and not schedule.in_window(j.window, now)):
            continue
        lane = "gpu" if j.resource == "gpu" else "other"
        count[lane] += 1
        out[j.pk] = count[lane]
    return out


def summary(now: datetime | None = None) -> dict:
    """The numbers of the header counter and the top of the queue page."""
    now = now or timezone.now()
    queued = list(Job.objects.filter(status=Job.QUEUED))
    running = Job.objects.filter(status=Job.RUNNING).count()
    waiting_node = sum(1 for j in queued if j.wait_code in WAIT_CODES_NODE)
    waiting_service = sum(1 for j in queued if j.wait_code in WAIT_CODES_SERVICE or j.wait_code == "gpu_busy")
    scheduled = sum(1 for j in queued if (j.window and not schedule.in_window(j.window, now)) or (not j.wait_code and j.run_after and j.run_after > now and not (j.attempts and j.error)))
    waiting_turn = len(queued) - waiting_node - waiting_service - scheduled
    return {"running": running, "queued": len(queued), "waiting_node": waiting_node, "waiting_service": waiting_service, "scheduled": scheduled,
            "waiting_turn": max(0, waiting_turn), "waiting": waiting_node + waiting_service,
            "offline_nodes": [n["key"] for n in node_status(now) if n["kind"] == "worker" and n["enabled"] and not n["online"]]}


def node_status(now: datetime | None = None) -> list[dict]:
    """Online / offline of this PC and every paired worker, from the same rule as the report."""
    from django.db.models import Max

    now = now or timezone.now()
    last = dict(report.NodeSession.objects.values_list("node").annotate(m=Max("last_seen")))
    out = []
    for n in report.node_catalog():
        seen = last.get(n["key"])
        online = bool(seen and (now - seen).total_seconds() <= report.grace(n["key"]))
        out.append({**n, "online": online, "last_seen": seen.isoformat() if seen else None})
    return out
