"""Motion library for the puppet rig: keyframed tracks with easing, additive layers and deterministic blinking.

A motion is {"duration", "loop", "tracks": {part: {channel: [(t, value[, easing])]}}, "root_speed": design px per second}.
Channels: dx, dy (design px, in the part's parent space), rot (degrees, clockwise), sx, sy (scale). Motions never name a part the
rig lacks - missing parts are ignored, so the same library drives a bust-only presenter and a full-body character.
`Timeline` stacks motion clips in layers (base: idle/walk/sit..., overlay: talk/wave/point...); layers add up, clip edges blend.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import geometry as g

CHANNELS = ("dx", "dy", "rot", "sx", "sy")


def _loop(amp: float, period: float, phase: float = 0.0, easing: str = "inout", n: int = 4) -> list:
    """A smooth back-and-forth keyframe list over one period."""
    out = []
    for i in range(n + 1):
        u = i / n
        out.append((period * u, round(amp * math.sin(2 * math.pi * (u + phase)), 4), easing))
    return out


MOTIONS: dict[str, dict] = {
    "idle": {"duration": 3.2, "loop": True, "tracks": {
        "body": {"dy": [(0, 0), (1.6, -3, "inout"), (3.2, 0, "inout")], "sy": [(0, 1), (1.6, 1.012, "inout"), (3.2, 1, "inout")]},
        "head": {"rot": [(0, 0), (1.6, 1.2, "inout"), (3.2, 0, "inout")]},
        "arm_l": {"rot": [(0, 0), (1.6, 2, "inout"), (3.2, 0, "inout")]},
        "arm_r": {"rot": [(0, 0), (1.6, -2, "inout"), (3.2, 0, "inout")]}}},
    "talk": {"duration": 1.8, "loop": True, "tracks": {
        "head": {"rot": [(0, -1.5), (0.45, 2.0, "inout"), (0.9, -1.0, "inout"), (1.35, 1.8, "inout"), (1.8, -1.5, "inout")],
                 "dy": [(0, 0), (0.45, -4, "inout"), (0.9, 0, "inout"), (1.35, -3, "inout"), (1.8, 0, "inout")]},
        "arm_r": {"rot": [(0, -4), (0.6, -22, "inout"), (1.2, -8, "inout"), (1.8, -4, "inout")]},
        "arm_l": {"rot": [(0, 4), (0.9, 12, "inout"), (1.8, 4, "inout")]},
        "body": {"dy": [(0, 0), (0.9, -2, "inout"), (1.8, 0, "inout")]}}},
    "walk": {"duration": 0.8, "loop": True, "root_speed": 190.0, "tracks": {
        "leg_l": {"rot": [(0, 24), (0.4, -24, "inout"), (0.8, 24, "inout")]},
        "leg_r": {"rot": [(0, -24), (0.4, 24, "inout"), (0.8, -24, "inout")]},
        "arm_l": {"rot": [(0, -20), (0.4, 20, "inout"), (0.8, -20, "inout")]},
        "arm_r": {"rot": [(0, 20), (0.4, -20, "inout"), (0.8, 20, "inout")]},
        "body": {"dy": [(0, 0), (0.2, -7, "inout"), (0.4, 0, "inout"), (0.6, -7, "inout"), (0.8, 0, "inout")], "rot": [(0, 1.5), (0.4, -1.5, "inout"), (0.8, 1.5, "inout")]},
        "head": {"rot": [(0, -1), (0.4, 1, "inout"), (0.8, -1, "inout")]}}},
    "wave": {"duration": 1.8, "loop": False, "tracks": {
        "arm_r": {"rot": [(0, 0), (0.3, -150, "out"), (0.5, -128, "inout"), (0.7, -160, "inout"), (0.9, -128, "inout"), (1.1, -160, "inout"),
                          (1.3, -150, "inout"), (1.8, 0, "inout")]},
        "head": {"rot": [(0, 0), (0.4, 4, "inout"), (1.4, 4, "inout"), (1.8, 0, "inout")]}}},
    "point": {"duration": 1.6, "loop": False, "tracks": {
        "arm_r": {"rot": [(0, 0), (0.3, -78, "out"), (1.2, -78, "inout"), (1.6, 0, "inout")]},
        "body": {"rot": [(0, 0), (0.3, 3, "inout"), (1.2, 3, "inout"), (1.6, 0, "inout")]},
        "head": {"rot": [(0, 0), (0.3, 4, "inout"), (1.2, 4, "inout"), (1.6, 0, "inout")]}}},
    "react": {"duration": 1.4, "loop": False, "tracks": {
        "body": {"dy": [(0, 0), (0.12, -14, "out"), (0.4, 0, "inout"), (1.4, 0)], "sy": [(0, 1), (0.12, 1.04, "out"), (0.4, 1, "inout")],
                 "sx": [(0, 1), (0.12, 0.97, "out"), (0.4, 1, "inout")]},
        "head": {"rot": [(0, 0), (0.15, -6, "out"), (0.9, -6, "inout"), (1.4, 0, "inout")], "dy": [(0, 0), (0.15, -8, "out"), (0.9, -6), (1.4, 0)]},
        "arm_l": {"rot": [(0, 0), (0.2, 70, "out"), (1.0, 62, "inout"), (1.4, 0, "inout")]},
        "arm_r": {"rot": [(0, 0), (0.2, -70, "out"), (1.0, -62, "inout"), (1.4, 0, "inout")]}}},
    "jump": {"duration": 0.9, "loop": False, "tracks": {
        "body": {"dy": [(0, 0), (0.12, 10, "in"), (0.4, -120, "out"), (0.7, 0, "in"), (0.78, 8, "out"), (0.9, 0, "inout")],
                 "sy": [(0, 1), (0.12, 0.93, "in"), (0.4, 1.06, "out"), (0.7, 1.0), (0.78, 0.94), (0.9, 1)],
                 "sx": [(0, 1), (0.12, 1.06, "in"), (0.4, 0.96, "out"), (0.7, 1.0), (0.78, 1.05), (0.9, 1)]},
        "leg_l": {"rot": [(0, 0), (0.4, 28, "out"), (0.7, 0, "in")]}, "leg_r": {"rot": [(0, 0), (0.4, -28, "out"), (0.7, 0, "in")]},
        "arm_l": {"rot": [(0, 0), (0.4, 120, "out"), (0.8, 10, "inout"), (0.9, 0)]}, "arm_r": {"rot": [(0, 0), (0.4, -120, "out"), (0.8, -10, "inout"), (0.9, 0)]}}},
    "sit": {"duration": 1.0, "loop": True, "tracks": {
        "body": {"dy": [(0, 70)]}, "leg_l": {"rot": [(0, 88)]}, "leg_r": {"rot": [(0, 88)]},
        "head": {"rot": [(0, 0), (0.5, 1.2, "inout"), (1.0, 0, "inout")]}}},
    "nod": {"duration": 0.9, "loop": False, "tracks": {"head": {"rot": [(0, 0), (0.2, 7, "inout"), (0.4, -1, "inout"), (0.6, 5, "inout"), (0.9, 0, "inout")]}}},
    "shake": {"duration": 0.9, "loop": False, "tracks": {"head": {"rot": [(0, 0), (0.15, -7, "inout"), (0.35, 7, "inout"), (0.55, -6, "inout"), (0.75, 4, "inout"), (0.9, 0)]}}},
}
BASE_MOTIONS = {"idle", "walk", "sit"}


def known() -> list[str]:
    return sorted(MOTIONS)


def local_time(m: dict, t: float) -> float:
    d = m["duration"]
    return (t % d) if m.get("loop") else max(0.0, min(d, t))


def evaluate(motion: str, t: float, *, speed: float = 1.0) -> dict[str, dict[str, float]]:
    """{part: {channel: value}} of a motion at time `t` (seconds since the clip started)."""
    m = MOTIONS[motion]
    lt = local_time(m, t * speed)
    out: dict[str, dict[str, float]] = {}
    for part, chans in m["tracks"].items():
        out[part] = {c: g.track_value(keys, lt, 1.0 if c in ("sx", "sy") else 0.0) for c, keys in chans.items()}
    return out


@dataclass
class Clip:
    motion: str
    start: float
    end: float
    speed: float = 1.0
    blend: float = 0.2

    def weight(self, t: float) -> float:
        if t < self.start or t > self.end:
            return 0.0
        w_in = (t - self.start) / self.blend if self.blend > 0 else 1.0
        w_out = (self.end - t) / self.blend if self.blend > 0 else 1.0
        return g.ease("inout", min(1.0, w_in, w_out))


@dataclass
class Timeline:
    """layers: {"base": [Clip...], "overlay": [Clip...], ...} added in layer order. The base layer falls back to idle."""

    duration: float
    layers: dict[str, list[Clip]] = field(default_factory=dict)

    @classmethod
    def from_spec(cls, duration: float, spec: list[dict] | None) -> "Timeline":
        """spec: [{"layer": "base", "clips": [{"motion": "walk", "start": 0, "end": 3}]}]; unknown motions are ignored."""
        tl = cls(duration=duration)
        for layer in spec or []:
            clips = [Clip(c["motion"], float(c["start"]), float(c["end"]), float(c.get("speed", 1.0)), float(c.get("blend", 0.2)))
                     for c in layer.get("clips", []) if c.get("motion") in MOTIONS and float(c["end"]) > float(c["start"])]
            tl.layers.setdefault(layer.get("layer", "base"), []).extend(sorted(clips, key=lambda c: c.start))
        if "base" not in tl.layers or not tl.layers["base"]:
            tl.layers["base"] = [Clip("idle", 0.0, max(duration, 0.1), blend=0.0)]
        return tl

    def pose(self, t: float) -> dict[str, tuple[float, float, float, float, float]]:
        """Combined pose of every layer: dx, dy, rot add; scales multiply (each weighted by its clip's blend weight)."""
        acc: dict[str, list[float]] = {}
        gap_fill = True
        for layer, clips in self.layers.items():
            for c in clips:
                w = c.weight(t)
                if w <= 0:
                    continue
                if layer == "base":
                    gap_fill = False
                for part, ch in evaluate(c.motion, t - c.start, speed=c.speed).items():
                    a = acc.setdefault(part, [0.0, 0.0, 0.0, 1.0, 1.0])
                    a[0] += ch.get("dx", 0.0) * w
                    a[1] += ch.get("dy", 0.0) * w
                    a[2] += ch.get("rot", 0.0) * w
                    a[3] *= 1.0 + (ch.get("sx", 1.0) - 1.0) * w
                    a[4] *= 1.0 + (ch.get("sy", 1.0) - 1.0) * w
        if gap_fill:  # a hole in the base layer: stay alive with idle
            for part, ch in evaluate("idle", t).items():
                a = acc.setdefault(part, [0.0, 0.0, 0.0, 1.0, 1.0])
                a[0] += ch.get("dx", 0.0)
                a[1] += ch.get("dy", 0.0)
                a[2] += ch.get("rot", 0.0)
                a[3] *= ch.get("sx", 1.0)
                a[4] *= ch.get("sy", 1.0)
        return {k: tuple(v) for k, v in acc.items()}  # type: ignore[misc]

    def root_x(self, t: float) -> float:
        """Distance (design px) the character has travelled by time t: the integral of the base clips' root speed."""
        total = 0.0
        for c in self.layers.get("base", []):
            sp = MOTIONS[c.motion].get("root_speed", 0.0) * c.speed
            if sp and t > c.start:
                total += sp * (min(t, c.end) - c.start)
        return total


def blink_times(duration: float, seed: int = 1, every: tuple[float, float] = (2.4, 5.0)) -> list[float]:
    """Deterministic blink start times (a blink lasts ~0.16 s)."""
    rnd = random.Random(seed)
    t, out = rnd.uniform(*every) * 0.6, []
    while t < duration:
        out.append(round(t, 3))
        t += rnd.uniform(*every)
    return out


def is_blinking(times: list[float], t: float, length: float = 0.16) -> bool:
    return any(b <= t < b + length for b in times)


def talk_timeline(duration: float, speaking: list[tuple[float, float]], base: str = "idle", gestures: list[tuple[str, float]] | None = None) -> list[dict]:
    """Convenience: base motion for the whole shot, `talk` overlays while someone speaks, optional timed gestures [(motion, start)]."""
    layers = [{"layer": "base", "clips": [{"motion": base, "start": 0.0, "end": duration, "blend": 0.0}]},
              {"layer": "overlay", "clips": [{"motion": "talk", "start": s, "end": e} for s, e in speaking if e - s > 0.2]}]
    for motion, start in gestures or []:
        dur = MOTIONS[motion]["duration"]
        layers[1]["clips"].append({"motion": motion, "start": start, "end": min(duration, start + dur)})
    return layers
