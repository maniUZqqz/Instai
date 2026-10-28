"""Workers screen API (localhost only): devices, pairing code + LAN address, LAN listener switch, enable/disable/remove a worker, per-worker benchmark."""
from __future__ import annotations

from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai import lan
from instai.core import settings_store
from instai.core.errors import DomainError
from instai.gpu import compute

from . import workers
from .models import RemoteTask, WorkerNode


def _lan_status() -> dict:
    st = lan.LAN.status()
    st["enabled"] = bool(settings_store.get_setting("lan_worker_enabled"))
    return st


def _task_dict(t: RemoteTask) -> dict:
    return {"id": t.pk, "kind": t.kind, "status": t.status, "worker": t.worker.name if t.worker_id else (t.target_worker.name if t.target_worker_id else ""),
            "progress": t.progress, "progress_text": t.progress_text, "seconds": t.seconds, "error": t.error[:200], "created_at": t.created_at,
            "job": t.job_id}


def _worker_dict(w: WorkerNode) -> dict:
    now = timezone.now()
    online = bool(w.last_seen and (now - w.last_seen).total_seconds() < compute.ONLINE_SECONDS)
    return {"id": w.pk, "name": w.name, "enabled": w.enabled, "online": online, "last_seen": w.last_seen, "address": w.address, "gpu_name": w.gpu_name,
            "vram_total_mb": w.vram_total_mb, "vram_free_mb": w.vram_free_mb, "capabilities": w.capabilities, "models": w.models_info, "measured": w.measured,
            "info": w.info, "busy": compute.worker_busy(w), "current_task": w.current_task, "created_at": w.created_at}


@api_view(["GET"])
def workers_overview(request):
    from instai.core import hardware

    devices = compute.overview()
    gpu = hardware.gpu_status()
    for d in devices:
        if d.get("local"):
            d["gpu_name"] = (gpu or {}).get("name") or ""
    return Response({"devices": devices, "workers": [_worker_dict(w) for w in WorkerNode.objects.all()], "lan": _lan_status(),
                     "recent_tasks": [_task_dict(t) for t in RemoteTask.objects.select_related("worker", "target_worker")[:15]]})


@api_view(["POST"])
def pairing(request):
    """Show a one-time code (valid 15 minutes) and the address to type on PC B. Also opens the LAN listener (the owner asked to pair)."""
    st = lan.LAN.status()
    if not st["running"]:
        port = int(settings_store.get_setting("lan_worker_port") or lan.DEFAULT_PORT)
        if not lan.LAN.start(port):
            raise DomainError("not_ready", "درگاه شبکه باز نشد: " + lan.LAN.error, http_status=409)
        settings_store.set_setting("lan_worker_enabled", True)
    code, row = workers.new_pairing_code()
    st = _lan_status()
    return Response({"code": code, "expires_at": row.expires_at, "valid_minutes": workers.PAIRING_MINUTES, "port": st["port"], "addresses": st["addresses"],
                     "urls": [f"http://{a}:{st['port']}" for a in st["addresses"]], "lan": st})


@api_view(["POST"])
def lan_switch(request):
    enabled = bool(request.data.get("enabled"))
    if enabled:
        port = int(request.data.get("port") or settings_store.get_setting("lan_worker_port") or lan.DEFAULT_PORT)
        if not lan.LAN.start(port):
            raise DomainError("not_ready", "درگاه شبکه باز نشد: " + lan.LAN.error, http_status=409)
        settings_store.set_setting("lan_worker_port", port)
    else:
        lan.LAN.stop()
    settings_store.set_setting("lan_worker_enabled", enabled)
    return Response(_lan_status())


@api_view(["GET", "PATCH", "DELETE"])
def worker_detail(request, pk):
    w = get_object_or_404(WorkerNode, pk=pk)
    if request.method == "DELETE":
        RemoteTask.objects.filter(target_worker=w, status__in=(RemoteTask.QUEUED, RemoteTask.RUNNING)).update(status=RemoteTask.CANCELLED, cancel_requested=True,
                                                                                                         error="worker removed")
        w.delete()
        return Response(status=204)
    if request.method == "PATCH":
        if "enabled" in request.data:
            w.enabled = bool(request.data["enabled"])
        if request.data.get("name"):
            nm = str(request.data["name"]).strip()[:60]
            if WorkerNode.objects.filter(name=nm).exclude(pk=w.pk).exists():
                raise DomainError("conflict", "این نام قبلاً استفاده شده است.", http_status=409)
            w.name = nm
        w.save()
    d = _worker_dict(w)
    d["tasks"] = [_task_dict(t) for t in RemoteTask.objects.filter(worker=w).select_related("worker", "target_worker")[:15]]
    return Response(d)


@api_view(["POST"])
def worker_benchmark(request, pk):
    """Queue a benchmark task pinned to this worker; the numbers land in worker.measured (and feed the router)."""
    w = get_object_or_404(WorkerNode, pk=pk)
    if not w.enabled:
        raise DomainError("conflict", "این کارگر غیرفعال است.", http_status=409)
    if RemoteTask.objects.filter(kind="bench.node", target_worker=w, status__in=(RemoteTask.QUEUED, RemoteTask.RUNNING)).exists():
        raise DomainError("conflict", "یک بنچمارک برای این کارگر در حال اجراست.", http_status=409)
    t = RemoteTask.objects.create(kind="bench.node", payload={"timeout": 3600}, target_worker=w, priority=5)
    return Response(_task_dict(t), status=202)


@api_view(["GET"])
def remote_tasks(request):
    qs = RemoteTask.objects.select_related("worker", "target_worker")
    if request.query_params.get("worker"):
        qs = qs.filter(worker_id=request.query_params["worker"])
    return Response([_task_dict(t) for t in qs[: int(request.query_params.get("limit", 30))]])


urlpatterns = [
    path("workers", workers_overview),
    path("workers/pairing", pairing),
    path("workers/lan", lan_switch),
    path("workers/<int:pk>", worker_detail),
    path("workers/<int:pk>/benchmark", worker_benchmark),
    path("remote-tasks", remote_tasks),
]
