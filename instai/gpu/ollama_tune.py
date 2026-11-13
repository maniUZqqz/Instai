"""Ollama on the GPU, completely (0.8.0): the context size, the layers and the cache settings that keep the owner's models on the graphics card.

The owner's models are never changed (no pull, no delete, no re-quantising); only HOW they are loaded:

* per request - `plan()` chooses `num_ctx` (the largest context, not below InstAI's own default, with which the whole model still fits in the
  VRAM that is free right now) and `num_gpu` (999 = "every layer", only when the numbers say it fits: forcing it on a model that does not fit
  makes Ollama fail instead of spilling to the CPU, so it is never forced then);
* per Ollama server - flash attention and a quantised KV cache (`OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`) halve the cache that grows
  with the context. They are environment variables of the Ollama PROCESS, so InstAI can only advise them (`env_status`) or save them in the Windows
  user environment (`apply_env`, the owner presses a button) and, when the owner agrees, restart Ollama (`restart_ollama`).

Nothing here talks to a GPU by itself: it works on the numbers Ollama (/api/tags, /api/ps) and nvidia-smi report, and degrades to "unknown".
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

from instai.providers import ollama_fit

log = logging.getLogger("instai.gpu.ollama")

CTX_LADDER = (4096, 6144, 8192, 12288, 16384, 24576, 32768, 49152, 65536)
FORCE_ALL_LAYERS = 999
KV_FACTOR = {"f16": 1.0, "q8_0": 0.5, "q4_0": 0.27}            # size of the KV cache relative to the default f16
RECOMMENDED = {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"}
MIN_CTX = 4096                                                  # never plan below this; a story prompt would be cut
_CACHE: dict = {}


def kv_type_in_use() -> str:
    """The KV cache type Ollama was told to use, as far as InstAI can see (this process and the Windows environment), else f16."""
    from instai.core import gpu_diag

    for where, val in gpu_diag.win_env("OLLAMA_KV_CACHE_TYPE").items():
        if val and val.strip().lower() in KV_FACTOR:
            return val.strip().lower()
    return "f16"


def need_mb(size_mb: float, params_b: float | None, ctx: int, kv: str = "f16") -> float:
    """VRAM one loaded model needs: weights + KV cache for the context (scaled by the cache type) + compute buffers."""
    return size_mb + ollama_fit.kv_cache_mb(ctx, params_b) * KV_FACTOR.get(kv, 1.0) + ollama_fit.BUFFERS_MB


def plan(model: dict, *, wanted_ctx: int, vram_total_mb: float | None, vram_free_mb: float | None = None, kv: str = "f16",
         forced_gpu: int | None = None, auto: bool = True) -> dict:
    """What to send with a request for `model` (a row of ollama_fit.fetch_models): {num_ctx, num_gpu, fit, est_gpu_pct, note_fa, note_en}.

    `num_gpu` is None (let Ollama decide) unless the whole model plainly fits right now; an explicit `forced_gpu` (the owner's own setting) always wins.
    The context shrinks only to keep the model completely on the GPU, and never below the default / 4096."""
    size, params = float(model.get("size_mb") or 0), model.get("params_b")
    floor = max(MIN_CTX, min(int(wanted_ctx), 8192))           # the default context (8192) is what story prompts were designed for
    out = {"num_ctx": int(wanted_ctx), "num_gpu": forced_gpu, "kv": kv, "fit": "unknown", "est_gpu_pct": None, "note_fa": "", "note_en": ""}
    if not vram_total_mb or not size:
        return out
    budget = float(vram_total_mb) - ollama_fit.RESERVE_MB
    if vram_free_mb is not None:                                # what is really free now (another program may hold some)
        budget = min(budget, float(vram_free_mb) - 200)
    ctx = int(wanted_ctx)
    if auto:
        ladder = [c for c in CTX_LADDER if floor <= c <= int(wanted_ctx)] or [int(wanted_ctx)]
        fitting = [c for c in ladder if need_mb(size, params, c, kv) <= budget]
        if fitting:
            ctx = max(fitting)
        else:
            ctx = floor                                         # nothing fits completely: the smallest context loses the least
    need = need_mb(size, params, ctx, kv)
    if need <= budget:
        fit, pct = "gpu", 100
    else:
        kv_mb = ollama_fit.kv_cache_mb(ctx, params) * KV_FACTOR.get(kv, 1.0)
        pct = int(max(0.0, min(99.0, (budget - kv_mb - ollama_fit.BUFFERS_MB) / size * 100)))
        fit = "partial" if pct >= 50 else "cpu"
    out.update(num_ctx=ctx, fit=fit, est_gpu_pct=pct)
    if forced_gpu is None and need <= budget:
        out["num_gpu"] = FORCE_ALL_LAYERS
    if ctx < int(wanted_ctx):
        out["note_fa"] = (f"زمینهٔ مدل از {wanted_ctx} به {ctx} توکن کم شد تا کل مدل روی کارت گرافیک بماند (حافظهٔ آزاد: {int(budget)} مگابایت).")
        out["note_en"] = f"The context was reduced from {wanted_ctx} to {ctx} tokens so the whole model stays on the graphics card ({int(budget)} MB free)."
    return out


def plan_for(base_url: str, model: str, wanted_ctx: int, forced_gpu: int | None = None) -> dict:
    """`plan()` for an installed model, from Ollama's own list and the GPU now. Cached for 20 s per (model, context); never raises."""
    key = (base_url, model, int(wanted_ctx), forced_gpu)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < 20:
        return hit[1]
    base = {"num_ctx": int(wanted_ctx), "num_gpu": forced_gpu, "kv": "f16", "fit": "unknown", "est_gpu_pct": None, "note_fa": "", "note_en": ""}
    try:
        from instai.core import hardware

        g = hardware.gpu_status()
        rows = ollama_fit.fetch_models(base_url, int(wanted_ctx), float(g["total_mb"]) if g and g.get("total_mb") else None, timeout=1.5) or []
        row = next((r for r in rows if ollama_fit.same_model(r["name"], model)), None)
        if row and g and g.get("total_mb"):
            free = None
            if g.get("used_mb") is not None:
                loaded = ollama_fit.loaded_one(base_url, model, timeout=1.0)          # the model itself is already counted in "used"
                free = float(g["total_mb"]) - float(g["used_mb"]) + float((loaded or {}).get("vram_mb") or 0)
            base = plan(row, wanted_ctx=int(wanted_ctx), vram_total_mb=float(g["total_mb"]), vram_free_mb=free, kv=kv_type_in_use(), forced_gpu=forced_gpu)
    except Exception:  # noqa: BLE001 - tuning is a bonus; a failure must never stop a job
        log.debug("ollama plan failed", exc_info=True)
    _CACHE[key] = (time.time(), base)
    return base


# ------------------------------------------------------------------ the Ollama server's own settings

def env_status() -> dict:
    """{vars: [{name, recommended, current, where, ok}], ok, kv, restart_needed_hint} for the two recommended settings."""
    from instai.core import gpu_diag

    rows, ok = [], True
    for name, want in RECOMMENDED.items():
        seen = gpu_diag.win_env(name)
        cur = next((v for v in (seen["user"], seen["machine"], seen["process"]) if v not in (None, "")), None)
        good = cur is not None and cur.strip().lower() == want
        ok = ok and good
        rows.append({"name": name, "recommended": want, "current": cur, "ok": good,
                     "where": next((k for k in ("user", "machine", "process") if seen[k] not in (None, "")), None)})
    return {"vars": rows, "ok": ok, "kv": kv_type_in_use(), "windows": sys.platform.startswith("win")}


def apply_env() -> dict:
    """Save the recommended Ollama settings in the Windows USER environment (setx, no administrator needed). They reach Ollama the next time it
    starts. Returns {saved: [...], error}. On other systems nothing is changed."""
    if not sys.platform.startswith("win"):
        return {"saved": [], "error": "not Windows"}
    saved, err = [], ""
    for name, val in RECOMMENDED.items():
        try:
            p = subprocess.run(["setx", name, val], capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if p.returncode == 0:
                saved.append(name)
            else:
                err = (p.stderr or p.stdout or "setx failed").strip()[:200]
        except (OSError, subprocess.SubprocessError) as e:
            err = f"{type(e).__name__}: {e}"
    return {"saved": saved, "error": err}


def ollama_app_path() -> str:
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
        for rel in (r"Programs\Ollama\ollama app.exe", r"Ollama\ollama app.exe"):
            p = os.path.join(base, rel) if base else ""
            if p and os.path.isfile(p):
                return p
    return ""


def restart_ollama(base_url: str, *, force: bool = False) -> dict:
    """Quit and start Ollama again so it reads the new environment. Only when no model is generating (nothing loaded) unless `force`.
    Returns {restarted, reason}. The owner's models and files are not touched."""
    if not sys.platform.startswith("win"):
        return {"restarted": False, "reason": "not_windows"}
    loaded = ollama_fit.loaded(base_url, timeout=2.0)
    if loaded and not force:
        return {"restarted": False, "reason": "busy", "loaded": [m["name"] for m in loaded]}
    app = ollama_app_path()
    if not app:
        return {"restarted": False, "reason": "no_app"}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for exe in ("ollama app.exe", "ollama.exe"):
        subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True, timeout=30, creationflags=flags)
    time.sleep(2)
    subprocess.Popen([app], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0), close_fds=True)
    return {"restarted": True, "reason": ""}
