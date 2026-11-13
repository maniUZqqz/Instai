"""Real sample images of the styles, made by the GPU (ComfyUI) one by one and stored as `StylePreview`.

The gallery always has a built-in swatch (`preview_svg.py`); this module replaces it with a picture the owner's own image model made from the
style's sample prompt, so he sees what the look really gives. Rules:
* idempotent and resumable: a style whose sample was made from the same prompt is skipped, each finished image is saved at once;
* the work goes through `gpu.compute.run_task` like every other ComfyUI task, so a worker PC can take it and the queue waits when ComfyUI is down;
* the cost is shown before it starts (count x the workflow's expected seconds).
"""
from __future__ import annotations

import hashlib

from django.db import DatabaseError

from . import library
from .models import StylePreview

SIZE = (768, 480)           # the gallery card is 16:10
MIN_STEPS, MAX_STEPS = 12, 30


def prompt_for(style: dict) -> tuple[str, str]:
    """(positive, negative) of a style's sample: its sample subject + the composed look (style + default colour theme)."""
    comp = library.compose(style["key"])
    positive = ", ".join(x for x in (style.get("sample_prompt", ""), comp["positive"]) if x)
    return positive, comp["negative"]


def steps_for(style: dict) -> int:
    try:
        n = int((style.get("gen") or {}).get("steps") or 24)
    except (TypeError, ValueError):
        n = 24
    return max(MIN_STEPS, min(MAX_STEPS, n))


def prompt_hash(style: dict, workflow: str) -> str:
    pos, neg = prompt_for(style)
    return hashlib.sha256(f"{workflow}|{pos}|{neg}|{steps_for(style)}|{SIZE}".encode()).hexdigest()[:20]


def seed_for(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % (2 ** 31 - 1) + 1


def builtin_styles() -> list[dict]:
    return [s for s in library.list_presets("style") if s["builtin"]]


def pending(workflow: str, keys: list[str] | None = None, force: bool = False) -> list[str]:
    """Style keys that still need a sample image (none made yet, or made from an older prompt)."""
    try:
        have = {r.style_key: r.prompt_hash for r in StylePreview.objects.exclude(asset=None)}
    except DatabaseError:
        have = {}
    out = []
    for s in builtin_styles():
        if keys and s["key"] not in keys:
            continue
        if force or have.get(s["key"]) != prompt_hash(s, workflow):
            out.append(s["key"])
    return out


def status(workflow: str, expected_seconds: float = 60.0) -> dict:
    todo = pending(workflow)
    total = len(builtin_styles())
    return {"total": total, "done": total - len(todo), "pending": len(todo), "pending_keys": todo, "workflow": workflow,
            "expected_seconds": round(len(todo) * expected_seconds)}


# ------------------------------------------------------------------ automatic: samples get made by themselves once the GPU side is ready

AUTO_EVERY_S = 600          # look at most every ten minutes
AUTO_RETRY_H = 6            # after a finished (or failed) run wait this long before queueing the rest again
_LAST_AUTO = [0.0]


def auto_queue(force: bool = False):
    """Queue the sample-making job by itself when everything needed is there: a real image engine, ComfyUI answering with the image workflow
    ready, samples still missing, no such job already waiting and none finished in the last hours.

    The owner asked that nothing be left for him to do once the GPU PC is on. The job is queued INSIDE THE NIGHT WINDOW (the Downloads page's
    window, default 02:00-07:00) at low priority, so it never takes the card while he works; it can be switched off with
    `INSTAI_STYLE_SAMPLES_AUTO=0`. Returns the queued job, or None."""
    import os
    import time

    from django.utils import timezone

    from instai.core import settings_store
    from instai.jobs import queue, schedule
    from instai.jobs.models import Job

    if not force and time.time() - _LAST_AUTO[0] < AUTO_EVERY_S:
        return None
    _LAST_AUTO[0] = time.time()
    if os.environ.get("INSTAI_STYLE_SAMPLES_AUTO", "1") == "0" or settings_store.get_setting("style_samples_auto", True) in (False, 0, "0"):
        return None
    if str(settings_store.effective("image_engine")) == "placeholder":
        return None
    from instai.gpu import compute

    wid = str(settings_store.effective("image_workflow"))
    try:
        if not compute.workflow_available(wid) or not pending(wid):
            return None
    except Exception:  # noqa: BLE001 - a look at ComfyUI must never disturb the worker
        return None
    if Job.objects.filter(kind="styles.preview", status__in=[Job.QUEUED, Job.RUNNING]).exists():
        return None
    last = Job.objects.filter(kind="styles.preview").order_by("-id").first()
    if last is not None and (timezone.now() - (last.finished_at or last.created_at)).total_seconds() < AUTO_RETRY_H * 3600:
        return None
    return queue.enqueue("styles.preview", {"keys": [], "force": False, "auto": True}, title="تصویر نمونهٔ سبک‌ها (خودکار)",
                         priority=-10, window=schedule.config()["download_window"])
