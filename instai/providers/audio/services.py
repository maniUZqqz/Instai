"""Local GPU audio servers (MOSS-TTS, MOSS-SoundEffect, ACE-Step) started and stopped on demand.

Same protocol as the NMarketing agent (Qasem processing-server/agent.py ServiceManager + audio/*_server.py): each engine is a small
HTTP server inside its own virtual environment (venvs/<name>), `GET /health` says loading|ready|error, `POST /run` does the work.
If the owner's NMarketing agent already serves one of them (same URL), InstAI just uses it; otherwise it starts its own copy and
the GPU arbiter stops it again when ComfyUI or an LLM needs the card. `INSTAI_VOICE_FAKE=1` starts the real server scripts with
`--fake` (a test tone instead of a model): used by the tests and for a first smoke check.
The models, the engine code (vendor/) and the Python environment are taken from wherever model discovery found them (InstAI's own
folder or NMarketing's, which may be split into code and data folders): see `paths()` and core/discovery.py. They are only read.
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
             "url_fn": "moss_tts_url", "vram_mb": 9500, "licence": "Apache-2.0", "commercial": "yes"},
    "sfx": {"label": "MOSS-SoundEffect v2.0", "script": "moss_sfx_server.py", "port": 5641, "venv": "moss-sfx", "package": "moss-sfx",
            "url_fn": "moss_sfx_url", "vram_mb": 8000, "licence": "Apache-2.0", "commercial": "yes"},
    "music": {"label": "ACE-Step 1.5 (turbo)", "script": "acestep_server.py", "port": 5642, "venv": "acestep", "package": "acestep",
              "url_fn": "acestep_url", "vram_mb": 7000, "licence": "MIT", "commercial": "yes"},
}


def fake_mode() -> bool:
    return os.environ.get("INSTAI_VOICE_FAKE", "").strip() in ("1", "true", "yes")


def home() -> Path:
    return runtime.project_root()


def _own_python(key: str) -> Path:
    venv = home() / "venvs" / SERVICES[key]["venv"]
    return venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"


def paths(key: str) -> dict:
    """{models_dir, vendor_dir, python, source}: where this engine's parts are. Model discovery's choice (complete copy first, newest
    wins; InstAI's own folder is one of the candidates), else InstAI's own layout (where Download-Models.bat puts them)."""
    from instai.core import model_status

    try:
        v = model_status.voice(key)
    except Exception:  # noqa: BLE001 - discovery must never break the voice engines
        v = {}
    models = v.get("models_dir") or str(runtime.models_root())
    vendor = v.get("vendor_dir") or str(home() / "vendor")
    python = v.get("python") or str(_own_python(key))
    return {"models_dir": models, "vendor_dir": vendor, "python": python,
            "source": "discovered" if v.get("models_dir") and Path(models).resolve() != runtime.models_root().resolve() else "instai"}


def venv_python(key: str) -> Path:
    return Path(paths(key)["python"])


def service_url(key: str) -> str:
    """The URL set in Settings / .env, else the managed default on this PC."""
    configured = getattr(runtime, SERVICES[key]["url_fn"])()
    port = os.environ.get(f"INSTAI_VOICE_PORT_{key.upper()}") or SERVICES[key]["port"]
    return (configured or f"http://127.0.0.1:{port}").rstrip("/")


def missing(key: str) -> list[str]:
    """What is still missing for this engine (checked live in the folders `paths()` chose); [] = installed."""
    from instai.core.discovery import VOICE_PARTS, _venv_broken

    spec, p = VOICE_PARTS[key], paths(key)
    out = ["models/" + f for f in spec["models"] if not (Path(p["models_dir"]) / Path(*f.split("/"))).is_file()]
    out += ["vendor/" + f for f in spec["vendor"] if not (Path(p["vendor_dir"]) / Path(*f.split("/"))).is_file()]
    py = Path(p["python"])
    broken = _venv_broken(str(py)) if py.is_file() else ""
    if not py.is_file() or broken:
        out.append(f"venvs/{SERVICES[key]['venv']} (Python packages)" + (f" - {broken}" if broken else ""))
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
                    "vram_mb": spec["vram_mb"], "managed": key in MANAGER.procs and MANAGER.procs[key].poll() is None,
                    "models_dir": paths(key)["models_dir"]})
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
        p = paths(key)
        work = Path(runtime.media_root()).parent / "voice-work" / key
        base = [str(SERVERS_DIR / spec["script"]), "--port", str(port), "--home", str(home()), "--models-dir", p["models_dir"],
                "--vendor-dir", p["vendor_dir"], "--work-dir", str(work), "--parent-pid", str(os.getpid())]
        if fake_mode():
            return [sys.executable, *base, "--fake"]
        py = Path(p["python"])
        if not py.is_file():
            raise RuntimeError(f"{spec['label']} is not installed (missing {', '.join(missing(key)[:2])}); see the Models page or run "
                               f"Download-Models.bat --only {spec['package']}")
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
