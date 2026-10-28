"""Hero shots: Wan 2.2 image-to-video from an approved reference keyframe, first/last-frame transitions, chained extension, colour match
to the reference and an embedding-similarity QC against the keyframe and the character sheet. Every ComfyUI call goes through the GPU
router (`gpu.compute`), so shots of one episode - or of two episodes - run on this PC and on a worker PC at the same time."""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.gpu import compute
from instai.providers.base import ProviderError
from instai.providers.comfy.workflows import get_workflow
from instai.render import colormatch, ffmpeg

from . import consistency

HERO_TECHNIQUES = ("wan_i2v", "wan_flf")
FPS = 16
SEG_MAX_FRAMES = 81                       # ~5 s at 16 fps: what one Wan pass makes
VIDEO_SUFFIX = (".mp4", ".webm", ".mov", ".mkv")
IMAGE_SUFFIX = (".png", ".jpg", ".jpeg", ".webp")
ANIME_WORKFLOW = {"wan22": "wan22_i2v_a14b_fp8", "anisora": "anisora_v32_i2v_gguf", "animegen": "animegen_i2v_gguf"}
FLF_WORKFLOW = "wan22_flf_a14b_fp8"
REF_WORKFLOWS = ("qwen_image_edit_ref", "flux_dev_fp8_img2img")     # preferred first; availability decides
NEG = "flicker, jitter, sudden camera shake, morphing, unstable identity, blurry, low quality, deformed, extra limbs, subtitles, watermark, text artifacts"


# ------------------------------------------------------------------ which models

def anime_model(page) -> str:
    from .models import PageProductionConfig

    cfg = PageProductionConfig.objects.filter(page=page).first()
    return cfg.anime_model if cfg and cfg.anime_model in ANIME_WORKFLOW else "wan22"


def i2v_workflow(page) -> tuple[str, str | None]:
    """(workflow id, note). The page's anime default (set by the comparison vote) if a device can run it, else plain Wan 2.2."""
    want = ANIME_WORKFLOW[anime_model(page)]
    if want != ANIME_WORKFLOW["wan22"] and not compute.workflow_available(want):
        return ANIME_WORKFLOW["wan22"], f"{want} is not available on any PC; plain Wan 2.2 used"
    return want, None


def reference_workflow() -> str | None:
    for wid in REF_WORKFLOWS:
        if compute.workflow_available(wid):
            return wid
    return None


# ------------------------------------------------------------------ references

def reference_sheet(shot, ep) -> tuple[Path | None, object | None]:
    """The approved character sheet (a file) of the shot's character: the speaker, else a character of the scene, else of the page."""
    from instai.pages.models import Character, CharacterReference

    page = ep.series.page
    chars: list = []
    if shot.speaker:
        c = Character.objects.filter(page=page, name=shot.speaker).first()
        if c:
            chars.append(c)
    chars += list(shot.scene.characters.all()) + list(page.characters.all())
    for c in chars:
        ref = (CharacterReference.objects.filter(character=c, approved=True, kind__in=("sheet", "image")).exclude(asset=None).select_related("asset")
               .order_by("kind", "-id").first())
        if ref and asset_storage.storage.exists(ref.asset.path):
            return asset_storage.storage.path_for(ref.asset.path), ref
    return None, None


def keyframe_inputs(shot, ep, base_inputs: dict, files: dict) -> tuple[str, dict, dict, str]:
    """(workflow id, inputs, input files, note) for a keyframe: from the character sheet when the shot is a hero shot and a sheet exists."""
    sheet, _ = reference_sheet(shot, ep) if shot.technique in HERO_TECHNIQUES else (None, None)
    wid = reference_workflow() if sheet else None
    if not sheet or not wid:
        return "", base_inputs, files, ("no approved character sheet: the keyframe comes from the prompt only" if shot.technique in HERO_TECHNIQUES else "")
    prompt = base_inputs["prompt"] + ", keep exactly the same character design, face, hair and outfit as in the reference image"
    inputs = {"prompt": prompt, "image": "@input:ref.png", "seed": base_inputs.get("seed"), "negative_prompt": base_inputs.get("negative_prompt", "")}
    if wid == "flux_dev_fp8_img2img":
        inputs.update(width=base_inputs["width"], height=base_inputs["height"], steps=base_inputs.get("steps", 24))
    return wid, inputs, {"ref.png": sheet}, f"keyframe edited from the character sheet with {wid}"


# ------------------------------------------------------------------ video helpers

def segment_frames(duration: float) -> list[int]:
    """Frame counts (4k+1, <= 81) of the chained Wan passes that cover `duration` seconds."""
    n = max(1, math.ceil(duration / (SEG_MAX_FRAMES / FPS) - 1e-9))
    each = duration / n
    return [max(9, min(SEG_MAX_FRAMES, int(round(each * FPS / 4)) * 4 + 1)) for _ in range(n)]


def last_frame(video: Path, out_png: Path) -> Path:
    ff, _ = ffmpeg.binaries()
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-sseof", "-0.15", "-i", str(video), "-update", "1", "-frames:v", "1", str(out_png)],
                   capture_output=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if not out_png.exists():       # very short clip: take the first frame instead
        ffmpeg.run(["-i", str(video), "-frames:v", "1", str(out_png)])
    return out_png


def concat_segments(parts: list[Path], out: Path, fps: int = FPS) -> Path:
    """Join chained passes: every pass after the first starts from the previous one's last frame, so its first frame is dropped."""
    if len(parts) == 1:
        shutil.copyfile(parts[0], out)
        return out
    args: list[str] = []
    for p in parts:
        args += ["-i", str(p)]
    chains = []
    for i in range(len(parts)):
        trim = "trim=start_frame=1," if i else ""
        chains.append(f"[{i}:v]{trim}setpts=PTS-STARTPTS,fps={fps},setsar=1,format=yuv420p[s{i}]")
    graph = ";".join(chains) + ";" + "".join(f"[s{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[v]"
    ffmpeg.run([*args, "-filter_complex", graph, "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-an", str(out)])
    return out


# ------------------------------------------------------------------ generation

def generate_chain(ctx, *, page, start_path: Path, end_path: Path | None, duration: float, prompt: str, negative: str, seed: int, work: Path) -> dict:
    """Chained Wan passes covering `duration` seconds from `start_path`; the last pass runs first/last-frame to `end_path` when given.
    Returns {video (joined mp4 in `work`), devices, seconds, segments, workflow, notes}."""
    wid, note = i2v_workflow(page)
    notes = [note] if note else []
    plan = segment_frames(duration)
    parts: list[Path] = []
    devices: list[str] = []
    total = 0.0
    start = start_path
    for i, frames in enumerate(plan):
        ctx.check()
        use_flf = bool(end_path and i == len(plan) - 1)
        workflow = FLF_WORKFLOW if use_flf else wid
        spec = get_workflow(workflow)
        inputs = {"prompt": prompt, "negative_prompt": negative or NEG, "image": "@input:start.png", "width": 480, "height": 832, "length": frames, "seed": seed + i}
        files = {"start.png": start}
        if use_flf:
            inputs["image_end"] = "@input:end.png"
            files["end.png"] = end_path
        res = compute.run_task(ctx, "comfy.graph", {"graph": spec.build(inputs), "workflow": workflow, "timeout": 3600, "expected": spec.expected_seconds}, inputs=files)
        try:
            vids = res.of_kind(*VIDEO_SUFFIX)
            if not vids:
                raise ProviderError("the worker returned no video file", retryable=True)
            seg = work / f"seg{i}{vids[0].suffix}"
            shutil.move(str(vids[0]), seg)
        finally:
            res.cleanup()
        parts.append(seg)
        devices.append(res.device)
        total += res.seconds
        if i < len(plan) - 1:
            start = last_frame(seg, work / f"last{i}.png")
    joined = concat_segments(parts, work / "joined.mp4")
    return {"video": joined, "devices": devices, "seconds": total, "segments": len(plan), "workflow": wid, "notes": notes, "flf": bool(end_path)}


# ------------------------------------------------------------------ one hero shot

def make_clip(ctx, shot, ep, keyframe, end_keyframe, *, prompt: str, seed: int, flf: bool, on_note=None) -> dict:
    """Generate the clip of one shot. Returns {path (a temp mp4 the caller registers), device, seconds, segments, colour, qc, workflow, notes}."""
    page = ep.series.page
    kf_path = asset_storage.storage.path_for(keyframe.path)
    end_path = asset_storage.storage.path_for(end_keyframe.path) if (flf and end_keyframe is not None) else None
    extra = ["first/last-frame shot without a following keyframe: image-to-video used"] if (flf and end_path is None) else []
    work = Path(tempfile.mkdtemp(prefix="hero-", dir=settings.MEDIA_ROOT))
    try:
        g = generate_chain(ctx, page=page, start_path=kf_path, end_path=end_path, duration=shot.duration_sec, prompt=prompt, negative=shot.negative_prompt, seed=seed, work=work)
        matched = work / "matched.mp4"
        colour = colormatch.match_clip(g["video"], kf_path, matched, ctx=ctx)
        sheet, _ = reference_sheet(shot, ep)
        qc = consistency.check_clip(matched, kf_path, sheet)
        final = Path(tempfile.mkdtemp(prefix="clip-", dir=settings.MEDIA_ROOT)) / "clip.mp4"
        shutil.move(str(matched), final)
        return {"path": final, "device": "+".join(dict.fromkeys(g["devices"])), "seconds": round(g["seconds"], 2), "segments": g["segments"], "colour": colour, "qc": qc,
                "workflow": g["workflow"], "flf": g["flf"], "notes": g["notes"] + extra}
    finally:
        shutil.rmtree(work, ignore_errors=True)
