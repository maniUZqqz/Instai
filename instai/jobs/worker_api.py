"""The HTTP API a worker PC (PC B) uses: /api/worker/*  - the ONLY part of InstAI reachable from the LAN (see instai/lan.py).

Auth: `Authorization: Worker <token>` (token from pairing). Pairing itself is authenticated by the one-time code. Plain Django views
(not DRF) so uploads and downloads of large files stream instead of being loaded into memory.

  POST /api/worker/pair                       {code, name, info}                    -> {token, worker}
  POST /api/worker/hello                      {gpu, caps, models, info, measured}   -> {protocol, worker}
  POST /api/worker/claim                      {caps, free_mb, wait}                 -> {task | null}   (long poll, <= 20 s)
  GET  /api/worker/tasks/<id>/inputs/<name>                                         -> file
  POST /api/worker/tasks/<id>/progress        {progress, text}                      -> {cancel}
  PUT  /api/worker/tasks/<id>/outputs/<name>  (raw body)                            -> {ok, size}
  POST /api/worker/tasks/<id>/finish          {ok, error, retryable, result, seconds}
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from django.http import FileResponse, Http404, JsonResponse
from django.urls import path
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from instai.gpu.compute import task_dir

from . import workers
from .models import RemoteTask, WorkerNode

MAX_UPLOAD = 4 * 1024 ** 3


def _client(request) -> str:
    return request.META.get("REMOTE_ADDR", "?")


def _json(request) -> dict:
    try:
        d = json.loads(request.body.decode("utf-8") or "{}") if request.body else {}
    except (ValueError, UnicodeDecodeError):
        return {}
    return d if isinstance(d, dict) else {}


def _error(code: str, message: str, status: int):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def _auth(request):
    """(worker, None) or (None, error response)."""
    client = _client(request)
    if workers.too_many_failures(client):
        return None, _error("too_many_attempts", "Too many failed attempts; wait a few minutes.", 429)
    header = request.headers.get("Authorization", "")
    w = workers.authenticate(header[7:].strip()) if header.startswith("Worker ") else None
    if w is None:
        workers.note_failure(client)
        return None, _error("unauthorized", "The worker token is missing, wrong, or this worker was disabled.", 401)
    return w, None


@csrf_exempt
def pair(request):
    if request.method != "POST":
        return _error("method_not_allowed", "POST only", 405)
    client = _client(request)
    if workers.too_many_failures(client):
        return _error("too_many_attempts", "Too many failed attempts; wait a few minutes.", 429)
    d = _json(request)
    try:
        w, token = workers.pair(str(d.get("code") or ""), str(d.get("name") or ""), d.get("info") if isinstance(d.get("info"), dict) else {}, client)
    except workers.PairingError as e:
        workers.note_failure(client)
        return _error(e.code, str(e), 403)
    return JsonResponse({"token": token, "worker": {"id": w.pk, "name": w.name}, "protocol": workers.PROTOCOL})


@csrf_exempt
def hello(request):
    w, err = _auth(request)
    if err:
        return err
    workers.hello(w, _json(request), _client(request))
    workers.reap_expired()
    return JsonResponse({"protocol": workers.PROTOCOL, "worker": {"id": w.pk, "name": w.name}, "time": time.time()})


@csrf_exempt
def claim(request):
    w, err = _auth(request)
    if err:
        return err
    d = _json(request)
    if d.get("caps") is not None or d.get("free_mb") is not None:
        WorkerNode.objects.filter(pk=w.pk).update(**({"vram_free_mb": int(d["free_mb"])} if d.get("free_mb") is not None else {}))
        if isinstance(d.get("caps"), list):
            WorkerNode.objects.filter(pk=w.pk).update(capabilities=[str(c)[:60] for c in d["caps"]][:80])
        w.refresh_from_db()
    deadline = time.time() + max(0.0, min(20.0, float(d.get("wait") or 0)))
    while True:
        workers.reap_expired()
        t = workers.claim(w)
        if t is not None:
            return JsonResponse({"task": workers.task_payload(t)})
        WorkerNode.objects.filter(pk=w.pk).update(last_seen=timezone.now())
        if time.time() >= deadline:
            return JsonResponse({"task": None})
        time.sleep(0.5)


def _task(request, pk: int):
    w, err = _auth(request)
    if err:
        return None, None, err
    t = RemoteTask.objects.filter(pk=pk, worker=w).first()
    if t is None:
        return None, None, _error("not_your_task", "This task is not assigned to this worker.", 403)
    return w, t, None


@csrf_exempt
def task_input(request, pk: int, name: str):
    w, t, err = _task(request, pk)
    if err:
        return err
    f = task_dir(t.pk) / "in" / Path(name).name
    if not f.is_file():
        raise Http404()
    resp = FileResponse(open(f, "rb"), content_type="application/octet-stream")
    resp["Content-Length"] = str(f.stat().st_size)
    return resp


@csrf_exempt
def task_progress(request, pk: int):
    w, t, err = _task(request, pk)
    if err:
        return err
    d = _json(request)
    cancel = workers.progress(t, w, float(d.get("progress") or 0), str(d.get("text") or ""))
    return JsonResponse({"cancel": bool(cancel)})


@csrf_exempt
def task_output(request, pk: int, name: str):
    w, t, err = _task(request, pk)
    if err:
        return err
    if request.method not in ("PUT", "POST"):
        return _error("method_not_allowed", "PUT only", 405)
    name = Path(name).name
    if not name or name.startswith("."):
        return _error("bad_name", "bad file name", 400)
    out = task_dir(t.pk) / "out"
    out.mkdir(parents=True, exist_ok=True)
    part = out / (name + ".part")
    size, h = 0, hashlib.sha256()
    with open(part, "wb") as fh:
        while True:
            chunk = request.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD:
                fh.close()
                part.unlink(missing_ok=True)
                return _error("too_large", "file too large", 413)
            h.update(chunk)
            fh.write(chunk)
    want = request.headers.get("X-Content-SHA256")
    if want and want.lower() != h.hexdigest():
        part.unlink(missing_ok=True)
        return _error("checksum_mismatch", "the upload was corrupted; send it again", 422)
    part.replace(out / name)
    return JsonResponse({"ok": True, "size": size, "sha256": h.hexdigest()})


@csrf_exempt
def task_finish(request, pk: int):
    w, t, err = _task(request, pk)
    if err:
        return err
    d = _json(request)
    ok = bool(d.get("ok"))
    if ok:   # a "successful" task whose promised files did not arrive is a failure, never silently half done
        got = {f.name for f in (task_dir(t.pk) / "out").glob("*") if f.is_file() and not f.name.endswith(".part")}
        missing = [n for n in (d.get("outputs") or []) if Path(n).name not in got]
        if missing:
            ok, d["error"], d["retryable"] = False, "outputs missing on the main PC: " + ", ".join(missing[:3]), True
    done = workers.finish(t, w, ok, str(d.get("error") or ""), bool(d.get("retryable", True)), d.get("result") if isinstance(d.get("result"), dict) else {},
                          float(d["seconds"]) if d.get("seconds") is not None else None)
    return JsonResponse({"ok": done})


urlpatterns = [
    path("worker/pair", pair),
    path("worker/hello", hello),
    path("worker/claim", claim),
    path("worker/tasks/<int:pk>/inputs/<str:name>", task_input),
    path("worker/tasks/<int:pk>/progress", task_progress),
    path("worker/tasks/<int:pk>/outputs/<str:name>", task_output),
    path("worker/tasks/<int:pk>/finish", task_finish),
]
