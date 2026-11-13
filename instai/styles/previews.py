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
# ONE fixed, neutral subject for every sample, so the owner compares the LOOKS and not the subjects (the style's own `sample_prompt` stays as a
# showcase idea in the details panel). A person in a room works for a drawing, a render, a puppet and a photograph alike.
SUBJECT = "a young person sitting at a desk in a small cozy room with a window, a lamp and a plant, simple friendly character, medium shot"


def prompt_for(style: dict) -> tuple[str, str]:
    """(positive, negative) of a style's sample: the one fixed subject + the composed look (style + default colour theme)."""
    comp = library.compose(style["key"])
    positive = ", ".join(x for x in (SUBJECT, comp["positive"]) if x)
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

AUTO_EVERY_S = 300          # look at most every five minutes
AUTO_CHUNK = 12             # styles per automatic job: about ten minutes of GPU, so the owner's own jobs never wait long behind it
AUTO_NEXT_S = 240           # after a chunk that made pictures the next one may follow this soon
AUTO_RETRY_H = 6            # after a failed or empty run wait this long before trying again
_LAST_AUTO = [0.0]


def auto_queue(force: bool = False):
    """Queue the sample-making job by itself when everything needed is there: a real image engine, ComfyUI answering with the image workflow
    ready, samples still missing and no such job already waiting.

    The owner asked that nothing be left for him to do once the GPU PC is on. The work is cut into chunks of `AUTO_CHUNK` styles at low priority
    (his own jobs go first and wait at most one chunk), each finished picture is kept, and the next chunk follows a few minutes after the
    previous one made pictures. The download schedule he chose on the Downloads page (a night window, when he picked one) is respected.
    It can be switched off with `INSTAI_STYLE_SAMPLES_AUTO=0` or the setting `style_samples_auto`. Returns the queued job, or None."""
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
        if not compute.workflow_available(wid):
            return None
        todo = pending(wid)
    except Exception:  # noqa: BLE001 - a look at ComfyUI must never disturb the worker
        return None
    if not todo:
        return None
    if Job.objects.filter(kind="styles.preview", status__in=[Job.QUEUED, Job.RUNNING]).exists():
        return None
    last = Job.objects.filter(kind="styles.preview", payload__auto=True).order_by("-id").first()
    if last is not None:
        age = (timezone.now() - (last.finished_at or last.created_at)).total_seconds()
        made = (last.result or {}).get("made", 0) if last.status == Job.SUCCEEDED else 0
        if age < (AUTO_NEXT_S if made else AUTO_RETRY_H * 3600):
            return None
    return queue.enqueue("styles.preview", {"keys": todo[:AUTO_CHUNK], "force": False, "auto": True},
                         title=f"تصویر نمونهٔ سبک‌ها (خودکار، {min(AUTO_CHUNK, len(todo))} از {len(todo)} مانده)",
                         priority=-10, window=schedule.resolve(None)["window"])
