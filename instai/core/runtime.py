"""Where things are on this machine: folders, service URLs and external tools (ffmpeg, ...).

Settings saved in the UI (AppSetting rows) override environment/.env values; see core.settings_store.
"""
from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
from pathlib import Path

from django.conf import settings


def project_root() -> Path:
    return Path(settings.BASE_DIR) if hasattr(settings, "BASE_DIR") else Path(__file__).resolve().parents[2]


def media_root() -> Path:
    return Path(settings.MEDIA_ROOT)


def models_root() -> Path:
    return Path(settings.MODELS_DIR)


def tools_root() -> Path:
    return Path(settings.TOOLS_DIR)


def _setting(key: str, env: str, default: str = "") -> str:
    try:
        from .settings_store import get_setting

        v = get_setting(key)
        if v not in (None, ""):
            return str(v)
    except Exception:
        pass
    return os.environ.get(env, default).strip()


def ollama_url() -> str:
    return _setting("ollama_url", "INSTAI_OLLAMA_URL", "http://127.0.0.1:11434")


def comfyui_url() -> str:
    """Settings / .env, else the port written in the found run_nvidia_gpu.bat (--port), else ComfyUI's default 8188."""
    v = _setting("comfyui_url", "INSTAI_COMFYUI_URL", "")
    if v:
        return v
    port = 8188
    try:
        from . import discovery

        sel = discovery.selected_comfy(discovery.peek())
        port = int((sel or {}).get("port") or 8188)
    except Exception:  # noqa: BLE001 - a lookup must never break a URL
        pass
    return f"http://127.0.0.1:{port}"


def moss_tts_url() -> str:
    return _setting("moss_tts_url", "INSTAI_MOSS_TTS_URL", "")


def pocket_url() -> str:
    return _setting("pocket_url", "INSTAI_POCKET_URL", "http://127.0.0.1:5620")


def moss_sfx_url() -> str:
    return _setting("moss_sfx_url", "INSTAI_MOSS_SFX_URL", "")


def acestep_url() -> str:
    return _setting("acestep_url", "INSTAI_ACESTEP_URL", "")


def explicit_comfyui_dir() -> str:
    """Only what the owner set (Settings / .env)."""
    return _setting("comfyui_dir", "COMFYUI_DIR", "")


def comfyui_dir() -> str:
    """The ComfyUI folder: Settings / .env, else the one model discovery found (see core/discovery.py)."""
    v = explicit_comfyui_dir()
    if v:
        return v
    try:
        from . import discovery, model_status

        return (discovery.selected_comfy(model_status.current()) or {}).get("root") or ""
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- external tools

def find_tool(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    env = os.environ.get(f"INSTAI_{name.upper()}_EXE")
    if env and os.path.isfile(env):
        return env
    for base in (tools_root() / name / "bin", tools_root() / name, tools_root()):
        p = base / exe
        if p.is_file():
            return str(p)
    nested = sorted((tools_root() / name).glob(f"*/{exe}")) if (tools_root() / name).is_dir() else []
    if nested:  # e.g. tools/piper/piper/piper.exe, tools/rhubarb/Rhubarb-Lip-Sync-x/rhubarb.exe
        return str(nested[0])
    if name == "piper":  # the one NMarketing's voice kit already has (model discovery)
        try:
            from . import model_status

            found = model_status.piper().get("exe")
            if found and os.path.isfile(found):
                return found
        except Exception:  # noqa: BLE001
            pass
    return shutil.which(name)


_FEATURE_CACHE: dict[str, dict] = {}


def ffmpeg_info() -> dict:
    """Locate ffmpeg/ffprobe and report the features InstAI needs (cached per path)."""
    ff = find_tool("ffmpeg")
    fp = find_tool("ffprobe")
    if not ff:
        return {"ffmpeg": None, "ffprobe": fp, "version": None, "features": {}}
    if ff not in _FEATURE_CACHE:
        feats: dict[str, bool] = {}
        version = None
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, text=True, timeout=10, creationflags=flags).stdout
            m = re.search(r"version\s+(\S+)", out)
            version = m.group(1) if m else None
            filt = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=10, creationflags=flags).stdout
            enc = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10, creationflags=flags).stdout
            feats = {"ass": bool(re.search(r"\bass\b", filt)), "zoompan": "zoompan" in filt, "xfade": "xfade" in filt,
                     "loudnorm": "loudnorm" in filt, "sidechaincompress": "sidechaincompress" in filt,
                     "libx264": "libx264" in enc, "aac": " aac " in enc}
        except (OSError, subprocess.SubprocessError):
            pass
        _FEATURE_CACHE[ff] = {"version": version, "features": feats}
    c = _FEATURE_CACHE[ff]
    return {"ffmpeg": ff, "ffprobe": fp, "version": c["version"], "features": c["features"]}


@functools.lru_cache(maxsize=1)
def windows_font_dir() -> str | None:
    d = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    return d if os.path.isdir(d) else None
