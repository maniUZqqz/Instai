"""Living next to the NMarketing node agent on the same PC (0.8.0): the same ports, ONE Ollama, ONE ComfyUI, one graphics card.

The rules (written down in docs/COEXISTENCE.md and enforced here):
* one Ollama (:11434) and one ComfyUI (:8188) per PC. InstAI uses whichever answers; it never starts a second one, never kills a program it did not
  start, and does not start ComfyUI while another program is still starting it (`comfy_booting`: a main.py process of that ComfyUI exists
  but the port does not answer yet);
* the same fixed ports as NMarketing for the shared helpers (voice servers 5640/5641/5642, pocket 5620): a server that already runs is used;
* InstAI's own port (default 8765) is taken over by `scripts/bootstrap.py` only when another program holds it (it picks the next free one);
* the card is shared by politeness: before a GPU job InstAI waits while another program holds VRAM (gpu/arbiter.py), a model it loaded stays in
  VRAM for minutes only (Ollama keep_alive 3m), and when InstAI has no GPU work left `release_idle()` frees ComfyUI's models and stops the voice servers it started so the other program
  gets the whole card; it reports which program holds what (`vram_report`, from nvidia-smi).
Everything is read-only except `release_idle` (ComfyUI /free; Ollama needs no help: its keep_alive is short)."""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time

log = logging.getLogger("instai.coexist")

#: port -> (what it is, who normally starts it)
KNOWN_PORTS = {
    11434: ("Ollama", "shared"),
    8188: ("ComfyUI", "shared"),
    5640: ("MOSS-TTS voice server", "shared"),
    5641: ("MOSS-SoundEffect server", "shared"),
    5642: ("ACE-Step music server", "shared"),
    5620: ("NMarketing voice gateway", "nmarketing"),
}
NM_MARKERS = ("processing-server", "processing\\agent.py", "processing/agent.py")
IDLE_RELEASE_SECONDS = int(os.environ.get("INSTAI_GPU_RELEASE_AFTER", "90"))
_PROC_CACHE: dict = {"at": 0.0, "rows": []}
_LOCK = threading.Lock()
STATE: dict = {"released_at": 0.0}


# ------------------------------------------------------------------ processes (Windows: PowerShell CIM; tests inject a list)

def processes(max_age: float = 5.0) -> list[dict]:
    """[{pid, name, cmd}] of the python / node / ollama processes of this PC (cached 5 s). Empty where it cannot be read."""
    injected = os.environ.get("INSTAI_COEXIST_PROCS")
    if injected:
        try:
            return json.loads(injected)
        except ValueError:
            return []
    now = time.time()
    if now - _PROC_CACHE["at"] < max_age:
        return _PROC_CACHE["rows"]
    rows: list[dict] = []
    if sys.platform.startswith("win"):
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw|node|ollama|ollama app)(\\.exe)?$' } | "
              "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True, timeout=12,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
            data = json.loads(out) if out else []
            for r in data if isinstance(data, list) else [data]:
                rows.append({"pid": r.get("ProcessId"), "name": r.get("Name") or "", "cmd": r.get("CommandLine") or ""})
        except (OSError, subprocess.SubprocessError, ValueError):
            rows = []
    _PROC_CACHE.update(at=now, rows=rows)
    return rows


def nm_agent() -> dict | None:
    """The NMarketing node agent on this PC (a python process running processing-server's agent.py), or None."""
    for r in processes(max_age=20.0):                  # polled by the page every 10 s: one PowerShell call per 20 s is enough
        cmd = (r.get("cmd") or "").lower().replace("/", "\\")
        if "agent.py" in cmd and any(m.replace("/", "\\") in cmd for m in NM_MARKERS):
            return r
    return None


def comfy_booting(comfy_root: str, url: str) -> dict | None:
    """A ComfyUI of this folder that is starting (its main.py process exists) while its port does not answer yet - started by another program.
    InstAI waits for it instead of starting a second copy. Returns the process row or None."""
    if not comfy_root:
        return None
    from instai.providers.comfy import launcher

    if launcher._up(url):
        return None
    root = comfy_root.lower().replace("/", "\\").rstrip("\\")
    for r in processes(max_age=2.0):
        cmd = (r.get("cmd") or "").lower().replace("/", "\\")
        if "main.py" in cmd and (root in cmd or "comfyui" in cmd):
            return r
    return None


# ------------------------------------------------------------------ ports

def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ports_report() -> list[dict]:
    """Every port InstAI and its neighbours use: {port, name, owner, open}. `owner` = shared | nmarketing | instai."""
    from django.conf import settings

    rows = [{"port": int(settings.PORT), "name": "InstAI", "owner": "instai", "open": port_open(int(settings.PORT))}]
    for port, (name, owner) in sorted(KNOWN_PORTS.items()):
        rows.append({"port": port, "name": name, "owner": owner, "open": port_open(port)})
    return rows


# ------------------------------------------------------------------ VRAM: who holds what

def vram_report() -> dict:
    """{total_mb, used_mb, free_mb, apps: [{pid, name, mb, who}]} from nvidia-smi; `who` tells InstAI's shared services (Ollama, ComfyUI) from others.
    Empty dict without a GPU."""
    from instai.core import hardware

    g = hardware.gpu_status()
    if not g:
        return {}
    apps = []
    exe = _which("nvidia-smi")
    if exe:
        try:
            out = subprocess.run([exe, "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"], capture_output=True, text=True,
                                 timeout=6, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            for line in out.splitlines():
                parts = [x.strip() for x in line.split(",")]
                if len(parts) >= 3 and parts[0].isdigit():
                    shown = re.split(r"[\\/]", parts[1])[-1]
                    name = shown.lower()
                    who = "ollama" if "ollama" in name else ("comfyui" if name.startswith("python") else "other")
                    apps.append({"pid": int(parts[0]), "name": shown, "mb": int(float(parts[2] or 0)) if re.match(r"^[\d.]+$", parts[2]) else None,
                                 "who": who})
        except (OSError, subprocess.SubprocessError):
            pass
    total, used = g.get("total_mb"), g.get("used_mb")
    return {"name": g.get("name"), "total_mb": total, "used_mb": used, "free_mb": (total - used) if total is not None and used is not None else None, "apps": apps}


def _which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


# ------------------------------------------------------------------ giving the card back

def release_idle(*, now: float | None = None, idle_for: float | None = None) -> dict:
    """When InstAI has been without GPU work for IDLE_RELEASE_SECONDS: free ComfyUI's models (POST /free) so another program (the NMarketing
    agent) gets the whole card. Ollama needs no help: InstAI asks it to keep a model only 3 minutes. Does nothing while a GPU job of InstAI runs or waits.
    `idle_for` is how long the GPU has been unused (None = measured from the job table). Returns {freed: bool, reason}."""
    from instai.jobs.models import Job

    now = now or time.time()
    if Job.objects.filter(resource="gpu", status__in=(Job.RUNNING,)).exists():
        return {"freed": False, "reason": "running"}
    if Job.objects.filter(resource="gpu", status=Job.QUEUED).exists():
        return {"freed": False, "reason": "queued"}
    if idle_for is None:
        last = Job.objects.filter(resource="gpu").exclude(finished_at=None).order_by("-finished_at").values_list("finished_at", flat=True).first()
        idle_for = (now - last.timestamp()) if last else 10 ** 9
    if idle_for < IDLE_RELEASE_SECONDS:
        return {"freed": False, "reason": "recent"}
    with _LOCK:
        if STATE["released_at"] and STATE["released_at"] > now - max(idle_for, 1):      # once per idle period, not every tick
            return {"freed": False, "reason": "already"}
        STATE["released_at"] = now
    voice = _release_voice(int(idle_for))
    try:
        from instai.core import runtime
        from instai.providers.comfy.client import ComfyClient

        c = ComfyClient(runtime.comfyui_url())
        if not c.is_up():
            return {"freed": voice, "reason": "comfy_down", "voice": voice}
        c.free()
        log.info("no GPU work for %d s: ComfyUI's models were released for other programs", int(idle_for))
        return {"freed": True, "reason": "", "voice": voice}
    except Exception as e:  # noqa: BLE001 - best effort
        log.debug("release_idle failed: %s", e)
        return {"freed": voice, "reason": "error", "voice": voice}


def _release_voice(idle_for: int) -> bool:
    """The speech / effects / music servers THIS worker started keep their models in VRAM until they are stopped (the idle reaper waits 15 minutes):
    the NMarketing agent cannot stop a server it did not start, so a quiet InstAI stops its own. Never a server another program runs."""
    try:
        from instai.providers.audio import services

        if not services.MANAGER.procs:
            return False
        services.unload_voice()
        log.info("no GPU work for %d s: the voice servers started by InstAI were stopped to free the card", idle_for)
        return True
    except Exception as e:  # noqa: BLE001 - best effort
        log.debug("release voice failed: %s", e)
        return False


# ------------------------------------------------------------------ the page's report

def report() -> dict:
    """Everything the 'Coexistence' card shows: the neighbours, the ports, the card, the Ollama settings, and plain-language advice."""
    from instai.core import runtime
    from instai.gpu import ollama_tune

    agent = nm_agent()
    ports = ports_report()
    vram = {}
    try:
        vram = vram_report()
    except Exception:  # noqa: BLE001
        pass
    env = ollama_tune.env_status()
    advice: list[dict] = []
    if agent:
        advice.append({"id": "nm_agent", "level": "info", "fa": "عامل پردازش NMarketing روی همین رایانه کار می‌کند؛ InstAI با آن یک Ollama و یک ComfyUI را شریک است و هیچ‌کدام را خاموش یا دوباره روشن نمی‌کند.",
                       "en": "The NMarketing processing agent runs on this PC; InstAI shares one Ollama and one ComfyUI with it and never stops or restarts either."})
    if not env["ok"] and env["windows"]:
        advice.append({"id": "ollama_env", "level": "tip", "fa": "برای ماندن کامل مدل روی GPU و جای بیشتر برای زمینه، Flash Attention و کش KV فشرده را در Ollama روشن کنید (دکمهٔ «اعمال تنظیمات Ollama»).",
                       "en": "To keep the model completely on the GPU with room for context, switch on Flash Attention and the compressed KV cache in Ollama (the 'Apply Ollama settings' button)."})
    foreign = [a for a in vram.get("apps", []) if a["who"] == "other"]
    if foreign:
        mb = sum(a["mb"] or 0 for a in foreign)
        advice.append({"id": "foreign_vram", "level": "info", "fa": f"برنامه‌ای غیر از Ollama و ComfyUI حدود {mb} مگابایت از حافظهٔ کارت گرافیک را گرفته؛ کارهای GPU منتظر آزاد شدن آن می‌مانند.",
                       "en": f"A program other than Ollama and ComfyUI holds about {mb} MB of VRAM; GPU jobs wait until it is free."})
    return {"nm_agent": bool(agent), "nm_agent_pid": (agent or {}).get("pid"), "ports": ports, "vram": vram, "ollama_env": env,
            "ollama_url": runtime.ollama_url(), "comfyui_url": runtime.comfyui_url(), "advice": advice, "release_after_seconds": IDLE_RELEASE_SECONDS}
