"""Worker PCs (PC B): pairing, token authentication, atomic task claim with a lease, progress, finish and lease reaping.

Pull model, like NMarketing's node agent (Qasem processing-server/agent.py): the worker asks A for work over HTTP; A never connects to
the worker. Tokens are random 32-byte values shown to the worker ONCE; only their SHA-256 is stored.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from .models import PairingCode, RemoteTask, WorkerNode

PROTOCOL = 1
PAIRING_MINUTES = 15
LEASE_SECONDS = 120
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"        # no 0/O/1/I: easy to read aloud and type
MAX_FAILURES = 12                                          # failed pairing / token attempts per client per window
FAILURE_WINDOW = 300
_FAILURES: dict[str, list[float]] = {}


class PairingError(Exception):
    def __init__(self, message: str, code: str = "pairing_failed"):
        super().__init__(message)
        self.code = code


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalise_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch in CODE_ALPHABET)


# ------------------------------------------------------------------ throttling of failed attempts

def too_many_failures(client: str) -> bool:
    now = time.time()
    xs = [t for t in _FAILURES.get(client, []) if now - t < FAILURE_WINDOW]
    _FAILURES[client] = xs
    return len(xs) >= MAX_FAILURES


def note_failure(client: str) -> None:
    _FAILURES.setdefault(client, []).append(time.time())


# ------------------------------------------------------------------ pairing

def new_pairing_code() -> tuple[str, PairingCode]:
    """A fresh one-time code like 'K7QX-93MF'. Older unused codes stop working."""
    PairingCode.objects.filter(used_at__isnull=True).update(used_at=timezone.now())
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    row = PairingCode.objects.create(code_hash=hash_secret(raw), expires_at=timezone.now() + timedelta(minutes=PAIRING_MINUTES))
    return f"{raw[:4]}-{raw[4:]}", row


def pair(code: str, name: str, info: dict, address: str) -> tuple[WorkerNode, str]:
    norm = normalise_code(code)
    row = PairingCode.objects.filter(code_hash=hash_secret(norm), used_at__isnull=True, expires_at__gt=timezone.now()).first() if len(norm) == 8 else None
    if row is None:
        raise PairingError("The pairing code is wrong or expired. Show a new code on the main PC and try again.", "bad_code")
    claimed = PairingCode.objects.filter(pk=row.pk, used_at__isnull=True).update(used_at=timezone.now())
    if claimed != 1:
        raise PairingError("This pairing code was just used.", "bad_code")
    name = "".join(ch for ch in (name or "worker").strip() if ch.isalnum() or ch in "-_ .")[:60] or "worker"
    base, n = name, 2
    while WorkerNode.objects.filter(name=name).exists():
        name, n = f"{base}-{n}", n + 1
    token = secrets.token_urlsafe(32)
    w = WorkerNode.objects.create(name=name, token_hash=hash_secret(token), address=address[:80], info=info or {}, last_seen=timezone.now())
    return w, token


def authenticate(token: str) -> WorkerNode | None:
    if not token or len(token) < 20:
        return None
    h = hash_secret(token)
    for w in WorkerNode.objects.filter(token_hash=h):
        if hmac.compare_digest(w.token_hash, h):
            return w if w.enabled else None
    return None


def hello(w: WorkerNode, data: dict, address: str) -> None:
    gpu = data.get("gpu") or {}
    WorkerNode.objects.filter(pk=w.pk).update(
        last_seen=timezone.now(), address=address[:80], gpu_name=str(gpu.get("name") or data.get("gpu_name") or "")[:120],
        vram_total_mb=int(gpu.get("total_mb") or data.get("vram_total_mb") or 0), vram_free_mb=int(gpu.get("free_mb") or data.get("vram_free_mb") or 0),
        capabilities=[str(c)[:60] for c in (data.get("caps") or [])][:80], models_info=data.get("models") or {},
        info={**(w.info or {}), **(data.get("info") or {})},
        measured={**(w.measured or {}), **{k: v for k, v in (data.get("measured") or {}).items() if k != "avg"}})


# ------------------------------------------------------------------ tasks

def pending_for(w: WorkerNode):
    return RemoteTask.objects.filter(status=RemoteTask.QUEUED, cancel_requested=False).filter(target_worker__isnull=True) | \
        RemoteTask.objects.filter(status=RemoteTask.QUEUED, cancel_requested=False, target_worker=w)


def claim(w: WorkerNode, caps: list[str] | None = None, free_mb: int | None = None) -> RemoteTask | None:
    """Atomically take the best queued task this worker can do (compare-and-set, like the local job queue)."""
    have = set(caps if caps is not None else (w.capabilities or []))
    now = timezone.now()
    for t in pending_for(w).order_by("-priority", "id")[:10]:
        if not set(t.needs or []) <= have:
            continue
        if t.vram_mb and w.vram_total_mb and w.vram_total_mb < t.vram_mb:
            continue
        n = RemoteTask.objects.filter(pk=t.pk, status=RemoteTask.QUEUED, cancel_requested=False).update(
            status=RemoteTask.RUNNING, worker=w, lease_expires=now + timedelta(seconds=LEASE_SECONDS), attempts=F("attempts") + 1, started_at=now,
            progress=0.0, progress_text="")
        if n == 1:
            WorkerNode.objects.filter(pk=w.pk).update(current_task=t.pk, last_seen=now)
            return RemoteTask.objects.get(pk=t.pk)
    return None


def progress(t: RemoteTask, w: WorkerNode, fraction: float, text: str) -> bool:
    """Heartbeat: extend the lease and store progress. Returns True when the main PC wants the task cancelled."""
    now = timezone.now()
    n = RemoteTask.objects.filter(pk=t.pk, status=RemoteTask.RUNNING, worker=w).update(
        lease_expires=now + timedelta(seconds=LEASE_SECONDS), progress=max(0.0, min(1.0, fraction)), progress_text=str(text)[:300])
    WorkerNode.objects.filter(pk=w.pk).update(last_seen=now)
    if n == 0:
        return True                          # no longer ours (cancelled or re-queued): tell the worker to stop
    return RemoteTask.objects.filter(pk=t.pk, cancel_requested=True).exists()


def finish(t: RemoteTask, w: WorkerNode, ok: bool, error: str, retryable: bool, result: dict, seconds: float | None) -> bool:
    now = timezone.now()
    cancelled = RemoteTask.objects.filter(pk=t.pk, cancel_requested=True).exists()
    status = RemoteTask.SUCCEEDED if ok else (RemoteTask.CANCELLED if cancelled else RemoteTask.FAILED)
    n = RemoteTask.objects.filter(pk=t.pk, status=RemoteTask.RUNNING, worker=w).update(
        status=status, error=str(error)[:2000], retryable=bool(retryable), result=result or {}, finished_at=now, lease_expires=None, progress=1.0 if ok else F("progress"),
        seconds=seconds if seconds is not None else (now - t.started_at).total_seconds() if t.started_at else None)
    WorkerNode.objects.filter(pk=w.pk).update(current_task=None, last_seen=now)
    if n == 1 and ok and t.kind == "bench.node":
        store_benchmark(w, result or {})
    return n == 1


def store_benchmark(w: WorkerNode, result: dict) -> None:
    """The per-worker benchmark: keep the report and turn the timings into the router's per-kind averages."""
    w.refresh_from_db()
    m = dict(w.measured or {})
    avg = dict(m.get("avg") or {})
    img = result.get("image") or {}
    if img.get("warm"):
        avg[img.get("workflow") or "flux_dev_fp8_t2i"] = {"avg": img["warm"], "n": 1}
    for eng, row in (result.get("tts") or {}).items():
        avg[eng] = {"avg": row["seconds"], "n": 1}
    m["avg"] = avg
    m["bench"] = {"at": timezone.now().isoformat(), **{k: v for k, v in result.items() if k in ("image", "tts", "skipped", "gpu")}}
    WorkerNode.objects.filter(pk=w.pk).update(measured=m)


def reap_expired() -> int:
    """A worker that stopped sending heartbeats loses its task: it fails (retryable) so the waiting job can use another device."""
    now = timezone.now()
    n = 0
    for t in RemoteTask.objects.filter(status=RemoteTask.RUNNING, lease_expires__lt=now):
        RemoteTask.objects.filter(pk=t.pk, status=RemoteTask.RUNNING).update(status=RemoteTask.FAILED, error="worker stopped sending heartbeats", retryable=True,
                                                                         finished_at=now, lease_expires=None)
        WorkerNode.objects.filter(pk=t.worker_id, current_task=t.pk).update(current_task=None)
        n += 1
    return n


def task_payload(t: RemoteTask) -> dict:
    from instai.gpu.compute import task_dir

    d = task_dir(t.pk) / "in"
    files = []
    if d.is_dir():
        for f in sorted(d.iterdir()):
            if f.is_file():
                files.append({"name": f.name, "size": f.stat().st_size})
    return {"id": t.pk, "kind": t.kind, "payload": t.payload, "inputs": files, "timeout": int((t.payload or {}).get("timeout") or 3600),
            "lease_seconds": LEASE_SECONDS}
