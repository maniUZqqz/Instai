"""0.6.0 durable queue: work meant for a computer / service that is not there WAITS (never fails because of that); it fails only for a real
error (after its retries) or when the owner cancels it. Worker PC B is emulated by direct calls to the same functions its HTTP API uses."""
from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest
from django.utils import timezone

from instai.gpu import compute
from instai.jobs import queue, workers
from instai.jobs.models import Job, JobLog, RemoteTask, WorkerNode
from instai.jobs.registry import HANDLERS, handler
from instai.jobs.worker import WorkerRunner
from instai.providers.base import ProviderError
from tests.fakes import wait_until

pytestmark = pytest.mark.django_db(transaction=True)

WF = "flux_dev_fp8_t2i"


@pytest.fixture(autouse=True)
def _fresh():
    compute._CAP_CACHE.update(at=0.0, value=None)
    compute._RESERVED.clear()
    from instai.ops import report

    report.reset_state()
    yield
    compute._CAP_CACHE.update(at=0.0, value=None)


@pytest.fixture
def reg():
    added = []

    def add(kind, fn, **kw):
        handler(kind, **kw)(fn)
        added.append(kind)

    yield add
    for k in added:
        HANDLERS.pop(k, None)


def make_b(name="pcb", online=False, caps=("gpu", f"comfy:{WF}", "downloads"), vram=12288):
    return WorkerNode.objects.create(name=name, token_hash=workers.hash_secret(name), enabled=True, capabilities=list(caps), vram_total_mb=vram, vram_free_mb=vram,
                                     last_seen=timezone.now() if online else timezone.now() - timedelta(hours=2))


def gpu_handler(ctx):
    res = compute.run_task(ctx, "comfy.graph", {"workflow": WF, "graph": {}, "timeout": 30}, timeout=30)
    res.cleanup()
    return {"device": res.device}


def run_once() -> Job | None:
    """One pass of the worker over every job whose time has come (waiting jobs are looked at again at once: run_after -> now)."""
    Job.objects.filter(status=Job.QUEUED).update(run_after=timezone.now())
    WorkerRunner("w").run_once()


def emulate_b(w: WorkerNode, ok=True, stop=None, hold_running=None):
    """What the agent of PC B does: poll, take the task, (optionally hold it running), finish it."""
    def go():
        from django.db import close_old_connections

        end = time.time() + 30
        while time.time() < end and not (stop and stop.is_set()):
            WorkerNode.objects.filter(pk=w.pk).update(last_seen=timezone.now())
            t = workers.claim(WorkerNode.objects.get(pk=w.pk))
            if t:
                if hold_running is not None:
                    hold_running.set()
                    while not (stop and stop.is_set()):
                        time.sleep(0.05)
                    break
                workers.finish(t, w, ok, "" if ok else "the model crashed", False, {}, 0.5)
                break
            time.sleep(0.05)
        close_old_connections()
    th = threading.Thread(target=go, daemon=True)
    th.start()
    return th


# ------------------------------------------------------------------ offline worker: the job waits, then runs when it connects

def test_offline_worker_job_waits_without_failing_then_runs_when_it_connects(reg):
    reg("t.gpu", gpu_handler, resource="gpu")
    w = make_b(online=False)
    job = queue.enqueue("t.gpu", {}, max_attempts=2)
    for _ in range(4):                                         # many passes while B is off: it must never fail or use an attempt
        run_once()
        job.refresh_from_db()
        assert job.status == Job.QUEUED, (job.status, job.error)
        assert job.attempts == 0 and job.wait_code == "worker_offline" and job.error == ""
        assert "رایانه" in job.waiting_reason and "pcb" in job.waiting_reason
    assert job.deferrals == 4 and job.waiting_since is not None
    lines = [l.message for l in JobLog.objects.filter(job=job)]
    assert len(lines) <= 6, "a waiting job must not flood its log: %r" % lines     # queued, started, waiting - not 12 lines
    # B connects (hello) and takes the task
    WorkerNode.objects.filter(pk=w.pk).update(last_seen=timezone.now())
    stop = threading.Event()
    th = emulate_b(WorkerNode.objects.get(pk=w.pk), stop=stop)
    run_once()
    th.join(10)
    job.refresh_from_db()
    assert job.status == Job.SUCCEEDED, (job.status, job.error, job.waiting_reason)
    assert job.attempts == 1 and job.result["device"] == "pcb" and job.node == "pcb" and job.devices.get("pcb", 0) > 0
    assert job.wait_code == ""


def test_worker_that_drops_mid_job_requeues_the_job_without_losing_an_attempt(reg):
    reg("t.gpu", gpu_handler, resource="gpu")
    w = make_b(online=True)
    job = queue.enqueue("t.gpu", {}, max_attempts=2)
    stop, holding = threading.Event(), threading.Event()
    th = emulate_b(w, stop=stop, hold_running=holding)
    runner = threading.Thread(target=lambda: WorkerRunner("w").run_once(), daemon=True)
    Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
    runner.start()
    assert holding.wait(15), "B should have taken the task"
    # B is switched off: its heartbeat stops, the task's lease runs out
    stop.set()
    th.join(5)
    WorkerNode.objects.filter(pk=w.pk).update(last_seen=timezone.now() - timedelta(minutes=5))
    RemoteTask.objects.filter(status="running").update(lease_expires=timezone.now() - timedelta(seconds=1))
    workers.reap_expired()
    runner.join(30)
    job.refresh_from_db()
    t = RemoteTask.objects.get()
    assert t.status == "failed" and t.error_code == "worker_lost"
    assert job.status == Job.QUEUED and job.attempts == 0, (job.status, job.attempts, job.error)
    assert job.wait_code in ("worker_offline", "worker_lost") and job.deferrals == 1
    # B comes back: the job is picked up again and completes, still with its first attempt
    WorkerNode.objects.filter(pk=w.pk).update(last_seen=timezone.now())
    th2 = emulate_b(WorkerNode.objects.get(pk=w.pk))
    run_once()
    th2.join(10)
    job.refresh_from_db()
    assert job.status == Job.SUCCEEDED and job.attempts == 1


def test_a_task_the_worker_really_failed_is_a_real_error_not_a_wait(reg):
    reg("t.gpu", gpu_handler, resource="gpu")
    w = make_b(online=True)
    job = queue.enqueue("t.gpu", {}, max_attempts=1)
    th = emulate_b(w, ok=False)
    run_once()
    th.join(10)
    job.refresh_from_db()
    assert job.status == Job.FAILED and job.wait_code == "" and job.attempts == 1 and "crashed" in job.error


def test_job_cancelled_while_waiting_for_an_offline_worker(reg):
    reg("t.gpu", gpu_handler, resource="gpu")
    make_b(online=False)
    job = queue.enqueue("t.gpu", {})
    run_once()
    job.refresh_from_db()
    assert job.status == Job.QUEUED and job.wait_code == "worker_offline"
    queue.request_cancel(job)
    job.refresh_from_db()
    assert job.status == Job.CANCELLED and job.finished_at and job.wait_code == ""      # at once, no answer from B needed
    assert queue.claim("w", ("gpu",)) is None


def test_cancel_of_a_running_job_whose_task_nobody_took_ends_at_once(reg):
    reg("t.gpu", gpu_handler, resource="gpu")
    w = make_b(online=True)                                           # online but never takes the task (busy / stuck)
    job = queue.enqueue("t.gpu", {})
    th = threading.Thread(target=lambda: WorkerRunner("w").run_once(), daemon=True)
    Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
    th.start()
    assert wait_until(lambda: RemoteTask.objects.filter(status="queued").exists(), timeout=15)
    queue.request_cancel(job)
    th.join(15)
    job.refresh_from_db()
    assert job.status == Job.CANCELLED
    assert RemoteTask.objects.get().status == "cancelled"
    WorkerNode.objects.filter(pk=w.pk).delete()


# ------------------------------------------------------------------ services that are not up

def test_ollama_down_waits_and_the_job_finishes_when_it_is_up(reg):
    from instai.providers.ollama import OllamaProvider

    state = {"up": False}

    def llm_job(ctx):
        if not state["up"]:
            OllamaProvider("http://127.0.0.1:9").generate([{"role": "user", "content": "hi"}], model="qwen3:8b")
        return {"ok": True}
    reg("t.llm", llm_job, resource="gpu")
    job = queue.enqueue("t.llm", {}, max_attempts=2)
    for _ in range(3):
        run_once()
        job.refresh_from_db()
        assert job.status == Job.QUEUED and job.attempts == 0 and job.wait_code == "ollama_down"
        assert "Ollama" in job.waiting_reason
    state["up"] = True
    run_once()
    job.refresh_from_db()
    assert job.status == Job.SUCCEEDED and job.attempts == 1


def test_comfyui_that_cannot_be_started_waits(reg):
    from instai.providers.comfy import launcher

    def comfy_job(ctx):
        launcher.start = lambda install=None: {"started": False, "already_running": False, "cmd": None, "error": "no ComfyUI was found on this PC"}
        launcher._up = lambda url: False
        launcher.ensure_running(timeout=1)
    orig = (launcher.start, launcher._up)
    reg("t.comfy", comfy_job, resource="gpu")
    job = queue.enqueue("t.comfy", {})
    try:
        run_once()
    finally:
        launcher.start, launcher._up = orig
    job.refresh_from_db()
    assert job.status == Job.QUEUED and job.wait_code == "comfy_down" and job.attempts == 0


def test_gpu_busy_waits_instead_of_failing(reg):
    reg("t.busy", lambda ctx: (_ for _ in ()).throw(ProviderError("GPU busy", code="gpu_busy")), resource="gpu")
    job = queue.enqueue("t.busy", {}, max_attempts=1)
    run_once()
    job.refresh_from_db()
    assert job.status == Job.QUEUED and job.wait_code == "gpu_busy" and job.attempts == 0


# ------------------------------------------------------------------ real errors still fail (after their retries)

def test_a_real_error_fails_after_its_retries_and_a_fatal_one_at_once(reg):
    reg("t.bad", lambda ctx: (_ for _ in ()).throw(ProviderError("the model returned garbage", code="llm_invalid_output")), resource="cpu")
    reg("t.fatal", lambda ctx: (_ for _ in ()).throw(ProviderError("no such file", retryable=False, code="not_ready")), resource="cpu")
    job = queue.enqueue("t.bad", {}, max_attempts=3)
    seen = []
    for _ in range(5):
        run_once()
        job.refresh_from_db()
        seen.append((job.status, job.attempts))
        if job.status == Job.FAILED:
            break
    assert seen == [(Job.QUEUED, 1), (Job.QUEUED, 2), (Job.FAILED, 3)], seen
    assert job.error_code == "llm_invalid_output" and job.wait_code == ""
    fatal = queue.enqueue("t.fatal", {}, max_attempts=3)
    run_once()
    fatal.refresh_from_db()
    assert fatal.status == Job.FAILED and fatal.attempts == 1


def test_a_crashing_handler_is_a_real_error(reg):
    reg("t.boom", lambda ctx: 1 / 0, resource="cpu")
    job = queue.enqueue("t.boom", {}, max_attempts=1)
    run_once()
    job.refresh_from_db()
    assert job.status == Job.FAILED and job.error_code == "crash"


# ------------------------------------------------------------------ a worker PROCESS that dies

def test_dead_worker_process_requeues_without_an_attempt_up_to_a_limit():
    job = queue.enqueue("t.x", {}, max_attempts=3)
    for i in range(queue.MAX_LOST_FREE):
        claimed = queue.claim("dead", ("cpu",))
        assert claimed is not None and claimed.attempts == 1, "the attempt of every claim is given back"
        Job.objects.filter(pk=claimed.pk).update(lease_expires=timezone.now() - timedelta(seconds=5))
        assert queue.reap_expired() == 1
        job.refresh_from_db()
        assert job.status == Job.QUEUED and job.attempts == 0 and job.lost_count == i + 1 and job.error_code == "lease_expired"
    # a job that kills the worker every single time must not loop forever
    claimed = queue.claim("dead", ("cpu",))
    Job.objects.filter(pk=claimed.pk).update(lease_expires=timezone.now() - timedelta(seconds=5))
    queue.reap_expired()
    job.refresh_from_db()
    assert job.status == Job.QUEUED and job.attempts == 1 and job.lost_count == queue.MAX_LOST_FREE, "from now on the death counts as an attempt"


# ------------------------------------------------------------------ optional maximum wait, wake-up, priority

def test_optional_maximum_wait_fails_a_job_that_waited_too_long(reg):
    from instai.core import settings_store

    reg("t.gpu", gpu_handler, resource="gpu")
    make_b(online=False)
    job = queue.enqueue("t.gpu", {}, max_attempts=2)
    run_once()
    job.refresh_from_db()
    assert job.status == Job.QUEUED, "no limit by default: it waits"
    settings_store.set_setting("ops_config", {"max_wait_hours": 1})
    Job.objects.filter(pk=job.pk).update(waiting_since=timezone.now() - timedelta(hours=3))
    run_once()
    job.refresh_from_db()
    assert job.status == Job.FAILED and job.error_code == "wait_limit"


def test_a_computer_coming_online_wakes_the_jobs_waiting_for_it(reg):
    from instai.ops import report

    reg("t.gpu", gpu_handler, resource="gpu")
    make_b(online=False)
    job = queue.enqueue("t.gpu", {})
    run_once()
    Job.objects.filter(pk=job.pk).update(run_after=timezone.now() + timedelta(seconds=55))
    new = report.record_heartbeat("pcb", version="0.6.0", now=timezone.now())
    assert new is True
    job.refresh_from_db()
    assert job.run_after <= timezone.now() + timedelta(seconds=1), "no waiting for the pause to end once the computer is back"


def test_waiting_jobs_do_not_block_others_and_keep_their_order(reg):
    reg("t.gpu", gpu_handler, resource="gpu")
    reg("t.ok", lambda ctx: {"ok": 1}, resource="gpu")
    make_b(online=False)
    waiting = queue.enqueue("t.gpu", {})
    later = queue.enqueue("t.ok", {})
    run_once()                                                       # claims `waiting` (id 1) -> deferred (run_after in the future)
    Job.objects.filter(pk=waiting.pk).update(run_after=timezone.now() + timedelta(seconds=30))
    WorkerRunner("w").run_once()
    later.refresh_from_db()
    assert later.status == Job.SUCCEEDED
    waiting.refresh_from_db()
    assert waiting.status == Job.QUEUED


def test_requeue_clears_the_waiting_marks():
    job = queue.enqueue("t.x", {})
    Job.objects.filter(pk=job.pk).update(status=Job.FAILED, wait_code="worker_offline", waiting_since=timezone.now(), lost_count=3)
    job.refresh_from_db()
    j = queue.requeue(job, reset_attempts=True)
    assert j.status == Job.QUEUED and j.wait_code == "" and j.waiting_since is None and j.lost_count == 0 and j.ready_at is not None


def test_queue_wait_is_measured_from_when_the_job_could_first_start(reg):
    from instai.ops import report

    reg("t.ok", lambda ctx: {"ok": 1}, resource="cpu")
    job = queue.enqueue("t.ok", {}, run_after=timezone.now() + timedelta(hours=5))
    Job.objects.filter(pk=job.pk).update(run_after=timezone.now(), created_at=timezone.now() - timedelta(hours=1))
    Job.objects.filter(pk=job.pk).update(ready_at=timezone.now() - timedelta(seconds=40))
    WorkerRunner("w").run_once()
    job.refresh_from_db()
    assert job.first_started_at is not None
    assert 35 <= report.queue_wait(job) <= 60, "the 5 hours of a scheduled start are not 'waiting in the queue'"
