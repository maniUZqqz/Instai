"""GPU-first and living next to the NMarketing agent (0.8.0): Ollama keeps the owner's models completely on the graphics card (context / layers
chosen from the free VRAM, never forced when it would not fit), a model stays in VRAM only minutes, ComfyUI's models are released when InstAI has no
GPU work left, ComfyUI is not started twice when the other program is starting it, and a port clash never stops START.bat."""
from __future__ import annotations

import importlib
import json
import os
import socket
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from tests import fakes

pytestmark = pytest.mark.django_db(transaction=True)
ROOT = Path(__file__).resolve().parents[1]
MSG = [{"role": "user", "content": "hi"}]
GB = 1024 ** 3

QWEN8 = {"name": "qwen3:8b", "size_mb": 5200, "params_b": 8.2}
QWEN14 = {"name": "qwen3:14b", "size_mb": 9300, "params_b": 14.8}
QWQ32 = {"name": "qwq:32b", "size_mb": 19900, "params_b": 32.8}


# ------------------------------------------------------------------ the plan

def test_a_model_that_fits_gets_every_layer_and_the_default_context():
    from instai.gpu import ollama_tune as t

    p = t.plan(QWEN8, wanted_ctx=8192, vram_total_mb=12288, vram_free_mb=11300)
    assert p["num_gpu"] == 999 and p["num_ctx"] == 8192 and p["fit"] == "gpu" and p["est_gpu_pct"] == 100 and not p["note_en"]


def test_the_context_shrinks_before_the_model_leaves_the_gpu():
    from instai.gpu import ollama_tune as t

    p = t.plan(QWEN14, wanted_ctx=16384, vram_total_mb=12288, vram_free_mb=11800)
    assert p["fit"] == "gpu" and p["num_gpu"] == 999 and p["num_ctx"] == 8192, "16k does not fit with 14b; the default 8k does"
    assert "8192" in p["note_en"] and "16384" in p["note_en"] and "8192" in p["note_fa"]
    p = t.plan(QWEN14, wanted_ctx=24576, vram_total_mb=12288, vram_free_mb=11800, kv="q8_0")
    assert p["num_ctx"] == 16384 and p["fit"] == "gpu", "a compressed KV cache buys context (24k still does not fit, 16k does)"


def test_never_forced_when_it_would_not_fit_and_never_below_the_default_context():
    from instai.gpu import ollama_tune as t

    p = t.plan(QWQ32, wanted_ctx=8192, vram_total_mb=12288, vram_free_mb=11300)
    assert p["num_gpu"] is None and p["fit"] in ("partial", "cpu") and p["num_ctx"] == 8192
    busy = t.plan(QWEN8, wanted_ctx=8192, vram_total_mb=12288, vram_free_mb=3000)        # ComfyUI holds 8 GB right now
    assert busy["num_gpu"] is None, "the free VRAM decides, not the card's size"
    assert t.plan(QWEN8, wanted_ctx=8192, vram_total_mb=None)["num_gpu"] is None, "no GPU information: untouched"
    assert t.plan({"name": "x"}, wanted_ctx=8192, vram_total_mb=12288)["num_ctx"] == 8192


def test_the_owners_own_num_gpu_always_wins():
    from instai.gpu import ollama_tune as t

    assert t.plan(QWEN8, wanted_ctx=8192, vram_total_mb=12288, vram_free_mb=11300, forced_gpu=20)["num_gpu"] == 20
    assert t.plan(QWQ32, wanted_ctx=8192, vram_total_mb=12288, forced_gpu=0)["num_gpu"] == 0


# ------------------------------------------------------------------ the request Ollama really gets

@pytest.fixture
def gpu(monkeypatch):
    from instai.core import hardware
    from instai.gpu import ollama_tune

    state = {"name": "NVIDIA GeForce RTX 3060", "total_mb": 12288, "used_mb": 900, "free_mb": 11388}
    monkeypatch.setattr(hardware, "gpu_status", lambda: dict(state))
    ollama_tune._CACHE.clear()
    yield state
    ollama_tune._CACHE.clear()


def chat_options(o) -> dict:
    return next(r["body"]["options"] for r in o.requests if r["path"] == "/api/chat")


def test_the_chat_request_carries_the_gpu_plan_and_a_short_keep_alive(gpu, monkeypatch):
    from instai.providers.ollama import OllamaProvider

    monkeypatch.delenv("INSTAI_OLLAMA_KEEP_ALIVE", raising=False)
    details = {"qwen3:8b": {"size": int(5.2 * 1024 ** 3), "parameter_size": "8.2B"}}
    with fakes.ollama_server(models=("qwen3:8b",), loaded=(), details=details) as o:
        prov = OllamaProvider(o.url, model="qwen3:8b")
        prov.generate(MSG)
        opts = chat_options(o)
        assert opts["num_gpu"] == 999 and opts["num_ctx"] == 8192
        assert next(r["body"] for r in o.requests if r["path"] == "/api/chat")["keep_alive"] == "3m", "the card is shared: a model stays minutes, not hours"


def test_nothing_is_forced_when_the_model_does_not_fit_or_tuning_is_off(gpu, monkeypatch):
    from instai.gpu import ollama_tune
    from instai.providers.ollama import OllamaProvider

    details = {"qwq:32b": {"size": int(19.9 * 1024 ** 3), "parameter_size": "32.8B"}, "qwen3:8b": {"size": int(5.2 * 1024 ** 3), "parameter_size": "8.2B"}}
    with fakes.ollama_server(models=("qwq:32b", "qwen3:8b"), loaded=(), details=details) as o:
        OllamaProvider(o.url, model="qwq:32b").generate(MSG)
        assert "num_gpu" not in chat_options(o), "forcing layers onto a card that cannot hold them makes Ollama fail"
        o.requests.clear()
        monkeypatch.setenv("INSTAI_OLLAMA_AUTOTUNE", "0")
        OllamaProvider(o.url, model="qwen3:8b").generate(MSG)
        assert "num_gpu" not in chat_options(o) and chat_options(o)["num_ctx"] == 8192
        monkeypatch.delenv("INSTAI_OLLAMA_AUTOTUNE")
        ollama_tune._CACHE.clear()
        o.requests.clear()
        monkeypatch.setenv("INSTAI_OLLAMA_NUM_GPU", "12")
        OllamaProvider(o.url, model="qwen3:8b").generate(MSG)
        assert chat_options(o)["num_gpu"] == 12, "the owner's own setting beats the plan"


def test_a_job_shows_the_context_and_forced_gpu_in_its_live_state(gpu, monkeypatch):
    from instai.jobs import queue
    from instai.jobs.context import JobContext, set_current
    from instai.jobs.models import Job
    from instai.providers.ollama import OllamaProvider

    gpu["used_mb"] = 400
    details = {"qwen3:14b": {"size": int(9.0 * 1024 ** 3), "parameter_size": "14.8B"}}
    queue.enqueue("models.test", {"id": "x"}, resource="cpu", title="t")
    job = queue.claim("t", ("cpu",))
    ctx = JobContext(job, "t")
    set_current(ctx)
    try:
        with fakes.ollama_server(models=("qwen3:14b",), loaded=(), details=details) as o:
            OllamaProvider(o.url, model="qwen3:14b", num_ctx=16384).generate(MSG)
        ctx.flush_live()
        live = Job.objects.get(pk=job.pk).live
        assert live["num_ctx"] == 8192 and live["forced_gpu"] is True
        assert any("16384" in m for m in Job.objects.get(pk=job.pk).logs.values_list("message", flat=True)), "the reduced context is written in the job's log"
    finally:
        set_current(None)


# ------------------------------------------------------------------ the Ollama server's own settings

def test_env_status_reports_what_is_missing_and_apply_is_windows_only(monkeypatch):
    from instai.core import gpu_diag
    from instai.gpu import ollama_tune as t

    monkeypatch.setattr(gpu_diag, "win_env", lambda name: {"process": None, "user": {"OLLAMA_FLASH_ATTENTION": "1"}.get(name), "machine": None})
    st = t.env_status()
    by = {v["name"]: v for v in st["vars"]}
    assert by["OLLAMA_FLASH_ATTENTION"]["ok"] and not by["OLLAMA_KV_CACHE_TYPE"]["ok"] and st["ok"] is False and st["kv"] == "f16"
    monkeypatch.setattr(gpu_diag, "win_env", lambda name: {"process": None, "user": {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"}.get(name), "machine": None})
    assert t.env_status()["ok"] is True and t.kv_type_in_use() == "q8_0"
    monkeypatch.setattr(sys, "platform", "linux")
    assert t.apply_env() == {"saved": [], "error": "not Windows"}
    assert t.restart_ollama("http://127.0.0.1:9")["restarted"] is False


def test_the_settings_endpoints(api, monkeypatch):
    from instai.gpu import ollama_tune

    monkeypatch.setattr(ollama_tune, "apply_env", lambda: {"saved": ["OLLAMA_FLASH_ATTENTION", "OLLAMA_KV_CACHE_TYPE"], "error": ""})
    monkeypatch.setattr(ollama_tune, "restart_ollama", lambda url, force=False: {"restarted": False, "reason": "busy", "loaded": ["qwen3:8b"]})
    r = api.post("/api/gpu/ollama-settings", {"restart": True}, format="json")
    assert r.status_code == 200 and r.json()["saved"] == ["OLLAMA_FLASH_ATTENTION", "OLLAMA_KV_CACHE_TYPE"] and r.json()["restart"]["reason"] == "busy"
    assert api.post("/api/gpu/ollama-settings", {}, format="json").json()["restart"] is None, "no restart unless asked"


# ------------------------------------------------------------------ the neighbours

NM_PROCS = [{"pid": 4242, "name": "python.exe", "cmd": r'"C:\Users\QQz\Desktop\N\Main V4\processing-server\python312\python.exe" agent.py --site https://x'},
            {"pid": 777, "name": "python.exe", "cmd": r'"C:\Users\QQz\Desktop\N\ComfyUI_windows_portable\python_embeded\python.exe" -s ComfyUI\main.py --windows-standalone-build'},
            {"pid": 9, "name": "ollama.exe", "cmd": "ollama.exe serve"}]


def test_the_nm_agent_and_a_booting_comfyui_are_recognised(monkeypatch):
    from instai.gpu import coexist

    monkeypatch.setenv("INSTAI_COEXIST_PROCS", json.dumps(NM_PROCS))
    assert coexist.nm_agent()["pid"] == 4242
    monkeypatch.setenv("INSTAI_COEXIST_PROCS", json.dumps(NM_PROCS[1:]))
    assert coexist.nm_agent() is None
    root = r"C:\Users\QQz\Desktop\N\ComfyUI_windows_portable\ComfyUI"
    assert coexist.comfy_booting(root, "http://127.0.0.1:9")["pid"] == 777, "main.py runs but the port does not answer: it is starting"
    assert coexist.comfy_booting("", "http://127.0.0.1:9") is None
    with fakes.comfy_server() as c:
        assert coexist.comfy_booting(root, c.url) is None, "it answers: it is up, not booting"
    monkeypatch.setenv("INSTAI_COEXIST_PROCS", "[]")
    assert coexist.comfy_booting(root, "http://127.0.0.1:9") is None


def test_comfyui_is_not_started_twice(monkeypatch, tmp_path):
    from instai.providers.comfy import launcher

    monkeypatch.setenv("INSTAI_COEXIST_PROCS", json.dumps(NM_PROCS))
    started = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: started.append(a) or (_ for _ in ()).throw(AssertionError("must not start")))
    install = {"root": r"C:\Users\QQz\Desktop\N\ComfyUI_windows_portable\ComfyUI", "launcher": str(tmp_path / "run_nvidia_gpu.bat")}
    r = launcher.start(install)
    assert r["already_running"] is True and not r["started"] and not started


def test_the_report_names_the_neighbours_ports_and_the_card(api, monkeypatch):
    from instai.core import hardware
    from instai.gpu import coexist

    monkeypatch.setenv("INSTAI_COEXIST_PROCS", json.dumps(NM_PROCS))
    monkeypatch.setattr(hardware, "gpu_status", lambda: {"name": "NVIDIA GeForce RTX 3060", "total_mb": 12288, "used_mb": 9000})
    monkeypatch.setattr(coexist, "_which", lambda n: None)
    r = api.get("/api/gpu/coexist").json()
    assert r["nm_agent"] is True and r["nm_agent_pid"] == 4242
    ports = {p["port"]: p for p in r["ports"]}
    assert {11434, 8188, 5640, 5641, 5642, 5620} <= set(ports) and ports[11434]["owner"] == "shared" and ports[5620]["owner"] == "nmarketing"
    assert any(p["owner"] == "instai" for p in r["ports"])
    assert r["vram"]["free_mb"] == 3288 and any(a["id"] == "nm_agent" for a in r["advice"])


def test_who_holds_the_vram_is_read_from_nvidia_smi(monkeypatch):
    import subprocess

    from instai.core import hardware
    from instai.gpu import coexist

    monkeypatch.setattr(hardware, "gpu_status", lambda: {"name": "RTX", "total_mb": 12288, "used_mb": 9000})
    monkeypatch.setattr(coexist, "_which", lambda n: "nvidia-smi")
    out = "4242, C:\\Python\\python.exe, 3000\n9, C:\\Ollama\\ollama.exe, 5200\n55, C:\\Apps\\game.exe, 800\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out, stderr=""))
    apps = {a["name"]: a for a in coexist.vram_report()["apps"]}
    assert apps["ollama.exe"]["who"] == "ollama" and apps["python.exe"]["who"] == "comfyui" and apps["game.exe"]["who"] == "other" and apps["game.exe"]["mb"] == 800


# ------------------------------------------------------------------ giving the card back

def test_comfyui_is_freed_only_after_a_quiet_period_and_only_once(monkeypatch):
    from instai.gpu import coexist
    from instai.jobs import queue
    from instai.jobs.models import Job

    with fakes.comfy_server() as c:
        from instai.core import settings_store

        settings_store.set_setting("comfyui_url", c.url)
        coexist.STATE["released_at"] = 0.0
        j = queue.enqueue("prod.keyframes", {}, resource="gpu", title="gpu job")
        assert coexist.release_idle()["reason"] == "queued", "InstAI still has GPU work waiting"
        Job.objects.filter(pk=j.pk).update(status=Job.RUNNING)
        assert coexist.release_idle()["reason"] == "running"
        Job.objects.filter(pk=j.pk).update(status=Job.SUCCEEDED, finished_at=timezone.now() - timedelta(seconds=10))
        assert coexist.release_idle()["reason"] == "recent" and c.freed == 0, "just finished: the next shot may need the models"
        Job.objects.filter(pk=j.pk).update(finished_at=timezone.now() - timedelta(seconds=coexist.IDLE_RELEASE_SECONDS + 5))
        assert coexist.release_idle()["freed"] is True and c.freed == 1, "quiet long enough: the other program gets the whole card"
        assert coexist.release_idle()["reason"] == "already" and c.freed == 1, "once per quiet period, not every half minute"
        settings_store.set_setting("comfyui_url", "")


def test_a_comfyui_that_is_down_is_left_alone(monkeypatch):
    from instai.gpu import coexist

    coexist.STATE["released_at"] = 0.0
    assert coexist.release_idle(idle_for=10 ** 6)["reason"] == "comfy_down"


# ------------------------------------------------------------------ START.bat never fails on a port clash

@pytest.fixture
def boot(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    here = os.getcwd()
    b = importlib.import_module("bootstrap")
    importlib.reload(b)
    os.chdir(here)
    monkeypatch.setattr(b, "ROOT", str(tmp_path))
    monkeypatch.delenv("INSTAI_PORT", raising=False)
    yield b
    sys.path.remove(str(ROOT / "scripts"))
    sys.modules.pop("bootstrap", None)


def hold(port: int):
    s = socket.socket()
    s.bind(("127.0.0.1", port))
    s.listen(1)
    return s


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_port_held_by_another_program_moves_instai_to_the_next_free_port(boot, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SECRET=mine", encoding="utf-8")
    monkeypatch.setattr(boot, "_is_instai", lambda port, host="127.0.0.1": False)
    real = boot._port_free
    monkeypatch.setattr(boot, "_port_free", lambda port, host="127.0.0.1": False if port == 8765 else real(port, host))     # "8765 is taken"
    got = boot.ensure_port()
    assert 8765 < got < 8810
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "SECRET=mine" in text and f"INSTAI_PORT={got}" in text, "saved once, the other settings are kept"
    assert boot.ensure_port() == got, "next start: the saved port is used"
    assert (tmp_path / ".env").read_text(encoding="utf-8").count("INSTAI_PORT") == 1


def test_the_owners_own_port_is_never_replaced_and_a_running_instai_is_fine(boot, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("INSTAI_PORT=8800\n", encoding="utf-8")
    monkeypatch.setattr(boot, "_port_free", lambda port, host="127.0.0.1": False)
    monkeypatch.setattr(boot, "_is_instai", lambda port, host="127.0.0.1": False)
    assert boot.ensure_port() == 8800 and (tmp_path / ".env").read_text(encoding="utf-8") == "INSTAI_PORT=8800\n", "a port the owner chose is only reported"
    monkeypatch.setattr(boot, "_is_instai", lambda port, host="127.0.0.1": True)
    assert boot.ensure_port() == 8800
