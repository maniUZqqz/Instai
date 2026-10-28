"""Production jobs: keyframes, narration, video clips, assembly. Each finishes by calling pipeline.advance(), which enqueues
the next missing step or moves the episode forward - so the chain is resumable and re-runnable at any point."""
from __future__ import annotations

from instai.core import settings_store
from instai.jobs.registry import handler
from instai.production import pipeline
from instai.story import services, states
from instai.story.models import Episode


def _ep(ctx) -> tuple[Episode, str]:
    return Episode.objects.select_related("series__page").get(pk=ctx.payload["episode_id"]), ctx.payload.get("mode", "final")


def _image_resource(payload: dict) -> str:
    return "cpu" if str(settings_store.effective("image_engine")) == "placeholder" else "gpu"


def _tts_resource(payload: dict) -> str:
    eng = str(settings_store.effective("tts_engine") or "auto")
    if eng in ("fake", "piper"):
        return "cpu"
    if eng == "moss":
        return "gpu"
    try:
        from instai.providers.tts import get_tts

        return get_tts().resource
    except Exception:  # noqa: BLE001
        return "cpu"


@handler("prod.keyframes", resource=_image_resource, timeout=6 * 3600)
def keyframes(ctx):
    ep, mode = _ep(ctx)
    return pipeline.step_keyframes(ctx, ep, mode)  # the worker calls pipeline.advance() once this job is marked done


@handler("prod.tts", resource=_tts_resource, timeout=3600)
def tts(ctx):
    ep, mode = _ep(ctx)
    return pipeline.step_tts(ctx, ep, mode)


@handler("prod.clips", resource="gpu", timeout=12 * 3600)
def clips(ctx):
    ep, mode = _ep(ctx)
    return pipeline.step_clips(ctx, ep, mode)


@handler("prod.assemble", resource="cpu", timeout=3 * 3600)
def assemble(ctx):
    from instai.assets.models import Asset

    ep, mode = _ep(ctx)
    res = pipeline.step_assemble(ctx, ep, mode)
    video = Asset.objects.get(pk=res["asset_id"])
    ctx.progress(0.97, "quality checks")
    report = pipeline.run_qc(ep, video)
    ep.qc = {**report, "asset_id": video.pk, "mode": mode}
    ep.save(update_fields=["qc", "updated_at"])
    ep.refresh_from_db()
    if ep.state == states.ASSEMBLY:
        services.transition(ep, states.QUALITY_REVIEW, reason="render finished", actor="system")
        if report["ok"]:
            services.transition(ep, states.READY_FOR_APPROVAL, reason=f"quality checks passed ({report['warnings']} warnings)", actor="system")
    return {**res, "qc_ok": report["ok"], "warnings": report["warnings"]}
