"""The worker: claims jobs from the DB queue and runs their handlers.

Lanes: one GPU lane (GPU jobs are serialised; the arbiter does the unload/load switching) and N CPU/network lanes that run
ffmpeg, Piper, file work and API calls in parallel. Started by START.bat as `manage.py run_worker`.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import traceback

from django.db import close_old_connections, connections
from django.utils import timezone

from instai.providers.base import ProviderError

from . import queue
from .context import JobCancelled, JobContext, JobTimeout
from .models import Job, Worker
from .registry import HANDLERS, load_handlers

log = logging.getLogger("instai.worker")
LEASE_SEC = 90


def execute(job: Job, worker: str = "inline") -> str:
    """Run one claimed job to its end state. Returns the resulting status. Never raises."""
    load_handlers()
    ctx = JobContext(job, worker, LEASE_SEC)
    fn = HANDLERS.get(job.kind)
    stop = threading.Event()

    def beat():  # keeps the lease alive during long, silent steps (an LLM call can take minutes)
        while not stop.wait(LEASE_SEC / 3):
            try:
                queue.heartbeat(job, worker, LEASE_SEC)
            except Exception:  # noqa: BLE001
                pass
            finally:
                close_old_connections()

    t = threading.Thread(target=beat, daemon=True)
    t.start()
    try:
        if fn is None:
            return queue.fail(job, f"no handler for job kind {job.kind}", retryable=False, code="no_handler")
        queue.log_job(job, f"started (attempt {job.attempts}/{job.max_attempts}) by {worker}")
        ctx.check()
        result = fn(ctx) or {}
        queue.complete(job, result, ctx.gpu_seconds)
        if ctx.vram_peak_mb:
            Job.objects.filter(pk=job.pk).update(result={**result, "vram_peak_mb": ctx.vram_peak_mb})
        return Job.SUCCEEDED
    except JobCancelled:
        queue.mark_cancelled(job)
        _on_cancel(job)
        return Job.CANCELLED
    except JobTimeout as e:
        return queue.fail(job, str(e), retryable=True, code="timeout")
    except ProviderError as e:
        return queue.fail(job, str(e), retryable=e.retryable, code=e.code)
    except Exception as e:  # noqa: BLE001 - a handler bug must not kill the worker
        from instai.agents.runner import AgentError
        from instai.core.errors import DomainError

        if isinstance(e, AgentError):
            return queue.fail(job, f"{e} :: " + "; ".join(e.errors[:5]), retryable=True, code=e.code)
        if isinstance(e, DomainError):
            return queue.fail(job, str(e.detail), retryable=False, code=e.code)
        log.exception("job %s crashed", job.pk)
        return queue.fail(job, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}", retryable=True, code="crash")
    finally:
        stop.set()
        final = Job.objects.filter(pk=job.pk).values_list("status", flat=True).first()
        if final == Job.FAILED:
            _on_final_failure(job)


def _on_cancel(job: Job) -> None:
    """A cancelled production job leaves the episode where it was (nothing is thrown away)."""


def _on_final_failure(job: Job) -> None:
    """Production jobs that fail for good move their episode to `failed` (retry resumes there); story jobs just report."""
    if job.kind.startswith("prod.") and job.episode_id:
        from instai.story import services
        from instai.story.models import Episode

        ep = Episode.objects.filter(pk=job.episode_id).first()
        if ep:
            err = Job.objects.filter(pk=job.pk).values_list("error", flat=True).first() or "job failed"
            try:
                services.fail_episode(ep, err[:300])
            except Exception:  # noqa: BLE001
                pass


class WorkerRunner:
    def __init__(self, name: str | None = None, cpu_lanes: int = 2, gpu_lanes: int = 1, poll: float = 1.0):
        self.name = name or f"{socket.gethostname()}-{os.getpid()}"
        self.cpu_lanes, self.gpu_lanes, self.poll = cpu_lanes, gpu_lanes, poll
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []

    def run_once(self, resources=("cpu", "net", "gpu")) -> bool:
        """Claim and run at most one job (tests and `manage.py run_worker --once`)."""
        job = queue.claim(self.name, tuple(resources), LEASE_SEC)
        if not job:
            return False
        execute(job, self.name)
        return True

    def drain(self, max_jobs: int = 200, resources=("cpu", "net", "gpu")) -> int:
        n = 0
        while n < max_jobs and self.run_once(resources):
            n += 1
        return n

    def _lane(self, resources: tuple[str, ...], label: str) -> None:
        tick = 0
        while not self.stop_event.is_set():
            try:
                close_old_connections()
                if tick % 10 == 0:
                    queue.reap_expired()
                tick += 1
                if not self.run_once(resources):
                    self.stop_event.wait(self.poll)
            except Exception:  # noqa: BLE001
                log.exception("lane %s error", label)
                self.stop_event.wait(3)
        connections.close_all()

    def _heartbeat_row(self) -> None:
        row, _ = Worker.objects.get_or_create(name=self.name)
        Worker.objects.filter(pk=row.pk).update(pid=os.getpid(), last_seen=timezone.now(), info={"cpu_lanes": self.cpu_lanes,
                                                                                               "gpu_lanes": self.gpu_lanes})
        running = list(Job.objects.filter(lease_owner=self.name, status=Job.RUNNING).values_list("pk", flat=True))
        Worker.objects.filter(pk=row.pk).update(current_jobs=running)

    def run_forever(self) -> None:
        load_handlers()
        log.info("worker %s starting: %d cpu lanes, %d gpu lane(s)", self.name, self.cpu_lanes, self.gpu_lanes)
        reaped = queue.reap_expired()
        if reaped:
            log.info("re-queued %d job(s) left by a previous worker", reaped)
        for i in range(self.gpu_lanes):
            self.threads.append(threading.Thread(target=self._lane, args=(("gpu",), f"gpu{i}"), daemon=True))
        for i in range(self.cpu_lanes):
            self.threads.append(threading.Thread(target=self._lane, args=(("cpu", "net"), f"cpu{i}"), daemon=True))
        for t in self.threads:
            t.start()
        try:
            while not self.stop_event.is_set():
                close_old_connections()
                self._heartbeat_row()
                self.stop_event.wait(5)
        except KeyboardInterrupt:
            log.info("stopping ...")
        finally:
            self.stop_event.set()
            for t in self.threads:
                t.join(timeout=5)
            Worker.objects.filter(name=self.name).update(last_seen=None)
