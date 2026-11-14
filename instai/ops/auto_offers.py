"""Optional downloads that the owner's own brief depends on are fetched BY THEMSELVES, in the night window, when there is room for them.

The owner asked that nothing be left for him to do once the GPU PC is on. Consistent AI-drawn characters (the open counterpart of IP-Adapter / PuLID: the
model SEES the approved model sheets) need Qwen-Image-Edit, about 31 GB, Apache-2.0. Until it is on the PC the strategy is "not ready" and its self-test is
skipped - which is a task left to the owner. So this module queues the download by itself, with these guards (reasons in docs/DECISIONS.md):

* only the offers listed in `AUTO` (never a model whose licence is non-commercial or unclear: those keep needing the owner's confirmation);
* only at night: the job carries the download window of the Downloads page (default 02:00-07:00 local time), it resumes from the partial files the next night;
* only when the disk of the ComfyUI folder keeps `MARGIN` free after the download - otherwise it waits and says so on the Models page (never a full disk);
* never against his will: cancelling the job on the queue page means "no" - it is not started again by itself (the button on the Models page still works);
  a failed download is tried again after `RETRY_S`; the switch `INSTAI_AUTO_OFFERS=0` or the setting `auto_offers` turns the whole thing off;
* nothing in demo mode (image engine "placeholder") and nothing when no ComfyUI folder is known.

The state of each offer is part of the Models page payload (`offer["auto"]`), so the owner sees "will download tonight", "waiting for disk space" and so on.
"""
from __future__ import annotations

import logging
import os
import shutil
import time

from django.utils import timezone

log = logging.getLogger("instai.auto_offers")

AUTO = ("qwen_edit",)               # offer ids (manifests: packages with an "offer" block) that are fetched by themselves
AUTO_EVERY_S = 600                  # look at most every ten minutes
RETRY_S = 12 * 3600                 # after a failed download wait this long (the downloader resumes from the partial files)
MARGIN = 25 * 1024 ** 3             # free space that must remain on the ComfyUI drive after the download
GB = 1024 ** 3
_LAST_AUTO = [0.0]


def switched_off() -> bool:
    from instai.core import settings_store

    return os.environ.get("INSTAI_AUTO_OFFERS", "1") == "0" or settings_store.get_setting("auto_offers", True) in (False, 0, "0")


def free_bytes() -> int | None:
    """Free space on the drive that holds the ComfyUI folder (where the files will land); None when it cannot be told."""
    from instai.core import runtime

    root = runtime.comfyui_dir()
    try:
        return int(shutil.disk_usage(root).free) if root else None
    except OSError:
        return None


def status(offer: dict) -> dict:
    """What the automatic download of this offer is doing: {state, ...}. States: manual (never automatic), off, complete, no_comfyui, queued, declined,
    failed_recently, low_disk, ready (will be queued at the next look)."""
    from instai.core import runtime
    from instai.jobs.models import Job

    oid = offer["id"]
    if oid not in AUTO:
        return {"state": "manual"}
    if offer.get("complete") and all(n.get("complete") for n in offer.get("needs", [])):
        return {"state": "complete"}
    if switched_off():
        return {"state": "off"}
    if not runtime.comfyui_dir():
        return {"state": "no_comfyui"}
    jobs = list(Job.objects.filter(kind="downloads.run", payload__offer=oid).order_by("-id")[:20])
    live = next((j for j in jobs if j.status in (Job.QUEUED, Job.RUNNING)), None)
    if live is not None:
        return {"state": "queued", "job": live.pk, "window": (live.payload or {}).get("schedule", {}).get("window", ""), "auto": bool((live.payload or {}).get("auto")),
                "running": live.status == Job.RUNNING}
    if any(j.status == Job.CANCELLED for j in jobs):
        return {"state": "declined"}                      # he cancelled it: that is a "no" and it is never started again by itself
    last = jobs[0] if jobs else None
    if last is not None and last.status == Job.FAILED and (timezone.now() - (last.finished_at or last.created_at)).total_seconds() < RETRY_S:
        return {"state": "failed_recently", "job": last.pk}
    need, free = int(offer.get("missing_size") or 0), free_bytes()
    if free is not None and free < need + MARGIN:
        return {"state": "low_disk", "free_gb": round(free / GB, 1), "need_gb": round((need + MARGIN) / GB, 1)}
    return {"state": "ready", "need_gb": round(need / GB, 1)}


def auto_queue(force: bool = False):
    """Queue the download of the first offer whose state is `ready` (called from the automation tick). Returns the job or None."""
    from instai.core import model_status, settings_store
    from instai.ops import downloads

    if not force and time.time() - _LAST_AUTO[0] < AUTO_EVERY_S:
        return None
    _LAST_AUTO[0] = time.time()
    if os.environ.get("INSTAI_TESTING") == "1" and not force:          # the test suite never gets surprise downloads; the tests of this module pass force=True
        return None
    if switched_off() or str(settings_store.effective("image_engine")) == "placeholder":
        return None
    for offer in model_status.offers():
        st = offer.get("auto") or status(offer)
        if st["state"] != "ready":
            continue
        parts = [n["id"] for n in offer["needs"] if not n["complete"]] + [offer["id"]]
        job = downloads.start_packages(parts, "دانلود خودکار شبانه: " + offer["name"], when={"mode": "window"},
                                       extra={"offer": offer["id"], "auto": True, "auto_at": timezone.now().isoformat()}, key_extra=f":offer:{offer['id']}")
        log.info("automatic download of %s queued (job %s)", offer["id"], job.pk)
        return job
    return None
