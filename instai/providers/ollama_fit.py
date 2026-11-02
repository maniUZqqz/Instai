"""Which Ollama model fits this PC's graphics card, and where a loaded model really runs (GPU or CPU).

Ollama puts as many layers of a model on the GPU as fit into the free VRAM and runs the rest on the CPU. A 32B model on a 12 GB card is
~40% on the GPU and 60% on the CPU: Task Manager shows the GPU nearly idle and generation takes minutes. So InstAI
  * estimates before running whether a model fits (`fit_model`), and prefers one that fits when the owner chose none (`pick_default`);
  * reads the truth after loading from Ollama's /api/ps: size_vram / size (`loaded`, `placement_of`).
The estimate is a rule of thumb (weights + KV cache for the context + CUDA buffers); /api/ps is what counts.
"""
from __future__ import annotations

import re

import requests

# VRAM the desktop and the CUDA context keep for themselves, and the compute buffers of one running model
RESERVE_MB = 800
BUFFERS_MB = 700
# a model is chosen as the default only when it fits with this much room to spare (speed and a safety margin)
COMFORT = 0.92

EMBEDDING_HINTS = ("embed", "bge-", "minilm", "nomic", "e5-", "rerank", "arctic-embed", "granite-embedding")
VISION_HINTS = ("-vl", "vision", "llava", "moondream", "minicpm-v", "bakllava", "mllama", "paligemma")
SPECIAL_HINTS = ("translategemma", "coder", "guard", "shield", "-math", "codellama", "starcoder")
REASONER_HINTS = ("qwq", "deepseek-r1", "thinking", "magistral", "r1-", "reasoner")


def parse_params_b(text) -> float | None:
    """'8.2B' -> 8.2, '566M' -> 0.566, '7B' -> 7.0."""
    m = re.match(r"^\s*([\d.]+)\s*([BbMmKk]?)", str(text or ""))
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2).lower()
    return v / 1000 if unit == "m" else (v / 1e6 if unit == "k" else v)


def kind_of(name: str, details: dict | None = None) -> str:
    """text | vision | embedding | special (translation / coding / guard models are not general story writers)."""
    low = name.lower()
    details = details or {}
    fam = str(details.get("family") or "").lower()
    fams = [str(x).lower() for x in (details.get("families") or [])]
    if any(h in low for h in EMBEDDING_HINTS) or "bert" in fam:
        return "embedding"
    if any(h in low for h in VISION_HINTS) or "clip" in fams or "mllama" in fam:
        return "vision"
    if any(h in low for h in SPECIAL_HINTS):
        return "special"
    return "text"


def is_reasoner(name: str) -> bool:
    low = name.lower()
    return any(low.startswith(h) or h in low for h in REASONER_HINTS)


def kv_cache_mb(ctx: int, params_b: float | None) -> float:
    """Rough KV-cache size: ~0.14 MB per token for an 8B model, ~0.26 for a 32B one (grouped-query attention)."""
    return ctx * (0.1 + 0.005 * (params_b or 8.0))


def fit_model(size_mb: float, params_b: float | None, ctx: int, vram_mb: float | None) -> dict:
    """{fit: gpu|partial|cpu|unknown, est_gpu_pct, comfortable}. `partial` = at least half of the weights on the GPU; `cpu` = mostly CPU."""
    if not vram_mb or not size_mb:
        return {"fit": "unknown", "est_gpu_pct": None, "comfortable": False}
    kv = kv_cache_mb(ctx, params_b)
    budget = vram_mb - RESERVE_MB
    need = size_mb + kv + BUFFERS_MB
    if need <= budget:
        return {"fit": "gpu", "est_gpu_pct": 100, "comfortable": need <= budget * COMFORT}
    pct = int(max(0.0, min(99.0, (budget - kv - BUFFERS_MB) / size_mb * 100)))
    return {"fit": "partial" if pct >= 50 else "cpu", "est_gpu_pct": pct, "comfortable": False}


def fetch_models(base_url: str, ctx: int, vram_mb: float | None, timeout: float = 2.0) -> list[dict] | None:
    """Every installed model with size and fit (None when Ollama does not answer)."""
    try:
        r = requests.get(base_url.rstrip("/") + "/api/tags", timeout=timeout)
        r.raise_for_status()
        tags = r.json().get("models", [])
    except Exception:  # noqa: BLE001
        return None
    out = []
    for m in tags:
        name = m.get("name") or m.get("model") or ""
        if not name:
            continue
        d = m.get("details") or {}
        size_mb = round((m.get("size") or 0) / 1048576)
        params = parse_params_b(d.get("parameter_size"))
        out.append({"name": name, "size_mb": size_mb, "params": d.get("parameter_size"), "params_b": params, "quant": d.get("quantization_level"),
                    "family": d.get("family"), "kind": kind_of(name, d), "reasoner": is_reasoner(name), **fit_model(size_mb, params, ctx, vram_mb)})
    return out


def pick_default(models: list[dict], vram_mb: float | None) -> dict | None:
    """The model InstAI uses when the owner chose none: {model, partial, reason_fa, reason_en}; None when nothing can chat.

    A general text model that fits the GPU with room to spare wins (the biggest of them; thinking models last, because they spend minutes
    "thinking" before the first word). When none fits, the one with the largest share on the GPU, and `partial` is set."""
    texts = [m for m in models if m["kind"] == "text"] or [m for m in models if m["kind"] == "special"] or [m for m in models if m["kind"] == "vision"]
    if not texts:
        return None
    if not vram_mb:
        # no GPU information: the owner's long-standing preference order, then the smallest model
        for pref in ("qwen3:8b", "qwen3.5:9b", "gemma3:12b", "qwen3:14b", "qwen3.5:4b"):
            hit = next((m for m in texts if m["name"] == pref), None)
            if hit:
                return {"model": hit["name"], "partial": False, "reason_fa": f"مدل «{hit['name']}» انتخاب شد (کارت گرافیک پیدا نشد، پس اندازه‌گیری ممکن نبود).",
                        "reason_en": f"'{hit['name']}' is used (no GPU was found, so fit could not be measured)."}
        hit = min(texts, key=lambda m: (m["reasoner"], m["size_mb"] or 10 ** 9, m["name"]))
        return {"model": hit["name"], "partial": False, "reason_fa": f"مدل «{hit['name']}» انتخاب شد (کوچک‌ترین مدل نصب‌شده).",
                "reason_en": f"'{hit['name']}' is used (the smallest installed model)."}
    comfy = [m for m in texts if m["fit"] == "gpu" and m["comfortable"]]
    pool = comfy or [m for m in texts if m["fit"] == "gpu"]
    if pool:
        hit = sorted(pool, key=lambda m: (m["reasoner"], -(m["size_mb"] or 0), m["name"]))[0]
        gb = f"{(hit['size_mb'] or 0) / 1024:.1f}"
        return {"model": hit["name"], "partial": False,
                "reason_fa": f"مدل «{hit['name']}» ({_fa(gb)} گیگابایت) کاملاً در حافظهٔ کارت گرافیک جا می‌شود؛ پس روی GPU و سریع کار می‌کند.",
                "reason_en": f"'{hit['name']}' ({gb} GB) fits completely in the graphics card memory, so it runs on the GPU and fast."}
    hit = sorted(texts, key=lambda m: (-(m["est_gpu_pct"] or 0), m["reasoner"], m["size_mb"] or 0, m["name"]))[0]
    pct = hit["est_gpu_pct"]
    return {"model": hit["name"], "partial": True,
            "reason_fa": f"هیچ مدل نصب‌شده‌ای کاملاً در حافظهٔ کارت گرافیک جا نمی‌شود. «{hit['name']}» از همه بیشتر روی GPU می‌افتد"
                         + (f" (حدود {_fa(pct)}٪)" if pct is not None else "") + " و بقیه‌اش روی CPU کند کار می‌کند. برای سرعت، یک مدل کوچک‌تر مثل qwen3:8b نصب کنید.",
            "reason_en": f"No installed model fits completely in the graphics card memory. '{hit['name']}' puts the largest share on the GPU"
                         + (f" (about {pct}%)" if pct is not None else "") + " and runs the rest slowly on the CPU. For speed, install a smaller model such as qwen3:8b."}


def _fa(n) -> str:
    return str(n).translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫"))


def placement_of(size: int | float | None, size_vram: int | float | None) -> dict:
    """{gpu_pct, placement} of a loaded model from Ollama's /api/ps numbers (bytes)."""
    if not size:
        return {"gpu_pct": None, "placement": "unknown"}
    pct = int(round(100.0 * float(size_vram or 0) / float(size)))
    pct = max(0, min(100, pct))
    return {"gpu_pct": pct, "placement": "gpu" if pct >= 95 else ("cpu" if pct <= 5 else "mixed")}


def loaded(base_url: str, timeout: float = 2.0) -> list[dict] | None:
    """The models Ollama holds in memory right now with their GPU share (None when Ollama does not answer)."""
    try:
        r = requests.get(base_url.rstrip("/") + "/api/ps", timeout=timeout)
        r.raise_for_status()
        rows = r.json().get("models", [])
    except Exception:  # noqa: BLE001
        return None
    out = []
    for m in rows:
        size, vram = m.get("size") or 0, m.get("size_vram") or 0
        p = placement_of(size or vram, vram)           # an old Ollama without "size": what is in VRAM is all we know
        out.append({"name": m.get("name") or m.get("model") or "", "size_mb": round((size or vram) / 1048576), "vram_mb": round(vram / 1048576),
                    "gpu_pct": p["gpu_pct"] if p["gpu_pct"] is not None else 0,
                    "placement": p["placement"] if p["placement"] != "unknown" else "cpu", "context": m.get("context_length"),
                    "expires": m.get("expires_at")})
    return out


def same_model(a: str, b: str) -> bool:
    """'qwen3' and 'qwen3:latest' are the same model."""
    a, b = a.strip(), b.strip()
    return a == b or (a if ":" in a else a + ":latest") == (b if ":" in b else b + ":latest")


def loaded_one(base_url: str, model: str, timeout: float = 2.0) -> dict | None:
    return next((r for r in (loaded(base_url, timeout) or []) if same_model(r["name"], model)), None)
