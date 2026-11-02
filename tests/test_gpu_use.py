"""Why the owner saw the GPU idle, and the fixes: how ComfyUI is launched (GPU python, never --cpu), the Ollama request (options, streaming with a
per-chunk idle timeout, retry policy, plain Persian errors, a model that fits the card), the GPU panel / deep check, and the model tests.
Everything runs against in-process fake Ollama / ComfyUI servers; the GPU is faked by patching nvidia-smi's reader."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests import fakes
from tests.conftest import finish
from tests.test_discovery import FLUX, owner_pc, scan_owner, touch  # noqa: F401  (the fake copy of the owner's PC)

pytestmark = pytest.mark.django_db(transaction=True)

GPU = {"name": "NVIDIA GeForce RTX 3060", "total_mb": 12288, "used_mb": 900, "free_mb": 11388, "driver": "560.94", "utilization": 3, "temperature": 41,
       "processes": []}
GB = 1024 ** 3
MSG = [{"role": "user", "content": "hi"}]


@pytest.fixture(autouse=True)
def _fresh_router_caps():
    from instai.gpu import compute

    compute._CAP_CACHE.update(at=0.0, value=None)
    yield
    compute._CAP_CACHE.update(at=0.0, value=None)


@pytest.fixture
def gpu(monkeypatch):
    from instai.core import hardware

    monkeypatch.setattr(hardware, "gpu_status", lambda: dict(GPU))
    return GPU


@pytest.fixture
def running_job():
    """A claimed job with its JobContext active in this thread, like a handler sees it."""
    from instai.jobs import queue
    from instai.jobs.context import JobContext, set_current

    queue.enqueue("models.test", {"id": "x"}, resource="cpu", title="t")
    job = queue.claim("t", ("cpu",))
    ctx = JobContext(job, "t")
    set_current(ctx)
    yield ctx
    set_current(None)


def live_of(ctx) -> dict:
    from instai.jobs.models import Job

    return Job.objects.get(pk=ctx.job.pk).live


# ------------------------------------------------------------------ ComfyUI launch: GPU python, never --cpu

def write_bat(portable: Path, name: str, line: str) -> Path:
    p = portable / name
    p.write_text(line + "\r\npause\r\n", encoding="utf-8")
    return p


def test_launch_command_has_no_cpu_flag_and_uses_the_bats_own_python(owner_pc, monkeypatch):
    from instai.core import discovery
    from instai.providers.comfy import launcher

    write_bat(owner_pc["portable"], "run_nvidia_gpu.bat", ".\\python_embeded\\python.exe -s ComfyUI\\main.py --windows-standalone-build --cpu --port 8199")
    d = scan_owner(owner_pc, monkeypatch)
    sel = discovery.selected_comfy(d)
    assert sel["cpu_flag"] is True and sel["port"] == 8199, "the scan reports the flag (the deep check says so) ..."
    argv, cwd = launcher.command(sel)
    assert "--cpu" not in argv, "... but it is never passed on"
    assert Path(argv[0]) == owner_pc["portable"] / "python_embeded" / "python.exe" and argv[1] == "-s" and Path(argv[2]) == owner_pc["comfy"] / "main.py"
    assert argv[3:] == ["--windows-standalone-build", "--port", "8199", "--disable-auto-launch"] and Path(cwd) == owner_pc["portable"]


def test_run_cpu_bat_is_not_used_with_its_cpu_flag(owner_pc, monkeypatch):
    from instai.core import discovery
    from instai.providers.comfy import launcher

    (owner_pc["portable"] / "run_nvidia_gpu.bat").unlink()
    write_bat(owner_pc["portable"], "run_cpu.bat", ".\\python_embeded\\python.exe -s ComfyUI\\main.py --cpu --windows-standalone-build")
    sel = discovery.selected_comfy(scan_owner(owner_pc, monkeypatch))
    assert sel["cpu_launcher"] is True
    argv, _ = launcher.command(sel)
    assert "--cpu" not in argv and "--windows-standalone-build" in argv and argv[-1] == "--disable-auto-launch"
    # without its python the .bat would have to run as it is (with --cpu): refuse instead of rendering on the processor
    sel_no_py = {**sel, "python": None}
    assert launcher.command(sel_no_py) is None
    r = launcher.start(sel_no_py)
    assert r["started"] is False and "run_cpu.bat" in r["error"]


def test_launcher_finds_the_python_the_bat_names(tmp_path):
    from instai.core.discovery import _launcher_info

    root = tmp_path / "portable"
    for rel in ("python_embeded/python.exe", "py311/python.exe"):
        touch(root / rel)
    cases = {".\\python_embeded\\python.exe -s ComfyUI\\main.py --a": "python_embeded/python.exe",
             "\"%~dp0py311\\python.exe\" -s ComfyUI\\main.py": "py311/python.exe",
             "call .\\python_embeded\\python.exe -s ComfyUI\\main.py": "python_embeded/python.exe"}
    for line, want in cases.items():
        bat = root / "run.bat"
        bat.write_text("@echo off\r\n" + line + "\r\npause\r\n", encoding="utf-8")
        info = _launcher_info(str(bat))
        assert info["python"] and Path(info["python"]) == (root / want).resolve() or Path(info["python"]) == root / want, line
    bat.write_text("python -s ComfyUI\\main.py\r\n", encoding="utf-8")
    assert _launcher_info(str(bat))["python"] is None, "a bare `python` is not InstAI's to guess"


def test_environment_given_to_comfyui_hides_nothing(monkeypatch):
    from instai.providers.comfy import launcher

    base = {"PATH": "x", "CUDA_VISIBLE_DEVICES": "-1", "PYTHONPATH": "C:\\instai\\.venv\\Lib", "PYTHONHOME": "C:\\py", "VIRTUAL_ENV": "C:\\instai\\.venv"}
    env = launcher.launch_env(base)
    assert "CUDA_VISIBLE_DEVICES" not in env and not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} & set(env)
    assert env["PATH"] == "x" and env["PYTHONIOENCODING"] == "utf-8"
    assert launcher.launch_env({"CUDA_VISIBLE_DEVICES": "0"})["CUDA_VISIBLE_DEVICES"] == "0", "a real device choice of the owner stays"
    assert "CUDA_VISIBLE_DEVICES" not in launcher.launch_env({"CUDA_VISIBLE_DEVICES": ""})


def test_start_runs_the_gpu_command_with_the_clean_environment(owner_pc, monkeypatch):
    from instai.core import discovery
    from instai.providers.comfy import launcher

    write_bat(owner_pc["portable"], "run_nvidia_gpu.bat", ".\\python_embeded\\python.exe -s ComfyUI\\main.py --cpu")
    sel = discovery.selected_comfy(scan_owner(owner_pc, monkeypatch))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    monkeypatch.setenv("PYTHONPATH", "C:\\somewhere")
    monkeypatch.setattr(launcher, "_up", lambda url: False)
    seen = {}

    class P:
        def poll(self):
            return None

    def fake_popen(argv, **kw):
        seen.update(argv=argv, **kw)
        return P()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    launcher.STATE.update(proc=None, started_at=0.0, cmd=None)
    r = launcher.start(sel)
    assert r["started"] and "--cpu" not in seen["argv"] and "--cpu" not in r["cmd"]
    assert "CUDA_VISIBLE_DEVICES" not in seen["env"] and "PYTHONPATH" not in seen["env"]
    launcher.STATE.update(proc=None, started_at=0.0, cmd=None)


def comfy_stats(device_type: str, torch="2.5.1+cu124", argv=()):
    name = "cuda:0 NVIDIA GeForce RTX 3060 : cudaMallocAsync" if device_type == "cuda" else "cpu"
    return {"system": {"comfyui_version": "0.3.60", "pytorch_version": torch, "argv": list(argv)},
            "devices": [{"name": name, "type": device_type, "vram_total": 12 * GB, "vram_free": 11 * GB}]}


def test_a_comfyui_on_the_cpu_stops_the_job_with_a_plain_message(monkeypatch, gpu):
    from instai.core import settings_store
    from instai.providers.base import ProviderError
    from instai.providers.comfy import launcher

    with fakes.comfy_server() as c:
        settings_store.set_setting("comfyui_url", c.url)
        c.stats = comfy_stats("cuda")
        assert launcher.ensure_running(timeout=2) == c.url, "on the GPU: fine"
        c.stats = comfy_stats("cpu", torch="2.5.1+cpu")
        with pytest.raises(ProviderError) as e:
            launcher.ensure_running(timeout=2)
        assert e.value.code == "comfy_on_cpu" and e.value.retryable is False
        assert "CPU" in e.value.fa and "update_comfyui_and_python_dependencies" in e.value.fa and "شما روشن کرده بودید" in e.value.fa
        assert e.value.user_text().splitlines()[0] == e.value.fa, "the Persian line comes first, the English technical text after it"
        c.stats = comfy_stats("cpu", torch="2.5.1+cu124", argv=["main.py", "--cpu"])
        with pytest.raises(ProviderError) as e:
            launcher.ensure_running(timeout=2)
        assert "--cpu" in e.value.fa
    settings_store.set_setting("comfyui_url", "")


def test_unknown_device_or_no_gpu_does_not_block_comfyui(monkeypatch):
    """No NVIDIA card on this PC (dev machine): a CPU ComfyUI is simply what there is. An old ComfyUI that names no device passes too."""
    from instai.core import hardware, settings_store
    from instai.providers.comfy import launcher

    monkeypatch.setattr(hardware, "gpu_status", lambda: None)
    with fakes.comfy_server() as c:
        settings_store.set_setting("comfyui_url", c.url)
        c.stats = comfy_stats("cpu", torch="2.5.1+cpu")
        assert launcher.ensure_running(timeout=2) == c.url
        c.stats = {"system": {}, "devices": []}
        monkeypatch.setattr(hardware, "gpu_status", lambda: dict(GPU))
        assert launcher.ensure_running(timeout=2) == c.url
    settings_store.set_setting("comfyui_url", "")


# ------------------------------------------------------------------ Ollama: options, streaming, timeouts, retry, messages

def test_ollama_options_are_explicit_and_overridable(monkeypatch):
    from instai.providers.ollama import OllamaProvider

    p = OllamaProvider("http://x")
    assert p.options(0.4, 100) == {"temperature": 0.4, "num_predict": 100, "num_ctx": 8192}, "no num_gpu: Ollama fits the layers to the VRAM itself"
    monkeypatch.setenv("INSTAI_OLLAMA_NUM_GPU", "999")
    monkeypatch.setenv("INSTAI_OLLAMA_NUM_CTX", "4096")
    q = OllamaProvider("http://x")
    assert q.options(0.1, 5) == {"temperature": 0.1, "num_predict": 5, "num_ctx": 4096, "num_gpu": 999}
    assert OllamaProvider("http://x", num_ctx=2048, num_gpu=0).options(0, 1)["num_gpu"] == 0


def test_ollama_streams_tokens_and_reports_model_device_to_the_queue(running_job, gpu):
    from instai.providers.ollama import OllamaProvider

    with fakes.ollama_server(chunk_delay=0.03, placement={"qwen3:8b": (5 * GB, 5 * GB)}) as srv:
        res = OllamaProvider(srv.url, "qwen3:8b").generate(MSG, max_tokens=100)
        assert res.text == "ok" and res.completion_tokens == 100 and res.tokens_per_second == 50.0
        live = live_of(running_job)
        assert live["model"] == "qwen3:8b" and live["device"] == "gpu" and live["gpu_pct"] == 100
        assert live["tokens"] == 100 and live["tps"] == 50.0 and live["phase"] == "parsing"
        assert res.raw["gpu_pct"] == 100 and res.raw["placement"] == "gpu" and res.raw["load_seconds"] == 1.5


def test_a_long_answer_survives_while_tokens_keep_coming():
    """The old single read timeout (600 s) killed long generations. Now only silence counts: 1.8 s of answer passes a 0.6 s idle limit."""
    from instai.providers.ollama import OllamaProvider

    with fakes.ollama_server(models=("qwen3:8b",), pieces=12, chunk_delay=0.2) as srv:
        res = OllamaProvider(srv.url, "qwen3:8b", idle_timeout=0.6, first_token_timeout=5).generate(MSG, schema={"type": "object", "properties": {"a": {"type": "string"}},
                                                                                                           "required": ["a"]})
        assert res.seconds > 1.5 and res.text.startswith("{") and res.completion_tokens == 100


def test_a_close_delimited_stream_works_too():
    from instai.providers.ollama import OllamaProvider

    with fakes.ollama_server(chunked=False, pieces=3) as srv:
        assert OllamaProvider(srv.url, "qwen3:8b").generate(MSG).text == "ok"


def test_idle_timeout_is_per_silence_and_the_error_says_what_happened():
    from instai.providers.base import ProviderError
    from instai.providers.ollama import OllamaProvider

    with fakes.ollama_server(pieces=8, stall_after=3, stall_seconds=4, chunk_delay=0.01) as srv:
        t0 = time.time()
        with pytest.raises(ProviderError) as e:
            OllamaProvider(srv.url, "qwen3:8b", idle_timeout=0.7, first_token_timeout=5).generate(MSG, schema={"type": "object", "properties": {"a": {"type": "string"}},
                                                                                                           "required": ["a"]})
        assert time.time() - t0 < 3, "gave up after the silence, not after the whole stall"
        assert e.value.code == "llm_stalled" and e.value.retryable is True and "ساکت" in e.value.fa


def test_first_token_timeout_blames_a_model_too_big_for_the_card(running_job, gpu):
    from instai.providers.base import ProviderError
    from instai.providers.ollama import OllamaProvider

    # qwq:32b: 20 GB, only 8 GB of it in VRAM -> mostly CPU; nothing comes for a long time
    with fakes.ollama_server(models=("qwq:32b",), loaded=("qwq:32b",), first_delay=3, placement={"qwq:32b": (20 * GB, 8 * GB)}) as srv:
        with pytest.raises(ProviderError) as e:
            OllamaProvider(srv.url, "qwq:32b").generate(MSG, timeout=1.2)
        err = e.value
        assert err.code == "llm_timeout" and err.retryable is False, "the same too-big model would only time out again"
        assert "qwq:32b" in err.fa and "۴۰٪" in err.fa and "qwen3:8b" in err.fa
        assert "only 40% on the GPU" in str(err)


def test_first_token_timeout_of_a_model_that_is_on_the_gpu_may_be_retried(gpu):
    from instai.providers.base import ProviderError
    from instai.providers.ollama import OllamaProvider

    with fakes.ollama_server(first_delay=3, placement={"qwen3:8b": (5 * GB, 5 * GB)}) as srv:
        with pytest.raises(ProviderError) as e:
            OllamaProvider(srv.url, "qwen3:8b").generate(MSG, timeout=0.8)
        assert e.value.code == "llm_timeout" and e.value.retryable is True


def test_connection_problems_are_retried_a_couple_of_times(monkeypatch):
    from instai.providers import ollama
    from instai.providers.base import ProviderError

    monkeypatch.setattr(ollama, "CONNECT_RETRY_DELAYS", (0.05, 0.05))
    with fakes.ollama_server(reset_first=2) as srv:
        assert ollama.OllamaProvider(srv.url, "qwen3:8b").generate(MSG).text == "ok"
        assert len([r for r in srv.requests if r["path"] == "/api/chat"]) == 3, "two dropped connections, then the answer"
    with fakes.ollama_server(reset_first=9) as srv:
        with pytest.raises(ProviderError) as e:
            ollama.OllamaProvider(srv.url, "qwen3:8b").generate(MSG)
        assert e.value.code == "ollama_down" and e.value.retryable is True and "Ollama" in e.value.fa and "روشن" in e.value.fa
        assert len([r for r in srv.requests if r["path"] == "/api/chat"]) == 3
    with pytest.raises(ProviderError) as e:
        ollama.OllamaProvider("http://127.0.0.1:9", "x").generate(MSG, timeout=2)
    assert e.value.retryable is True and e.value.code == "ollama_down"


def test_out_of_memory_is_final_and_tells_the_owner_to_pick_a_smaller_model():
    from instai.providers.base import ProviderError
    from instai.providers.ollama import OllamaProvider

    with fakes.ollama_server(error_status=500, error_message="model requires more system memory (22.5 GiB) than is available (9.1 GiB)") as srv:
        with pytest.raises(ProviderError) as e:
            OllamaProvider(srv.url, "qwen3:8b").generate(MSG)
        assert e.value.code == "llm_oom" and e.value.retryable is False and "qwen3:8b" in e.value.fa and "حافظه" in e.value.fa
        assert len([r for r in srv.requests if r["path"] == "/api/chat"]) == 1, "no pointless second try"


def test_a_generic_server_error_gets_one_retry_then_a_persian_error(monkeypatch):
    from instai.providers import ollama
    from instai.providers.base import ProviderError

    monkeypatch.setattr(ollama, "SERVER_RETRY_DELAY", 0.05)
    with fakes.ollama_server(error_status=500, error_message="llama runner process has terminated: exit status 2") as srv:
        with pytest.raises(ProviderError) as e:
            ollama.OllamaProvider(srv.url, "qwen3:8b").generate(MSG)
        assert e.value.code == "ollama_error" and e.value.retryable is True and "Ollama" in e.value.fa
        assert len([r for r in srv.requests if r["path"] == "/api/chat"]) == 2


def test_missing_model_error_is_persian_and_final():
    from instai.providers.base import ProviderError
    from instai.providers.ollama import OllamaProvider

    with fakes.ollama_server() as srv:
        with pytest.raises(ProviderError) as e:
            OllamaProvider(srv.url, "nope:1b").generate(MSG)
        assert e.value.retryable is False and "نصب نیست" in e.value.fa and "nope:1b" in e.value.fa


def test_cancel_works_while_the_model_is_still_loading(running_job):
    from instai.jobs import queue
    from instai.jobs.context import JobCancelled
    from instai.providers.ollama import OllamaProvider

    with fakes.ollama_server(first_delay=3) as srv:
        queue.request_cancel(running_job.job)
        t0 = time.time()
        with pytest.raises(JobCancelled):
            OllamaProvider(srv.url, "qwen3:8b").generate(MSG, timeout=30)
        assert time.time() - t0 < 2.5


def test_a_model_only_partly_on_the_gpu_is_warned_about_in_the_job_log(running_job, gpu):
    from instai.jobs.models import JobLog
    from instai.providers.ollama import OllamaProvider

    with fakes.ollama_server(models=("gemma3:27b",), loaded=("gemma3:27b",), placement={"gemma3:27b": (17 * GB, 7 * GB)}) as srv:
        res = OllamaProvider(srv.url, "gemma3:27b").generate(MSG)
        assert res.raw["placement"] == "mixed" and res.raw["gpu_pct"] == 41
        live = live_of(running_job)
        assert live["device"] == "mixed" and live["gpu_pct"] == 41
        warn = JobLog.objects.filter(job_id=running_job.job.pk, level="warning").first()
        assert warn and "هشدار" in warn.message and "۴۱٪" in warn.message and "CPU" in warn.message


def test_the_default_model_is_one_that_fits_the_graphics_card(gpu):
    from instai.providers import ollama_fit
    from instai.providers.ollama import OllamaProvider

    owner = [("qwq:32b", 19.9, "32.8B", "qwen2"), ("qwen3-vl:30b", 19.5, "31B", "qwen3vl"), ("bge-m3:latest", 1.2, "566M", "bert"), ("qwen3:8b", 5.2, "8.2B", "qwen3")]
    details = {n: {"size": int(s * 1e9), "parameter_size": p, "family": f} for n, s, p, f in owner}
    with fakes.ollama_server(models=[n for n, *_ in owner], loaded=(), details=details) as srv:
        p = OllamaProvider(srv.url)
        choice = p.default_choice()
        assert choice["model"] == "qwen3:8b" and choice["partial"] is False and "GPU" in choice["reason_fa"] + choice["reason_en"]
        assert p.effective_model() == "qwen3:8b"
        p.generate(MSG)
        assert [r["body"]["model"] for r in srv.requests if r["path"] == "/api/chat"] == ["qwen3:8b"], "not the first or the biggest model in the list"
    # only the two big models were pulled (the owner's NMarketing PC): the one with the most GPU share, flagged as partial, and a plain hint
    with fakes.ollama_server(models=["qwq:32b", "qwen3-vl:30b"], loaded=(), details={k: details[k] for k in ("qwq:32b", "qwen3-vl:30b")}) as srv:
        choice = OllamaProvider(srv.url).default_choice()
        assert choice["partial"] is True and "qwen3:8b" in choice["reason_fa"] and "CPU" in choice["reason_fa"]
        assert choice["model"] == "qwq:32b" or choice["model"] == "qwen3-vl:30b"
    assert ollama_fit.kind_of("bge-m3:latest", {"family": "bert"}) == "embedding" and ollama_fit.kind_of("qwen3-vl:30b") == "vision"
    assert ollama_fit.kind_of("translategemma:12b") == "special" and ollama_fit.is_reasoner("qwq:32b") and not ollama_fit.is_reasoner("qwen3:8b")


def test_fit_estimate_on_a_12_gb_card():
    from instai.providers.ollama_fit import fit_model, placement_of

    assert fit_model(5300, 8.2, 8192, 12288)["fit"] == "gpu" and fit_model(5300, 8.2, 8192, 12288)["comfortable"]
    big = fit_model(20400, 32.8, 8192, 12288)
    assert big["fit"] == "cpu" and 35 <= big["est_gpu_pct"] <= 50
    mid = fit_model(17400, 27, 8192, 12288)
    assert mid["fit"] == "partial" and mid["est_gpu_pct"] >= 50
    assert fit_model(5300, 8.2, 8192, None)["fit"] == "unknown"
    assert placement_of(20 * GB, 8 * GB) == {"gpu_pct": 40, "placement": "mixed"}
    assert placement_of(5 * GB, 5 * GB)["placement"] == "gpu" and placement_of(5 * GB, 0)["placement"] == "cpu"


def test_loading_a_model_unloads_the_other_ollama_models_first(monkeypatch):
    """A model another job (or another program) left in VRAM would push the new one onto the CPU."""
    from instai.gpu.arbiter import GPUArbiter
    from instai.core import settings_store

    with fakes.ollama_server(models=("qwen3:8b", "qwq:32b"), loaded=("qwq:32b", "qwen3:8b")) as srv:
        settings_store.set_setting("ollama_url", srv.url)
        GPUArbiter().unload_other_llms("qwen3:8b")
        assert {"model": "qwq:32b", "keep_alive": 0} in [r["body"] for r in srv.requests if r["path"] == "/api/generate"]
        assert srv.loaded == {"qwen3:8b"}
    settings_store.set_setting("ollama_url", "")


# ------------------------------------------------------------------ GPU panel and the deep check

def test_live_panel_says_a_model_is_mostly_on_the_cpu(gpu):
    from instai.core import gpu_diag, settings_store

    with fakes.ollama_server(models=("qwq:32b",), loaded=("qwq:32b",), placement={"qwq:32b": (20 * GB, 8 * GB)}) as o, fakes.comfy_server() as c:
        settings_store.set_setting("ollama_url", o.url)
        settings_store.set_setting("comfyui_url", c.url)
        c.stats = comfy_stats("cuda")
        r = gpu_diag.live()
        assert r["gpu"]["name"].startswith("NVIDIA") and r["ollama"]["up"] and r["ollama"]["loaded"][0]["gpu_pct"] == 40
        assert r["ollama"]["loaded"][0]["placement"] == "mixed" and "۴۰٪" in r["ollama"]["note_fa"]
        assert r["comfy"]["up"] and r["comfy"]["device"] == "cuda" and r["comfy"]["torch"] == "2.5.1+cu124"
        assert r["verdict"]["level"] == "warn" and "qwq:32b" in r["verdict"]["text_fa"] and "40%" in r["verdict"]["text_en"]
        c.stats = comfy_stats("cpu", torch="2.5.1+cpu")
        r = gpu_diag.live()
        assert r["verdict"]["level"] == "bad" and r["comfy"]["device"] == "cpu" and "update_comfyui" in r["comfy"]["note_fa"]
    settings_store.set_setting("ollama_url", "")
    settings_store.set_setting("comfyui_url", "")


def test_live_panel_without_a_gpu_or_services(monkeypatch):
    from instai.core import gpu_diag, hardware

    monkeypatch.setattr(hardware, "gpu_status", lambda: None)
    r = gpu_diag.live()
    assert r["gpu"] is None and r["verdict"]["level"] == "none" and r["ollama"]["up"] is False and r["comfy"]["up"] is False
    monkeypatch.setattr(hardware, "gpu_status", lambda: dict(GPU))
    assert gpu_diag.live()["verdict"]["level"] == "idle"


def test_ollama_log_scan():
    from instai.core.gpu_diag import scan_ollama_log

    ok = 'time=1 level=INFO source=types.go:130 msg="inference compute" id=GPU-abc library=cuda variant=v12 compute=8.6 name="NVIDIA GeForce RTX 3060" total="12.0 GiB"'
    none = 'time=2 level=INFO msg="no compatible GPUs were discovered"'
    cpu = 'time=2 level=INFO msg="inference compute" id=cpu library=cpu compute="" name=cpu'
    assert scan_ollama_log(ok)["library"] == "cuda" and not scan_ollama_log(ok)["none_found"]
    assert scan_ollama_log(none)["none_found"] is True
    assert scan_ollama_log(ok + "\n" + none)["none_found"] is True, "the LAST statement wins"
    assert scan_ollama_log(none + "\n" + ok)["none_found"] is False
    assert scan_ollama_log(cpu)["library"] == "cpu"
    assert scan_ollama_log("load_tensors: offloaded 12/65 layers to GPU")["offloaded"] == (12, 65)


def test_deep_check_names_the_causes(owner_pc, monkeypatch, gpu):
    from instai.core import gpu_diag, hardware, settings_store

    write_bat(owner_pc["portable"], "run_nvidia_gpu.bat", ".\\python_embeded\\python.exe -s ComfyUI\\main.py --cpu")
    settings_store.set_setting("model_paths", [str(owner_pc["desk"])])
    monkeypatch.setenv("OLLAMA_MODELS", str(owner_pc["ollama"]))
    from instai.core import model_status

    model_status.current(force=True)
    monkeypatch.setattr(gpu_diag, "win_env", lambda name: {"process": "-1" if name == "CUDA_VISIBLE_DEVICES" else None, "user": None, "machine": None})
    monkeypatch.setattr(gpu_diag, "probe_torch", lambda py, timeout=90.0: {"torch": "2.5.1+cpu", "cuda_build": None, "available": False})
    monkeypatch.setattr(gpu_diag, "ollama_log_path", lambda: None)
    r = gpu_diag.deep_check()
    by = {c["id"]: c for c in r["checks"]}
    assert by["nvidia"]["level"] == "ok" and "RTX 3060" in by["nvidia"]["detail_en"]
    assert by["env"]["level"] == "bad" and "CUDA_VISIBLE_DEVICES" in by["env"]["detail_en"]
    assert by["comfy_launcher"]["level"] == "warn" and "--cpu" in by["comfy_launcher"]["detail_en"] and "--cpu" not in by["comfy_launcher"]["detail_en"].split("InstAI runs:")[1]
    assert by["comfy_torch"]["level"] == "bad" and "CPU-only" in by["comfy_torch"]["title_en"] and "update_comfyui_and_python_dependencies" in by["comfy_torch"]["fix_en"]
    assert r["gpu_used"] == "no" and r["verdict"]["level"] == "bad" and "GPU" in r["verdict"]["text_fa"] and "CPU" in r["verdict"]["text_en"] + by["comfy_torch"]["title_en"]
    text = gpu_diag.ascii_report(r)
    assert text.isascii() and "VERDICT: GPU USED = NO" in text and "[ NO ]" in text and "FIX:" in text


def test_deep_check_all_good_and_the_ollama_model_that_does_not_fit(owner_pc, monkeypatch, gpu):
    from instai.core import gpu_diag, model_status, settings_store

    settings_store.set_setting("model_paths", [str(owner_pc["desk"])])
    model_status.current(force=True)
    monkeypatch.setattr(gpu_diag, "win_env", lambda name: {"process": None, "user": None, "machine": None})
    monkeypatch.setattr(gpu_diag, "probe_torch", lambda py, timeout=90.0: {"torch": "2.5.1+cu124", "cuda_build": "12.4", "available": True, "name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288})
    monkeypatch.setattr(gpu_diag, "ollama_log_path", lambda: None)
    details = {"qwq:32b": {"size": int(19.9e9), "parameter_size": "32.8B", "family": "qwen2"}}
    with fakes.ollama_server(models=("qwq:32b",), loaded=(), details=details) as o:
        settings_store.set_setting("ollama_url", o.url)
        settings_store.set_setting("llm_provider", "ollama")
        settings_store.set_setting("ollama_model", "qwq:32b")
        by = {c["id"]: c for c in gpu_diag.deep_check()["checks"]}
        assert by["comfy_torch"]["level"] == "ok" and by["env"]["level"] == "ok" and by["comfy_launcher"]["level"] == "ok"
        m = by["ollama_model"]
        assert m["level"] == "bad" and "qwq:32b" in m["title_en"] and "CPU" in m["detail_en"] and "qwen3:8b" in m["fix_en"]
    with fakes.ollama_server(models=("qwen3:8b",), loaded=(), placement={}) as o:
        settings_store.set_setting("ollama_url", o.url)
        settings_store.set_setting("ollama_model", "")
        r = gpu_diag.deep_check()
        assert {c["id"]: c for c in r["checks"]}["ollama_model"]["level"] == "ok" and r["gpu_used"] == "yes"
        trial = gpu_diag.probe_ollama()
        assert trial["level"] == "ok" and "100% on the GPU" in trial["detail_en"]
    for k in ("ollama_url", "ollama_model", "llm_provider", "model_paths"):
        settings_store.set_setting(k, "" if k != "model_paths" else [])


def test_torch_probe_reads_the_json_line(monkeypatch):
    from instai.core import gpu_diag

    class R:
        stdout = 'warning noise\nINSTAI_PROBE {"torch": "2.6.0+cu126", "cuda_build": "12.6", "available": true, "name": "RTX"}\n'
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert gpu_diag.probe_torch(sys.executable)["available"] is True
    R.stdout, R.stderr = "", "Traceback ...\nModuleNotFoundError: No module named 'torch'"
    assert "torch" in gpu_diag.probe_torch(sys.executable)["error"]
    real = gpu_diag.PROBE_CODE
    monkeypatch.undo()
    out = subprocess.run([sys.executable, "-c", real], capture_output=True, text=True).stdout
    assert out.startswith("INSTAI_PROBE ") and "error" in out, "the probe code itself runs (this venv has no torch: it reports the import error)"


def test_gpu_endpoints(api, gpu):
    r = api.get("/api/gpu/live").json()
    assert set(r) == {"at", "gpu", "ollama", "comfy", "verdict"} and r["gpu"]["name"].startswith("NVIDIA")
    assert set(r["ollama"]) == {"up", "loaded", "note_fa", "note_en"} and set(r["comfy"]) >= {"up", "device", "device_name", "torch", "cpu_flag", "vram_total_mb"}
    assert set(r["verdict"]) == {"level", "text_fa", "text_en"}
    c = api.post("/api/gpu/check", {}, format="json").json()
    assert set(c) >= {"took", "gpu_used", "verdict", "checks"} and c["checks"] and all({"id", "level", "title_fa", "title_en", "detail_fa", "fix_fa"} <= set(x) for x in c["checks"])


def test_models_payload_lists_each_ollama_model_with_its_fit(api, gpu):
    from instai.core import settings_store

    details = {"qwen3:8b": {"size": int(5.2e9), "parameter_size": "8.2B"}, "qwq:32b": {"size": int(19.9e9), "parameter_size": "32.8B", "family": "qwen2"},
               "bge-m3": {"size": int(1.2e9), "parameter_size": "566M", "family": "bert"}}
    with fakes.ollama_server(models=list(details), loaded=("qwq:32b",), details=details, placement={"qwq:32b": (20 * GB, 8 * GB)}) as o:
        settings_store.set_setting("ollama_url", o.url)
        r = api.get("/api/models/found?refresh=1").json()
        ollama = next(i for i in r["items"] if i["id"] == "ollama")
        rows = {m["name"]: m for m in ollama["models_detail"]}
        assert r["vram_total_mb"] == 12288 and ollama["testable"] is True
        assert rows["qwen3:8b"]["fit"] == "gpu" and rows["qwen3:8b"]["default"] is True and rows["qwen3:8b"]["kind"] == "text"
        assert rows["qwq:32b"]["fit"] == "cpu" and rows["qwq:32b"]["loaded"]["gpu_pct"] == 40 and rows["bge-m3"]["kind"] == "embedding"
        assert ollama["default_model"]["model"] == "qwen3:8b" and ollama["default_model"]["partial"] is False and ollama["default_model"]["reason_fa"]
        settings_store.set_setting("ollama_model", "qwq:32b")
        rows = {m["name"]: m for m in next(i for i in api.get("/api/models/found").json()["items"] if i["id"] == "ollama")["models_detail"]}
        assert rows["qwq:32b"]["chosen"] is True and rows["qwen3:8b"]["default"] is False
    settings_store.set_setting("ollama_url", "")
    settings_store.set_setting("ollama_model", "")


# ------------------------------------------------------------------ the model tests

def test_test_endpoint_validates_the_id_and_queues_a_job(api):
    assert api.post("/api/models/test", {"id": "nonsense"}, format="json").status_code == 400
    assert api.post("/api/models/test", {"id": "voice:nope"}, format="json").status_code == 400
    assert api.post("/api/models/test", {}, format="json").status_code == 400
    j = api.post("/api/models/test", {"id": "ollama:qwen3:8b"}, format="json")
    assert j.status_code == 202
    job = j.json()["job"]
    assert job["kind"] == "models.test" and job["resource"] == "gpu" and job["payload"] == {"id": "ollama:qwen3:8b"} and "qwen3:8b" in job["title"]
    assert api.post("/api/models/test", {"id": "piper"}, format="json").json()["job"]["resource"] == "cpu"
    assert api.post("/api/models/test", {"id": "comfy:" + FLUX}, format="json").json()["job"]["resource"] == "gpu"


def run_test(api, worker, tid: str) -> dict:
    j = finish(api, worker, api.post("/api/models/test", {"id": tid}, format="json"))
    return j["result"]


def test_ollama_test_passes_warns_or_fails_with_the_reason(api, worker, gpu):
    from instai.core import settings_store

    models = ("qwen3:8b", "gemma3:27b", "qwq:32b", "tiny:1b")
    place = {"qwen3:8b": (5 * GB, 5 * GB), "gemma3:27b": (17 * GB, 7 * GB), "qwq:32b": (20 * GB, int(0.3 * GB)), "tiny:1b": (1 * GB, 1 * GB)}
    with fakes.ollama_server(models=models, loaded=(), placement=place) as o:
        settings_store.set_setting("ollama_url", o.url)
        ok = run_test(api, worker, "ollama:qwen3:8b")
        assert ok["verdict"] == "pass" and ok["ok"] is True and ok["kind"] == "ollama" and ok["device"] == {"label": "GPU", "gpu_pct": 100}
        m = {x["key"]: x for x in ok["metrics"]}
        assert m["gpu_pct"]["value"] == 100 and m["tokens_per_second"] == {"key": "tokens_per_second", "value": 50.0, "unit": "tok/s"} and m["tokens"]["value"] == 100
        assert "seconds" in m and m["size_mb"]["value"] == 5120 and ok["sample"] == "ok"
        assert "۱۰۰٪" in ok["reason_fa"] and "درست کار کرد" in ok["reason_fa"] and "It works" in ok["reason_en"]
        mixed = run_test(api, worker, "ollama:gemma3:27b")
        assert mixed["verdict"] == "warn" and mixed["ok"] is True and mixed["device"]["label"] == "GPU + CPU" and mixed["device"]["gpu_pct"] == 41
        assert "۴۱٪" in mixed["reason_fa"] and "41%" in mixed["reason_en"]
        cpu = run_test(api, worker, "ollama:qwq:32b")
        assert cpu["verdict"] == "fail" and cpu["ok"] is False and cpu["device"]["label"] == "CPU" and "CPU" in cpu["reason_fa"] and "GPU" in cpu["reason_fa"] and "almost entirely on the CPU" in cpu["reason_en"]
        gone = run_test(api, worker, "ollama:nope:1b")
        assert gone["verdict"] == "fail" and "نصب نیست" in gone["reason_fa"]
    down = run_test(api, worker, "ollama:qwen3:8b")
    assert down["verdict"] == "fail" and "Ollama" in down["reason_fa"] and "روشن" in down["reason_fa"]
    settings_store.set_setting("ollama_url", "")


def test_ollama_test_without_a_gpu_is_not_called_a_pass(api, worker, monkeypatch):
    from instai.core import hardware, settings_store

    monkeypatch.setattr(hardware, "gpu_status", lambda: None)
    with fakes.ollama_server(loaded=()) as o:
        settings_store.set_setting("ollama_url", o.url)
        r = run_test(api, worker, "ollama:qwen3:8b")
        assert r["verdict"] == "warn" and "nvidia-smi" in r["reason_fa"] + r["reason_en"]
    settings_store.set_setting("ollama_url", "")


def test_comfy_test_makes_a_tiny_image_with_the_cheapest_ready_workflow(api, worker, owner_pc, monkeypatch, gpu):
    from instai.core import model_status, settings_store

    settings_store.set_setting("model_paths", [str(owner_pc["desk"])])
    with fakes.comfy_server() as c:
        settings_store.set_setting("comfyui_url", c.url)
        c.stats = comfy_stats("cuda")
        model_status.current(force=True)
        r = run_test(api, worker, "comfy:" + FLUX)
        assert r["verdict"] == "pass" and r["kind"] == "comfy" and r["device"]["label"] == "GPU", r
        assert r["media"]["type"] == "image" and r["media"]["url"].startswith("/media/model-tests/") and r["media"]["name"].endswith(".png")
        g = c.prompts[-1]
        sizes = {(n["inputs"].get("width"), n["inputs"].get("height")) for n in g.values() if n["class_type"] == "EmptyLatentImage"}
        steps = {n["inputs"].get("steps") for n in g.values() if n["class_type"] == "KSampler"}
        assert sizes == {(256, 256)} and steps == {4}, "a TINY generation"
        keys = {m["key"] for m in r["metrics"]}
        assert {"seconds", "workflow", "width", "height", "steps"} <= keys
        # a ComfyUI that works on the CPU is a failure, not a pass
        c.stats = comfy_stats("cpu", torch="2.5.1+cpu")
        bad = run_test(api, worker, "comfy:" + FLUX)
        assert bad["verdict"] == "fail" and "CPU" in bad["reason_fa"]
        # a file whose workflow cannot run (nodes / models missing): the reason names what is missing
        none = run_test(api, worker, "comfy:animagine-xl-4.0-opt.safetensors")
        assert none["verdict"] == "fail" and none["reason_fa"] and none["reason_en"]
    settings_store.set_setting("comfyui_url", "")
    settings_store.set_setting("model_paths", [])


def test_voice_test_makes_a_sample_to_play(api, worker, monkeypatch):
    def fake_synth(self, text, out_path, **kw):
        from instai.providers.tts import FakeTTS

        r = FakeTTS().synthesize(text, out_path, language="fa")
        r.engine = "piper"
        return r

    from instai.providers.tts import PiperTTS

    monkeypatch.setattr(PiperTTS, "available", lambda self: (True, "ok"))
    monkeypatch.setattr(PiperTTS, "synthesize", fake_synth)
    r = run_test(api, worker, "piper")
    assert r["verdict"] == "pass" and r["media"]["type"] == "audio" and r["media"]["url"].startswith("/media/model-tests/") and r["media"]["name"].endswith(".wav")
    assert {"seconds", "audio_seconds", "engine"} <= {m["key"] for m in r["metrics"]} and r["device"]["label"] == "CPU"
    assert api.get(r["media"]["url"]).status_code == 200, "the browser can play it"
    monkeypatch.setattr(PiperTTS, "available", lambda self: (False, "piper.exe not found"))
    bad = run_test(api, worker, "piper")
    assert bad["verdict"] == "fail" and "piper.exe not found" in bad["reason_fa"]


def test_voice_engine_test_goes_through_the_gpu_router_and_flags_a_cpu_engine(api, worker, monkeypatch):
    from instai.core import model_tests
    from instai.gpu import compute
    from instai.providers.audio import services

    def fake_run_task(ctx, kind, payload, inputs=None, **kw):
        import tempfile

        d = Path(tempfile.mkdtemp(prefix="rt-"))
        from instai.providers.tts import FakeTTS

        FakeTTS().synthesize("hello there general kenobi", d / "speech.wav", language="en")
        return compute.TaskResult([d / "speech.wav"], {"engine": "moss", "render_seconds": 2.5}, "local", 2.5, _dir=d)

    monkeypatch.setattr(compute, "run_task", fake_run_task)
    monkeypatch.setattr(services, "health", lambda key, timeout=1.5: {"status": "ready", "error": "", "device": "cpu"})
    r = run_test(api, worker, "voice:moss")
    assert r["verdict"] == "warn" and r["device"]["label"] == "CPU" and "CPU" in r["reason_fa"] and r["media"]["type"] == "audio"
    monkeypatch.setattr(services, "health", lambda key, timeout=1.5: {"status": "ready", "error": "", "device": "cuda"})
    assert run_test(api, worker, "voice:moss")["verdict"] == "pass"
    assert model_tests.resource_for({"id": "voice:moss"}) == "gpu" and model_tests.resource_for({"id": "piper"}) == "cpu"


def test_design_sheet_image_is_rendered_by_comfyui_through_the_gpu_router(api, worker, gpu):
    """studio.design_image called a function that no longer existed, so ComfyUI could never render a design sheet."""
    from instai.core import settings_store
    from instai.pages.models import ContentPage
    from instai.studio.models import DesignSheet
    from instai.story.models import Episode, Series

    page = ContentPage.objects.create(name="p")
    ep = Episode.objects.create(series=Series.objects.create(page=page, title="s"), number=1, title="e")
    sheet = DesignSheet.objects.create(page=page, episode=ep, kind="prop", subject="red scarf", prompt="a red scarf")
    with fakes.comfy_server() as c:
        c.stats = comfy_stats("cuda")
        settings_store.set_setting("comfyui_url", c.url)
        settings_store.set_setting("image_engine", "comfyui")
        try:
            j = finish(api, worker, api.post(f"/api/design-sheets/{sheet.pk}/image", {}, format="json"))
        finally:
            settings_store.set_setting("image_engine", "")
            settings_store.set_setting("comfyui_url", "")
        assert j["resource"] == "gpu"
        sheet.refresh_from_db()
        assert sheet.status == "done" and sheet.asset_id and sheet.asset.provenance["provider"] == "comfyui" and sheet.asset.provenance["device"] == "local"
        assert c.prompts and any(n["class_type"] == "SaveImage" for n in c.prompts[-1].values())