"""The AI background of a cover: the image model (ComfyUI, FLUX by default) draws the SCENE behind the layout; Pillow draws every letter on top.

* It goes through ``instai.gpu.compute.run_task`` like every other GPU task, so a paired worker PC can take it and the GPU arbiter keeps one heavy task per card.
* A missing ComfyUI or model is a WAIT, never a failure: ``compute.require_workflow`` raises ``ProviderError(wait="comfy_down")`` and the job goes back to the queue with a Persian reason. The
  cover is already finished with the procedural background by then (``service.make`` stores it first), and the job completes it by itself when ComfyUI is up (NM's WAITING_BG idea).
* The prompt is the layout's scene line + the image prompt of the series look (``styles.library.compose_for_series``) + an optional scene line of the owner. The negative prompt is the look's negative
  plus "text, letters": the model must never be asked for Persian text (it cannot draw it); the cover text is always drawn by Pillow.
* Demo mode (``image_engine == "placeholder"``) never asks a model: the cover keeps the procedural gradient background and says so.

SOURCE: adapted from NMarketing:backend/apps/thumbs/aibg.py @ v3.02 (c23f861) (the idea: a prompt per layout, English only, "no text", the WAITING_BG state, one background per design);
the NM node jobs and photo library are replaced by ``instai.gpu.compute`` and ``instai.assets``.
"""
from __future__ import annotations

import hashlib
import math
import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.core import settings_store
from instai.providers.base import ProviderError

from .engine import hooks

NEGATIVE_TAIL = "text, letters, words, watermark, logo, people, face, signature"
PROBE_PROMPT = "soft abstract gradient background with gentle bokeh light, dark teal and orange, no text, no people"


def engine_state() -> dict:
    """What the cover maker may do with the image model right now (for the UI): {engine, workflow, demo, available}."""
    from instai.gpu import compute

    engine = str(settings_store.effective("image_engine") or "auto")
    wid = str(settings_store.effective("image_workflow") or "")
    demo = engine == "placeholder"
    try:
        available = (not demo) and bool(wid) and compute.workflow_available(wid)
    except Exception:  # noqa: BLE001 - a detection problem is "not available", never an error
        available = False
    return {"engine": engine, "workflow": wid, "demo": demo, "available": available}


def size_for(width: int, height: int, megapixels: float = 1.0) -> tuple[int, int]:
    """The generation size for a format: the same aspect, about ``megapixels`` MP, both sides a multiple of 16 (the model's grid); the cover covers it to its exact size later."""
    aspect = width / float(height)
    w = math.sqrt(megapixels * 1_000_000 * aspect)
    h = w / aspect
    return max(256, int(round(w / 16.0)) * 16), max(256, int(round(h / 16.0)) * 16)


def prompts(style: str, look: dict, scene: str = "") -> tuple[str, str]:
    positive = hooks.bg_prompt(style, (look or {}).get("positive", ""), scene)
    negative = ", ".join(x for x in ((look or {}).get("negative", ""), NEGATIVE_TAIL) if x)
    return positive, negative


def seed_for(cover_pk: int, positive: str) -> int:
    return int(hashlib.sha256(f"{cover_pk}|{positive}".encode()).hexdigest()[:8], 16) % (2 ** 31)


def prompt_hash(positive: str, negative: str, size: tuple[int, int], wid: str) -> str:
    return hashlib.sha256(f"{positive}|{negative}|{size}|{wid}".encode()).hexdigest()[:16]


def _run(ctx, wid: str, inputs: dict, work: Path) -> tuple[Path, dict]:
    from instai.gpu import compute
    from instai.production import hero
    from instai.providers.comfy.workflows import get_workflow

    compute.require_workflow(wid)                      # the GPU PC is off / ComfyUI is not up: the job WAITS and resumes by itself
    spec = get_workflow(wid)
    res = compute.run_task(ctx, "comfy.graph", {"graph": spec.build(inputs), "workflow": wid, "timeout": 1800, "expected": spec.expected_seconds})
    try:
        pics = res.of_kind(*hero.IMAGE_SUFFIX)
        if not pics:
            raise ProviderError("ComfyUI returned no image", retryable=True)
        out = work / "bg.png"
        shutil.move(str(pics[0]), out)
        return out, {**spec.provenance(inputs), "engine": "comfyui", "device": res.device, "seconds": round(res.seconds, 1)}
    finally:
        res.cleanup()


def generate(ctx, cover, spec: dict, look: dict, *, scene: str = ""):
    """Draw the background of ``cover`` and register it as an Asset. Raises ``ProviderError`` (a WAIT) when no PC can run the image workflow now."""
    from .engine import formats as F

    st = engine_state()
    wid = st["workflow"]
    fmt = F.get(spec["format"])
    size = size_for(fmt.w, fmt.h)
    positive, negative = prompts(spec["style"], look, scene)
    seed = seed_for(cover.pk, positive)
    work = Path(tempfile.mkdtemp(prefix="coverbg-", dir=settings.MEDIA_ROOT))
    try:
        out, prov = _run(ctx, wid, {"prompt": positive, "negative_prompt": negative, "width": size[0], "height": size[1], "seed": seed}, work)
        h = prompt_hash(positive, negative, size, wid)
        return asset_storage.register(out, f"covers/{cover.pk}/background-{h}.png", kind="image", role="reference", page=cover.page,
                                      provenance={**prov, "cover": cover.pk, "style": spec["style"], "prompt": positive, "negative": negative, "seed": seed, "size": list(size),
                                                  "note": "AI background of a cover; the text of the cover is drawn by Pillow, never by the model"})
    finally:
        shutil.rmtree(work, ignore_errors=True)


def probe(ctx, work: Path) -> dict:
    """The GPU self-test: ONE small 512x512 background through the real path. Raises ProviderError (wait) when ComfyUI / the model is not there yet."""
    st = engine_state()
    if st["demo"]:
        return {"demo": True}
    wid = st["workflow"]
    out, prov = _run(ctx, wid, {"prompt": PROBE_PROMPT + hooks.BG_SUFFIX, "negative_prompt": NEGATIVE_TAIL, "width": 512, "height": 512, "seed": 7}, work)
    return {"path": out, "workflow": wid, **prov}
