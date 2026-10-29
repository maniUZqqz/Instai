"""Start the owner's ComfyUI when a job needs it and nobody started it (as the NMarketing agent does with run_nvidia_gpu.bat).

The launcher comes from model discovery (instai.core.discovery): the portable run_nvidia_gpu.bat (started as the python + main.py line it
contains, plus --disable-auto-launch so no browser tab opens), or the ComfyUI Desktop app. Its output goes to data/logs/comfyui.log.
InstAI never stops a ComfyUI it did not start, and starting is idempotent (one start at a time, an already running ComfyUI is used).
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path

import requests

from instai.providers.base import ProviderError

log = logging.getLogger("instai.comfy")
_LOCK = threading.Lock()
STATE: dict = {"proc": None, "started_at": 0.0, "cmd": None}


def _up(url: str) -> bool:
    try:
        requests.get(url.rstrip("/") + "/system_stats", timeout=2).raise_for_status()
        return True
    except requests.RequestException:
        return False


def selected() -> dict | None:
    from instai.core import discovery, model_status

    return discovery.selected_comfy(model_status.current())


def command(install: dict) -> tuple[list[str], str] | None:
    """(argv, working folder) to start this ComfyUI without opening a browser, or None when it has no launcher."""
    launcher = install.get("launcher")
    if not launcher or not os.path.isfile(launcher):
        return None
    if launcher.lower().endswith(".exe"):                      # ComfyUI Desktop
        return [launcher], os.path.dirname(launcher)
    py, main = install.get("python"), install.get("main")
    if py and main and os.path.isfile(py) and os.path.isfile(main):
        args = [a for a in (install.get("launch_args") or []) if a]
        if "--disable-auto-launch" not in args:
            args.append("--disable-auto-launch")
        return [py, "-s", main, *args], os.path.dirname(launcher)
    return ["cmd.exe", "/c", launcher], os.path.dirname(launcher)


def running_ours() -> bool:
    p = STATE.get("proc")
    return p is not None and p.poll() is None


def start(install: dict | None = None) -> dict:
    """Start ComfyUI in the background (no waiting). Returns {started, already_running, cmd, error}."""
    from instai.core import runtime

    url = runtime.comfyui_url()
    if _up(url):
        return {"started": False, "already_running": True, "cmd": None, "error": ""}
    install = install or selected()
    if not install:
        return {"started": False, "already_running": False, "cmd": None, "error": "no ComfyUI was found on this PC"}
    cmd = command(install)
    if not cmd:
        return {"started": False, "already_running": False, "cmd": None, "error": "ComfyUI was found but no run_nvidia_gpu.bat next to it"}
    with _LOCK:
        if running_ours() and time.time() - STATE["started_at"] < 600:
            return {"started": False, "already_running": False, "cmd": " ".join(STATE["cmd"] or []), "error": ""}
        argv, cwd = cmd
        logdir = Path(runtime.media_root()).parent / "logs"
        logdir.mkdir(parents=True, exist_ok=True)
        fh = open(logdir / "comfyui.log", "a", encoding="utf-8", errors="replace")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        log.info("starting ComfyUI: %s (in %s)", " ".join(argv), cwd)
        try:
            STATE["proc"] = subprocess.Popen(argv, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, creationflags=flags,
                                             env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        except OSError as e:
            return {"started": False, "already_running": False, "cmd": " ".join(argv), "error": f"{type(e).__name__}: {e}"}
        STATE.update(started_at=time.time(), cmd=argv)
    return {"started": True, "already_running": False, "cmd": " ".join(argv), "error": ""}


def ensure_running(progress=None, cancelled=None, timeout: float = 420) -> str:
    """Make sure ComfyUI answers; start it when it does not. Returns its URL. ProviderError (not_ready) says plainly what is missing."""
    from instai.core import hardware, runtime

    url = runtime.comfyui_url()
    if _up(url):
        return url
    r = start()
    if r["error"] and not r["already_running"]:
        raise ProviderError(f"ComfyUI is not running and InstAI cannot start it: {r['error']}. Start ComfyUI yourself or set its folder "
                            "on the Models page.", retryable=False, code="not_ready")
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _up(url):
            hardware._NODES_CACHE.update(at=0.0, info=None, url=None)       # the node list of the new ComfyUI
            return url
        if cancelled and cancelled():
            raise ProviderError("cancelled while ComfyUI was starting", retryable=True)
        p = STATE.get("proc")
        if p is not None and p.poll() is not None:
            raise ProviderError(f"ComfyUI stopped while starting (exit {p.returncode}); see data/logs/comfyui.log", retryable=True, code="not_ready")
        if progress:
            progress(f"starting ComfyUI ({int(time.time() - t0)} s)")
        time.sleep(2.0)
    raise ProviderError(f"ComfyUI did not answer within {int(timeout)} s after starting; see data/logs/comfyui.log", retryable=True, code="not_ready")
