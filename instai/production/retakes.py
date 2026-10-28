"""Time-range retake of a rendered episode (the episode editor's "retake"): see instai/render/retake.py for the video maths.
This module is the job: pick the source video, generate the piece through the GPU router, fit, stitch, verify, register as the episode's
new current video (the old one stays as history; `revert` brings it back)."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.core.errors import DomainError
from instai.render import colormatch, ffmpeg
from instai.render import retake as rk

from . import hero
from .models import Retake


def best_source(episode) -> Asset | None:
    for role in ("final", "preview"):
        a = Asset.objects.filter(episode=episode, role=role, is_current=True, kind="video").order_by("-id").first()
        if a:
            return a
    return None


def create(episode, *, start_sec: float, end_sec: float, prompt: str = "", audio_mode: str = "keep", audio_asset: int | None = None,
           source_asset: int | None = None) -> Retake:
    src = Asset.objects.filter(pk=source_asset, episode=episode, kind="video").first() if source_asset else best_source(episode)
    if src is None:
        raise DomainError("not_ready", "برای این قسمت هنوز ویدئویی ساخته نشده است.", http_status=409)
    if audio_mode not in rk.AUDIO_MODES:
        raise DomainError("validation_error", "حالت صدا نامعتبر است.", http_status=400, details={"audio_mode": ["invalid"]})
    if audio_mode == "replace" and not Asset.objects.filter(pk=audio_asset, kind="audio").exists():
        raise DomainError("validation_error", "برای جایگزینیِ صدا یک فایل صوتی انتخاب کنید.", http_status=400, details={"audio_asset": ["required"]})
    try:
        info = ffmpeg.probe(asset_storage.storage.path_for(src.path))
        plan = rk.plan_range(info, float(start_sec), float(end_sec), cut=audio_mode == "cut")
        if audio_mode != "cut" and (plan.start < 1 or plan.end >= plan.total_frames):
            raise rk.RetakeError("a regenerated range cannot touch the very first or last frame (the model needs a frame on each side)")
    except (rk.RetakeError, ValueError) as e:
        raise DomainError("validation_error", f"بازه نامعتبر است: {e}", http_status=400, details={"range": [str(e)]}) from e
    return Retake.objects.create(episode=episode, source_asset=src, start_sec=plan.t_start, end_sec=plan.t_end, prompt=prompt, audio_mode=audio_mode,
                                 seam={"audio_asset": audio_asset} if audio_asset else {})


def run(ctx, retake: Retake) -> dict:
    ep = retake.episode
    src = retake.source_asset
    src_path = asset_storage.storage.path_for(src.path)
    info = ffmpeg.probe(src_path)
    cut = retake.audio_mode == "cut"
    plan = rk.plan_range(info, retake.start_sec, retake.end_sec, cut=cut)
    Retake.objects.filter(pk=retake.pk).update(status="running", error="")
    work = Path(tempfile.mkdtemp(prefix="retake-", dir=settings.MEDIA_ROOT))
    result: dict = {"mode": retake.audio_mode, "frames": plan.n, "seconds": round(plan.seconds, 3)}
    try:
        piece = None
        if not cut:
            ctx.progress(0.05, "boundary frames")
            b, a = rk.extract_frame(src_path, plan.before, plan.fps, work / "before.png"), rk.extract_frame(src_path, plan.after, plan.fps, work / "after.png")
            g = hero.generate_chain(ctx, page=ep.series.page, start_path=b, end_path=a, duration=(plan.n + 1) / plan.fps, prompt=retake.prompt or "continue the motion naturally, keep the same character and style",
                                    negative="", seed=int(retake.pk) * 7 + 1, work=work)
            ctx.progress(0.7, "colour match and fit")
            ref = rk.reference_between(b, a, work / "ref.png")
            matched = work / "matched.mp4"
            colour = colormatch.match_clip(g["video"], ref, matched, ctx=ctx)
            piece = rk.fit_piece(matched, plan, src_path, work / "fitted.mp4", edge=1, ctx=ctx)
            result.update(device="+".join(dict.fromkeys(g["devices"])), colour=colour, segments=g["segments"], workflow=g["workflow"], gpu_seconds=round(g["seconds"], 1))
        audio_file = None
        aid = (retake.seam or {}).get("audio_asset")
        if retake.audio_mode == "replace" and aid:
            audio_file = asset_storage.storage.path_for(Asset.objects.get(pk=aid).path)
        ctx.progress(0.85, "stitching")
        out = work / "retaken.mp4"
        rk.stitch(src_path, piece, plan, out, audio_mode=retake.audio_mode, audio_file=audio_file, ctx=ctx)
        ver = rk.verify(info, out, plan, retake.audio_mode)
        seams = {"start": rk.seam_ratio(out, plan.start), **({} if cut else {"end": rk.seam_ratio(out, plan.end)})}
        result.update(verify=ver, seam=seams)
        if not ver["ok"]:
            raise ffmpeg.FFmpegError(f"the stitched video does not match the plan (duration error {ver['duration_error']} s, frames {ver['frames']} vs {ver['expected_frames']})")
        rel = f"episodes/{ep.pk}/renders/{src.role}-retake{retake.pk}.mp4"
        asset = asset_storage.register(out, rel, kind="video", role=src.role, page=ep.series.page, episode=ep, input_hash=src.input_hash, loudness=True,
                                       provenance={**(src.provenance or {}), "retake": retake.pk, "retake_of": src.pk, "range": [round(plan.t_start, 3), round(plan.t_end, 3)],
                                                   "audio_mode": retake.audio_mode, "expected_duration": ver["expected_duration"]})
        Retake.objects.filter(pk=retake.pk).update(status="done", result_asset=asset, seam={**(retake.seam or {}), **result})
        try:                                              # the new video gets the same technical checks as a fresh render
            from . import pipeline

            report = pipeline.run_qc(ep, asset)
            ep.qc = {**report, "asset_id": asset.pk, "mode": src.role, "retake": retake.pk}
            ep.save(update_fields=["qc", "updated_at"])
        except Exception as e:  # noqa: BLE001 - QC is informative here, never a reason to lose the retake
            result["qc_error"] = str(e)[:200]
        return {**result, "asset_id": asset.pk}
    except BaseException as e:
        Retake.objects.filter(pk=retake.pk).update(status="failed", error=str(e)[:500])
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def revert(retake: Retake) -> None:
    """Make the video from before this retake the episode's current video again (the retaken one stays in the history)."""
    if not retake.result_asset_id:
        raise DomainError("conflict", "این بازسازی هنوز نتیجه‌ای ندارد.", http_status=409)
    Asset.objects.filter(pk=retake.result_asset_id).update(is_current=False)
    Asset.objects.filter(pk=retake.source_asset_id).update(is_current=True)
