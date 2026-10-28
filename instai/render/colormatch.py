"""Colour matching of a generated clip to a reference image (Pillow + ffmpeg pipes, no numpy).

Image-to-video models drift in colour and brightness over a clip. We measure per-channel mean/std at a few anchor frames, pull them
towards the reference's statistics (gain + offset per channel, limited to a gentle range, scaled by `strength`) and interpolate the
correction smoothly over time, so there is no flicker. Same idea as the colour match of the NMarketing regen tool
(Qasem services/video/regen/stitch.py: mean/std matching, linear in time) but 8-bit RGB instead of Lab.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageStat

from . import ffmpeg

GAIN_RANGE = (0.85, 1.18)
MAX_OFFSET = 28.0


def stats(img: Image.Image) -> tuple[list[float], list[float]]:
    small = img.convert("RGB").resize((96, 96), Image.BILINEAR)
    st = ImageStat.Stat(small)
    return list(st.mean), [max(1.0, s) for s in st.stddev]


def correction(frame_stats, ref_stats, strength: float) -> tuple[list[float], list[float]]:
    (fm, fs), (rm, rs) = frame_stats, ref_stats
    gains, offs = [], []
    for c in range(3):
        g = max(GAIN_RANGE[0], min(GAIN_RANGE[1], rs[c] / fs[c]))
        g = 1.0 + (g - 1.0) * strength
        o = (rm[c] - g * fm[c]) * strength
        gains.append(g)
        offs.append(max(-MAX_OFFSET, min(MAX_OFFSET, o)))
    return gains, offs


def colour_distance(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute difference of the per-channel means (0-255): how far the overall colour/brightness is apart."""
    am, _ = stats(a)
    bm, _ = stats(b)
    return sum(abs(x - y) for x, y in zip(am, bm)) / 3.0


def read_frames(path: Path, width: int, height: int):
    ff, _ = ffmpeg.binaries()
    p = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    n = width * height * 3
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            yield Image.frombytes("RGB", (width, height), buf)
    finally:
        p.stdout.close()
        p.wait()


def match_clip(src: Path, reference: Path, out: Path, *, strength: float = 0.85, anchors: int = 5, ctx=None) -> dict:
    """Write `out` = `src` with the colour pulled towards `reference`. Returns {gain, offset, before, after (colour distance of the last frame to the reference)}."""
    info = ffmpeg.probe(src)
    w, h, fps = int(info["width"]), int(info["height"]), float(info["fps"] or 16)
    frames = list(read_frames(src, w, h))
    if not frames:
        raise ffmpeg.FFmpegError("the clip has no frames")
    ref = Image.open(reference).convert("RGB")
    ref_stats = stats(ref)
    n = len(frames)
    idx = sorted({round(i * (n - 1) / max(1, anchors - 1)) for i in range(anchors)})
    corr = {i: correction(stats(frames[i]), ref_stats, strength) for i in idx}
    before = colour_distance(frames[-1], ref)

    def at(i: int) -> tuple[list[float], list[float]]:
        lo = max(k for k in idx if k <= i)
        hi = min(k for k in idx if k >= i)
        if lo == hi:
            return corr[lo]
        u = (i - lo) / (hi - lo)
        return ([a + (b - a) * u for a, b in zip(corr[lo][0], corr[hi][0])], [a + (b - a) * u for a, b in zip(corr[lo][1], corr[hi][1])])

    ff, _ = ffmpeg.binaries()
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-",
                            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
                           stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    last_fixed = None
    try:
        for i, fr in enumerate(frames):
            if ctx is not None and i % 8 == 0:
                ctx.check()
            gains, offs = at(i)
            channels = fr.split()
            fixed = Image.merge("RGB", [ch.point([max(0, min(255, int(round(v * g + o)))) for v in range(256)]) for ch, g, o in zip(channels, gains, offs)])
            enc.stdin.write(fixed.tobytes())
            last_fixed = fixed
        enc.stdin.close()
        err = enc.stderr.read().decode("utf-8", "replace")
        if enc.wait() != 0:
            raise ffmpeg.FFmpegError("colour match encode failed: " + err[-300:])
    except BaseException:
        enc.kill()
        raise
    last_gain, last_off = at(n - 1)
    return {"gain": [round(x, 3) for x in last_gain], "offset": [round(x, 1) for x in last_off], "before": round(before, 2),
            "after": round(colour_distance(last_fixed, ref), 2), "frames": n}
