"""Durable queue, worker semantics and the GPU arbiter."""
from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest
from django.utils import timezone

from instai.gpu.arbiter import GPUArbiter
from instai.jobs import queue
from instai.jobs.context import JobContext
from instai.jobs.models import Job, JobLog
from instai.jobs.registry import HANDLERS, handler
from instai.jobs.worker import WorkerRunner, execute
from instai.providers.base import ProviderError

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def reg():
    """Register throw-away handlers; removed afterwards."""
    added = []

    def add(kind, fn, **kw):
        handler(kind, **kw)(fn)
        added.append(kind)

    yield add
    for k in added:
        HANDLERS.pop(k, None)


def test_enqueue_is_idempotent_and_failed_jobs_requeue():
    a = queue.enqueue("t.noop", {"x": 1}, idempotency_key="k1")
    b = queue.enqueue("t.noop", {"x": 2}, idempotency_key="k1")
    assert a.pk == b.pk and Job.objects.count() == 1 and b.payload == {"x": 1}
    Job.objects.filter(pk=a.pk).update(status=Job.FAILED, attempts=3, error="boom")
    c = queue.enqueue("t.noop", {}, idempotency_key="k1")
    assert c.pk == a.pk and c.status == Job.QUEUED and c.attempts == 0 and c.error == ""


def test_claim_order_priority_then_age_and_run_after():
    low = queue.enqueue("t.a", priority=0)
    high = queue.enqueue("t.a", priority=5)
    later = queue.enqueue("t.a", priority=9, run_after=timezone.now() + timedelta(hours=1))
    first = queue.claim("w1", ("cpu",))
    second = queue.claim("w1", ("cpu",))
    assert (first.pk, second.pk) == (high.pk, low.pk)
    assert queue.claim("w1", ("cpu",)) is None, "a job whose run_after is in the future is not claimable"
    assert Job.objects.get(pk=later.pk).status == Job.QUEUED
    assert first.attempts == 1 and first.status == Job.RUNNING and first.lease_owner == "w1" and first.lease_expires > timezone.now()


def test_resource_lanes_do_not_steal_each_others_jobs():
    g = queue.enqueue("t.g", resource="gpu")
    assert queue.claim("cpu-lane", ("cpu", "net")) is None
    assert queue.claim("gpu-lane", ("gpu",)).pk == g.pk


def test_atomic_claim_under_contention():
    ids = [queue.enqueue("t.race").pk for _ in range(12)]
    got, lock = [], threading.Lock()

    def lane(name):
        from django.db import connection

        while True:
            j = queue.claim(name, ("cpu",))
            if not j:
                break
            with lock:
                got.append(j.pk)
        connection.close()

    ts = [threading.Thread(target=lane, args=(f"w{i}",)) for i in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(got) == sorted(ids), "every job claimed exactly once"


def test_success_progress_logs_and_time_accounting(reg):
    def fn(ctx):
        ctx.progress(0.5, "halfway")
        ctx.log("hello from the handler")
        ctx.add_gpu_seconds(2.5, 4096)
        return {"answer": 42}

    reg("t.ok", fn)
    job = queue.enqueue("t.ok", title="demo")
    assert WorkerRunner("w").drain() == 1
    job.refresh_from_db()
    assert job.status == Job.SUCCEEDED and job.result["answer"] == 42 and job.progress == 1.0
    assert job.duration_sec is not None and job.gpu_seconds == 2.5 and job.result["vram_peak_mb"] == 4096
    msgs = [l.message for l in JobLog.objects.filter(job=job)]
    assert "hello from the handler" in msgs and any("succeeded" in m for m in msgs)


def test_retry_with_backoff_then_permanent_failure(reg):
    calls = []

    def flaky(ctx):
        calls.append(1)
        raise ProviderError("network blip", retryable=True)

    reg("t.flaky", flaky)
    job = queue.enqueue("t.flaky", max_attempts=2)
    w = WorkerRunner("w")
    w.run_once()
    job.refresh_from_db()
    assert job.status == Job.QUEUED and job.attempts == 1 and job.run_after > timezone.now() + timedelta(seconds=10)
    assert w.run_once() is False, "backoff: not claimable yet"
    Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
    w.run_once()
    job.refresh_from_db()
    assert job.status == Job.FAILED and job.attempts == 2 and "network blip" in job.error and len(calls) == 2


def test_non_retryable_errors_fail_at_once_and_handler_crash_is_contained(reg):
    reg("t.fatal", lambda ctx: (_ for _ in ()).throw(ProviderError("bad model file", retryable=False, code="not_ready")))
    reg("t.crash", lambda ctx: 1 / 0)
    a, b = queue.enqueue("t.fatal"), queue.enqueue("t.crash", max_attempts=1)
    WorkerRunner("w").drain()
    a.refresh_from_db()
    b.refresh_from_db()
    assert (a.status, a.attempts, a.error_code) == (Job.FAILED, 1, "not_ready")
    assert b.status == Job.FAILED and b.error_code == "crash" and "ZeroDivisionError" in b.error
    assert queue.enqueue("t.nohandler").pk and WorkerRunner("w").drain() == 1


def test_cancel_queued_and_running(reg):
    started = threading.Event()

    def long(ctx):
        started.set()
        for _ in range(200):
            ctx.sleep(0.05)
        return {}

    reg("t.long", long)
    q = queue.enqueue("t.long")
    assert queue.request_cancel(q).status == Job.CANCELLED and queue.claim("w", ("cpu",)) is None

    r = queue.enqueue("t.long")
    job = queue.claim("w", ("cpu",))
    t = threading.Thread(target=lambda: (execute(job, "w"), __import__("django").db.connection.close()))
    t.start()
    assert started.wait(5)
    queue.request_cancel(job)
    t.join(10)
    r.refresh_from_db()
    assert r.status == Job.CANCELLED and r.finished_at is not None


def test_timeout_and_expired_lease_requeue(reg):
    reg("t.slow", lambda ctx: [ctx.sleep(0.05) for _ in range(100)])
    job = queue.enqueue("t.slow", timeout_sec=1, max_attempts=1)
    WorkerRunner("w").run_once()
    job.refresh_from_db()
    assert job.status == Job.FAILED and job.error_code == "timeout"

    j2 = queue.enqueue("t.slow", max_attempts=3)
    claimed = queue.claim("dead-worker", ("cpu",))
    Job.objects.filter(pk=claimed.pk).update(lease_expires=timezone.now() - timedelta(seconds=5))
    assert queue.reap_expired() == 1
    j2.refresh_from_db()
    assert j2.status == Job.QUEUED and j2.error_code == "lease_expired", "a job whose worker vanished is not lost"


def test_heartbeat_extends_lease_only_for_owner():
    queue.enqueue("t.hb")
    job = queue.claim("w1", ("cpu",), lease_sec=5)
    before = Job.objects.get(pk=job.pk).lease_expires
    assert queue.heartbeat(job, "w1", 120) is True
    assert Job.objects.get(pk=job.pk).lease_expires > before
    assert queue.heartbeat(job, "someone-else") is False


# ------------------------------------------------------------------ GPU arbiter

class FakeCtx:
    """Just enough of JobContext for the arbiter."""

    def __init__(self, pk):
        self.job = type("J", (), {"pk": pk})()
        self.reasons: list[str] = []
        self.gpu = 0.0
        self.cancel = False

    def waiting(self, r): self.reasons.append(r)
    def check(self):
        if self.cancel:
            from instai.jobs.context import JobCancelled
            raise JobCancelled()
    def sleep(self, s): time.sleep(s); self.check()
    def add_gpu_seconds(self, s, peak=0): self.gpu += s


def test_arbiter_serialises_gpu_jobs_and_unloads_others():
    unloaded: list[str] = []
    arb = GPUArbiter(probe=lambda: None, unloaders={"llm": lambda: unloaded.append("llm"), "comfy": lambda: unloaded.append("comfy"),
                                                    "tts": lambda: unloaded.append("tts")})
    inside, overlap = [0], [False]

    def job(pk, occupant):
        with arb.hold(FakeCtx(pk), occupant):
            inside[0] += 1
            overlap[0] = overlap[0] or inside[0] > 1
            time.sleep(0.15)
            inside[0] -= 1

    ts = [threading.Thread(target=job, args=(i, o)) for i, o in enumerate(["llm", "comfy", "tts"])]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert overlap[0] is False, "never two GPU jobs at once"
    assert sorted(unloaded) == sorted(["comfy", "tts", "llm", "tts", "llm", "comfy"]), "each entry unloads the two OTHER occupants"


def test_arbiter_waits_while_another_program_uses_vram_and_shows_it():
    state = {"used": 9000}
    arb = GPUArbiter(probe=lambda: {"used_mb": state["used"], "total_mb": 12288}, unloaders={}, poll=0.05)
    ctx = FakeCtx(1)
    threading.Timer(0.3, lambda: state.update(used=900)).start()  # the other program finishes
    t0 = time.time()
    with arb.hold(ctx, "comfy"):
        waited = time.time() - t0
    assert waited >= 0.25, "waited for the foreign VRAM to be released"
    assert any("GPU busy" in r and "8.8" in r for r in ctx.reasons), ctx.reasons
    assert ctx.reasons[-1] == "", "the busy notice is cleared when the job starts"


def test_arbiter_wait_is_cancellable_and_no_gpu_means_no_wait():
    arb = GPUArbiter(probe=lambda: {"used_mb": 11000, "total_mb": 12288}, unloaders={}, poll=0.05)
    ctx = FakeCtx(2)
    threading.Timer(0.2, lambda: setattr(ctx, "cancel", True)).start()
    from instai.jobs.context import JobCancelled

    with pytest.raises(JobCancelled):
        with arb.hold(ctx, "llm"):
            pass
    assert arb._lock.acquire(blocking=False), "the lock is released after a cancelled wait"
    arb._lock.release()
    nogpu = GPUArbiter(probe=lambda: None, unloaders={})
    with nogpu.hold(FakeCtx(3), "llm"):
        pass
    assert nogpu.foreign_load_mb() == 0


def test_arbiter_does_not_mistake_our_own_loaded_models_for_another_program():
    """ComfyUI keeps FLUX loaded (~11 GB) after our job: that is ours, so the next job must not wait for it."""
    arb = GPUArbiter(probe=lambda: {"used_mb": 11800, "total_mb": 12288}, unloaders={}, poll=0.05, ours=lambda: 11200)
    assert arb.foreign_load_mb() == 0
    arb2 = GPUArbiter(probe=lambda: {"used_mb": 11800, "total_mb": 12288}, unloaders={}, poll=0.05, ours=lambda: 1200)
    assert arb2.foreign_load_mb() == 10600, "10.6 GB beyond what Ollama/ComfyUI report = another program (e.g. the NMarketing agent)"
    arb3 = GPUArbiter(probe=lambda: {"used_mb": 1500, "total_mb": 12288}, unloaders={}, ours=lambda: 0)
    assert arb3.foreign_load_mb() == 0, "desktop/compositor usage is below the busy threshold"


def test_arbiter_our_load_reads_ollama_and_comfy(monkeypatch):
    from instai.core import hardware
    from tests import fakes

    arb = GPUArbiter(probe=lambda: None, unloaders={})
    arb._probe = None  # use the real code path for "ours"
    with fakes.ollama_server(loaded=("qwen3:8b",)) as o:
        monkeypatch.setattr("instai.core.runtime.ollama_url", lambda: o.url)
        monkeypatch.setattr("instai.core.runtime.comfyui_url", lambda: "http://127.0.0.1:9")
        assert arb.our_load_mb() == int(5_000_000_000 / 1048576)


def test_job_context_run_cmd_is_cancellable(reg):
    import sys

    def fn(ctx):
        rc, out = ctx.run_cmd([sys.executable, "-c", "import time; time.sleep(30)"])
        return {"rc": rc}

    reg("t.cmd", fn)
    job = queue.enqueue("t.cmd", max_attempts=1)
    claimed = queue.claim("w", ("cpu",))
    t = threading.Thread(target=lambda: (execute(claimed, "w"), __import__("django").db.connection.close()))
    t0 = time.time()
    t.start()
    time.sleep(1.0)
    queue.request_cancel(claimed)
    t.join(15)
    job.refresh_from_db()
    assert job.status == Job.CANCELLED and time.time() - t0 < 12, "the subprocess was killed, not waited for"
