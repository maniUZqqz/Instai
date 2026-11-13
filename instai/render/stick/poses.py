"""Poses (still) and extra motions (video) for stick figures, registered into the puppet motion library.

Angles are degrees, clockwise (screen), seen on the right-facing figure: for a hanging limb a NEGATIVE angle swings it forward (to the
right) and a positive one back. `forearm_*` / `shin_*` are relative to their parent (elbow, knee). dx/dy are design pixels; when the body
moves down, the legs must move with it (they are separate root parts), which `_lower` does.
"""
from __future__ import annotations

from instai.render.puppet import motions

Pose = dict[str, dict[str, float]]


def _lower(pose: Pose, dy: float) -> Pose:
    for part in ("body", "leg_l", "leg_r"):
        pose.setdefault(part, {})["dy"] = pose.get(part, {}).get("dy", 0) + dy
    return pose


POSES: dict[str, Pose] = {
    "stand": {"leg_l": {"rot": 3}, "leg_r": {"rot": -3}, "arm_l": {"rot": 5}, "arm_r": {"rot": -5}},
    "walk_a": {"leg_l": {"rot": -28}, "shin_l": {"rot": 8}, "leg_r": {"rot": 22}, "shin_r": {"rot": 30}, "arm_l": {"rot": 24}, "forearm_l": {"rot": 14},
               "arm_r": {"rot": -26}, "forearm_r": {"rot": -22}, "body": {"rot": 2}},
    "walk_b": {"leg_l": {"rot": 22}, "shin_l": {"rot": 30}, "leg_r": {"rot": -28}, "shin_r": {"rot": 8}, "arm_l": {"rot": -26}, "forearm_l": {"rot": -22},
               "arm_r": {"rot": 24}, "forearm_r": {"rot": 14}, "body": {"rot": 2}},
    "run_a": {"body": {"rot": 14}, "head": {"rot": -8}, "leg_l": {"rot": -72}, "shin_l": {"rot": 28}, "leg_r": {"rot": 34}, "shin_r": {"rot": 96},
              "arm_l": {"rot": -58}, "forearm_l": {"rot": -86}, "arm_r": {"rot": 52}, "forearm_r": {"rot": -78}},
    "run_b": {"body": {"rot": 14}, "head": {"rot": -8}, "leg_l": {"rot": 34}, "shin_l": {"rot": 96}, "leg_r": {"rot": -72}, "shin_r": {"rot": 28},
              "arm_l": {"rot": 52}, "forearm_l": {"rot": -78}, "arm_r": {"rot": -58}, "forearm_r": {"rot": -86}},
    "wave": {"arm_r": {"rot": -150}, "forearm_r": {"rot": -24}, "head": {"rot": 4}},
    "point_right": {"arm_r": {"rot": -92}, "forearm_r": {"rot": -2}, "body": {"rot": 3}, "head": {"rot": 3}},
    "point_up": {"arm_r": {"rot": -122}, "forearm_r": {"rot": -48}, "head": {"rot": -3}},
    "hands_up": {"arm_l": {"rot": 128}, "forearm_l": {"rot": 38}, "arm_r": {"rot": -128}, "forearm_r": {"rot": -38}},
    "surrender": {"arm_l": {"rot": 108}, "forearm_l": {"rot": 74}, "arm_r": {"rot": -108}, "forearm_r": {"rot": -74}, "head": {"rot": -3}},
    "shrug": {"arm_l": {"rot": 52}, "forearm_l": {"rot": 38}, "arm_r": {"rot": -52}, "forearm_r": {"rot": -38}, "head": {"rot": -5}},
    "think": {"arm_r": {"rot": -30}, "forearm_r": {"rot": -132}, "head": {"rot": 7}, "arm_l": {"rot": 8}},
    "cheer": _lower({"arm_l": {"rot": 128}, "forearm_l": {"rot": 40}, "arm_r": {"rot": -128}, "forearm_r": {"rot": -40}, "leg_l": {"rot": 22}, "leg_r": {"rot": -22},
                     "shin_l": {"rot": 10}, "shin_r": {"rot": -10}}, -34),
    "punch": {"body": {"rot": 12}, "arm_r": {"rot": -84}, "forearm_r": {"rot": -6}, "arm_l": {"rot": 40}, "forearm_l": {"rot": -60}, "leg_l": {"rot": -30},
              "leg_r": {"rot": 24}, "shin_r": {"rot": 20}},
    "kick": {"body": {"rot": -10}, "leg_l": {"rot": -88}, "shin_l": {"rot": 4}, "leg_r": {"rot": 6}, "arm_l": {"rot": 60}, "arm_r": {"rot": -40}},
    "push": {"body": {"rot": 8}, "arm_l": {"rot": -72}, "forearm_l": {"rot": -4}, "arm_r": {"rot": -78}, "forearm_r": {"rot": -2}, "leg_l": {"rot": -24},
             "leg_r": {"rot": 22}, "shin_r": {"rot": 14}},
    "shock": {"body": {"rot": -12}, "head": {"rot": -8}, "arm_l": {"rot": 70}, "forearm_l": {"rot": 46}, "arm_r": {"rot": -58}, "forearm_r": {"rot": -40},
              "leg_l": {"rot": 16}, "leg_r": {"rot": -26}, "shin_r": {"rot": 24}},
    "tired": {"body": {"rot": 14}, "head": {"rot": 14}, "arm_l": {"rot": -8}, "arm_r": {"rot": -14}, "forearm_r": {"rot": -10}, "leg_l": {"rot": -6}, "leg_r": {"rot": 8}},
    "hold": {"arm_r": {"rot": -62}, "forearm_r": {"rot": -30}, "arm_l": {"rot": 8}},
    "crouch": _lower({"body": {"rot": 24, "dx": -70}, "head": {"rot": -14, "dx": -70}, "leg_l": {"rot": -80, "dx": -70}, "shin_l": {"rot": 94}, "leg_r": {"rot": -70, "dx": -70}, "shin_r": {"rot": 88},
                      "arm_l": {"rot": -20}, "forearm_l": {"rot": -64}, "arm_r": {"rot": -34}, "forearm_r": {"rot": -76}}, 136),
    "hide": _lower({"body": {"rot": 30, "dx": -70}, "head": {"rot": 10, "dx": -70}, "leg_l": {"rot": -80, "dx": -70}, "shin_l": {"rot": 94}, "leg_r": {"rot": -70, "dx": -70}, "shin_r": {"rot": 88},
                    "arm_l": {"rot": 125, "dx": 0}, "forearm_l": {"rot": 100}, "arm_r": {"rot": -125}, "forearm_r": {"rot": -100}}, 136),
    "sneak": _lower({"body": {"rot": 16}, "head": {"rot": -8}, "leg_l": {"rot": -40}, "shin_l": {"rot": 62}, "leg_r": {"rot": 14}, "shin_r": {"rot": 38},
                     "arm_l": {"rot": 20}, "forearm_l": {"rot": -40}, "arm_r": {"rot": -34}, "forearm_r": {"rot": -50}}, 52),
    "sit": _lower({"leg_l": {"rot": -88}, "shin_l": {"rot": 86}, "leg_r": {"rot": -90}, "shin_r": {"rot": 90}, "arm_l": {"rot": -20}, "forearm_l": {"rot": -50},
                   "arm_r": {"rot": -24}, "forearm_r": {"rot": -56}}, 158),
    "lying": _lower({"body": {"rot": 88, "dx": -40}, "head": {"rot": 4}, "leg_l": {"rot": 88, "dx": -40}, "leg_r": {"rot": 92, "dx": -40}, "shin_l": {"rot": 4}, "shin_r": {"rot": -2},
                     "arm_l": {"rot": 70}, "forearm_l": {"rot": 10}, "arm_r": {"rot": 110}, "forearm_r": {"rot": 8}}, 300),
}
POSE_LABELS = {  # fa / en (UI picker)
    "stand": ("ایستاده", "Standing"), "walk_a": ("قدم اول", "Walk A"), "walk_b": ("قدم دوم", "Walk B"), "run_a": ("دویدن ۱", "Run A"), "run_b": ("دویدن ۲", "Run B"),
    "wave": ("دست تکان‌دادن", "Wave"), "point_right": ("اشاره به جلو", "Point ahead"), "point_up": ("اشاره به بالا", "Point up"),
    "hands_up": ("دست‌ها بالا", "Hands up"), "surrender": ("تسلیم", "Surrender"), "shrug": ("شانه بالا", "Shrug"), "think": ("فکر", "Think"),
    "cheer": ("شادی", "Cheer"), "punch": ("مشت", "Punch"), "kick": ("لگد", "Kick"), "push": ("هل‌دادن", "Push"), "shock": ("جا خوردن", "Shock"),
    "tired": ("خسته", "Tired"), "hold": ("نگه‌داشتن چیزی", "Hold an item"), "crouch": ("خم شدن", "Crouch"), "hide": ("پنهان شدن", "Hide"),
    "sneak": ("دزدکی", "Sneak"), "sit": ("نشسته", "Sitting"), "lying": ("روی زمین", "Lying down"),
}
SHEET_POSES = ("stand", "walk_a", "run_a", "point_right", "hands_up", "crouch", "sit", "think")


def _constant(pose: Pose) -> dict:
    tracks: dict[str, dict[str, list]] = {}
    for part, ch in pose.items():
        tracks[part] = {c: [(0.0, float(v)), (1.0, float(v))] for c, v in ch.items()}
    return {"duration": 1.0, "loop": False, "tracks": tracks}


def _key(vals: list[float], period: float, ease: str = "inout") -> list:
    n = len(vals) - 1
    return [(period * i / n, v, ease) for i, v in enumerate(vals)]


def _run_motion() -> dict:
    p = 0.62
    return {"duration": p, "loop": True, "root_speed": 360.0, "tracks": {
        "body": {"rot": [(0, 14), (p, 14)], "dy": _key([0, -16, 0, -16, 0], p)},
        "head": {"rot": [(0, -8), (p, -8)]},
        "leg_l": {"rot": _key([-72, 34, -72], p)}, "shin_l": {"rot": _key([28, 96, 28], p)},
        "leg_r": {"rot": _key([34, -72, 34], p)}, "shin_r": {"rot": _key([96, 28, 96], p)},
        "arm_l": {"rot": _key([-58, 52, -58], p)}, "forearm_l": {"rot": _key([-86, -78, -86], p)},
        "arm_r": {"rot": _key([52, -58, 52], p)}, "forearm_r": {"rot": _key([-78, -86, -78], p)}}}


def _sneak_motion() -> dict:
    p = 1.5
    return {"duration": p, "loop": True, "root_speed": 80.0, "tracks": {
        "body": {"rot": [(0, 16), (p, 16)], "dy": [(0, 52), (p, 52)]},
        "leg_l": {"dy": [(0, 52), (p, 52)], "rot": _key([-40, 14, -40], p)}, "shin_l": {"rot": _key([62, 38, 62], p)},
        "leg_r": {"dy": [(0, 52), (p, 52)], "rot": _key([14, -40, 14], p)}, "shin_r": {"rot": _key([38, 62, 38], p)},
        "head": {"rot": _key([-8, -2, -8], p)}, "arm_r": {"rot": [(0, -34), (p, -34)]}, "forearm_r": {"rot": [(0, -50), (p, -50)]}}}


def _panic_motion() -> dict:
    p = 0.5
    return {"duration": p, "loop": True, "tracks": {
        "body": {"dy": _key([0, -12, 0], p)}, "head": {"rot": _key([-9, 9, -9], p, "linear")},
        "arm_l": {"rot": _key([150, 128, 150], p)}, "arm_r": {"rot": _key([-128, -150, -128], p)},
        "forearm_l": {"rot": _key([20, -10, 20], p)}, "forearm_r": {"rot": _key([-20, 10, -20], p)},
        "leg_l": {"dy": _key([0, -12, 0], p), "rot": _key([-14, 10, -14], p)}, "leg_r": {"dy": _key([0, -12, 0], p), "rot": _key([10, -14, 10], p)}}}


def _shiver_motion() -> dict:
    p = 0.18
    return {"duration": p, "loop": True, "tracks": {
        "body": {"dx": _key([-3, 3, -3], p, "linear")}, "head": {"rot": _key([-2, 2, -2], p, "linear")},
        "arm_l": {"rot": [(0, 28), (p, 28)], "dx": _key([-2, 2, -2], p, "linear")}, "arm_r": {"rot": [(0, -28), (p, -28)]},
        "forearm_l": {"rot": [(0, 60), (p, 60)]}, "forearm_r": {"rot": [(0, -60), (p, -60)]}}}


def _fall_motion() -> dict:
    d = 1.3
    lying = POSES["lying"]
    tr: dict[str, dict[str, list]] = {}
    for part, ch in lying.items():
        tr[part] = {c: [(0.0, 0.0), (0.35, 0.0), (0.95, float(v), "in"), (1.1, float(v) * 0.97, "out"), (d, float(v), "inout")] for c, v in ch.items()}
    return {"duration": d, "loop": False, "tracks": tr}


def _punch_motion() -> dict:
    d = 0.9
    return {"duration": d, "loop": False, "tracks": {
        "body": {"rot": [(0, 0), (0.2, -6, "out"), (0.38, 14, "in"), (0.6, 12, "inout"), (d, 0, "inout")]},
        "arm_r": {"rot": [(0, -5), (0.2, 40, "out"), (0.38, -86, "in"), (0.6, -84, "inout"), (d, -5, "inout")]},
        "forearm_r": {"rot": [(0, 0), (0.2, -110, "out"), (0.38, -4, "in"), (0.6, -4), (d, 0, "inout")]},
        "leg_l": {"rot": [(0, 3), (0.38, -30, "out"), (d, 3, "inout")]}, "leg_r": {"rot": [(0, -3), (0.38, 24, "out"), (d, -3, "inout")]}}}


def _cheer_motion() -> dict:
    p = 0.7
    return {"duration": p, "loop": True, "tracks": {
        "body": {"dy": _key([0, -40, 0], p, "inout")}, "leg_l": {"dy": _key([0, -40, 0], p), "rot": _key([6, 22, 6], p)},
        "leg_r": {"dy": _key([0, -40, 0], p), "rot": _key([-6, -22, -6], p)},
        "arm_l": {"rot": _key([120, 156, 120], p)}, "arm_r": {"rot": _key([-120, -156, -120], p)}}}


EXTRA_MOTIONS = {"run": _run_motion, "sneak": _sneak_motion, "panic": _panic_motion, "shiver": _shiver_motion, "fall_down": _fall_motion,
                 "punch": _punch_motion, "cheer_jump": _cheer_motion}


def register() -> None:
    """Add the stick poses (as one-second constant motions named pose_<name>) and the extra motions to the puppet library (idempotent)."""
    for name, pose in POSES.items():
        motions.MOTIONS.setdefault(f"pose_{name}", _constant(pose))
    for name, make in EXTRA_MOTIONS.items():
        motions.MOTIONS.setdefault(name, make())
    motions.BASE_MOTIONS.update({"run", "sneak", "panic", "shiver", "cheer_jump"})


register()


def names() -> list[str]:
    return list(POSES)
