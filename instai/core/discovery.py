"""Find what is already installed on this PC, without the owner configuring anything.

What is looked for (Windows first; the same code runs on Linux for the tests):
  * ComfyUI: every folder with main.py + comfy/ + custom_nodes/ (the portable one is ComfyUI_windows_portable\\ComfyUI), its launcher
    (run_nvidia_gpu.bat next to it, or the ComfyUI Desktop app), its own Python (python_embeded or a venv), its custom nodes and EVERY
    folder it loads models from: models\\<kind>\\..., extra_model_paths.yaml and ComfyUI Desktop's extra_models_config.yaml.
    A running ComfyUI (/object_info) adds the exact names it lists, sub-folders included.
  * NMarketing's voice engines (a separate product: its files are only read, never changed): <x>\\models\\moss-tts|moss-sfx|acestep,
    <x>\\venvs\\<engine>, <x>\\vendor\\MOSS-TTS|ACE-Step-1.5 and Piper under tools\\PersianAiKit\\Voice\\models\\piper. Each part is looked up
    on its own because code and data may live in different folders (NMarketing is moving its data to a stable folder); a complete copy
    beats an incomplete one and the newest copy wins.
  * Ollama: its API, else the model manifests on disk (OLLAMA_MODELS or ~/.ollama/models) and ollama.exe.

Where: manual folders (Settings), hints from the environment (COMFYUI_DIR, NM_HOME, NM_DATA_DIR ...), %USERPROFILE%\\NMarketing-data,
the Desktop (also the OneDrive one) four levels deep, Downloads / Documents, the user folder, the folders around InstAI and the roots of
FIXED drives. Network and removable drives are never scanned. A time and folder budget keeps a scan to a few seconds.

Standard library only: scripts/download_models.py uses it before the virtual environment exists. Results are cached in
data/discovery.json. Tests set INSTAI_SCAN_DEFAULTS=0 (nothing on the real disk is read) and pass their own folders.
"""
from __future__ import annotations

import json
import os
import string
import sys
import threading
import time
import urllib.request
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IS_WIN = sys.platform.startswith("win")
MODEL_EXT = (".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".bin", ".sft", ".onnx")
SCAN_SECONDS = 12.0
SCAN_MAX_DIRS = 60000
CACHE_FILE = "discovery.json"
FORMAT = 1

# folders that never hold an install worth finding (lower case); dot- and $-folders are skipped too
SKIP_DIRS = {
    "windows", "program files", "program files (x86)", "programdata", "system volume information", "recovery", "perflogs",
    "appdata", "application data", "local settings", "node_modules", "__pycache__", "site-packages", "dist-packages",
    "python_embeded", "python_embedded", "venvs", "venv", "vendor", "models", "custom_nodes", "output", "input", "temp", "tmp",
    "cache", "logs", "lib", "libs", "include", "scripts", "dlls", "tcl", "pip-cache", "downloads-cache", "my music", "my pictures",
    "my videos", "music", "pictures", "videos", "saved games", "searches", "contacts", "favorites", "links", "3d objects",
    "microsoft", "windowsapps", "steamapps", "msys64", "cygwin64", "anaconda3", "miniconda3", "nvidia", "amd", "intel", "users",
}

# NMarketing's voice engines: files relative to a models folder, the venv name, files relative to a vendor folder
# (same lists as Qasem processing-server/agent.py AUDIO_ENGINES; only read here).
VOICE_PARTS: dict[str, dict] = {
    "moss": {"models": ["moss-tts/MOSS-TTS-Realtime/model.safetensors", "moss-tts/MOSS-Audio-Tokenizer/model-00001-of-00002.safetensors",
                        "moss-tts/MOSS-Audio-Tokenizer/model-00002-of-00002.safetensors", "moss-tts/persian-lora/adapter_model.safetensors",
                        "moss-tts/persian-lora/fa_normalize.py", "moss-tts/persian-lora/ref.wav"],
             "venv": "moss-tts", "vendor": ["MOSS-TTS/moss_tts_realtime/inferencer.py"]},
    "sfx": {"models": ["moss-sfx/MOSS-SoundEffect-v2.0/transformer/diffusion_pytorch_model.safetensors",
                       "moss-sfx/MOSS-SoundEffect-v2.0/text_encoder/model-00001-of-00002.safetensors",
                       "moss-sfx/MOSS-SoundEffect-v2.0/text_encoder/model-00002-of-00002.safetensors",
                       "moss-sfx/MOSS-SoundEffect-v2.0/vae/vae_128d_48k.pth"],
            "venv": "moss-sfx", "vendor": ["MOSS-TTS/moss_soundeffect_v2/pipeline_moss_soundeffect.py"]},
    "music": {"models": ["acestep/checkpoints/acestep-v15-turbo/model.safetensors", "acestep/checkpoints/vae/diffusion_pytorch_model.safetensors",
                         "acestep/checkpoints/Qwen3-Embedding-0.6B/model.safetensors"],
              "venv": "acestep", "vendor": ["ACE-Step-1.5/acestep/api_server.py"]},
}
PIPER_DIRS = ("tools/PersianAiKit/Voice/models/piper", "PersianAiKit/Voice/models/piper", "Voice/models/piper", "models/piper", "piper")


def _j(*parts: str) -> str:
    return os.path.join(*[p.replace("/", os.sep) for p in parts])


def _isfile(p: str) -> bool:
    try:
        return os.path.isfile(p)
    except (OSError, ValueError):
        return False


def _isdir(p: str) -> bool:
    try:
        return os.path.isdir(p)
    except (OSError, ValueError):
        return False


def _mtime(p: str) -> float:
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def data_dir() -> str:
    return os.environ.get("INSTAI_DATA_DIR") or os.path.join(ROOT, "data")


# ------------------------------------------------------------------ where to look

def fixed_drives() -> list[str]:
    """Roots of local fixed disks only (C:\\, D:\\ ...). Network shares, removable and CD drives are never scanned."""
    if not IS_WIN:
        return []
    try:
        import ctypes

        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        mask = k32.GetLogicalDrives()
        out = []
        for i, letter in enumerate(string.ascii_uppercase):
            if mask & (1 << i):
                root = letter + ":\\"
                if k32.GetDriveTypeW(ctypes.c_wchar_p(root)) == 3:          # DRIVE_FIXED (4 = network, 2 = removable)
                    out.append(root)
        return out
    except Exception:  # noqa: BLE001
        return []


def _desktops(home: str) -> list[str]:
    out = [os.path.join(home, "Desktop")]
    for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(k):
            out.append(os.path.join(os.environ[k], "Desktop"))
    out.append(os.path.join(home, "OneDrive", "Desktop"))
    if IS_WIN:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
                out.insert(0, str(winreg.QueryValueEx(k, "Desktop")[0]))
        except OSError:
            pass
    return out


def defaults_enabled(env=None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("INSTAI_SCAN_DEFAULTS", "1")).strip().lower() not in ("0", "false", "no", "off")


def scan_roots(manual=(), env=None, extra=()) -> list[list[tuple[str, int]]]:
    """Groups of (folder, depth), most likely first; each group is searched completely before the next one starts, so a slow
    drive can never use up the time budget before the Desktop was searched. Manual folders and INSTAI_SCAN_ROOTS always count;
    the machine's usual places only when INSTAI_SCAN_DEFAULTS is not 0. `extra` = InstAI's own folders (checked, not walked)."""
    env = os.environ if env is None else env
    first: list[tuple[str, int]] = [(m, 4) for m in manual if m]
    first += [(r, 4) for r in str(env.get("INSTAI_SCAN_ROOTS", "")).split(os.pathsep) if r.strip()]
    first += [(ROOT, 0)] + [(x, 0) for x in extra if x]         # InstAI's own models/, venvs/, vendor/, tools/
    if not defaults_enabled(env):
        return [first]
    for var in ("COMFYUI_DIR", "NM_COMFY_DIR", "NM_HOME", "NM_DATA_DIR", "NM_DATA", "NMARKETING_DATA", "NMARKETING_HOME", "NMARKETING_DATA_DIR"):
        if env.get(var):
            first.append((env[var].strip().strip('"'), 3))
    if env.get("NM_COMFY_BAT"):
        first.append((os.path.dirname(env["NM_COMFY_BAT"].strip().strip('"')), 2))
    home = os.path.expanduser("~")
    for name in ("NMarketing-data", "NMarketing", "NMarketing Data", "nm-data"):
        first.append((os.path.join(home, name), 3))
    for base in (env.get("LOCALAPPDATA", ""), env.get("APPDATA", "")):
        if base:
            first.append((os.path.join(base, "NMarketing"), 3))
    up = os.path.dirname(ROOT)
    near = [(d, 4) for d in _desktops(home)] + [(up, 3), (os.path.dirname(up), 2)]
    user = [(os.path.join(home, n), 3) for n in ("Downloads", "Documents")] + [(home, 2)]
    drives = [(d, 3) for d in fixed_drives()]
    return [first, near, user, drives]


# ------------------------------------------------------------------ ComfyUI

def parse_extra_model_paths(path: str) -> list[tuple[str, str]]:
    """[(kind, folder)] from a ComfyUI extra_model_paths.yaml, read without a YAML library: top-level sections with `base_path`,
    `kind: folder` lines and `kind: |` blocks with one folder per line. Relative folders are relative to base_path; a relative
    base_path is relative to the yaml file (as ComfyUI does)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    sections: list[dict] = []
    cur: dict | None = None
    block: tuple[int, str] | None = None
    for raw in lines:
        if raw.lstrip().startswith("#") or not raw.strip():
            continue
        line = raw.split(" #", 1)[0].rstrip()
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if indent == 0:
            cur, block = {"base": None, "paths": []}, None
            sections.append(cur)
            continue
        if cur is None:
            continue
        if block is not None and indent > block[0]:
            cur["paths"].append((block[1], text.strip("'\"")))
            continue
        block = None
        key, sep, val = text.partition(":")
        if not sep:
            continue
        key, val = key.strip(), val.strip().strip("'\"")
        if key == "base_path":
            cur["base"] = val
        elif key in ("is_default", "download_model_base"):
            continue
        elif val in ("|", ">", "|-", ">-", "|+", ""):
            block = (indent, key)
        else:
            cur["paths"].append((key, val))
    here = os.path.dirname(os.path.abspath(path))
    out = []
    for sec in sections:
        base = os.path.expandvars(os.path.expanduser(sec["base"])) if sec["base"] else None
        if base and not os.path.isabs(base):
            base = os.path.join(here, base)
        for kind, p in sec["paths"]:
            p = os.path.expandvars(os.path.expanduser(p))
            full = p if os.path.isabs(p) else os.path.join(base or here, p)
            out.append((kind, os.path.normpath(full)))
    return out


def _launcher_info(bat: str) -> dict:
    """What run_nvidia_gpu.bat starts: the python + main.py + arguments (so InstAI can start it without opening a browser tab) and
    the port. Falls back to running the .bat itself."""
    info = {"bat": bat, "port": 8188, "args": []}
    try:
        text = open(bat, encoding="utf-8", errors="replace").read()
    except OSError:
        return info
    for line in text.splitlines():
        if "main.py" not in line or line.strip().lower().startswith(("rem", "::", "echo")):
            continue
        tail = line.split("main.py", 1)[1].split()
        info["args"] = [a.strip('"') for a in tail]
        if "--port" in tail:
            try:
                info["port"] = int(tail[tail.index("--port") + 1])
            except (IndexError, ValueError):
                pass
        break
    return info


def _comfy_python(root: str) -> str | None:
    exe = "python.exe" if IS_WIN else "python"
    sub = "Scripts" if IS_WIN else "bin"
    for c in (_j(os.path.dirname(root), "python_embeded", exe), _j(root, "python_embeded", exe), _j(root, ".venv", sub, exe),
              _j(root, "venv", sub, exe)):
        if _isfile(c):
            return c
    return None


def comfy_install(root: str, desktop_base: bool = False) -> dict:
    """Facts about one ComfyUI folder (the one with main.py, or ComfyUI Desktop's base folder)."""
    root = os.path.abspath(root)
    parent = os.path.dirname(root)
    launcher = None
    for name in ("run_nvidia_gpu.bat", "run_nvidia_gpu_fast_fp16_accumulation.bat", "run_nvidia_gpu_fast.bat", "run_cpu.bat"):
        for d in (parent, root):
            if _isfile(os.path.join(d, name)):
                launcher = os.path.join(d, name)
                break
        if launcher:
            break
    yamls = [os.path.join(root, "extra_model_paths.yaml")]
    if desktop_base and os.environ.get("APPDATA"):
        yamls.append(os.path.join(os.environ["APPDATA"], "ComfyUI", "extra_models_config.yaml"))
    model_roots: list[tuple[str, str]] = []
    models = os.path.join(root, "models")
    if _isdir(models):
        try:
            for e in sorted(os.scandir(models), key=lambda e: e.name.lower()):
                if e.is_dir():
                    model_roots.append((e.name, e.path))
        except OSError:
            pass
    used_yaml = []
    for y in yamls:
        extra = parse_extra_model_paths(y)
        if extra:
            used_yaml.append(y)
        model_roots += extra
    nodes = []
    try:
        nodes = sorted(e.name for e in os.scandir(os.path.join(root, "custom_nodes")) if e.is_dir() and not e.name.startswith((".", "__")))
    except OSError:
        pass
    li = _launcher_info(launcher) if launcher and launcher.lower().endswith(".bat") else {"bat": launcher, "port": 8188, "args": []}
    return {"root": root, "portable": parent if launcher and os.path.dirname(launcher) == parent else None, "launcher": launcher,
            "launch_args": li["args"], "port": li["port"], "python": _comfy_python(root), "main": os.path.join(root, "main.py"),
            "desktop": desktop_base, "custom_nodes": nodes, "extra_yaml": used_yaml,
            "model_roots": [{"kind": k, "path": p, "exists": _isdir(p)} for k, p in model_roots], "mtime": _mtime(os.path.join(root, "main.py"))}


def index_models(model_roots: list[dict], limit: int = 20000) -> dict[str, dict]:
    """lower-case file name -> {name, path, size, kind, listed}. `listed` is the name ComfyUI shows in its loaders (relative to the
    kind folder, sub-folders included)."""
    out: dict[str, dict] = {}
    seen_dirs: set[str] = set()
    n = 0
    for r in model_roots:
        base = r["path"]
        if not _isdir(base):
            continue
        for d, dirs, files in os.walk(base, followlinks=True):
            real = _norm(os.path.realpath(d))
            if real in seen_dirs:
                dirs[:] = []
                continue
            seen_dirs.add(real)
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in files:
                low = f.lower()
                if not low.endswith(MODEL_EXT):
                    continue
                p = os.path.join(d, f)
                try:
                    size = os.path.getsize(p)
                except OSError:
                    continue
                if size <= 0:
                    continue
                n += 1
                out.setdefault(low, {"name": f, "path": p, "size": size, "kind": r["kind"], "listed": os.path.relpath(p, base)})
                if n >= limit:
                    return out
    return out


def _http_json(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": "InstAI-discovery"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def comfy_api_models(url: str, timeout: float = 20.0) -> dict | None:
    """{lower file name: the exact name ComfyUI lists} from a running ComfyUI's /object_info; None when nothing answers."""
    try:
        info = _http_json(url.rstrip("/") + "/object_info", timeout)
    except Exception:  # noqa: BLE001 - not running
        return None
    names: dict[str, str] = {}

    def take(v):
        if isinstance(v, str) and v.lower().endswith(MODEL_EXT):
            names.setdefault(v.replace("\\", "/").rsplit("/", 1)[-1].lower(), v)

    for node in (info or {}).values():
        req = ((node or {}).get("input") or {})
        for group in (req.get("required") or {}, req.get("optional") or {}):
            for spec in group.values():
                if isinstance(spec, list) and spec:
                    first = spec[0]
                    if isinstance(first, list):
                        for v in first:
                            take(v)
                    elif first == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
                        for v in spec[1].get("options") or []:
                            take(v)
    return {"nodes": len(info or {}), "names": names, "node_names": sorted((info or {}).keys())}


# ------------------------------------------------------------------ voice (NMarketing) and Piper

def _venv_python(venvs: str, name: str) -> str:
    return _j(venvs, name, "Scripts", "python.exe") if IS_WIN else _j(venvs, name, "bin", "python")


def _venv_broken(py: str) -> str:
    """'' when the venv's base Python still exists, else why not (venvs are not relocatable)."""
    cfg = os.path.join(os.path.dirname(os.path.dirname(py)), "pyvenv.cfg")
    try:
        for line in open(cfg, encoding="utf-8", errors="replace"):
            k, _, v = line.partition("=")
            if k.strip().lower() == "home" and v.strip() and not _isdir(v.strip()):
                return "base Python missing: " + v.strip()
    except OSError:
        pass
    return ""


class _Found:
    def __init__(self):
        self.comfy: dict[str, dict] = {}
        self.voice: dict[str, dict[str, list]] = {k: {"models": [], "venv": [], "vendor": []} for k in VOICE_PARTS}
        self.piper_exe: list[str] = []
        self.piper_dirs: list[str] = []
        self.homes: set[str] = set()

    def visit(self, path: str, names: set[str]) -> bool:
        """Check one folder for the markers. Returns True when the folder is an install (no need to look inside it)."""
        if "main.py" in names and "comfy" in names and ("custom_nodes" in names or "models" in names):
            key = _norm(path)
            if key not in self.comfy:
                self.comfy[key] = comfy_install(path)
            return True
        for key, spec in VOICE_PARTS.items():
            first = spec["models"][0].split("/")[0]
            for m in ([path] if first in names else []) + ([os.path.join(path, "models")] if "models" in names else []):
                if _isfile(_j(m, spec["models"][0])):
                    self.voice[key]["models"].append(m)
                    self.homes.add(os.path.abspath(path))
            vroot = os.path.join(path, "venvs") if "venvs" in names else (path if spec["venv"] in names else None)
            if vroot and _isfile(_venv_python(vroot, spec["venv"])):
                self.voice[key]["venv"].append(_venv_python(vroot, spec["venv"]))
                self.homes.add(os.path.abspath(path))
            vfirst = spec["vendor"][0].split("/")[0].lower()
            for vd in ([os.path.join(path, "vendor")] if "vendor" in names else []) + ([path] if vfirst in names else []):
                if _isfile(_j(vd, spec["vendor"][0])):
                    self.voice[key]["vendor"].append(vd)
        for rel in PIPER_DIRS:
            if rel.split("/")[0].lower() not in names:
                continue
            p = _j(path, rel)
            if not _isdir(p):
                continue
            for exe in (_j(p, "piper", "piper.exe"), _j(p, "piper.exe"), _j(p, "piper", "piper"), _j(p, "piper")):
                if _isfile(exe) and exe not in self.piper_exe:
                    self.piper_exe.append(exe)
            for vd in (_j(p, "voices"), p):
                if _isdir(vd) and vd not in self.piper_dirs and any(n.lower().endswith(".onnx") for n in _listdir(vd)):
                    self.piper_dirs.append(vd)
        return False


def _listdir(p: str) -> list[str]:
    try:
        return os.listdir(p)
    except OSError:
        return []


def _is_link(entry) -> bool:
    try:
        if entry.is_symlink():
            return True
        st = entry.stat(follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & 0x400)          # junction / reparse point (Windows)
    except OSError:
        return True


def walk(groups: list[list[tuple[str, int]]], found: _Found, seconds: float = SCAN_SECONDS, max_dirs: int = SCAN_MAX_DIRS) -> dict:
    """Breadth-first over each group of roots (shallow folders first), depth-limited, without following links/junctions."""
    t0 = time.time()
    depth_seen: dict[str, int] = {}
    visited: set[str] = set()
    n = 0
    stopped = ""
    for roots in groups:
        q: deque = deque((r, d) for r, d in roots)
        while q and not stopped:
            path, left = q.popleft()
            key = _norm(path)
            if depth_seen.get(key, -1) >= left:
                continue
            depth_seen[key] = left
            if time.time() - t0 > seconds:
                stopped = "time"
                break
            if n >= max_dirs:
                stopped = "folders"
                break
            try:
                with os.scandir(path) as it:
                    entries = list(it)
            except (OSError, ValueError):
                continue
            n += 1
            names = {e.name.lower() for e in entries}
            stop = False
            if key not in visited:
                visited.add(key)
                try:
                    stop = found.visit(path, names)
                except OSError:
                    stop = False
            if stop or left <= 0:
                continue
            for e in entries:
                low = e.name.lower()
                if low in SKIP_DIRS or low.startswith((".", "$", "~")):
                    continue
                try:
                    if not e.is_dir(follow_symlinks=False) or _is_link(e):
                        continue
                except OSError:
                    continue
                q.append((e.path, left - 1))
    return {"dirs": n, "seconds": round(time.time() - t0, 2), "stopped": stopped}


def _choose(cands: list[str], complete, stamp=_mtime) -> tuple[str | None, list[str]]:
    """Complete before incomplete, then the newest (by `stamp`, e.g. the marker file's time). Returns (choice, the others)."""
    uniq: list[str] = []
    for c in cands:
        if _norm(c) not in {_norm(u) for u in uniq}:
            uniq.append(c)
    if not uniq:
        return None, []
    ranked = sorted(uniq, key=lambda c: (bool(complete(c)), stamp(c)), reverse=True)
    return ranked[0], ranked[1:]


def voice_result(found: _Found) -> dict:
    out = {}
    for key, spec in VOICE_PARTS.items():
        def models_complete(m, spec=spec):
            return all(_isfile(_j(m, f)) for f in spec["models"])

        def vendor_complete(v, spec=spec):
            return all(_isfile(_j(v, f)) for f in spec["vendor"])

        def venv_ok(py):
            return not _venv_broken(py) and _isfile(py)

        cands = found.voice[key]
        models, other_models = _choose(cands["models"], models_complete, lambda m, spec=spec: _mtime(_j(m, spec["models"][0])))
        vendor, _ = _choose(cands["vendor"], vendor_complete, lambda v, spec=spec: _mtime(_j(v, spec["vendor"][0])))
        # the marker file of the NMarketing installer (its pip step finished) makes a venv "complete"
        python, _ = _choose(cands["venv"], lambda py: venv_ok(py) and any(n.startswith(".nm-pip-venv") for n in _listdir(os.path.dirname(os.path.dirname(py)))))
        missing = []
        if not models:
            missing += ["models/" + f for f in spec["models"]]
        else:
            missing += ["models/" + f for f in spec["models"] if not _isfile(_j(models, f))]
        if not vendor:
            missing += ["vendor/" + f for f in spec["vendor"]]
        else:
            missing += ["vendor/" + f for f in spec["vendor"] if not _isfile(_j(vendor, f))]
        broken = _venv_broken(python) if python else ""
        if not python or broken:
            missing.append("venvs/%s (Python packages)%s" % (spec["venv"], " - " + broken if broken else ""))
        out[key] = {"models_dir": models, "vendor_dir": vendor, "python": python, "missing": missing, "complete": not missing,
                    "other_models_dirs": other_models[:3]}
    return out


def piper_result(found: _Found) -> dict:
    voices: list[dict] = []
    seen = set()
    for d in found.piper_dirs:
        for n in sorted(_listdir(d)):
            if n.lower().endswith(".onnx") and _isfile(os.path.join(d, n + ".json")) and n.lower() not in seen:
                seen.add(n.lower())
                voices.append({"id": n[:-5], "path": os.path.join(d, n)})
    exe = sorted(found.piper_exe, key=_mtime, reverse=True)
    return {"exe": exe[0] if exe else None, "voice_dirs": found.piper_dirs, "voices": voices}


# ------------------------------------------------------------------ Ollama

def ollama_result(url: str | None, env=None) -> dict:
    env = os.environ if env is None else env
    out: dict = {"url": (url or "http://127.0.0.1:11434").rstrip("/"), "running": False, "models": [], "exe": None, "models_dir": None, "on_disk": []}
    try:
        tags = _http_json(out["url"] + "/api/tags", 1.5)
        out["running"] = True
        out["models"] = [{"name": m.get("name"), "size": m.get("size") or 0} for m in tags.get("models", [])]
    except Exception:  # noqa: BLE001
        pass
    if not (defaults_enabled(env) or env.get("OLLAMA_MODELS")):
        return out
    d = env.get("OLLAMA_MODELS") or os.path.join(os.path.expanduser("~"), ".ollama", "models")
    reg = os.path.join(d, "manifests", "registry.ollama.ai")
    if _isdir(reg):
        out["models_dir"] = d
        for ns in _listdir(reg):
            for model in _listdir(os.path.join(reg, ns)):
                for tag in _listdir(os.path.join(reg, ns, model)):
                    if _isfile(os.path.join(reg, ns, model, tag)):
                        out["on_disk"].append((model if ns == "library" else f"{ns}/{model}") + ":" + tag)
    if defaults_enabled(env):
        for c in ([os.path.join(env["LOCALAPPDATA"], "Programs", "Ollama", "ollama.exe")] if env.get("LOCALAPPDATA") else []) + [r"C:\Program Files\Ollama\ollama.exe"]:
            if IS_WIN and _isfile(c):
                out["exe"] = c
                break
        if not out["exe"]:
            import shutil

            out["exe"] = shutil.which("ollama")
    return out


# ------------------------------------------------------------------ the scan

def _desktop_comfy(found: _Found, env) -> None:
    """ComfyUI Desktop (Electron app): its base folder holds models/ and custom_nodes/, the code lives inside the app."""
    appdata = env.get("APPDATA", "")
    if not appdata:
        return
    try:
        base = json.load(open(os.path.join(appdata, "ComfyUI", "config.json"), encoding="utf-8")).get("basePath")
    except (OSError, ValueError):
        return
    if base and _isdir(base) and _norm(base) not in found.comfy:
        c = comfy_install(base, desktop_base=True)
        exe = os.path.join(env.get("LOCALAPPDATA", ""), "Programs", "@comfyorgcomfyui-electron", "ComfyUI.exe")
        c["launcher"] = exe if _isfile(exe) else None
        found.comfy[_norm(base)] = c


def choose_comfy(installs: list[dict], preferred: str = "", wanted=()) -> dict | None:
    """The ComfyUI InstAI uses: the folder set in Settings, else the one with most of the files InstAI needs, else the newest."""
    if not installs:
        return None
    if preferred:
        p = _norm(preferred)
        for c in installs:
            if p in (_norm(c["root"]), _norm(c.get("portable") or "-")):
                return c
    want = {w.lower() for w in wanted}

    def score(c):
        names = set(c.get("files", {}))
        return (len(names & want) if want else len(names), bool(c.get("launcher")), c.get("mtime") or 0)

    return sorted(installs, key=score, reverse=True)[0]


def scan(manual=(), comfy_url: str | None = None, ollama_url: str | None = None, preferred_comfy: str = "", wanted=(),
         env=None, seconds: float = SCAN_SECONDS, save: bool = True, extra=()) -> dict:
    from concurrent.futures import ThreadPoolExecutor

    env = os.environ if env is None else env
    t0 = time.time()
    found = _Found()
    groups = scan_roots(manual, env, extra)
    roots = [r for g in groups for r in g]
    pool = ThreadPoolExecutor(max_workers=2)          # the network probes run while the disk is searched (a closed port takes ~2 s on Windows)
    f_api = pool.submit(comfy_api_models, comfy_url) if comfy_url else None
    f_ollama = pool.submit(ollama_result, ollama_url, env)
    stats = walk(groups, found, seconds=seconds)
    if defaults_enabled(env):
        _desktop_comfy(found, env)
    for root in list(manual) + ([preferred_comfy] if preferred_comfy else []):   # a manual ComfyUI folder that is not a code checkout
        if root and _isdir(os.path.join(root, "models")) and _isdir(os.path.join(root, "custom_nodes")) and _norm(root) not in found.comfy:
            found.comfy[_norm(root)] = comfy_install(root)
        if root and _isdir(os.path.join(root, "ComfyUI")) and _isfile(os.path.join(root, "ComfyUI", "main.py")):
            r = os.path.join(root, "ComfyUI")
            found.comfy.setdefault(_norm(r), comfy_install(r))
    installs = list(found.comfy.values())
    for c in installs:
        c["files"] = index_models(c["model_roots"])
    api = f_api.result() if f_api else None
    ollama = f_ollama.result()
    pool.shutdown(wait=False)
    chosen = choose_comfy(installs, preferred_comfy, wanted)
    result = {
        "format": FORMAT, "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "at": time.time(),
        "seconds": round(time.time() - t0, 2), "dirs": stats["dirs"], "stopped": stats["stopped"],
        "roots": [r for r, _ in roots], "defaults": defaults_enabled(env), "manual": [m for m in manual if m],
        "comfyui": {"installs": installs, "selected": chosen["root"] if chosen else None,
                    "api": {"url": comfy_url, "up": api is not None, "nodes": (api or {}).get("nodes", 0), "names": (api or {}).get("names", {}),
                            "node_names": (api or {}).get("node_names", [])}},
        "voice": voice_result(found), "nm_homes": sorted(found.homes), "piper": piper_result(found),
        "ollama": ollama,
    }
    result["key"] = cache_key(manual, comfy_url, ollama_url, preferred_comfy, extra)
    if save:
        try:
            os.makedirs(data_dir(), exist_ok=True)
            tmp = os.path.join(data_dir(), CACHE_FILE + ".%d.tmp" % os.getpid())
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(data_dir(), CACHE_FILE))
        except OSError:
            pass
    return result


def cache_key(manual=(), comfy_url=None, ollama_url=None, preferred_comfy="", extra=()) -> str:
    return json.dumps([sorted(m for m in manual if m), comfy_url or "", ollama_url or "", preferred_comfy or "", sorted(x for x in extra if x),
                       os.environ.get("INSTAI_SCAN_ROOTS", ""), defaults_enabled()])


def load_cached(max_age: float | None = None, key: str | None = None) -> dict | None:
    try:
        with open(os.path.join(data_dir(), CACHE_FILE), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if d.get("format") != FORMAT or (key is not None and d.get("key") != key):
        return None
    if max_age is not None and time.time() - float(d.get("at") or 0) > max_age:
        return None
    return d


_MEM: dict = {"value": None, "key": None, "at": 0.0}
_LOCK = threading.Lock()
_BG: dict = {"thread": None}


def _disk_mtime() -> float:
    return _mtime(os.path.join(data_dir(), CACHE_FILE))


def get(force: bool = False, max_age: float = 900.0, disk_age: float = 6 * 3600.0, background: bool = True, **kw) -> dict:
    """Cached scan: memory -> data/discovery.json -> a new scan. A stale memory copy is returned at once and refreshed in the
    background, so callers on a hot path never wait for the disk. A newer file written by the other process (server / worker)
    replaces the memory copy."""
    key = cache_key(kw.get("manual", ()), kw.get("comfy_url"), kw.get("ollama_url"), kw.get("preferred_comfy", ""), kw.get("extra", ()))
    now = time.time()
    if not force:
        if _MEM["value"] is not None and _MEM["key"] == key:
            if _disk_mtime() > _MEM["at"] + 1:
                disk = load_cached(None, key)
                if disk is not None:
                    _MEM.update(value=disk, key=key, at=float(disk.get("at") or now))
                    return disk
            if now - _MEM["at"] > max_age and background:
                _refresh_in_background(key, kw)
            return _MEM["value"]
        disk = load_cached(disk_age, key)
        if disk is not None:
            _MEM.update(value=disk, key=key, at=float(disk.get("at") or now))
            return disk
    with _LOCK:
        if not force and _MEM["value"] is not None and _MEM["key"] == key and time.time() - _MEM["at"] <= max_age:
            return _MEM["value"]
        value = scan(**kw)
        _MEM.update(value=value, key=key, at=time.time())
        return value


def _refresh_in_background(key: str, kw: dict) -> None:
    t = _BG.get("thread")
    if t is not None and t.is_alive():
        return

    def run():
        try:
            with _LOCK:
                value = scan(**kw)
                _MEM.update(value=value, key=key, at=time.time())
        except Exception:  # noqa: BLE001 - a background refresh must never break anything
            pass

    t = threading.Thread(target=run, name="instai-discovery", daemon=True)
    _BG["thread"] = t
    t.start()


def forget() -> None:
    """Drop the in-memory copies (tests; after a download the next call re-reads the disk or rescans)."""
    _MEM.update(value=None, key=None, at=0.0)
    _PEEK.update(at=0.0, value=None)


_PEEK: dict = {"at": 0.0, "value": None}


def peek(ttl: float = 30.0) -> dict | None:
    """The last scan of any kind, without scanning (for cheap lookups that must never wait, e.g. the ComfyUI port)."""
    if _MEM["value"] is not None:
        return _MEM["value"]
    if time.time() - _PEEK["at"] > ttl:
        _PEEK.update(at=time.time(), value=load_cached())
    return _PEEK["value"]


# ------------------------------------------------------------------ small readers used by the providers

def selected_comfy(d: dict | None) -> dict | None:
    if not d:
        return None
    sel = (d.get("comfyui") or {}).get("selected")
    for c in (d.get("comfyui") or {}).get("installs", []):
        if c["root"] == sel:
            return c
    return None


def comfy_visible_files(d: dict | None) -> dict[str, dict]:
    """lower-case name -> entry for every model file the selected ComfyUI can load (disk index + the running API's names)."""
    c = selected_comfy(d)
    out = dict((c or {}).get("files") or {})
    api = ((d or {}).get("comfyui") or {}).get("api") or {}
    for low, listed in (api.get("names") or {}).items():
        out.setdefault(low, {"name": listed.replace("\\", "/").rsplit("/", 1)[-1], "path": None, "size": None, "kind": "", "listed": listed})
    return out
