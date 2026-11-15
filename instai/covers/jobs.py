"""The cover job: ``covers.make`` renders the A/B versions of a design (CPU), stores them, makes the first one the episode's cover and - when the owner asked for an AI background -
draws it on the GPU as soon as ComfyUI is available (a missing ComfyUI is a WAIT: the finished cover stays, the job resumes by itself)."""
from __future__ import annotations

from instai.jobs import describe
from instai.jobs.registry import handler

describe.KIND_TEXT.update({
    "covers.make": ("ساخت کاور قسمت یا سریال", "Making an episode or series cover"),
})


def _resource(payload: dict) -> str:
    """The cover itself is CPU work; only the AI background is GPU work, and only when the image model is a real one."""
    from instai.core import settings_store

    if not payload.get("ai_background") or str(settings_store.effective("image_engine")) == "placeholder":
        return "cpu"
    return "gpu"


@handler("covers.make", resource=_resource, timeout=7200)
def covers_make(ctx):
    from instai.jobs import queue
    from instai.jobs.context import JobCancelled, JobDeferred
    from instai.providers.base import ProviderError

    from . import service
    from .models import Cover

    cover = Cover.objects.select_related("page", "series", "episode__series").get(pk=ctx.payload["cover_id"])
    try:
        if ctx.payload.get("more"):
            service.add_variants(cover, int(ctx.payload.get("more")), ctx)
            return {"cover_id": cover.pk, "variants": len(cover.variants), "status": cover.status}
        return service.make(cover, ctx)
    except (JobDeferred, JobCancelled):
        raise
    except ProviderError as exc:
        if exc.wait or exc.code in queue.WAIT_CODES:             # not a failure: the job waits and resumes (the finished cover stays usable)
            raise
        _failed(cover, exc)
        raise
    except Exception as exc:  # noqa: BLE001 - the design must not stay "rendering" for ever
        _failed(cover, exc)
        raise


def _failed(cover, exc) -> None:
    from .models import Cover

    Cover.objects.filter(pk=cover.pk).update(status="failed", error=str(exc)[:500])
