"""Local GPU audio servers (MOSS-TTS, MOSS-SoundEffect, ACE-Step) started and stopped on demand.

Same protocol as the NMarketing agent (Qasem processing-server/agent.py ServiceManager + audio/*_server.py): each engine is a small
HTTP server inside its own virtual environment (venvs/<name>), `GET /health` says loading|ready|error, `POST /run` does the work.
If the owner's NMarketing agent already serves one of them (same URL), InstAI just uses it; otherwise it starts its own copy and
the GPU arbiter stops it again when ComfyUI or an LLM needs the card. `INSTAI_VOICE_FAKE=1` starts the real server scripts with
`--fake` (a test tone instead of a model): used by the tests and for a first smoke check.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from instai.core import runtime

log = logging.getLogger("instai.voice")
SERVERS_DIR = Path(__file__).resolve().parents[2] / "voice_servers"

SERVICES: dict[str, dict] = {
    "moss": {"label": "MOSS-TTS + Persian LoRA", "script": "moss_tts_server.py", "port": 5640, "venv": "moss-tts", "package": "moss-tts",
             "url_fn": "moss_tts_url", "vram_mb": 9500, "licence": "Apache-2.0", "commercial": "yes",
             "files": ["models/moss-tts/MOSS-TTS-Realtime/model.safetensors", "models/moss-tts/persian-lora/adapter_model.safetensors",
                       "models/moss-tts/persian-lora/ref.wav", "vendor/MOSS-TTS/moss_tts_realtime/inferencer.py"]},
    "sfx": {"label": "MOSS-SoundEffect v2.0", "script": "moss_sfx_server.py", "port": 5641, "venv": "moss-sfx", "package": "moss-sfx",
            "url_fn": "moss_sfx_url", "vram_mb": 8000, "licence": "Apache-2.0", "commercial": "yes",
            "files": ["models/moss-sfx/MOSS-SoundEffect-v2.0/transformer/diffusion_pytorch_model.safetensors",
                      "vendor/MOSS-TTS/moss_soundeffect_v2/pipeline_moss_soundeffect.py"]},
    "music": {"label": "ACE-Step 1.5 (turbo)", "script": "acestep_server.py", "port": 5642, "venv": "acestep", "package": "acestep",
              "url_fn": "acestep_url", "vram_mb": 7000, "licence": "MIT", "commercial": "yes",
              "files": ["models/acestep/checkpoints/acestep-v15-turbo/model.safetensors", "vendor/ACE-Step-1.5/acestep/api_server.py"]},
}


def fake_mode() -> bool:
    return os.environ.get("INSTAI_VOICE_FAKE", "").strip() in ("1", "true", "yes")


def home() -> Path:
    return runtime.project_root()


def venv_python(key: str) -> Path:
    venv = home() / "venvs" / SERVICES[key]["venv"]
    return venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"


def service_url(key: str) -> str:
    """The URL set in Settings / .env, else the managed default on this PC."""
    configured = getattr(runtime, SERVICES[key]["url_fn"])()
    port = os.environ.get(f"INSTAI_VOICE_PORT_{key.upper()}") or SERVICES[key]["port"]
    return (configured or f"http://127.0.0.1:{port}").rstrip("/")


def missing(key: str) -> list[str]:
    spec = SERVICES[key]
    out = [f for f in spec["files"] if not (home() / Path(*f.split("/"))).is_file()]
    if not venv_python(key).is_file():
        out.append(f"venvs/{spec['venv']} (Python packages)")
    return out


def installed(key: str) -> bool:
    return fake_mode() or not missing(key)


def health(key: str, timeout: float = 1.5) -> dict:
    """{status: down|loading|ready|error, error, device}. Understands our /health and ACE-Step's {"data": {"status": ...}}."""
    try:
        j = requests.get(service_url(key) + "/health", timeout=timeout).json()
    except Exception:  # noqa: BLE001 - nothing listening
        return {"status": "down", "error": "", "device": ""}
    if isinstance(j.get("data"), dict):
        j = {**j, **j["data"]}
    st = str(j.get("status") or "")
    st = "ready" if st in ("ready", "ok") else ("error" if st == "error" else "loading")
    return {"status": st, "error": j.get("error") or "", "device": j.get("device") or ""}


def describe() -> list[dict]:
    out = []
    for key, spec in SERVICES.items():
        h = health(key, 0.6)
        miss = [] if fake_mode() else missing(key)
        out.append({"id": key, "label": spec["label"], "status": h["status"], "installed": not miss, "missing": miss[:3],
                    "licence": spec["licence"], "commercial": spec["commercial"], "package": spec["package"], "url": service_url(key),
                    "vram_mb": spec["vram_mb"], "managed": key in MANAGER.procs and MANAGER.procs[key].poll() is None})
    return out


class ServiceManager:
    def __init__(self):
        self.procs: dict[str, subprocess.Popen] = {}
        self.last_use: dict[str, float] = {}
        self._lock = threading.Lock()

    def running(self, key: str) -> bool:
        p = self.procs.get(key)
        return p is not None and p.poll() is None

    def command(self, key: str) -> list[str]:
        spec = SERVICES[key]
        port = int(service_url(key).rsplit(":", 1)[-1])
        base = [str(SERVERS_DIR / spec["script"]), "--port", str(port), "--home", str(home()), "--parent-pid", str(os.getpid())]
        if fake_mode():
            return [sys.executable, *base, "--fake"]
        py = venv_python(key)
        if not py.is_file():
            raise RuntimeError(f"{spec['label']} is not installed (missing {', '.join(missing(key)[:2])}); run Download-Models.bat --only {spec['package']}")
        return [str(py), *base]

    def start(self, key: str) -> None:
        with self._lock:
            if self.running(key) or health(key)["status"] != "down":
                return
            cmd = self.command(key)
            logdir = Path(runtime.media_root()).parent / "logs"
            logdir.mkdir(parents=True, exist_ok=True)
            fh = open(logdir / f"voice-{key}.log", "a", encoding="utf-8", errors="replace")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            log.info("starting %s: %s", key, " ".join(cmd))
            self.procs[key] = subprocess.Popen(cmd, cwd=str(home()), stdout=fh, stderr=subprocess.STDOUT, creationflags=flags,
                                               env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1"))

    def stop(self, key: str) -> None:
        p = self.procs.pop(key, None)
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()

    def stop_all(self, keep: str | None = None) -> None:
        """Free the GPU: stop every voice server WE started (never a server another program runs)."""
        for key in list(self.procs):
            if key != keep:
                self.stop(key)

    def ensure_ready(self, key: str, ctx=None, timeout: float = 1500) -> str:
        """Start the server if it is down and wait until /health says ready. Returns its URL. ProviderError says what is missing."""
        from instai.providers.base import ProviderError

        h = health(key)
        if h["status"] == "down":
            try:
                self.start(key)
            except RuntimeError as e:
                raise ProviderError(str(e), retryable=False, code="not_ready") from e
        end = time.time() + timeout
        while time.time() < end:
            h = health(key)
            if h["status"] == "ready":
                self.last_use[key] = time.time()
                return service_url(key)
            if h["status"] == "error":
                raise ProviderError(f"{SERVICES[key]['label']} could not load its model: {h['error']}", retryable=False, code="not_ready")
            if h["status"] == "down" and key in self.procs and not self.running(key):
                raise ProviderError(f"{SERVICES[key]['label']} stopped while starting (see data/logs/voice-{key}.log)", retryable=True)
            if ctx is not None:
                ctx.waiting(f"loading {SERVICES[key]['label']} ...")
                ctx.check()
            time.sleep(1.0 if fake_mode() else 3.0)
        raise ProviderError(f"{SERVICES[key]['label']} did not become ready in {int(timeout)} s", retryable=True)

    def reap_idle(self, idle_s: float = 900) -> None:
        for key in list(self.procs):
            if time.time() - self.last_use.get(key, 0) > idle_s:
                self.stop(key)


MANAGER = ServiceManager()


def unload_voice() -> None:
    """Arbiter hook: stop the voice servers this process started."""
    MANAGER.stop_all()
