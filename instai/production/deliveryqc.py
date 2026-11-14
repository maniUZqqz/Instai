"""What happens to the SOUND of an episode right after the assembly, and what the quality panel reads from it (0.15, docs/DELIVERY.md).

1. `after_render` (called by `pipeline.step_assemble` on the finished mp4, before it becomes an Asset): the file is measured with the platforms' meter and brought
   to the page's loudness target (`render/loudness.py`, a few seconds, the picture is not touched), then the mix is checked for a doubled voice, music over the voice
   and a phase problem (`render/audioqc.py`, named by shot and track). Both results are returned for the asset's provenance. Neither can fail a render.
2. `audio_rows` (called by `pipeline.run_qc`): the rows of the quality panel. They come from the provenance; a file that has none (an older render, a retake) is
   analysed on the spot, file level only.
"""
from __future__ import annotations

import logging
from pathlib import Path

from instai.render import audioqc, loudness

log = logging.getLogger("instai.deliveryqc")
FINAL = "final"


def settle_wanted(page, mode: str) -> bool:
    """A preview is a quick look: it keeps the render's own loudness. A final render is corrected unless the page's audio profile switched it off."""
    return mode == FINAL and bool(page.profile("audio").get("loudness_settle", True))


def after_render(ctx, page, mode: str, out_path: Path, shots, timeline: list[dict], tracks: list[dict], work: Path) -> dict:
    """`{"loudness": {...}, "audio_qc": {...}}` for the asset's provenance."""
    out: dict = {}
    if settle_wanted(page, mode):
        try:
            ctx.progress(0.95, "loudness")
        except Exception:  # noqa: BLE001
            pass
        rep = loudness.settle(out_path, target=float(page.profile("audio")["target_lufs"]))
        out["loudness"] = rep or {"skipped": "no_sound"}
        if rep:
            ctx.log(f"loudness {rep['before']} -> {rep['lufs']} LUFS (target {rep['target']}, true peak {rep['tp']} dBTP, {rep['rounds']} round(s))")
    else:
        out["loudness"] = {"skipped": "preview" if mode != FINAL else "off"}
    try:
        ctx.progress(0.97, "audio check")
    except Exception:  # noqa: BLE001
        pass
    out["audio_qc"] = audioqc.analyze_episode(out_path, shots, timeline, tracks, work / "audioqc")
    if out["audio_qc"].get("problems"):
        ctx.log("audio check: " + ", ".join(out["audio_qc"]["problems"]), "warning")
    return out


def audio_rows(video, path: Path) -> list[dict]:
    """Echo / music-over-voice / phase rows for the quality panel."""
    rep = (video.provenance or {}).get("audio_qc")
    if not isinstance(rep, dict) or "ok" not in rep:
        rep = audioqc.analyze_file(path)
    return audioqc.qc_rows(rep)


def settled_of(video) -> dict | None:
    rep = (video.provenance or {}).get("loudness")
    return rep if isinstance(rep, dict) and rep.get("before") is not None else None
