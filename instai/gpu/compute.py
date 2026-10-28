"""Routing of GPU tasks to a device: this PC or a paired worker PC.

* Each PC has its OWN GPU arbiter (VRAM does not pool): at most one heavy task per GPU. This PC's arbiter is `gpu.arbiter.ARBITER`;
  a worker PC's agent runs its own.
* A task names the capabilities it needs (`comfy:<workflow>`, `voice:moss` ...) and the free VRAM it wants. Only devices that have the
  capabilities and the VRAM are candidates; an idle one wins, the faster one (measured average seconds per task kind) first, this PC
  first on a tie. If every candidate is busy the task waits ("waiting for a free GPU") - that is how two shots, two episodes or two
  different shot types run on both GPUs at once.
* A remote task is a `RemoteTask` row pinned to the chosen worker; the worker pulls it over HTTP, uploads its output files and finishes.
  If the worker fails or disappears, the task falls back to this PC (when this PC can do it).
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from instai.core import settings_store
from instai.jobs import queue
from instai.providers.base import ProviderError

from . import capabilities, executors
from .arbiter import ARBITER

log = logging.getLogger("instai.compute")
ONLINE_SECONDS = 45
LEASE_SECONDS = 120
LOCAL = "local"
_CAP_CACHE: dict = {"at": 0.0, "value": None}
_RESERVED: dict[str, int] = {}          # device name -> tasks that were handed to it and have not finished (set atomically with the choice)
_RESERVE_LOCK = threading.Lock()


def tasks_root() -> Path:
    p = Path(settings.DATA_DIR) / "tasks"
    p.mkdir(parents=True, exist_ok=True)
    return p


def task_dir(task_id: int) -> Path:
    return tasks_root() / str(task_id)


@dataclass
class Candidate:
    name: str
    local: bool
    busy: bool
    free_mb: int
    total_mb: int
    speed: float | None = None          # average seconds of this kind of task on that PC (None = unknown)
    worker_id: int | None = None


@dataclass
class TaskResult:
    files: list[Path]
    result: dict
    device: str
    seconds: float
    _dir: Path | None = None
    attempts: list[str] = field(default_factory=list)

    def file(self, name: str) -> Path | None:
        return next((f for f in self.files if f.name == name), None)

    def of_kind(self, *suffixes: str) -> list[Path]:
        return [f for f in self.files if f.suffix.lower() in suffixes]

    def cleanup(self) -> None:
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)


def local_caps(max_age: float = 15.0) -> dict:
    if time.time() - _CAP_CACHE["at"] > max_age or _CAP_CACHE["value"] is None:
        try:
            _CAP_CACHE.update(at=time.time(), value=capabilities.local_capabilities())
        except Exception:  # noqa: BLE001 - detection must never break a render
            _CAP_CACHE.update(at=time.time(), value={"caps": [], "vram_total_mb": 0, "vram_free_mb": 0})
    return _CAP_CACHE["value"]


def _speed_key(kind: str, payload: dict) -> str:
    return payload.get("workflow") or payload.get("engine") or kind


def local_speed(key: str) -> float | None:
    return ((settings_store.get_setting("device_speed.local") or {}).get(key) or {}).get("avg")


def record_speed(device: str, worker_id: int | None, key: str, seconds: float) -> None:
    """Running average (last ~5 runs weigh most) of how long a kind of task takes on a device: the router's measured speed."""
    def upd(d: dict) -> dict:
        row = d.get(key) or {"avg": seconds, "n": 0}
        n = min(row["n"] + 1, 5)
        row = {"avg": round(row["avg"] + (seconds - row["avg"]) / n, 2), "n": n}
        return {**d, key: row}
    if device == LOCAL:
        settings_store.set_setting("device_speed.local", upd(settings_store.get_setting("device_speed.local") or {}))
    elif worker_id:
        from instai.jobs.models import WorkerNode

        w = WorkerNode.objects.filter(pk=worker_id).first()
        if w:
            m = dict(w.measured or {})
            m["avg"] = upd(m.get("avg") or {})
            WorkerNode.objects.filter(pk=w.pk).update(measured=m)


def online_workers():
    from instai.jobs.models import WorkerNode

    return WorkerNode.objects.filter(enabled=True, last_seen__gte=timezone.now() - timedelta(seconds=ONLINE_SECONDS))


def worker_busy(w) -> bool:
    from instai.jobs.models import RemoteTask

    return RemoteTask.objects.filter(target_worker=w, status__in=(RemoteTask.QUEUED, RemoteTask.RUNNING)).exists()


def candidates(kind: str, payload: dict, *, needs: list[str], vram_mb: int, local_ok: bool = True, remote_ok: bool = True,
               exclude: tuple[str, ...] = ()) -> list[Candidate]:
    key = _speed_key(kind, payload)
    out: list[Candidate] = []
    if local_ok and LOCAL not in exclude:
        lc = local_caps()
        if all(n in lc["caps"] for n in needs) and (not vram_mb or not lc["vram_total_mb"] or lc["vram_total_mb"] >= vram_mb):
            out.append(Candidate(LOCAL, True, ARBITER.busy or _RESERVED.get(LOCAL, 0) > 0, lc["vram_free_mb"], lc["vram_total_mb"], local_speed(key)))
    if remote_ok:
        for w in online_workers():
            if w.name in exclude or not all(n in (w.capabilities or []) for n in needs):
                continue
            if vram_mb and w.vram_total_mb and w.vram_total_mb < vram_mb:
                continue
            free = w.vram_free_mb or w.vram_total_mb
            busy = worker_busy(w) or _RESERVED.get(w.name, 0) > 0 or (bool(vram_mb) and bool(w.vram_total_mb) and free < vram_mb * 0.9 and not w.current_task)
            out.append(Candidate(w.name, False, busy, free, w.vram_total_mb, ((w.measured or {}).get("avg") or {}).get(key, {}).get("avg"), w.pk))
    return out


def choose(cands: list[Candidate]) -> Candidate | None:
    idle = [c for c in cands if not c.busy]
    if not idle:
        return None
    known = [c for c in idle if c.speed is not None]
    if len(known) == len(idle) and len(idle) > 1:
        return sorted(idle, key=lambda c: (c.speed, not c.local))[0]
    return sorted(idle, key=lambda c: (not c.local,))[0]          # unknown speeds: this PC first, the other PC takes the next task


def overview() -> list[dict]:
    """Devices for the UI: this PC and every paired worker, with what they can do right now."""
    lc = local_caps()
    rows = [{"name": LOCAL, "local": True, "online": True, "enabled": True, "busy": ARBITER.busy, "caps": lc["caps"], "vram_total_mb": lc["vram_total_mb"],
             "vram_free_mb": lc["vram_free_mb"], "speed": (settings_store.get_setting("device_speed.local") or {})}]
    from instai.jobs.models import WorkerNode

    now = timezone.now()
    for w in WorkerNode.objects.all():
        rows.append({"name": w.name, "id": w.pk, "local": False, "enabled": w.enabled, "online": bool(w.last_seen and (now - w.last_seen).total_seconds() < ONLINE_SECONDS),
                     "busy": worker_busy(w), "caps": w.capabilities, "vram_total_mb": w.vram_total_mb, "vram_free_mb": w.vram_free_mb,
                     "speed": (w.measured or {}).get("avg") or {}})
    return rows


# ------------------------------------------------------------------ running a task

def _prepare_dirs(inputs: dict[str, Path] | None) -> tuple[Path, Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="task-", dir=tasks_root()))
    (root / "in").mkdir()
    (root / "out").mkdir()
    for name, src in (inputs or {}).items():
        shutil.copyfile(src, root / "in" / Path(name).name)
    return root, root / "in", root / "out"


def _run_local(ctx, kind: str, payload: dict, inputs: dict[str, Path] | None) -> TaskResult:
    root, in_dir, out_dir = _prepare_dirs(inputs)
    t0 = time.time()
    try:
        io = executors.TaskIO(in_dir, out_dir, progress=lambda f, t="": ctx.progress(f, t), cancelled=lambda: queue.is_cancel_requested(ctx.job.pk))
        with ARBITER.hold(ctx, executors.OCCUPANT.get(kind, "comfy")):
            res = executors.run(kind, payload, io)
    except executors.TaskCancelled:
        shutil.rmtree(root, ignore_errors=True)
        from instai.jobs.context import JobCancelled

        raise JobCancelled() from None
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return TaskResult(sorted(p for p in out_dir.iterdir() if p.is_file()), res, LOCAL, time.time() - t0, _dir=root)


def _run_remote(ctx, cand: Candidate, kind: str, payload: dict, inputs: dict[str, Path] | None, needs: list[str], vram_mb: int,
                timeout: float) -> TaskResult:
    from instai.jobs.models import RemoteTask, WorkerNode

    t = RemoteTask.objects.create(kind=kind, payload=payload, needs=needs, vram_mb=vram_mb, target_worker_id=cand.worker_id, job=ctx.job,
                                  priority=ctx.job.priority)
    d = task_dir(t.pk)
    (d / "in").mkdir(parents=True, exist_ok=True)
    (d / "out").mkdir(parents=True, exist_ok=True)
    for name, src in (inputs or {}).items():
        shutil.copyfile(src, d / "in" / Path(name).name)
    ctx.log(f"task {t.pk} ({kind}) sent to worker {cand.name}")
    t0 = time.time()
    queued_since = time.time()
    cancel_sent = False
    try:
        while True:
            t.refresh_from_db()
            if t.status == RemoteTask.SUCCEEDED:
                break
            if t.status in (RemoteTask.FAILED, RemoteTask.CANCELLED):
                if queue.is_cancel_requested(ctx.job.pk):
                    from instai.jobs.context import JobCancelled

                    raise JobCancelled()
                raise ProviderError(t.error or f"worker {cand.name} could not do the task", retryable=t.retryable, code="worker_failed")
            if t.status == RemoteTask.RUNNING:
                ctx.progress(t.progress, f"{cand.name}: {t.progress_text}"[:120])
            else:
                ctx.waiting(f"waiting for worker {cand.name} to pick the task up")
                w = WorkerNode.objects.filter(pk=cand.worker_id).first()
                offline = not (w and w.enabled and w.last_seen and (timezone.now() - w.last_seen).total_seconds() < ONLINE_SECONDS)
                if offline or time.time() - queued_since > 90:
                    RemoteTask.objects.filter(pk=t.pk, status=RemoteTask.QUEUED).update(status=RemoteTask.CANCELLED, error="worker did not pick the task up",
                                                                                         finished_at=timezone.now())
                    raise ProviderError(f"worker {cand.name} did not pick the task up", retryable=True, code="worker_offline")
            if queue.is_cancel_requested(ctx.job.pk) and not cancel_sent:
                RemoteTask.objects.filter(pk=t.pk).update(cancel_requested=True)
                cancel_sent = True
            if time.time() - t0 > timeout:
                RemoteTask.objects.filter(pk=t.pk).update(cancel_requested=True)
                raise ProviderError(f"worker {cand.name} took longer than {int(timeout)} s", retryable=True, code="worker_timeout")
            time.sleep(0.5)
            if not cancel_sent:
                ctx.check()
    except BaseException:
        RemoteTask.objects.filter(pk=t.pk, status__in=(RemoteTask.QUEUED, RemoteTask.RUNNING)).update(cancel_requested=True)
        raise
    secs = t.seconds or (time.time() - t0)
    keep = Path(tempfile.mkdtemp(prefix="task-", dir=tasks_root()))
    for f in (d / "out").iterdir():
        shutil.move(str(f), keep / f.name)
    shutil.rmtree(d, ignore_errors=True)
    return TaskResult(sorted(p for p in keep.iterdir() if p.is_file()), t.result or {}, cand.name, secs, _dir=keep)


def run_task(ctx, kind: str, payload: dict, inputs: dict[str, Path] | None = None, *, needs: list[str] | None = None, vram_mb: int | None = None,
             local_ok: bool = True, remote_ok: bool = True, timeout: float = 3600, wait_timeout: float = 7200) -> TaskResult:
    """Run a GPU task on the best free device. Raises ProviderError when no device can ever do it."""
    needs = capabilities.needs_for(kind, payload) if needs is None else needs
    vram = capabilities.vram_for(kind, payload) if vram_mb is None else vram_mb
    tried: list[str] = []
    t_wait = time.time()
    while True:
        ctx.check()
        with _RESERVE_LOCK:               # choose AND reserve in one step: two threads can never both take the same idle GPU
            cands = candidates(kind, payload, needs=needs, vram_mb=vram, local_ok=local_ok, remote_ok=remote_ok, exclude=tuple(tried))
            pick = choose(cands) if cands else None
            if pick is not None:
                _RESERVED[pick.name] = _RESERVED.get(pick.name, 0) + 1
        if not cands:
            if not tried:
                raise ProviderError("No PC can run this task (missing: " + ", ".join(needs or [kind]) + "). Check ComfyUI / the voice models on this PC or the worker.",
                                    retryable=False, code="not_ready")
            raise ProviderError("The worker failed and this PC cannot do the task itself.", retryable=True, code="worker_failed")
        if pick is None:
            ctx.waiting("waiting for a free GPU (" + ", ".join(c.name for c in cands) + " busy)")
            if time.time() - t_wait > wait_timeout:
                raise ProviderError("No GPU became free in time", retryable=True, code="gpu_busy")
            time.sleep(1.0)
            continue
        ctx.waiting("")
        key = _speed_key(kind, payload)
        try:
            try:
                if pick.local:
                    res = _run_local(ctx, kind, payload, inputs)
                else:
                    res = _run_remote(ctx, pick, kind, payload, inputs, needs, vram, timeout)
            finally:
                with _RESERVE_LOCK:
                    _RESERVED[pick.name] = max(0, _RESERVED.get(pick.name, 1) - 1)
        except ProviderError as e:
            if pick.local or not e.retryable:
                raise
            log.warning("worker %s failed (%s); trying another device", pick.name, e)
            ctx.log(f"worker {pick.name} failed ({str(e)[:160]}); trying another device", "warning")
            tried.append(pick.name)
            continue
        record_speed(res.device, pick.worker_id, key, res.seconds)
        res.attempts = tried
        return res


def fan_out(ctx, items: list, fn, *, kind: str, payload: dict | None = None, needs: list[str] | None = None, vram_mb: int | None = None) -> list:
    """Run fn(item) for every item on as many threads as there are devices that can take this kind of task (this PC + workers), keeping the
    order of `items` in the result. The first error stops the rest. Each call of fn runs its own `run_task`, so a busy GPU just waits."""
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    n = min(len(items), parallel_devices(kind, payload or {}, needs, vram_mb)) if items else 1
    if n <= 1:
        return [fn(it) for it in items]

    def call(it):
        try:
            return fn(it)
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=n, thread_name_prefix="fanout") as pool:
        futures = [pool.submit(call, it) for it in items]
        try:
            return [f.result() for f in futures]
        except BaseException:
            for f in futures:
                f.cancel()
            raise


def parallel_devices(kind: str, payload: dict, needs: list[str] | None = None, vram_mb: int | None = None) -> int:
    """How many devices could run this kind of task at once (1 = only this PC)."""
    needs = capabilities.needs_for(kind, payload) if needs is None else needs
    vram = capabilities.vram_for(kind, payload) if vram_mb is None else vram_mb
    return max(1, len(candidates(kind, payload, needs=needs, vram_mb=vram)))


def workflow_available(workflow_id: str) -> bool:
    """Can ANY device (this PC or an online worker) run this ComfyUI workflow right now (nodes + model files present)?"""
    return bool(candidates("comfy.graph", {"workflow": workflow_id}, needs=[f"comfy:{workflow_id}"], vram_mb=0))
