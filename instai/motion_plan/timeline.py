"""The timeline of a video: the length of every scene (frames), the overlaps of the transitions, the start of every scene and the total.

SOURCE: ported from NMarketing:backend/apps/motion/timeline.py @ motion v2, adapted for InstAI: the style's transition comes from the kit's motion
personality (motionlib.style_trans) instead of NMarketing's style catalogue.

An exact mirror of remotion/src/components/timeline.ts (computeTimeline); tests/test_motion_plan.py runs both over several plans and compares.
The render, the QA, the narration sync and the clip length all take the time of a scene from here, so there is one computation only.
"""
from __future__ import annotations

import math

from . import motionlib


def _round(x: float) -> int:
    return int(math.floor(x + 0.5))        # JavaScript's Math.round (not Python's banker's rounding)


def kit_of(spec: dict) -> dict:
    """The style kit of a plan: the one carried by the plan, else the library's kit of its `style` / `theme` (an unknown style falls back to the default)."""
    k = spec.get("kit")
    if isinstance(k, dict):
        return k
    from instai.remotion import kit as kitmod

    return kitmod.style_kit(spec.get("style") or None, spec.get("theme") or None)


def compute(spec: dict, fps: int | None = None, kit: dict | None = None) -> dict:
    """=> {frames[], starts[], tfs[], kinds[], total, fps} (frames)."""
    fps = int(fps or spec.get("fps") or 30)
    scenes = spec.get("scenes") or []
    style_kind, style_frames = motionlib.style_trans(kit or kit_of(spec))
    frames = []
    for s in scenes:
        try:
            d = float(s.get("duration") or 4)
        except (TypeError, ValueError):
            d = 4.0
        frames.append(max(fps, _round(max(1.0, min(60.0, d)) * fps)))
    tfs, kinds = [], []
    for j in range(len(frames) - 1):
        kind = scenes[j].get("transition") or spec.get("transition") or style_kind
        cap = int(math.floor(min(frames[j], frames[j + 1]) * 0.45))
        tfs.append(0 if kind == "cut" else max(0, min(style_frames, cap)))
        kinds.append(kind)
    starts, at = [], 0
    for i, f in enumerate(frames):
        starts.append(at)
        at += f - (tfs[i] if i < len(frames) - 1 else 0)
    return {"frames": frames, "starts": starts, "tfs": tfs, "kinds": kinds, "total": max(1, at), "fps": fps}


def seconds(spec: dict, kit: dict | None = None) -> dict:
    """The same timeline in seconds: starts / ends of every scene on the video's timeline, and the total."""
    t = compute(spec, kit=kit)
    fps = t["fps"]
    return {"starts": [s / fps for s in t["starts"]], "ends": [(s + f) / fps for s, f in zip(t["starts"], t["frames"])],
            "durations": [f / fps for f in t["frames"]], "tfs": [x / fps for x in t["tfs"]], "kinds": t["kinds"], "total": t["total"] / fps, "fps": fps}


def total_seconds(spec: dict, kit: dict | None = None) -> float:
    return seconds(spec, kit)["total"] if spec.get("scenes") else 0.0
