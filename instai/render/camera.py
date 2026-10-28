"""2.5D camera motion as ffmpeg filter strings: Ken Burns (zoom/pan over one still) and layered parallax.

Pure string builders (unit-tested without ffmpeg). The still is first scaled to cover an oversampled canvas, because zoompan
rounds crop positions to whole pixels and jitters on small inputs.
"""
from __future__ import annotations

MOVES = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "static"]


def zmax(intensity: float) -> float:
    return round(1.08 + 0.17 * max(0.0, min(1.0, intensity)), 4)


def _expr(move: str, frames: int, zm: float) -> tuple[str, str, str]:
    n = max(1, frames - 1)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if move == "zoom_in":
        return f"1+{zm - 1:.4f}*on/{n}", cx, cy
    if move == "zoom_out":
        return f"{zm:.4f}-{zm - 1:.4f}*on/{n}", cx, cy
    if move == "pan_right":
        return f"{zm:.4f}", f"(iw-iw/zoom)*on/{n}", cy
    if move == "pan_left":
        return f"{zm:.4f}", f"(iw-iw/zoom)*(1-on/{n})", cy
    if move == "pan_down":
        return f"{zm:.4f}", cx, f"(ih-ih/zoom)*on/{n}"
    if move == "pan_up":
        return f"{zm:.4f}", cx, f"(ih-ih/zoom)*(1-on/{n})"
    return "1", cx, cy  # static


def oversample(width: int) -> float:
    return 2.0 if width <= 720 else 1.5


def ken_burns(move: str, intensity: float, frames: int, width: int, height: int, fps: int, *, src_label: str = "") -> str:
    """Filter chain: still image -> `frames` frames of camera motion at width x height."""
    k = oversample(width)
    w2, h2 = int(width * k) // 2 * 2, int(height * k) // 2 * 2
    z, x, y = _expr(move if move in MOVES else "zoom_in", frames, zmax(intensity))
    return (f"scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},setsar=1,format=yuv420p")


def parallax(move: str, intensity: float, frames: int, width: int, height: int, fps: int) -> str:
    """Two-layer parallax: background [0:v] moves slowly, foreground [1:v] (RGBA cut-out) moves faster; returns a filter_complex
    that reads inputs 0 (background) and 1 (foreground) and outputs [out]."""
    k = oversample(width)
    w2, h2 = int(width * k) // 2 * 2, int(height * k) // 2 * 2
    bz, bx, by = _expr(move if move in MOVES else "zoom_in", frames, zmax(intensity * 0.5))
    fz, fx, fy = _expr(move if move in MOVES else "zoom_in", frames, zmax(min(1.0, intensity * 1.4 + 0.2)))
    return (f"[0:v]scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2},"
            f"zoompan=z='{bz}':x='{bx}':y='{by}':d={frames}:s={width}x{height}:fps={fps},setsar=1,format=yuv420p[bg];"
            f"[1:v]format=rgba,scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2},"
            f"zoompan=z='{fz}':x='{fx}':y='{fy}':d={frames}:s={width}x{height}:fps={fps},setsar=1,format=rgba[fg];"
            f"[bg][fg]overlay=format=auto,format=yuv420p[out]")
