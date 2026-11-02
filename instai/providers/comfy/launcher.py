"""Start the owner's ComfyUI when a job needs it and nobody started it (as the NMarketing agent does with run_nvidia_gpu.bat).

The launcher comes from model discovery (instai.core.discovery): the portable run_nvidia_gpu.bat (started as the python + main.py line it
contains, plus --disable-auto-launch so no browser tab opens), or the ComfyUI Desktop app. Its output goes to data/logs/comfyui.log.
InstAI never stops a ComfyUI it did not start, and starting is idempotent (one start at a time, an already running ComfyUI is used).

Why the GPU is used (the owner saw Task Manager idle):
  * the interpreter is the one the .bat itself starts (python_embeded), never InstAI's own;
  * `--cpu` is never passed on (it would come from run_cpu.bat or an edited .bat), and `run_cpu.bat` is never the launcher of choice;
  * the environment ComfyUI gets has no variable that hides the GPU (CUDA_VISIBLE_DEVICES=-1, a leaked PYTHONHOME/PYTHONPATH of InstAI's venv);
  * after it answers, its /system_stats must say the device is a GPU; if a GPU exists but ComfyUI runs on the CPU the job stops with a
    plain Persian message (the cause: CPU-only torch, a --cpu flag) instead of rendering for hours on the processor.
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
CPU_ARGS = ("--cpu",)
# variables of THIS process that must not reach ComfyUI: they point its python at InstAI's venv or hide the GPU
DROP_ENV = ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "PYTHONSTARTUP", "PYTHONUSERBASE")


def _up(url: str) -> bool:
    try:
        requests.get(url.rstrip("/") + "/system_stats", timeout=2).raise_for_status()
        return True
    except requests.RequestException:
        return False


def selected() -> dict | None:
    from instai.core import discovery, model_status

    return discovery.selected_comfy(model_status.current())


def clean_args(args: list[str]) -> tuple[list[str], list[str]]:
    """(arguments without anything that turns the GPU off, what was removed)."""
    keep, removed = [], []
    for a in args:
        (removed if a in CPU_ARGS else keep).append(a)
    return keep, removed


def command(install: dict) -> tuple[list[str], str] | None:
    """(argv, working folder) to start this ComfyUI on the GPU without opening a browser, or None when it has no launcher."""
    launcher = install.get("launcher")
    if not launcher or not os.path.isfile(launcher):
        return None
    if launcher.lower().endswith(".exe"):                      # ComfyUI Desktop
        return [launcher], os.path.dirname(launcher)
    py, main = install.get("python"), install.get("main")
    if py and main and os.path.isfile(py) and os.path.isfile(main):
        args, _ = clean_args([a for a in (install.get("launch_args") or []) if a])
        if os.path.basename(launcher).lower() == "run_cpu.bat" and "--windows-standalone-build" not in args:
            args.append("--windows-standalone-build")          # what run_nvidia_gpu.bat passes; run_cpu.bat's only difference is --cpu
        if "--disable-auto-launch" not in args:
            args.append("--disable-auto-launch")
        return [py, "-s", main, *args], os.path.dirname(launcher)
    if os.path.basename(launcher).lower() == "run_cpu.bat":
        return None                                            # without its python we cannot run it without --cpu: say so instead of using the CPU
    return ["cmd.exe", "/c", launcher], os.path.dirname(launcher)


def launch_env(base: dict | None = None) -> dict:
    """The environment ComfyUI is started with: ours, minus what hides the GPU or redirects its python."""
    env = dict(os.environ if base is None else base)
    for k in DROP_ENV:
        env.pop(k, None)
    cvd = env.get("CUDA_VISIBLE_DEVICES")
    if cvd is not None and cvd.strip() in ("", "-1", "NoDevFiles"):
        env.pop("CUDA_VISIBLE_DEVICES", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


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
        why = ("only run_cpu.bat was found and its python could not be located" if os.path.basename(install.get("launcher") or "").lower() == "run_cpu.bat"
               else "ComfyUI was found but no run_nvidia_gpu.bat next to it")
        return {"started": False, "already_running": False, "cmd": None, "error": why}
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
            STATE["proc"] = subprocess.Popen(argv, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, creationflags=flags, env=launch_env())
        except OSError as e:
            return {"started": False, "already_running": False, "cmd": " ".join(argv), "error": f"{type(e).__name__}: {e}"}
        STATE.update(started_at=time.time(), cmd=argv)
    return {"started": True, "already_running": False, "cmd": " ".join(argv), "error": ""}


# ------------------------------------------------------------------ is it really on the GPU?

def device_info(url: str, timeout: float = 4.0) -> dict | None:
    """What the RUNNING ComfyUI says about itself (/system_stats): {type: cuda|cpu|..., name, torch, argv, vram_total_mb, vram_free_mb}. None when it does not answer."""
    try:
        j = requests.get(url.rstrip("/") + "/system_stats", timeout=timeout).json()
    except Exception:  # noqa: BLE001
        return None
    system = j.get("system") or {}
    devs = j.get("devices") or []
    d = devs[0] if devs else {}
    name = str(d.get("name") or "")
    typ = str(d.get("type") or "").lower() or ("cpu" if name.lower().startswith("cpu") else ("cuda" if name.lower().startswith("cuda") else ""))
    mb = lambda v: int(v / 1048576) if isinstance(v, (int, float)) and v else None  # noqa: E731
    return {"type": typ or None, "name": name or None, "torch": system.get("pytorch_version"), "argv": system.get("argv") or [],
            "cpu_flag": any(a == "--cpu" for a in (system.get("argv") or [])), "vram_total_mb": mb(d.get("vram_total")), "vram_free_mb": mb(d.get("vram_free")),
            "version": system.get("comfyui_version")}


def cpu_reason_fa(info: dict) -> str:
    torch = str(info.get("torch") or "")
    if info.get("cpu_flag"):
        return ("ComfyUI با گزینهٔ «--cpu» روشن شده است. آن را ببندید و بگذارید InstAI خودش روشنش کند "
                "(یا فایل run_nvidia_gpu.bat را اجرا کنید، نه run_cpu.bat).")
    if "+cpu" in torch:
        return (f"نسخهٔ PyTorch داخل ComfyUI فقط برای CPU است ({torch}) و به کارت گرافیک دسترسی ندارد. "
                "فایل update\\update_comfyui_and_python_dependencies.bat را در پوشهٔ ComfyUI_windows_portable اجرا کنید تا نسخهٔ مخصوص NVIDIA نصب شود.")
    return ("ComfyUI کارت گرافیک را پیدا نکرد (CUDA در دسترس نیست). درایور NVIDIA را به‌روز کنید، رایانه را ری‌استارت کنید و اگر ادامه داشت "
            "update\\update_comfyui_and_python_dependencies.bat را اجرا کنید.")


def require_gpu(url: str) -> dict | None:
    """Stop with a plain message when this PC has an NVIDIA GPU but the running ComfyUI works on the CPU. Returns the device info.
    Unknown devices (an old ComfyUI without /system_stats details, tests) pass: only a clear 'cpu' stops the job."""
    info = device_info(url)
    if not info or info["type"] != "cpu":
        return info
    try:
        from instai.core import hardware

        has_gpu = hardware.gpu_status() is not None
    except Exception:  # noqa: BLE001
        has_gpu = False
    if not has_gpu:
        return info
    ours = running_ours()
    if ours:
        try:
            STATE["proc"].kill()
        except OSError:
            pass
    fa = cpu_reason_fa(info)
    raise ProviderError(f"ComfyUI runs on the CPU although this PC has an NVIDIA GPU (torch {info.get('torch')}, argv {info.get('argv')}); "
                        "a render on the CPU would take hours", retryable=False, code="comfy_on_cpu",
                        fa="ComfyUI روی پردازنده (CPU) کار می‌کند، نه کارت گرافیک؛ پس ساخت تصویر و ویدئو ساعت‌ها طول می‌کشد و متوقف شد. " + fa +
                           (" (InstAI آن را بست.)" if ours else " (این ComfyUI را شما روشن کرده بودید؛ InstAI آن را نمی‌بندد.)"))


def ensure_running(progress=None, cancelled=None, timeout: float = 420) -> str:
    """Make sure ComfyUI answers; start it when it does not. Returns its URL. ProviderError (not_ready) says plainly what is missing,
    and `comfy_on_cpu` says the running ComfyUI does not use the graphics card."""
    from instai.core import hardware, runtime

    url = runtime.comfyui_url()
    if _up(url):
        require_gpu(url)
        return url
    r = start()
    if r["error"] and not r["already_running"]:
        raise ProviderError(f"ComfyUI is not running and InstAI cannot start it: {r['error']}. Start ComfyUI yourself or set its folder "
                            "on the Models page.", retryable=False, code="not_ready",
                            fa="ComfyUI روشن نیست و InstAI هم نتوانست آن را روشن کند. ComfyUI را خودتان با run_nvidia_gpu.bat روشن کنید "
                               "یا پوشهٔ آن را در صفحهٔ «مدل‌ها» بدهید.")
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _up(url):
            hardware._NODES_CACHE.update(at=0.0, info=None, url=None)       # the node list of the new ComfyUI
            require_gpu(url)
            return url
        if cancelled and cancelled():
            raise ProviderError("cancelled while ComfyUI was starting", retryable=True)
        p = STATE.get("proc")
        if p is not None and p.poll() is not None:
            raise ProviderError(f"ComfyUI stopped while starting (exit {p.returncode}); see data/logs/comfyui.log", retryable=True, code="not_ready",
                                fa="ComfyUI هنگام روشن شدن بسته شد. فایل data\\logs\\comfyui.log دلیلش را می‌گوید.")
        if progress:
            progress(f"starting ComfyUI ({int(time.time() - t0)} s)")
        time.sleep(2.0)
    raise ProviderError(f"ComfyUI did not answer within {int(timeout)} s after starting; see data/logs/comfyui.log", retryable=True, code="not_ready",
                        fa=f"ComfyUI تا {int(timeout)} ثانیه بعد از روشن شدن جواب نداد. فایل data\\logs\\comfyui.log را ببینید.")
