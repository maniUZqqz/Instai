"""Estimated GPU/CPU time per shot and episode, shown BEFORE anything runs.

Numbers are planning estimates taken from the brief (Wan 2.2 480p 5 s shot ~ 8-10 GPU min on an RTX 3060) until the Phase 0
benchmark has been run on the real machine; then the latest measured values replace them (source: "measured").
Never present an estimate as a measurement: every figure carries its source.
"""
from __future__ import annotations

import math

# planning defaults (seconds of GPU time). Replaced by BenchmarkResult medians when available.
DEFAULTS = {"image": 60.0, "image_preview": 20.0, "video_5s": 540.0, "layer_split": 10.0, "puppet_layer": 5.0, "tts_gpu": 10.0}
# techniques that need a generated keyframe image
KEYFRAME = {"still_kenburns", "parallax_25d", "wan_i2v", "wan_flf", "talking_video"}
VIDEO = {"wan_i2v", "wan_flf", "talking_video"}
IMPLEMENTED = {"still_kenburns", "parallax_25d", "wan_i2v"}  # techniques with a render path today; others fall back to still_kenburns


def measured() -> dict[str, float]:
    """Latest successful benchmark time per step (seconds), if the benchmark has ever run."""
    out: dict[str, float] = {}
    try:
        from instai.core.models import BenchmarkResult

        for step, key in (("image", "image"), ("video", "video_5s")):
            r = BenchmarkResult.objects.filter(step=step, status="ok", seconds__isnull=False).order_by("-id").first()
            if r:
                out[key] = float(r.seconds)
    except Exception:  # noqa: BLE001 - estimates must never break the page
        pass
    return out


def table() -> tuple[dict[str, float], str]:
    m = measured()
    return {**DEFAULTS, **m}, ("measured" if m else "planning_estimate")


def shot_estimate(technique: str, duration_sec: float, mode: str = "final", costs: dict | None = None) -> dict:
    """{gpu_seconds, cpu_seconds, notes[]} for one shot."""
    c = costs or table()[0]
    gpu, notes = 0.0, []
    cpu = max(1.0, duration_sec * (0.6 if mode == "preview" else 1.5))
    if technique in KEYFRAME:
        gpu += c["image_preview"] if mode == "preview" else c["image"]
    if technique == "parallax_25d":
        gpu += c["layer_split"]
    if technique == "puppet_2d":
        gpu += c["puppet_layer"]
    if technique in VIDEO and mode != "preview":
        clips = max(1, math.ceil(duration_sec / 5.0))
        gpu += clips * c["video_5s"] * (0.8 if technique == "wan_flf" else 1.0)
        if clips > 1:
            notes.append("clips_chained")
    if technique not in IMPLEMENTED:
        notes.append("falls_back_to_still_kenburns")
    return {"gpu_seconds": round(gpu, 1), "cpu_seconds": round(cpu, 1), "notes": notes}


def episode_estimate(shots, mode_list=("preview", "final")) -> dict:
    """shots: iterable of objects with .technique and .duration_sec."""
    costs, source = table()
    shots = list(shots)
    out = {"source": source, "shots": len(shots), "modes": {}}
    for mode in mode_list:
        g = c = 0.0
        for s in shots:
            e = shot_estimate(s.technique, s.duration_sec, mode, costs)
            g += e["gpu_seconds"]
            c += e["cpu_seconds"]
        out["modes"][mode] = {"gpu_seconds": round(g), "gpu_minutes": round(g / 60, 1), "cpu_seconds": round(c),
                              "total_minutes": round((g + c) / 60, 1)}
    out["duration_sec"] = round(sum(s.duration_sec for s in shots), 1)
    out["video_shots"] = sum(1 for s in shots if s.technique in VIDEO)
    return out
