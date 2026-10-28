"""GPU smoke test: runs ONLY on the real machine (Computer A) against the real Ollama / ComfyUI / voice engines.
Everything skips cleanly where a service is missing.  Run with Test-GPU.bat  (or:  pytest -m gpu -s).
This file is deliberately NOT part of the default run (conftest points the services at dead ports); it clears that override."""
from __future__ import annotations

import os
import time

import pytest

pytestmark = [pytest.mark.gpu, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def real_services(monkeypatch):
    """Undo the test-suite defaults: look for the owner's real services at their usual addresses (or INSTAI_* env overrides)."""
    from instai.core import settings_store

    for k, env, default in (("ollama_url", "INSTAI_REAL_OLLAMA_URL", "http://127.0.0.1:11434"),
                            ("comfyui_url", "INSTAI_REAL_COMFYUI_URL", "http://127.0.0.1:8188")):
        settings_store.set_setting(k, os.environ.get(env, default))
    settings_store.clear_cache()
    yield
    for k in ("ollama_url", "comfyui_url"):
        settings_store.set_setting(k, "")


def test_gpu_is_visible_and_reports_vram():
    from instai.core import hardware

    g = hardware.gpu_status()
    if not g:
        pytest.skip("no NVIDIA GPU / nvidia-smi on this machine")
    print(f"GPU: {g['name']} {g['total_mb']} MB, used {g['used_mb']} MB, driver {g['driver']}")
    assert g["total_mb"] and g["total_mb"] > 3000


def test_real_ollama_writes_a_valid_persian_script():
    from instai.agents import roles
    from instai.core import runtime
    from instai.providers.ollama import OllamaProvider

    p = OllamaProvider(runtime.ollama_url())
    h = p.health()
    if not h["ok"] or not h["models"]:
        pytest.skip("Ollama not running or has no models")
    from instai.core.benchmark import LLM_META

    t0 = time.time()
    res = roles.scriptwriter(dict(LLM_META), provider=p)
    print(f"model={res.model} attempts={res.attempts} seconds={time.time() - t0:.1f} tokens={res.completion_tokens}")
    assert len(res.data["blocks"]) >= 3
    p.unload()


def test_real_comfyui_makes_one_image():
    import tempfile
    from pathlib import Path

    from instai.core import hardware, runtime
    from instai.providers.comfy.client import ComfyClient
    from instai.providers.comfy.workflows import get_workflow, workflow_availability

    info = hardware.comfy_object_info(force=True)
    if info is None:
        pytest.skip("ComfyUI not running")
    av = {w["id"]: w for w in workflow_availability(info)}["flux_dev_fp8_t2i"]
    if not av["available"]:
        pytest.skip("FLUX workflow not ready: " + ", ".join(av["missing_nodes"] + av["missing_models"]))
    c = ComfyClient(runtime.comfyui_url())
    t0 = time.time()
    _, files = c.run(get_workflow("flux_dev_fp8_t2i").build({"prompt": "a blue cape traveller on a rooftop, anime style", "seed": 1}), timeout=1800)
    print(f"image in {time.time() - t0:.1f}s")
    out = c.download(files[0], Path(tempfile.mkdtemp()) / "smoke.png")
    assert out.stat().st_size > 10_000
    c.free()


def test_a_real_speech_engine_speaks_ten_seconds_of_persian():
    import tempfile
    from pathlib import Path

    from instai.core.benchmark import PERSIAN_LINE
    from instai.providers.base import ProviderError
    from instai.providers.tts import get_tts

    try:
        eng = get_tts("auto")
    except ProviderError:
        pytest.skip("neither MOSS-TTS nor Piper is ready")
    t0 = time.time()
    r = eng.synthesize(PERSIAN_LINE, Path(tempfile.mkdtemp()) / "line.wav", language="fa")
    print(f"{eng.id}: {r.seconds:.1f}s of audio in {time.time() - t0:.1f}s")
    assert 3 < r.seconds < 30


def test_arbiter_unloads_the_llm_before_comfyui_runs():
    from instai.core import runtime
    from instai.gpu.arbiter import ARBITER
    from instai.providers.ollama import OllamaProvider

    p = OllamaProvider(runtime.ollama_url())
    if not p.health()["ok"]:
        pytest.skip("Ollama not running")
    ARBITER.unload_others("comfy")
    assert p.loaded_models() == [], "Ollama models must be unloaded before ComfyUI takes the GPU"
