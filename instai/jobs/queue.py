"""Durable DB-backed job queue (no Redis/Celery): atomic claim, lease + heartbeat, retries with backoff, timeouts, cancellation,
progress, logs, idempotency keys and time accounting. SQLite has no row locks, so claiming is a compare-and-set UPDATE."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from .models import Job, JobLog

log = logging.getLogger("instai.jobs")
BACKOFF_BASE = 20  # seconds; retry n waits BACKOFF_BASE * 2**(n-1), capped
BACKOFF_MAX = 900


def log_job(job: Job | int, message: str, level: str = "info") -> None:
    jid = job.pk if isinstance(job, Job) else job
    JobLog.objects.create(job_id=jid, level=level, message=str(message)[:4000])


def enqueue(kind: str, payload: dict | None = None, *, resource: str | None = None, title: str = "", page=None, episode=None,
            idempotency_key: str | None = None, priority: int = 0, max_attempts: int = 3, timeout_sec: int | None = None,
            run_after=None, parent: Job | None = None, estimated_sec: float | None = None) -> Job:
    """Create a job. With an idempotency key, an existing job with that key is returned instead of a duplicate:
    queued/running/succeeded ones as they are; failed/cancelled ones are re-queued from scratch."""
    from .registry import default_resource, default_timeout

    if idempotency_key:
        existing = Job.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.status in (Job.FAILED, Job.CANCELLED):
                return requeue(existing, reset_attempts=True)
            return existing
    fields = dict(kind=kind, payload=payload or {}, resource=resource or default_resource(kind, payload or {}), title=title or kind,
                  page_id=getattr(page, "pk", page), episode_id=getattr(episode, "pk", episode), idempotency_key=idempotency_key,
                  priority=priority, max_attempts=max_attempts, timeout_sec=timeout_sec or default_timeout(kind), parent=parent,
                  estimated_sec=estimated_sec)
    if run_after:
        fields["run_after"] = run_after
    try:
        job = Job.objects.create(**fields)
    except IntegrityError:  # two requests with the same key raced
        return Job.objects.get(idempotency_key=idempotency_key)
    if run_after:
        Job.objects.filter(pk=job.pk).update(run_after=run_after)
    log_job(job, "queued")
    return job


def claim(worker: str, resources: tuple[str, ...], lease_sec: int = 90) -> Job | None:
    """Atomically take the best queued job (highest priority, oldest first) whose time has come."""
    now = timezone.now()
    cands = (Job.objects.filter(status=Job.QUEUED, resource__in=resources, run_after__lte=now)
             .order_by("-priority", "id").values_list("pk", flat=True)[:10])
    for pk in cands:
        n = Job.objects.filter(pk=pk, status=Job.QUEUED, cancel_requested=False).update(
            status=Job.RUNNING, lease_owner=worker, lease_expires=now + timedelta(seconds=lease_sec), heartbeat_at=now,
            started_at=now, attempts=models_attempts_plus_one(), waiting_reason="", finished_at=None, error="", error_code="")
        if n == 1:
            return Job.objects.get(pk=pk)
    # jobs cancelled while queued
    Job.objects.filter(status=Job.QUEUED, cancel_requested=True).update(status=Job.CANCELLED, finished_at=now)
    return None


def models_attempts_plus_one():
    from django.db.models import F

    return F("attempts") + 1


def heartbeat(job: Job, worker: str, lease_sec: int = 90) -> bool:
    """Extend the lease. Returns False when the job no longer belongs to this worker."""
    now = timezone.now()
    n = Job.objects.filter(pk=job.pk, status=Job.RUNNING, lease_owner=worker).update(heartbeat_at=now,
                                                                                    lease_expires=now + timedelta(seconds=lease_sec))
    return n == 1


def set_progress(job: Job, fraction: float, text: str = "") -> None:
    Job.objects.filter(pk=job.pk).update(progress=max(0.0, min(1.0, fraction)), progress_text=text[:300])


def set_waiting(job: Job, reason: str) -> None:
    Job.objects.filter(pk=job.pk).update(waiting_reason=reason[:200])


def is_cancel_requested(job_id: int) -> bool:
    return Job.objects.filter(pk=job_id, cancel_requested=True).exists()


def complete(job: Job, result: dict | None, gpu_seconds: float = 0.0) -> None:
    now = timezone.now()
    dur = (now - job.started_at).total_seconds() if job.started_at else None
    Job.objects.filter(pk=job.pk).update(status=Job.SUCCEEDED, result=result or {}, progress=1.0, finished_at=now, duration_sec=dur,
                                         gpu_seconds=gpu_seconds, lease_owner="", lease_expires=None, waiting_reason="")
    log_job(job, f"succeeded in {dur:.1f}s" if dur is not None else "succeeded")


def fail(job: Job, error: str, *, retryable: bool = True, code: str = "job_failed") -> str:
    """Retry with exponential backoff while attempts remain, otherwise fail for good. Returns the new status."""
    job.refresh_from_db()
    now = timezone.now()
    if retryable and job.attempts < job.max_attempts and not job.cancel_requested:
        delay = min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (job.attempts - 1))
        Job.objects.filter(pk=job.pk).update(status=Job.QUEUED, error=error[:2000], error_code=code, lease_owner="", lease_expires=None,
                                             run_after=now + timedelta(seconds=delay), waiting_reason="", progress_text="retry scheduled")
        log_job(job, f"failed (attempt {job.attempts}/{job.max_attempts}); retry in {delay}s: {error[:300]}", "warning")
        return Job.QUEUED
    dur = (now - job.started_at).total_seconds() if job.started_at else None
    Job.objects.filter(pk=job.pk).update(status=Job.FAILED, error=error[:2000], error_code=code, finished_at=now, duration_sec=dur,
                                         lease_owner="", lease_expires=None, waiting_reason="")
    log_job(job, f"failed: {error[:500]}", "error")
    return Job.FAILED


def mark_cancelled(job: Job) -> None:
    now = timezone.now()
    Job.objects.filter(pk=job.pk).update(status=Job.CANCELLED, finished_at=now, lease_owner="", lease_expires=None, waiting_reason="",
                                         duration_sec=(now - job.started_at).total_seconds() if job.started_at else None)
    log_job(job, "cancelled", "warning")


def request_cancel(job: Job) -> Job:
    """Queued jobs are cancelled at once; running jobs stop at their next checkpoint (cooperative)."""
    job.refresh_from_db()
    if job.status == Job.QUEUED:
        Job.objects.filter(pk=job.pk, status=Job.QUEUED).update(status=Job.CANCELLED, cancel_requested=True, finished_at=timezone.now())
    elif job.status == Job.RUNNING:
        Job.objects.filter(pk=job.pk).update(cancel_requested=True)
    job.refresh_from_db()
    return job


def requeue(job: Job, *, reset_attempts: bool = False) -> Job:
    Job.objects.filter(pk=job.pk).update(status=Job.QUEUED, cancel_requested=False, error="", error_code="", finished_at=None,
                                         run_after=timezone.now(), progress=0.0, progress_text="", lease_owner="", lease_expires=None,
                                         **({"attempts": 0} if reset_attempts else {}))
    log_job(job, "re-queued")
    return Job.objects.get(pk=job.pk)


def reap_expired() -> int:
    """Jobs whose worker vanished (lease expired): re-queue them (or fail them when out of attempts)."""
    now = timezone.now()
    n = 0
    for job in Job.objects.filter(status=Job.RUNNING, lease_expires__lt=now):
        log_job(job, "lease expired (worker stopped?)", "warning")
        fail(job, "worker stopped before the job finished", retryable=True, code="lease_expired")
        n += 1
    return n


def active_jobs(limit: int = 50):
    return Job.objects.filter(Q(status=Job.QUEUED) | Q(status=Job.RUNNING)).order_by("-status", "-priority", "id")[:limit]
