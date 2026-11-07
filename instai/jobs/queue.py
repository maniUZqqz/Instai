"""Durable DB-backed job queue (no Redis/Celery): atomic claim, lease + heartbeat, retries with backoff, timeouts, cancellation,
progress, logs, idempotency keys and time accounting. SQLite has no row locks, so claiming is a compare-and-set UPDATE.

Waiting is not failing (0.6.0). A job that needs a computer or service that is not there right now (the second PC is off, Ollama is
not running, the graphics card is used by another program) goes BACK to the queue with a plain reason (`defer`), costs no attempt,
has no time limit (unless the owner sets one) and starts by itself when the thing is back. A job fails only for a real error (after
its retries) or when the owner cancels it. A worker that dies mid-job is not the job's fault either: `reap_expired` re-queues it
without using an attempt (up to MAX_LOST_FREE times, so a job that kills the worker every time cannot loop forever).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import IntegrityError
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

from instai.core.dbretry import retry_on_lock

from . import schedule
from .models import Job, JobLog

log = logging.getLogger("instai.jobs")
BACKOFF_BASE = 20  # seconds; retry n waits BACKOFF_BASE * 2**(n-1), capped
BACKOFF_MAX = 900

# ProviderError codes that mean "the computer or service is not there (yet)" and NOT "the work is wrong": the job waits.
WAIT_CODES = frozenset({"worker_offline", "worker_lost", "ollama_down", "comfy_down", "gpu_busy"})
MAX_LOST_FREE = 5              # worker-process deaths that do not cost an attempt, per job
WAIT_DELAY_FIRST = 15          # seconds before a waiting job looks again; grows to WAIT_DELAY_MAX
WAIT_DELAY_MAX = 60
WAIT_TEXT_FA = {
    "worker_offline": "رایانهٔ دوم (B) خاموش یا بدون ارتباط است؛ کار می‌ماند و همین که روشن شد خودش انجام می‌شود.",
    "worker_lost": "ارتباط با رایانهٔ دوم (B) وسط کار قطع شد؛ کار به صف برگشت (تلاشی از آن کم نشد) و با برگشتن رایانه ادامه می‌یابد.",
    "ollama_down": "Ollama روشن نیست؛ کار منتظر می‌ماند. Ollama را روشن کنید تا خودش ادامه دهد.",
    "comfy_down": "ComfyUI روشن نیست و InstAI نتوانست روشنش کند؛ کار منتظر می‌ماند. ComfyUI را روشن کنید یا پوشهٔ آن را در صفحهٔ «مدل‌ها» بدهید.",
    "gpu_busy": "برنامهٔ دیگری از حافظهٔ کارت گرافیک استفاده می‌کند؛ کار منتظر آزاد شدن آن می‌ماند.",
}
WAIT_TEXT_EN = {
    "worker_offline": "The second PC (B) is off or unreachable; the job waits and runs by itself when it is back.",
    "worker_lost": "The connection to the second PC (B) broke mid-job; the job went back to the queue (no attempt used) and continues when it is back.",
    "ollama_down": "Ollama is not running; the job waits. Start Ollama and it continues by itself.",
    "comfy_down": "ComfyUI is not running and InstAI could not start it; the job waits.",
    "gpu_busy": "Another program is using the graphics card; the job waits for it to be released.",
}


@retry_on_lock
def log_job(job: Job | int, message: str, level: str = "info", dedupe: bool = False) -> None:
    """One line in the job's log. `dedupe` skips it when it is one of the job's last six lines (a job that waits and looks again every
    15 seconds must not write the same two lines a thousand times)."""
    jid = job.pk if isinstance(job, Job) else job
    message = str(message)[:4000]
    if dedupe and message in list(JobLog.objects.filter(job_id=jid).order_by("-id").values_list("message", flat=True)[:6]):
        return
    JobLog.objects.create(job_id=jid, level=level, message=message)


@retry_on_lock
def _create(fields: dict) -> Job:
    return Job.objects.create(**fields)


def enqueue(kind: str, payload: dict | None = None, *, resource: str | None = None, title: str = "", page=None, episode=None,
            idempotency_key: str | None = None, priority: int = 0, max_attempts: int = 3, timeout_sec: int | None = None,
            run_after=None, parent: Job | None = None, estimated_sec: float | None = None, window: str = "") -> Job:
    """Create a job. With an idempotency key, an existing job with that key is returned instead of a duplicate:
    queued/running/succeeded ones as they are; failed/cancelled ones are re-queued from scratch. `window` ("02:00-07:00", local time)
    makes the job startable only inside that window."""
    from .registry import HANDLERS, default_resource, default_timeout, load_handlers

    if kind not in HANDLERS:
        load_handlers()      # the server process never ran a job: without this a GPU/net job would be filed as "cpu" until some request imported the handlers
    if idempotency_key:
        existing = Job.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.status in (Job.FAILED, Job.CANCELLED):
                return requeue(existing, reset_attempts=True)
            return existing
    now = timezone.now()
    fields = dict(kind=kind, payload=payload or {}, resource=resource or default_resource(kind, payload or {}), title=title or kind,
                  page_id=getattr(page, "pk", page), episode_id=getattr(episode, "pk", episode), idempotency_key=idempotency_key,
                  priority=priority, max_attempts=max_attempts, timeout_sec=timeout_sec or default_timeout(kind), parent=parent,
                  estimated_sec=estimated_sec, window=schedule.norm_window(window), ready_at=run_after or now)
    try:
        job = _create(fields)
    except IntegrityError:  # two requests with the same key raced
        return Job.objects.get(idempotency_key=idempotency_key)
    if run_after:
        Job.objects.filter(pk=job.pk).update(run_after=run_after)   # run_after is auto_now_add: a value given at creation is overwritten
        job.run_after = run_after
    log_job(job, "queued")
    return job


@retry_on_lock
def claim(worker: str, resources: tuple[str, ...], lease_sec: int = 90) -> Job | None:
    """Atomically take the best queued job (highest priority, oldest first) whose time has come (and whose window is open)."""
    now = timezone.now()
    cands = list(Job.objects.filter(status=Job.QUEUED, resource__in=resources, run_after__lte=now)
                 .order_by("-priority", "id").values_list("pk", "window")[:10])
    for pk, window in cands:
        if window and not schedule.in_window(window, now):
            # the night window is closed: do not look at it again until it opens
            Job.objects.filter(pk=pk, status=Job.QUEUED).update(run_after=schedule.next_window_start(window, now), wait_code="window",
                                                                 waiting_reason="منتظر بازهٔ شبانهٔ " + window)
            continue
        n = Job.objects.filter(pk=pk, status=Job.QUEUED, cancel_requested=False).update(
            status=Job.RUNNING, lease_owner=worker, lease_expires=now + timedelta(seconds=lease_sec), heartbeat_at=now,
            started_at=now, attempts=F("attempts") + 1, waiting_reason="", finished_at=None, error="", error_code="", live={},
            first_started_at=Coalesce(F("first_started_at"), Value(now)))
        if n == 1:
            return Job.objects.get(pk=pk)
    # jobs cancelled while queued
    Job.objects.filter(status=Job.QUEUED, cancel_requested=True).update(status=Job.CANCELLED, finished_at=now)
    return None


def models_attempts_plus_one():
    return F("attempts") + 1


@retry_on_lock
def heartbeat(job: Job, worker: str, lease_sec: int = 90) -> bool:
    """Extend the lease. Returns False when the job no longer belongs to this worker."""
    now = timezone.now()
    n = Job.objects.filter(pk=job.pk, status=Job.RUNNING, lease_owner=worker).update(heartbeat_at=now,
                                                                                    lease_expires=now + timedelta(seconds=lease_sec))
    return n == 1


@retry_on_lock
def set_progress(job: Job, fraction: float, text: str = "") -> None:
    Job.objects.filter(pk=job.pk).update(progress=max(0.0, min(1.0, fraction)), progress_text=text[:300])


@retry_on_lock
def set_waiting(job: Job, reason: str) -> None:
    Job.objects.filter(pk=job.pk).update(waiting_reason=reason[:200])


@retry_on_lock
def set_live(job: Job, live: dict) -> None:
    """What the job is doing right now (phase, model, device, tokens, step ...), read by jobs/describe.py for the queue screen."""
    Job.objects.filter(pk=job.pk).update(live=live)


def is_cancel_requested(job_id: int) -> bool:
    return Job.objects.filter(pk=job_id, cancel_requested=True).exists()


@retry_on_lock
def complete(job: Job, result: dict | None, gpu_seconds: float = 0.0) -> None:
    now = timezone.now()
    dur = (now - job.started_at).total_seconds() if job.started_at else None
    Job.objects.filter(pk=job.pk).update(status=Job.SUCCEEDED, result=result or {}, progress=1.0, finished_at=now, duration_sec=dur,
                                         gpu_seconds=gpu_seconds, lease_owner="", lease_expires=None, waiting_reason="", wait_code="",
                                         waiting_since=None)
    log_job(job, f"succeeded in {dur:.1f}s" if dur is not None else "succeeded")


@retry_on_lock
def fail(job: Job, error: str, *, retryable: bool = True, code: str = "job_failed") -> str:
    """Retry with exponential backoff while attempts remain, otherwise fail for good. Returns the new status."""
    job.refresh_from_db()
    now = timezone.now()
    if retryable and job.attempts < job.max_attempts and not job.cancel_requested:
        delay = min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (job.attempts - 1))
        Job.objects.filter(pk=job.pk).update(status=Job.QUEUED, error=error[:2000], error_code=code, lease_owner="", lease_expires=None,
                                             run_after=now + timedelta(seconds=delay), waiting_reason="", progress_text="retry scheduled",
                                             wait_code="", waiting_since=None)
        log_job(job, f"failed (attempt {job.attempts}/{job.max_attempts}); retry in {delay}s: {error[:300]}", "warning")
        return Job.QUEUED
    dur = (now - job.started_at).total_seconds() if job.started_at else None
    Job.objects.filter(pk=job.pk).update(status=Job.FAILED, error=error[:2000], error_code=code, finished_at=now, duration_sec=dur,
                                         lease_owner="", lease_expires=None, waiting_reason="", wait_code="", waiting_since=None)
    log_job(job, f"failed: {error[:500]}", "error")
    return Job.FAILED


@retry_on_lock
def mark_cancelled(job: Job) -> None:
    now = timezone.now()
    Job.objects.filter(pk=job.pk).update(status=Job.CANCELLED, finished_at=now, lease_owner="", lease_expires=None, waiting_reason="",
                                         wait_code="", waiting_since=None,
                                         duration_sec=(now - job.started_at).total_seconds() if job.started_at else None)
    log_job(job, "cancelled", "warning")


@retry_on_lock
def request_cancel(job: Job) -> Job:
    """Queued jobs (also the ones waiting for a computer) are cancelled at once; running jobs stop at their next checkpoint."""
    job.refresh_from_db()
    if job.status == Job.QUEUED:
        n = Job.objects.filter(pk=job.pk, status=Job.QUEUED).update(status=Job.CANCELLED, cancel_requested=True, finished_at=timezone.now(),
                                                                   waiting_reason="", wait_code="", waiting_since=None)
        if n:
            log_job(job, "cancelled while waiting", "warning")
    elif job.status == Job.RUNNING:
        Job.objects.filter(pk=job.pk).update(cancel_requested=True)
    job.refresh_from_db()
    return job


@retry_on_lock
def requeue(job: Job, *, reset_attempts: bool = False) -> Job:
    now = timezone.now()
    Job.objects.filter(pk=job.pk).update(status=Job.QUEUED, cancel_requested=False, error="", error_code="", finished_at=None,
                                         run_after=now, ready_at=now, progress=0.0, progress_text="", lease_owner="", lease_expires=None, live={},
                                         wait_code="", waiting_since=None, waiting_reason="", lost_count=0,
                                         **({"attempts": 0} if reset_attempts else {}))
    log_job(job, "re-queued")
    return Job.objects.get(pk=job.pk)


# ------------------------------------------------------------------ waiting (not failing)

def wait_code_of(err: BaseException) -> str:
    """The waiting code of a provider error ("" = a real error): an explicit `wait`, else its own code when that is a waiting one."""
    w = getattr(err, "wait", "") or ""
    if w:
        return w
    c = getattr(err, "code", "")
    return c if c in WAIT_CODES else ""


def wait_reason_text(code: str, detail: str = "") -> str:
    """The plain Persian line the queue shows for a waiting job (the provider's own Persian line, else the code's standard text)."""
    first = (detail or "").strip().splitlines()[0] if (detail or "").strip() else ""
    return (first or WAIT_TEXT_FA.get(code, "منتظر آماده شدن منبع مورد نیاز."))[:200]


@retry_on_lock
def defer(job: Job, reason: str, code: str, *, delay: float | None = None, run_after=None, since=None, count: bool = True) -> str:
    """Put a RUNNING job back in the queue to wait for a computer / service / the clock. It is NOT a failed attempt: the attempt the claim
    took is given back. Returns the new status (QUEUED, or CANCELLED when the owner cancelled meanwhile, or FAILED when the optional
    maximum wait the owner set is over). `count=False` is for planned pauses (the night window closed): not counted as a "wait", but
    still no attempt is used."""
    row = Job.objects.filter(pk=job.pk).values("cancel_requested", "waiting_since", "wait_code", "deferrals").first()
    if row is None:
        return Job.FAILED
    if row["cancel_requested"]:
        mark_cancelled(job)
        return Job.CANCELLED
    now = timezone.now()
    since = since or (row["waiting_since"] if row["wait_code"] == code and row["waiting_since"] else now)
    max_wait = schedule.config()["max_wait_hours"] if code in WAIT_CODES else 0
    if max_wait and (now - since).total_seconds() > max_wait * 3600:
        return fail(job, f"{reason}\nمدت انتظار از سقفی که تعیین کرده‌اید ({max_wait:g} ساعت) بیشتر شد.", retryable=False, code="wait_limit")
    if delay is None:
        delay = min(WAIT_DELAY_MAX, WAIT_DELAY_FIRST + 5 * row["deferrals"])
    when = run_after or (now + timedelta(seconds=delay))
    changed = Job.objects.filter(pk=job.pk, status=Job.RUNNING).update(
        status=Job.QUEUED, lease_owner="", lease_expires=None, run_after=when, waiting_reason=reason[:200], wait_code=code, waiting_since=since,
        progress_text="waiting", error="", error_code="", deferrals=F("deferrals") + (1 if count else 0),
        attempts=Greatest(F("attempts") - 1, 0))             # the attempt the claim took is given back, for a planned pause too
    if changed:
        log_job(job, f"waiting ({code}): {reason[:300]}", "warning", dedupe=True)
    return Job.QUEUED


@retry_on_lock
def wake_waiting(codes=("worker_offline", "worker_lost")) -> int:
    """A computer just came back: the jobs waiting for it look again now instead of after their pause."""
    now = timezone.now()
    return Job.objects.filter(status=Job.QUEUED, wait_code__in=codes, run_after__gt=now).update(run_after=now)


def reap_expired() -> int:
    """Jobs whose worker process vanished (lease expired): back to the queue WITHOUT using an attempt, up to MAX_LOST_FREE times;
    after that the death counts as a failed attempt (a job that crashes the worker every time must not loop forever)."""
    now = timezone.now()
    n = 0
    for job in Job.objects.filter(status=Job.RUNNING, lease_expires__lt=now):
        if job.lost_count >= MAX_LOST_FREE:
            log_job(job, f"lease expired (worker stopped?) for the {job.lost_count + 1}th time", "warning")
            fail(job, "worker stopped before the job finished (it did so repeatedly)", retryable=True, code="lease_expired")
            n += 1
            continue
        got = Job.objects.filter(pk=job.pk, status=Job.RUNNING, lease_expires__lt=now).update(
            status=Job.QUEUED, lease_owner="", lease_expires=None, run_after=now, lost_count=F("lost_count") + 1, wait_code="worker_lost",
            error_code="lease_expired",
            waiting_reason="کارگر (برنامهٔ اجراکننده) وسط کار بسته شد؛ کار به صف برگشت و دوباره انجام می‌شود.", progress_text="re-queued",
            attempts=Greatest(F("attempts") - 1, 0))
        if got:
            log_job(job, "lease expired (worker stopped?); re-queued without using an attempt", "warning")
            n += 1
    return n


def active_jobs(limit: int = 50):
    return Job.objects.filter(Q(status=Job.QUEUED) | Q(status=Job.RUNNING)).order_by("-status", "-priority", "id")[:limit]
