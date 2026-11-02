"""Is the graphics card really used? A live view (the GPU panel) and a deep check that names the cause when it is not.

The owner saw Task Manager's GPU idle while Ollama and ComfyUI worked. The usual causes, all checked here:
  * the NVIDIA driver / nvidia-smi is missing or the card is full (another program holds the VRAM);
  * an environment variable hides the card (CUDA_VISIBLE_DEVICES=-1, OLLAMA_NUM_GPU=0, OLLAMA_LLM_LIBRARY=cpu), also in the Windows
    user / system environment that Ollama inherits;
  * ComfyUI: started with --cpu / run_cpu.bat, or its python_embeded has a CPU-only PyTorch (`torch.cuda.is_available()` is False in ITS python);
  * Ollama: the model is bigger than the card, so most layers run on the CPU (size_vram < size in /api/ps), or Ollama itself found no GPU
    (its server.log says "no compatible GPUs were discovered").
Nothing here changes anything; every probe degrades to "unknown" instead of raising.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import hardware, runtime

PROBE_CODE = (
    "import json\nout={}\ntry:\n import torch\n out['torch']=torch.__version__\n out['cuda_build']=torch.version.cuda\n"
    " out['available']=bool(torch.cuda.is_available())\n"
    " if out['available']:\n  out['name']=torch.cuda.get_device_name(0)\n  out['vram_mb']=int(torch.cuda.get_device_properties(0).total_memory/1048576)\n"
    "except Exception as e:\n out['error']=type(e).__name__+': '+str(e)[:200]\nprint('INSTAI_PROBE '+json.dumps(out))\n")
HIDING_VALUES = ("", "-1", "NoDevFiles")
_FA = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")


def fa(n) -> str:
    return str(n).translate(_FA)


def _check(id_: str, level: str, title_fa: str, title_en: str, detail_fa: str = "", detail_en: str = "", fix_fa: str = "", fix_en: str = "") -> dict:
    return {"id": id_, "level": level, "title_fa": title_fa, "title_en": title_en, "detail_fa": detail_fa, "detail_en": detail_en, "fix_fa": fix_fa, "fix_en": fix_en}


# ------------------------------------------------------------------ live

def _ollama_loaded(url: str) -> list[dict] | None:
    from instai.providers import ollama_fit

    return ollama_fit.loaded(url, 1.5)


def _comfy_info(url: str) -> dict | None:
    from instai.providers.comfy import launcher

    return launcher.device_info(url, 2.0)


def _threaded(fn, *args):
    """Run in a helper thread and close that thread's database connection afterwards (settings live in the database)."""
    from django.db import connections

    try:
        return fn(*args)
    finally:
        connections.close_all()


def cpu_reason_en(info: dict) -> str:
    torch = str(info.get("torch") or "")
    if info.get("cpu_flag"):
        return "ComfyUI was started with --cpu. Close it and let InstAI start it (or run run_nvidia_gpu.bat, not run_cpu.bat)."
    if "+cpu" in torch:
        return (f"The PyTorch inside ComfyUI is a CPU-only build ({torch}). Run update\\update_comfyui_and_python_dependencies.bat in the "
                "ComfyUI_windows_portable folder to install the NVIDIA build.")
    return ("ComfyUI cannot see the graphics card (CUDA is not available). Update the NVIDIA driver, restart the PC, and if it persists run "
            "update\\update_comfyui_and_python_dependencies.bat.")


def live() -> dict:
    """What is on the GPU right now (nvidia-smi + Ollama /api/ps + ComfyUI /system_stats). Fast (about a second), never raises."""
    ollama_url, comfy_url = runtime.ollama_url(), runtime.comfyui_url()          # settings are read here, in the calling thread
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_gpu, f_ol, f_cf = ex.submit(hardware.gpu_status), ex.submit(_ollama_loaded, ollama_url), ex.submit(_comfy_info, comfy_url)
        gpu, loaded, info = f_gpu.result(), f_ol.result(), f_cf.result()
    ollama = {"up": loaded is not None, "loaded": loaded or [], "note_fa": "", "note_en": ""}
    for m in ollama["loaded"]:
        if m["placement"] != "gpu" and gpu:
            ollama["note_fa"] = (f"مدل «{m['name']}» فقط {fa(m['gpu_pct'])}٪ روی کارت گرافیک است و بقیه روی CPU کار می‌کند؛ برای همین کند است و "
                                 "GPU کم کار می‌کند. مدل کوچک‌تری انتخاب کنید.")
            ollama["note_en"] = (f"Model '{m['name']}' is only {m['gpu_pct']}% on the graphics card; the rest runs on the CPU, which is why it is slow and "
                                 "the GPU looks idle. Choose a smaller model.")
            break
    comfy = {"up": info is not None, "device": None, "device_name": None, "torch": None, "cpu_flag": False, "vram_total_mb": None,
             "vram_free_mb": None, "note_fa": "", "note_en": ""}
    if info:
        comfy.update(device=info["type"] if info["type"] in ("cuda", "cpu") else info["type"], device_name=info["name"], torch=info["torch"],
                     cpu_flag=info["cpu_flag"], vram_total_mb=info["vram_total_mb"], vram_free_mb=info["vram_free_mb"])
        if info["type"] == "cpu" and gpu:
            from instai.providers.comfy import launcher

            comfy["note_fa"], comfy["note_en"] = launcher.cpu_reason_fa(info), cpu_reason_en(info)
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "gpu": gpu, "ollama": ollama, "comfy": comfy, "verdict": _live_verdict(gpu, ollama, comfy)}


def _live_verdict(gpu: dict | None, ollama: dict, comfy: dict) -> dict:
    def v(level: str, fa_: str, en: str) -> dict:
        return {"level": level, "text_fa": fa_, "text_en": en}

    if not gpu:
        return v("none", "کارت گرافیک NVIDIA پیدا نشد (nvidia-smi کار نمی‌کند). بدون آن همه‌چیز روی CPU و بسیار کند است.",
                 "No NVIDIA graphics card was found (nvidia-smi does not work). Without it everything runs on the CPU, very slowly.")
    if comfy["device"] == "cpu":
        return v("bad", "ComfyUI روی CPU کار می‌کند، نه کارت گرافیک.", "ComfyUI is running on the CPU, not the graphics card.")
    cpu = [m for m in ollama["loaded"] if m["placement"] == "cpu"]
    if cpu:
        return v("bad", f"مدل «{cpu[0]['name']}» تقریباً کاملاً روی CPU کار می‌کند؛ کارت گرافیک بی‌کار می‌ماند.",
                 f"Model '{cpu[0]['name']}' runs almost entirely on the CPU; the graphics card stays idle.")
    mixed = [m for m in ollama["loaded"] if m["placement"] == "mixed"]
    if mixed:
        return v("warn", f"مدل «{mixed[0]['name']}» فقط {fa(mixed[0]['gpu_pct'])}٪ روی GPU است و بقیه روی CPU؛ کند است.",
                 f"Model '{mixed[0]['name']}' is only {mixed[0]['gpu_pct']}% on the GPU, the rest on the CPU; slow.")
    if ollama["loaded"] or comfy["device"] == "cuda":
        what = "، ".join([f"«{m['name']}»" for m in ollama["loaded"]] + (["ComfyUI"] if comfy["device"] == "cuda" else []))
        what_en = ", ".join([f"'{m['name']}'" for m in ollama["loaded"]] + (["ComfyUI"] if comfy["device"] == "cuda" else []))
        return v("ok", f"کارت گرافیک استفاده می‌شود: {what}.", f"The graphics card is in use: {what_en}.")
    return v("idle", "کارت گرافیک سالم است و الان کاری روی آن نیست.", "The graphics card is fine and nothing is loaded on it right now.")


# ------------------------------------------------------------------ deep check

def win_env(name: str) -> dict:
    """{process, user, machine}: the value of an environment variable in this process and in the Windows user / system environment
    (what a program started later, such as the Ollama service, inherits). Missing = None."""
    out = {"process": os.environ.get(name), "user": None, "machine": None}
    if sys.platform.startswith("win"):
        try:
            import winreg

            for key, root, path in (("user", winreg.HKEY_CURRENT_USER, "Environment"),
                                    ("machine", winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
                try:
                    with winreg.OpenKey(root, path) as k:
                        out[key] = str(winreg.QueryValueEx(k, name)[0])
                except OSError:
                    pass
        except ImportError:
            pass
    return out


def check_env() -> dict:
    bad: list[tuple[str, str, str]] = []
    for name, is_bad in (("CUDA_VISIBLE_DEVICES", lambda v: v.strip() in HIDING_VALUES or not re.fullmatch(r"[0-9, ]+|GPU-[\w-]+(,GPU-[\w-]+)*|MIG-[\w/-]+", v.strip())),
                         ("OLLAMA_NUM_GPU", lambda v: v.strip() == "0"),
                         ("OLLAMA_LLM_LIBRARY", lambda v: v.strip().lower().startswith("cpu"))):
        for where, val in win_env(name).items():
            if val is not None and is_bad(val):
                bad.append((name, where, val))
    if bad:
        txt = "، ".join(f"{n}={v!r} ({ {'process': 'همین برنامه', 'user': 'متغیر کاربر ویندوز', 'machine': 'متغیر سیستم ویندوز'}[w] })" for n, w, v in bad)
        txt_en = ", ".join(f"{n}={v!r} ({w})" for n, w, v in bad)
        return _check("env", "bad", "یک متغیر محیطی کارت گرافیک را پنهان می‌کند", "An environment variable hides the graphics card", txt, txt_en,
                      "این متغیر را از «Edit the system environment variables» ویندوز حذف کنید، سپس Ollama را کامل ببندید (آیکن کنار ساعت ← Quit) و دوباره روشن کنید.",
                      "Delete this variable in Windows 'Edit the system environment variables', then quit Ollama completely (tray icon > Quit) and start it again.")
    return _check("env", "ok", "هیچ متغیر محیطی کارت گرافیک را پنهان نکرده", "No environment variable hides the graphics card",
                  "CUDA_VISIBLE_DEVICES، OLLAMA_NUM_GPU و OLLAMA_LLM_LIBRARY بررسی شدند.", "CUDA_VISIBLE_DEVICES, OLLAMA_NUM_GPU and OLLAMA_LLM_LIBRARY were checked.")


def check_nvidia(gpu: dict | None) -> dict:
    if not gpu:
        return _check("nvidia", "bad", "کارت گرافیک NVIDIA پیدا نشد", "No NVIDIA graphics card was found", "nvidia-smi پیدا نشد یا کار نکرد.", "nvidia-smi was not found or did not work.",
                      "درایور NVIDIA را از سایت nvidia.com نصب کنید و رایانه را ری‌استارت کنید.", "Install the NVIDIA driver from nvidia.com and restart the PC.")
    total, used = gpu.get("total_mb") or 0, gpu.get("used_mb") or 0
    detail = f"{gpu['name']} · {fa(round(total / 1024, 1))} گیگابایت · درایور {gpu['driver']} · استفاده‌شده الان {fa(round(used / 1024, 1))} گیگابایت"
    detail_en = f"{gpu['name']} · {total / 1024:.1f} GB · driver {gpu['driver']} · {used / 1024:.1f} GB in use now"
    if total and used / total > 0.85:
        procs = ", ".join(f"{p['name']} ({p['used_mb']} MB)" for p in gpu.get("processes", [])[:4])
        return _check("nvidia", "warn", "حافظهٔ کارت گرافیک تقریباً پر است", "The graphics card memory is almost full", detail + (f" · {procs}" if procs else ""),
                      detail_en + (f" · {procs}" if procs else ""), "برنامه‌های سنگین دیگر را ببندید (یا مدل‌های لودشده را از ComfyUI/Ollama آزاد کنید).",
                      "Close other heavy programs (or unload the loaded models in ComfyUI / Ollama).")
    return _check("nvidia", "ok", "کارت گرافیک NVIDIA پیدا شد", "NVIDIA graphics card found", detail, detail_en)


def check_comfy_launcher() -> tuple[dict, dict | None]:
    from instai.providers.comfy import launcher

    try:
        sel = launcher.selected()
    except Exception:  # noqa: BLE001
        sel = None
    if not sel:
        return _check("comfy_launcher", "info", "ComfyUI روی این رایانه پیدا نشد", "ComfyUI was not found on this PC", "", "",
                      "پوشهٔ ComfyUI را در صفحهٔ «مدل‌ها» بدهید.", "Give the ComfyUI folder on the Models page."), None
    cmd = launcher.command(sel)
    base = os.path.basename(sel.get("launcher") or "") or "-"
    py = sel.get("python") or "-"
    if not cmd:
        return _check("comfy_launcher", "bad", "InstAI نمی‌تواند ComfyUI را روی GPU روشن کند", "InstAI cannot start ComfyUI on the GPU",
                      f"راه‌انداز: {base}", f"launcher: {base}", "فایل run_nvidia_gpu.bat باید کنار ComfyUI باشد؛ یا ComfyUI را خودتان روشن کنید.",
                      "run_nvidia_gpu.bat must sit next to ComfyUI, or start ComfyUI yourself."), sel
    argv = " ".join(cmd[0])
    cpu_bits = [x for x in ("run_cpu.bat" if sel.get("cpu_launcher") else "", "--cpu" if sel.get("cpu_flag") else "") if x]
    if cpu_bits:
        return _check("comfy_launcher", "warn", "در راه‌انداز ComfyUI گزینهٔ CPU هست؛ InstAI آن را حذف می‌کند", "The ComfyUI launcher has a CPU option; InstAI removes it",
                      f"پیدا شد: {', '.join(cpu_bits)}. دستوری که InstAI می‌زند: {argv}", f"Found: {', '.join(cpu_bits)}. InstAI runs: {argv}",
                      "اگر ComfyUI را خودتان با آن فایل روشن کنید روی CPU می‌ماند؛ از run_nvidia_gpu.bat استفاده کنید.",
                      "If you start ComfyUI yourself with that file it stays on the CPU; use run_nvidia_gpu.bat."), sel
    if not (sel.get("python") and os.path.isfile(sel["python"])) and "python" not in argv.lower():
        return _check("comfy_launcher", "warn", "پایتونِ ComfyUI پیدا نشد", "ComfyUI's python was not found", f"راه‌انداز: {base}", f"launcher: {base}"), sel
    return _check("comfy_launcher", "ok", "راه‌انداز ComfyUI درست است (بدون --cpu)", "The ComfyUI launcher is right (no --cpu)",
                  f"پایتون: {py} · دستور: {argv}", f"python: {py} · command: {argv}"), sel


def probe_torch(py: str, timeout: float = 90.0) -> dict:
    """Ask ComfyUI's OWN python whether PyTorch sees the graphics card: {torch, cuda_build, available, name, vram_mb} or {error}."""
    from instai.providers.comfy import launcher

    try:
        p = subprocess.run([py, "-s", "-c", PROBE_CODE], capture_output=True, text=True, timeout=timeout, cwd=os.path.dirname(py) or None,
                           env=launcher.launch_env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {int(timeout)} s"}
    except OSError as e:
        return {"error": f"{type(e).__name__}: {e}"}
    for line in (p.stdout or "").splitlines():
        if line.startswith("INSTAI_PROBE "):
            try:
                return json.loads(line[len("INSTAI_PROBE "):])
            except ValueError:
                break
    return {"error": ((p.stderr or p.stdout or "no output").strip().splitlines() or ["no output"])[-1][:200]}


def check_comfy_torch(sel: dict | None, probe: dict | None) -> dict:
    if not sel or not sel.get("python") or not os.path.isfile(sel["python"]):
        return _check("comfy_torch", "info", "پایتونِ ComfyUI برای آزمایش پیدا نشد", "ComfyUI's python was not found for the test")
    if not probe or probe.get("error"):
        err = (probe or {}).get("error", "")
        return _check("comfy_torch", "warn" if "torch" not in err.lower() else "bad", "آزمایش PyTorch در پایتونِ ComfyUI انجام نشد", "The PyTorch test in ComfyUI's python failed",
                      err, err, "اگر پیام دربارهٔ torch است، update\\update_comfyui_and_python_dependencies.bat را اجرا کنید.",
                      "If the message mentions torch, run update\\update_comfyui_and_python_dependencies.bat.")
    ver = str(probe.get("torch") or "")
    if probe.get("available"):
        return _check("comfy_torch", "ok", "PyTorchِ ComfyUI کارت گرافیک را می‌بیند (torch.cuda.is_available() = True)",
                      "ComfyUI's PyTorch sees the graphics card (torch.cuda.is_available() = True)",
                      f"torch {ver} · CUDA {probe.get('cuda_build')} · {probe.get('name')} · {fa(round((probe.get('vram_mb') or 0) / 1024, 1))} گیگابایت",
                      f"torch {ver} · CUDA {probe.get('cuda_build')} · {probe.get('name')} · {(probe.get('vram_mb') or 0) / 1024:.1f} GB")
    cpu_build = "+cpu" in ver or not probe.get("cuda_build")
    return _check("comfy_torch", "bad", "PyTorchِ ComfyUI کارت گرافیک را نمی‌بیند (torch.cuda.is_available() = False)" if not cpu_build else
                  "PyTorchِ ComfyUI فقط نسخهٔ CPU است", "ComfyUI's PyTorch cannot see the graphics card (torch.cuda.is_available() = False)" if not cpu_build else
                  "ComfyUI's PyTorch is a CPU-only build", f"torch {ver} · CUDA {probe.get('cuda_build')}", f"torch {ver} · CUDA {probe.get('cuda_build')}",
                  "فایل update\\update_comfyui_and_python_dependencies.bat را در پوشهٔ ComfyUI_windows_portable اجرا کنید (دوبار کلیک) تا نسخهٔ NVIDIA نصب شود؛ بعد رایانه را ری‌استارت کنید."
                  if cpu_build else "درایور NVIDIA را به‌روز کنید و رایانه را ری‌استارت کنید.",
                  "Run update\\update_comfyui_and_python_dependencies.bat in the ComfyUI_windows_portable folder (double-click) to install the NVIDIA build, then restart the PC."
                  if cpu_build else "Update the NVIDIA driver and restart the PC.")


def check_comfy_running(info: dict | None, gpu: dict | None) -> dict:
    if info is None:
        return _check("comfy_running", "info", "ComfyUI الان روشن نیست", "ComfyUI is not running right now",
                      "هر وقت کاری به آن نیاز داشته باشد، InstAI آن را روشن می‌کند.", "InstAI starts it when a job needs it.")
    dev = info.get("type")
    detail = f"{info.get('name')} · torch {info.get('torch')}"
    if dev == "cpu":
        from instai.providers.comfy import launcher

        return _check("comfy_running", "bad" if gpu else "info", "ComfyUIِ روشن روی CPU کار می‌کند", "The running ComfyUI works on the CPU", detail, detail,
                      launcher.cpu_reason_fa(info), cpu_reason_en(info))
    return _check("comfy_running", "ok" if dev == "cuda" else "info", "ComfyUIِ روشن روی کارت گرافیک کار می‌کند" if dev == "cuda" else "ComfyUI روشن است",
                  "The running ComfyUI works on the graphics card" if dev == "cuda" else "ComfyUI is running", detail, detail)


def ollama_log_path() -> Path | None:
    base = os.environ.get("LOCALAPPDATA")
    cands = [Path(base) / "Ollama" / "server.log"] if base else []
    cands.append(Path.home() / ".ollama" / "logs" / "server.log")
    return next((p for p in cands if p.is_file()), None)


RE_FOUND = re.compile(r"inference compute.*?library=(\w+)", re.I)
RE_NONE = re.compile(r"no compatible GPUs were discovered|unable to load cuda|cuda driver library failed|no nvidia gpu|failed to initialize NVML", re.I)
RE_LAYERS = re.compile(r"offloaded (\d+)/(\d+) layers to GPU", re.I)


def scan_ollama_log(text: str) -> dict:
    """What Ollama's own log says about the GPU: {library: cuda|cpu|None, none_found: bool, offloaded: (n, total)|None}, the LAST statements win."""
    found = None
    none_at = found_at = -1
    layers = None
    for i, line in enumerate(text.splitlines()):
        m = RE_FOUND.search(line)
        if m:
            found, found_at = m.group(1).lower(), i
        if RE_NONE.search(line):
            none_at = i
        m = RE_LAYERS.search(line)
        if m:
            layers = (int(m.group(1)), int(m.group(2)))
    return {"library": found, "none_found": none_at > found_at and none_at >= 0, "offloaded": layers}


def check_ollama_log() -> dict | None:
    p = ollama_log_path()
    if not p:
        return None
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 400_000))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    s = scan_ollama_log(text)
    if s["none_found"] or s["library"] == "cpu":
        return _check("ollama_log", "bad", "خودِ Ollama کارت گرافیک را پیدا نکرده است", "Ollama itself found no graphics card", f"فایل گزارش Ollama: {p}", f"Ollama log: {p}",
                      "درایور NVIDIA را به‌روز کنید، متغیرهای محیطی بالا را بررسی کنید و Ollama را کامل ببندید و دوباره روشن کنید. اگر ادامه داشت، Ollama را از ollama.com دوباره نصب کنید.",
                      "Update the NVIDIA driver, check the environment variables above, quit Ollama completely and start it again. If it persists, reinstall Ollama from ollama.com.")
    if s["offloaded"] and s["offloaded"][1] and s["offloaded"][0] / s["offloaded"][1] < 0.9:
        n, t = s["offloaded"]
        return _check("ollama_log", "warn", f"آخرین مدلِ Ollama فقط {fa(n)} از {fa(t)} لایه را روی GPU گذاشت", f"The last Ollama model put only {n} of {t} layers on the GPU",
                      f"فایل گزارش: {p}", f"log: {p}", "مدل کوچک‌تری انتخاب کنید که کامل در حافظهٔ کارت جا شود.", "Choose a smaller model that fits completely in the card's memory.")
    if s["library"] == "cuda":
        return _check("ollama_log", "ok", "Ollama کارت گرافیک را پیدا کرده است (library=cuda)", "Ollama found the graphics card (library=cuda)", f"فایل گزارش: {p}", f"log: {p}")
    return _check("ollama_log", "info", "گزارش Ollama دربارهٔ GPU چیزی نگفته است", "Ollama's log says nothing about the GPU", f"فایل گزارش: {p}", f"log: {p}")


def check_ollama_model(gpu: dict | None) -> dict:
    from instai.core import settings_store
    from instai.providers import ollama_fit
    from instai.providers.ollama import OllamaProvider

    provider = str(settings_store.effective("llm_provider") or "ollama")
    if provider != "ollama":
        return _check("ollama_model", "info", f"مدل متن از Ollama نیست ({provider})", f"The text model is not from Ollama ({provider})")
    url = runtime.ollama_url()
    prov = OllamaProvider(url, str(settings_store.effective("ollama_model") or ""))
    vram = float(gpu["total_mb"]) if gpu and gpu.get("total_mb") else None
    models = ollama_fit.fetch_models(url, prov.num_ctx, vram)
    if models is None:
        return _check("ollama_model", "warn", "Ollama روشن نیست", "Ollama is not running", url, url, "برنامهٔ Ollama را اجرا کنید.", "Start the Ollama app.")
    if not models:
        return _check("ollama_model", "warn", "هیچ مدلی در Ollama نصب نیست", "No model is installed in Ollama", "", "", "مثلاً qwen3:8b را نصب کنید.", "Install a model, for example qwen3:8b.")
    choice = ollama_fit.pick_default(models, vram)
    chosen_name = prov._model or (choice or {}).get("model", "")
    row = next((m for m in models if ollama_fit.same_model(m["name"], chosen_name)), None)
    if row is None:
        return _check("ollama_model", "warn", f"مدل انتخاب‌شده «{chosen_name}» نصب نیست", f"The chosen model '{chosen_name}' is not installed")
    why_fa = (choice or {}).get("reason_fa", "") if not prov._model else "این مدل را خودتان در تنظیمات انتخاب کرده‌اید."
    why_en = (choice or {}).get("reason_en", "") if not prov._model else "You chose this model in Settings."
    gb = round((row["size_mb"] or 0) / 1024, 1)
    if row["fit"] == "gpu":
        return _check("ollama_model", "ok", f"مدل «{row['name']}» کامل در حافظهٔ کارت گرافیک جا می‌شود", f"Model '{row['name']}' fits completely in the graphics card memory",
                      f"{fa(gb)} گیگابایت · {why_fa}", f"{gb} GB · {why_en}")
    if row["fit"] in ("partial", "cpu"):
        lvl = "warn" if row["fit"] == "partial" else "bad"
        small = next((m for m in sorted(models, key=lambda m: m["size_mb"]) if m["kind"] == "text" and m["fit"] == "gpu"), None)
        fix_fa = (f"مدل «{small['name']}» که از قبل نصب است کاملاً روی GPU جا می‌شود؛ آن را در تنظیمات انتخاب کنید." if small
                  else "مدل کوچک‌تری مثل qwen3:8b نصب کنید و در تنظیمات انتخاب کنید.")
        fix_en = (f"The installed model '{small['name']}' fits completely on the GPU; choose it in Settings." if small
                  else "Install a smaller model such as qwen3:8b and choose it in Settings.")
        return _check("ollama_model", lvl, f"مدل «{row['name']}» از حافظهٔ کارت گرافیک بزرگ‌تر است؛ حدود {fa(row['est_gpu_pct'])}٪ آن روی GPU می‌افتد" if row["est_gpu_pct"] is not None
                      else f"مدل «{row['name']}» از حافظهٔ کارت گرافیک بزرگ‌تر است",
                      f"Model '{row['name']}' is bigger than the graphics card memory; about {row['est_gpu_pct']}% of it lands on the GPU", f"{fa(gb)} گیگابایت · بقیه روی CPU کند کار می‌کند.",
                      f"{gb} GB · the rest runs slowly on the CPU.", fix_fa, fix_en)
    return _check("ollama_model", "info", f"مدل «{row['name']}»", f"Model '{row['name']}'", f"{fa(gb)} گیگابایت", f"{gb} GB")


def check_voice() -> dict | None:
    from instai.providers.audio import services

    bad = []
    for key in services.SERVICES:
        h = services.health(key, 0.6)
        if h["status"] == "ready" and "cpu" in str(h.get("device") or "").lower():
            bad.append(services.SERVICES[key]["label"])
    if not bad:
        return None
    return _check("voice", "warn", "یک موتور صدای روشن روی CPU کار می‌کند", "A running voice engine works on the CPU", "، ".join(bad), ", ".join(bad),
                  "PyTorchِ پایتونِ آن موتور نسخهٔ CPU است؛ از Download-Models.bat همان بسته را دوباره نصب کنید.",
                  "That engine's PyTorch is a CPU build; reinstall that package with Download-Models.bat.")


def probe_ollama() -> dict | None:
    """Really run the chosen model for a few tokens and read where it ran (Ollama /api/ps) and how busy the GPU got (nvidia-smi sampled during
    the run): the proof that does not depend on logs or estimates. None when Ollama is not usable (the other checks say why)."""
    import threading

    from instai.providers import ollama_fit
    from instai.providers.base import ProviderError
    from instai.providers.ollama import OllamaProvider
    from . import settings_store

    url = runtime.ollama_url()
    if ollama_fit.loaded(url, 1.5) is None:
        return None
    prov = OllamaProvider(url, str(settings_store.effective("ollama_model") or ""))
    peak = {"util": 0, "vram": 0}
    stop = threading.Event()

    def sample() -> None:
        while not stop.wait(0.4):
            g = hardware.gpu_status()
            if g:
                peak["util"] = max(peak["util"], g.get("utilization") or 0)
                peak["vram"] = max(peak["vram"], g.get("used_mb") or 0)

    th = threading.Thread(target=sample, daemon=True)
    th.start()
    try:
        model = prov.effective_model()
        res = prov.generate([{"role": "user", "content": "Write one short sentence about the sea."}], max_tokens=48, temperature=0.2)
    except ProviderError as e:
        return _check("ollama_run", "warn", "اجرای آزمایشی مدل Ollama انجام نشد", "The trial run of the Ollama model did not work", e.fa or str(e), str(e))
    finally:
        stop.set()
        th.join(timeout=2)
    raw = res.raw or {}
    pct, place = raw.get("gpu_pct"), raw.get("placement")
    tps = res.tokens_per_second
    d_en = (f"model {model}: {pct if pct is not None else '?'}% on the GPU, {tps if tps else '?'} tokens/s, peak GPU utilization {peak['util']}%, "
            f"peak VRAM in use {peak['vram']} MB")
    d_fa = (f"مدل {model}: {fa(pct) if pct is not None else '؟'}٪ روی GPU، {fa(tps) if tps else '؟'} توکن در ثانیه، بیشینهٔ فعالیت GPU {fa(peak['util'])}٪، "
            f"بیشینهٔ حافظهٔ استفاده‌شده {fa(peak['vram'])} مگابایت")
    if place == "gpu":
        return _check("ollama_run", "ok", "اجرای آزمایشی: مدل کامل روی کارت گرافیک اجرا شد", "Trial run: the model ran completely on the graphics card", d_fa, d_en)
    if place == "mixed":
        return _check("ollama_run", "warn", "اجرای آزمایشی: فقط بخشی از مدل روی کارت گرافیک بود", "Trial run: only part of the model was on the graphics card", d_fa, d_en,
                      "مدل کوچک‌تری انتخاب کنید که کامل جا شود.", "Choose a smaller model that fits completely.")
    if place == "cpu":
        return _check("ollama_run", "bad", "اجرای آزمایشی: مدل روی CPU اجرا شد و کارت گرافیک بی‌کار ماند", "Trial run: the model ran on the CPU and the graphics card stayed idle", d_fa, d_en,
                      "مدل کوچک‌تری انتخاب کنید یا علت را در بررسی‌های بالا ببینید (درایور، متغیرهای محیطی، گزارش Ollama).",
                      "Choose a smaller model, or see the checks above for the cause (driver, environment variables, Ollama log).")
    return _check("ollama_run", "info", "اجرای آزمایشی انجام شد ولی محل اجرا معلوم نشد", "The trial run worked but where it ran is unknown", d_fa, d_en)


def deep_check(probe: bool = True) -> dict:
    """The full 'why is the GPU not used' report. `probe` runs ComfyUI's python once (about 5-20 s)."""
    t0 = time.time()
    gpu = hardware.gpu_status()
    comfy_url = runtime.comfyui_url()
    checks: list[dict] = [check_nvidia(gpu), check_env()]
    launcher_check, sel = check_comfy_launcher()
    checks.append(launcher_check)
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_probe = ex.submit(probe_torch, sel["python"]) if probe and sel and sel.get("python") and os.path.isfile(sel["python"]) else None
        f_info, f_voice = ex.submit(_comfy_info, comfy_url), ex.submit(_threaded, check_voice)
        info = f_info.result()
        torch_probe = f_probe.result() if f_probe else None
        voice = f_voice.result()
    checks.append(check_comfy_torch(sel, torch_probe))
    checks.append(check_comfy_running(info, gpu))
    log_check = check_ollama_log()
    if log_check:
        checks.append(log_check)
    checks.append(check_ollama_model(gpu))
    if voice:
        checks.append(voice)
    return {"took": round(time.time() - t0, 1), **summarize(checks)}


def summarize(checks: list[dict]) -> dict:
    """gpu_used: yes | partial | no | unknown, the verdict sentence and the checks."""
    bad = [c for c in checks if c["level"] == "bad"]
    warn = [c for c in checks if c["level"] == "warn"]
    nv = next((c for c in checks if c["id"] == "nvidia"), None)
    if bad:
        used, lvl = "no", "bad"
        v = {"level": lvl, "text_fa": "GPU درست استفاده نمی‌شود: " + bad[0]["title_fa"] + ".", "text_en": "The GPU is not used properly: " + bad[0]["title_en"] + "."}
    elif warn:
        used, lvl = "partial", "warn"
        v = {"level": lvl, "text_fa": "GPU استفاده می‌شود ولی یک مشکل هست: " + warn[0]["title_fa"] + ".", "text_en": "The GPU is used but there is a problem: " + warn[0]["title_en"] + "."}
    elif nv and nv["level"] == "ok":
        used, lvl = "yes", "ok"
        v = {"level": lvl, "text_fa": "همه‌چیز درست است؛ کارِ هوش مصنوعی روی کارت گرافیک اجرا می‌شود.", "text_en": "Everything is right; the AI work runs on the graphics card."}
    else:
        used, lvl = "unknown", "idle"
        v = {"level": lvl, "text_fa": "نتیجهٔ قطعی نبود.", "text_en": "The result was not conclusive."}
    return {"gpu_used": used, "verdict": v, "checks": checks}


def ascii_report(result: dict, width: int = 100) -> str:
    """The deep check as plain ASCII text (Test-GPU.bat prints it; the Windows console garbles Persian)."""
    mark = {"ok": "[ OK ]", "warn": "[WARN]", "bad": "[ NO ]", "info": "[ .. ]"}
    lines = []
    for c in result["checks"]:
        lines.append(f"{mark.get(c['level'], '[ .. ]')} {c['title_en']}")
        if c["detail_en"]:
            lines.append(f"         {c['detail_en']}"[: width + 9])
        if c["fix_en"] and c["level"] in ("bad", "warn"):
            lines.append(f"         FIX: {c['fix_en']}")
    word = {"yes": "YES", "partial": "PARTLY", "no": "NO", "unknown": "UNKNOWN"}[result["gpu_used"]]
    lines += ["", f"VERDICT: GPU USED = {word}", f"         {result['verdict']['text_en']}"]
    return "\n".join(lines).encode("ascii", "replace").decode("ascii")
