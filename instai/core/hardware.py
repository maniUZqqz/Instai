"""Hardware and service detection. Nothing is assumed: every probe degrades to "missing" with a Persian hint.

Each item: {id, label, status: ok|warn|missing|error, detail, data, hint}
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

from . import runtime

_CACHE: dict[str, Any] = {"at": 0.0, "value": None}
_NODES_CACHE: dict[str, Any] = {"at": 0.0, "info": None, "url": None}
CACHE_SECONDS = 8
NODES_CACHE_SECONDS = 90


def _item(id_: str, label: str, status: str, detail: str = "", data: dict | None = None, hint: str = "") -> dict:
    return {"id": id_, "label": label, "status": status, "detail": detail, "data": data or {}, "hint": hint}


def _run(cmd: list[str], timeout: float = 8) -> tuple[int, str]:
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=creationflags)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def _get_json(url: str, timeout: float = 2.0) -> Any:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- system

def ram_info() -> dict:
    """Total/available RAM in MB (detected, never assumed: the owner's PC reported both 16 and 24 GB)."""
    try:
        if sys.platform.startswith("win"):
            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEMSTAT()
            m.dwLength = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))  # type: ignore[attr-defined]
            return {"total_mb": int(m.ullTotalPhys / 1048576), "available_mb": int(m.ullAvailPhys / 1048576)}
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, _, v = line.partition(":")
            info[k] = int(v.split()[0])
        return {"total_mb": info["MemTotal"] // 1024, "available_mb": info.get("MemAvailable", 0) // 1024}
    except Exception:
        return {"total_mb": 0, "available_mb": 0}


def cpu_name() -> str:
    if sys.platform.startswith("win"):
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def disk_info(path: Path) -> dict:
    p = path
    while not p.exists() and p.parent != p:
        p = p.parent
    u = shutil.disk_usage(p)
    return {"path": str(path), "free_gb": round(u.free / 1e9, 1), "total_gb": round(u.total / 1e9, 1)}


def check_system() -> list[dict]:
    ram = ram_info()
    items = [
        _item("python", "Python", "ok", f"{platform.python_version()} ({platform.system()} {platform.release()})",
              {"version": platform.python_version()}),
        _item("cpu", "پردازنده", "ok", f"{cpu_name()} - {os.cpu_count()} هسته", {"name": cpu_name(), "cores": os.cpu_count()}),
    ]
    gb = ram["total_mb"] / 1024
    items.append(_item("ram", "حافظه RAM", "ok" if gb >= 15 else ("warn" if gb else "error"),
                       f"{gb:.1f} گیگابایت (آزاد: {ram['available_mb'] / 1024:.1f})" if gb else "قابل تشخیص نبود", ram,
                       "" if gb >= 15 else "برای مدل‌های بزرگ‌تر RAM بیشتری لازم است."))
    root = runtime.project_root()
    for id_, label, path in (("disk_project", "دیسکِ پروژه", root), ("disk_media", "دیسکِ رسانه‌ها", runtime.media_root()),
                             ("disk_models", "دیسکِ مدل‌ها", runtime.models_root())):
        d = disk_info(path)
        st = "ok" if d["free_gb"] >= 30 else ("warn" if d["free_gb"] >= 8 else "error")
        items.append(_item(id_, label, st, f"{d['free_gb']} از {d['total_gb']} گیگابایت آزاد", d,
                           "" if st == "ok" else "فضای آزاد کم است؛ مدل‌ها و ویدئوها فضای زیادی می‌خواهند."))
    return items


# ---------------------------------------------------------------- GPU

def _nvidia_smi() -> str | None:
    exe = shutil.which("nvidia-smi")
    if exe:
        return exe
    for p in (r"C:\Windows\System32\nvidia-smi.exe", r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
        if os.path.isfile(p):
            return p
    return None


def gpu_status() -> dict | None:
    """First NVIDIA GPU: name, memory (MB), driver, utilisation, other processes. None when there is no GPU/driver."""
    exe = _nvidia_smi()
    if not exe:
        return None
    rc, out = _run([exe, "--query-gpu=name,memory.total,memory.used,memory.free,driver_version,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits"])
    if rc != 0 or not out.strip():
        return None
    parts = [p.strip() for p in out.strip().splitlines()[0].split(",")]
    if len(parts) < 7:
        return None

    def num(s: str) -> int | None:
        try:
            return int(float(s))
        except ValueError:
            return None

    gpu = {"name": parts[0], "total_mb": num(parts[1]), "used_mb": num(parts[2]), "free_mb": num(parts[3]),
           "driver": parts[4], "utilization": num(parts[5]), "temperature": num(parts[6]), "processes": []}
    rc, out = _run([exe, "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"])
    if rc == 0:
        for line in out.strip().splitlines():
            f = [x.strip() for x in line.split(",")]
            if len(f) >= 3:
                gpu["processes"].append({"pid": num(f[0]), "name": f[1], "used_mb": num(f[2])})
    return gpu


def check_gpu() -> dict:
    g = gpu_status()
    if not g:
        return _item("gpu", "کارت گرافیک (NVIDIA)", "missing", "nvidia-smi پیدا نشد", {},
                     "روی این رایانه GPU یا درایور NVIDIA دیده نشد. تولید ویدئو فقط روی رایانه‌ی GPUدار ممکن است.")
    gb = (g["total_mb"] or 0) / 1024
    st = "ok" if gb >= 11 else "warn"
    return _item("gpu", "کارت گرافیک (NVIDIA)", st,
                 f"{g['name']} - {gb:.0f} گیگابایت (استفاده‌شده: {(g['used_mb'] or 0) / 1024:.1f}) - درایور {g['driver']}", g,
                 "" if st == "ok" else "VRAM کمتر از ۱۲ گیگابایت است؛ ویدئوی Wan احتمالاً کند یا ناموفق است.")


# ---------------------------------------------------------------- services

def check_ollama(url: str | None = None) -> dict:
    url = (url or runtime.ollama_url()).rstrip("/")
    try:
        tags = _get_json(url + "/api/tags", 3)
    except Exception:
        return _item("ollama", "Ollama (مدل زبانی)", "missing", f"{url} پاسخ نداد", {"url": url},
                     "Ollama را اجرا کنید (یا در تنظیمات از سرویس API استفاده کنید).")
    models = [{"name": m.get("name"), "size_gb": round((m.get("size") or 0) / 1e9, 1),
               "params": (m.get("details") or {}).get("parameter_size"),
               "quant": (m.get("details") or {}).get("quantization_level"),
               "family": (m.get("details") or {}).get("family")} for m in tags.get("models", [])]
    loaded: list[dict] = []
    try:
        loaded = [{"name": m.get("name"), "size_vram_gb": round((m.get("size_vram") or 0) / 1e9, 1)}
                  for m in _get_json(url + "/api/ps", 2).get("models", [])]
    except Exception:
        pass
    return _item("ollama", "Ollama (مدل زبانی)", "ok" if models else "warn", f"{len(models)} مدل نصب است",
                 {"url": url, "models": models, "loaded": loaded},
                 "" if models else "هیچ مدلی نصب نیست؛ مثلاً: ollama pull qwen3:8b")


def comfy_object_info(url: str | None = None, force: bool = False) -> dict | None:
    """The running ComfyUI's /object_info (cached; it is large)."""
    url = (url or runtime.comfyui_url()).rstrip("/")
    now = time.time()
    if not force and _NODES_CACHE["url"] == url and _NODES_CACHE["info"] is not None and now - _NODES_CACHE["at"] < NODES_CACHE_SECONDS:
        return _NODES_CACHE["info"]
    try:
        info = _get_json(url + "/object_info", 30)
    except Exception:
        return None
    _NODES_CACHE.update(at=now, info=info, url=url)
    return info


def comfy_nodes(url: str | None = None, force: bool = False) -> list[str] | None:
    info = comfy_object_info(url, force)
    return sorted(info.keys()) if info is not None else None


def check_comfyui(url: str | None = None) -> dict:
    url = (url or runtime.comfyui_url()).rstrip("/")
    info = comfy_object_info(url)
    if info is None:
        return _item("comfyui", "ComfyUI (تصویر و ویدئو)", "missing", f"{url} پاسخ نداد", {"url": url},
                     "ComfyUI را اجرا کنید تا ساخت تصویر و ویدئو فعال شود.")
    from instai.providers.comfy.workflows import workflow_availability

    wf = workflow_availability(info)
    stats: dict = {}
    try:
        stats = _get_json(url + "/system_stats", 3)
    except Exception:
        pass
    ready = sum(1 for w in wf if w["available"])
    return _item("comfyui", "ComfyUI (تصویر و ویدئو)", "ok" if ready else "warn",
                 f"{len(info)} نود؛ نسخه {stats.get('system', {}).get('comfyui_version', '?')}؛ {ready} از {len(wf)} گردشِ کار آماده",
                 {"url": url, "node_count": len(info), "workflows": wf, "system": stats.get("system", {})},
                 "" if ready else "مدل‌های لازم برای گردش‌های کار پیدا نشد؛ Download-Models.bat را اجرا کنید.")


def check_ffmpeg() -> dict:
    info = runtime.ffmpeg_info()
    if not info["ffmpeg"]:
        return _item("ffmpeg", "FFmpeg (مونتاژ ویدئو)", "missing", "پیدا نشد", {},
                     "START.bat آن را به‌صورت خودکار دانلود می‌کند (پوشه‌ی tools).")
    feats = info.get("features", {})
    missing = [k for k in ("libx264", "ass", "zoompan", "xfade") if not feats.get(k)]
    return _item("ffmpeg", "FFmpeg (مونتاژ ویدئو)", "warn" if missing else "ok",
                 f"{info['version']} - {info['ffmpeg']}", info,
                 ("این نسخه امکانات لازم را ندارد: " + ", ".join(missing)) if missing else "")


def check_tts() -> list[dict]:
    from instai.providers.tts import tts_status

    out = []
    for s in tts_status():
        out.append(_item(s["id"], s["label"], s["status"], s["detail"], s.get("data", {}), s.get("hint", "")))
    return out


def check_tools() -> list[dict]:
    items = []
    rh = runtime.find_tool("rhubarb")
    items.append(_item("rhubarb", "Rhubarb Lip Sync (فازِ ۳)", "ok" if rh else "missing", rh or "نصب نیست",
                       {"path": rh}, "" if rh else "برای هم‌گام‌سازی لب در فاز ۳ لازم می‌شود؛ فعلاً ضروری نیست."))
    bl = runtime.find_tool("blender")
    items.append(_item("blender", "Blender (ارائه‌دهنده‌ی سه‌بعدی، فازِ ۳)", "ok" if bl else "missing", bl or "نصب نیست",
                       {"path": bl}, "" if bl else "فعلاً ضروری نیست."))
    return items


# ---------------------------------------------------------------- all

def detect_all(refresh: bool = False) -> dict:
    now = time.time()
    if not refresh and _CACHE["value"] and now - _CACHE["at"] < CACHE_SECONDS:
        return _CACHE["value"]
    items: list[dict] = []
    items += check_system()
    items.append(check_gpu())
    items.append(check_ollama())
    items.append(check_comfyui())
    items.append(check_ffmpeg())
    items += check_tts()
    items += check_tools()
    summary = {s: sum(1 for i in items if i["status"] == s) for s in ("ok", "warn", "missing", "error")}
    value = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "items": items, "summary": summary,
             "machine": machine_fingerprint(items)}
    _CACHE.update(at=now, value=value)
    return value


def machine_fingerprint(items: list[dict] | None = None) -> dict:
    items = items or []
    by = {i["id"]: i for i in items}
    gpu = (by.get("gpu") or {}).get("data") or {}
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": cpu_name(),
        "ram_gb": round(ram_info()["total_mb"] / 1024, 1),
        "gpu": gpu.get("name"),
        "vram_gb": round((gpu.get("total_mb") or 0) / 1024, 1) if gpu else None,
        "driver": gpu.get("driver"),
    }
