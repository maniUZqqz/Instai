"""The GPU panel: live numbers and the deep 'why is the graphics card not used' check (core/gpu_diag.py)."""
from __future__ import annotations

import threading
import time

from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import gpu_diag

_CHECK_LOCK = threading.Lock()
_LAST: dict = {"at": 0.0, "value": None}
CHECK_CACHE_SECONDS = 15


@api_view(["GET"])
def gpu_live(request):
    return Response(gpu_diag.live())


@api_view(["POST"])
def gpu_check(request):
    """Runs ComfyUI's own python once (5-20 s). Two presses in a row share one run."""
    with _CHECK_LOCK:
        now = time.time()
        if _LAST["value"] is None or now - _LAST["at"] > CHECK_CACHE_SECONDS:
            _LAST.update(value=gpu_diag.deep_check(), at=time.time())
        return Response(_LAST["value"])


@api_view(["GET"])
def coexist_view(request):
    """The neighbours on this PC (NMarketing's agent), the ports, who holds the graphics card's memory, and the Ollama settings."""
    from instai.gpu import coexist

    return Response(coexist.report())


@api_view(["POST"])
def ollama_apply(request):
    """Save the recommended Ollama settings (flash attention, compressed KV cache) in the Windows user environment; with `restart: true` also
    restart Ollama when nothing is loaded (or `force: true`). The owner's models are not touched."""
    from instai.core import runtime
    from instai.gpu import ollama_tune

    saved = ollama_tune.apply_env()
    res = {"saved": saved["saved"], "error": saved["error"], "restart": None, "env": ollama_tune.env_status()}
    if request.data.get("restart") is True and saved["saved"]:
        res["restart"] = ollama_tune.restart_ollama(runtime.ollama_url(), force=request.data.get("force") is True)
    return Response(res)


urlpatterns = [
    path("gpu/live", gpu_live),
    path("gpu/check", gpu_check),
    path("gpu/coexist", coexist_view),
    path("gpu/ollama-settings", ollama_apply),
]
