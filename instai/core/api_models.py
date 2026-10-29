"""The Models screen API: what model discovery found, rescan, manual folders, start ComfyUI, and the optional downloads that need the
owner's confirmation (a download request without `confirm: true` is refused)."""
from __future__ import annotations

import os

from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import model_status, settings_store
from .errors import DomainError

MAX_PATHS = 20


@api_view(["GET"])
def found(request):
    return Response(model_status.payload(force=request.query_params.get("refresh") in ("1", "true")))


@api_view(["POST"])
def rescan(request):
    from . import hardware

    hardware._CACHE.update(at=0.0, value=None)
    return Response(model_status.payload(force=True))


@api_view(["PUT"])
def manual_paths(request):
    """Folders to search first (for an unusual layout): a ComfyUI folder, NMarketing's folder, a drive... Saved in Settings."""
    raw = request.data.get("paths")
    if not isinstance(raw, list) or len(raw) > MAX_PATHS:
        raise DomainError("validation_error", "فهرست پوشه‌ها نامعتبر است.", http_status=400, message_en="The folder list is not valid.")
    paths = []
    bad = []
    for p in raw:
        p = str(p or "").strip().strip('"')
        if not p:
            continue
        if len(p) > 500 or not os.path.isdir(p):
            bad.append(p[:120])
        elif p not in paths:
            paths.append(p)
    if bad:
        raise DomainError("validation_error", "این پوشه‌ها پیدا نشدند: " + "، ".join(bad), http_status=400, details={"paths": bad},
                          message_en="These folders were not found: " + ", ".join(bad))
    settings_store.set_setting("model_paths", paths)
    if "comfyui_dir" in request.data:
        d = str(request.data.get("comfyui_dir") or "").strip().strip('"')
        if d and not os.path.isdir(d):
            raise DomainError("validation_error", "پوشهٔ ComfyUI پیدا نشد.", http_status=400, details={"comfyui_dir": [d[:120]]},
                              message_en="The ComfyUI folder was not found.")
        settings_store.set_setting("comfyui_dir", d)
    return Response(model_status.payload(force=True))


@api_view(["POST"])
def start_comfyui(request):
    from instai.providers.comfy import launcher

    r = launcher.start()
    if r["error"] and not r["already_running"]:
        raise DomainError("not_ready", "ComfyUI روشن نشد: " + r["error"], http_status=409, message_en="ComfyUI could not be started: " + r["error"])
    return Response(r)


@api_view(["POST"])
def download_offer(request, offer_id: str):
    """Download one optional model (plus the pieces it needs that are missing). Only with `confirm: true`: the UI shows the name, the
    size, the licence and why first, and sends the confirmation the owner gave."""
    from instai.jobs import queue
    from instai.jobs.api import job_response

    offer = next((o for o in model_status.offers() if o["id"] == offer_id), None)
    if offer is None:
        raise DomainError("not_found", http_status=404)
    if request.data.get("confirm") is not True:
        raise DomainError("validation_error", "دانلود فقط پس از تأیید شما شروع می‌شود.", http_status=400, details={"confirm": ["required"]},
                          message_en="The download starts only after you confirm it.")
    if offer["complete"] and all(n["complete"] for n in offer["needs"]):
        raise DomainError("conflict", "این مدل از قبل روی این رایانه هست.", message_en="This model is already on this PC.")
    parts = [n["id"] for n in offer["needs"] if not n["complete"]] + [offer_id]
    job = queue.enqueue("downloads.run", {"packages": parts, "offer": offer_id, "confirmed_at": timezone.now().isoformat()},
                        title="دانلود: " + offer["name"], idempotency_key=f"offer:{offer_id}:{int(timezone.now().timestamp() // 60)}")
    return job_response(job)


urlpatterns = [
    path("models/found", found),
    path("models/rescan", rescan),
    path("models/paths", manual_paths),
    path("models/comfyui/start", start_comfyui),
    path("models/offers/<str:offer_id>/download", download_offer),
]
