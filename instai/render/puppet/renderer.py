"""Puppet scene renderer: layered parallax background + rigged actors + camera -> frames (Pillow) -> H.264 (ffmpeg pipe).

Deterministic (same scene + same audio = same pixels), CPU only, no extra dependency. Scene spec (dict):
  {"width", "height", "fps", "duration", "color": "#202028",
   "background": {"layers": [{"image": path, "parallax": 0.25, "front": false, "fit": "cover"}]},
   "actors": [{"id", "rig": <rig spec, absolute image paths>, "x": 0.5, "y": 0.93, "height": 0.55, "flip": false, "seed": 1,
               "timeline": [{"layer": "base", "clips": [...]}], "mouth": [[start, end, shape], ...], "blink": true, "shadow": true}],
   "camera": [{"t": 0, "x": 0, "y": 0, "zoom": 1.0, "ease": "inout"}]}
Camera x/y are fractions of the canvas width/height; zoom >= 1. Layers with a larger `parallax` move more than the ones behind them.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from instai.render import ffmpeg

from . import geometry as g
from . import lipsync, motions
from .rig import Rig


def hex_rgb(s: str) -> tuple[int, int, int]:
    s = (s or "#202028").lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def camera_at(track: list[dict], t: float) -> tuple[float, float, float]:
    """(x, y, zoom) at time t from keyframes [{t, x, y, zoom, ease}]."""
    if not track:
        return 0.0, 0.0, 1.0
    keys = sorted(track, key=lambda k: k["t"])
    def val(field: str, default: float) -> float:
        return g.track_value([(k["t"], k.get(field, default), k.get("ease", "inout")) for k in keys], t, default)
    return val("x", 0.0), val("y", 0.0), max(1.0, val("zoom", 1.0))


def camera_from_move(move: str, intensity: float, duration: float) -> list[dict]:
    """The storyboard's camera move (zoom_in, pan_left ...) as puppet camera keyframes."""
    k = max(0.0, min(1.0, intensity))
    z, p = 0.08 + 0.14 * k, 0.04 + 0.08 * k
    table = {"zoom_in": ((0, 0, 1.0), (duration, 0, 1.0 + z)), "zoom_out": ((0, 0, 1.0 + z), (duration, 0, 1.0)),
             "pan_left": ((0, p, 1.05), (duration, -p, 1.05)), "pan_right": ((0, -p, 1.05), (duration, p, 1.05)),
             "pan_up": ((0, 0, 1.05), (duration, 0, 1.05)), "pan_down": ((0, 0, 1.05), (duration, 0, 1.05))}
    a, b = table.get(move, ((0, 0, 1.0), (duration, 0, 1.0)))
    track = [{"t": a[0], "x": a[1], "y": 0, "zoom": a[2]}, {"t": b[0], "x": b[1], "y": 0, "zoom": b[2]}]
    if move == "pan_up":
        track = [{"t": 0, "x": 0, "y": p, "zoom": 1.05}, {"t": duration, "x": 0, "y": -p, "zoom": 1.05}]
    if move == "pan_down":
        track = [{"t": 0, "x": 0, "y": -p, "zoom": 1.05}, {"t": duration, "x": 0, "y": p, "zoom": 1.05}]
    return track


class _Layer:
    def __init__(self, spec: dict, w: int, h: int):
        self.parallax = float(spec.get("parallax", 0.25))
        self.front = bool(spec.get("front", False))
        im = Image.open(spec["image"])
        im = im.convert("RGBA")
        margin = 1.0 + 0.10 + 0.25 * max(0.0, self.parallax)
        tw, th = int(w * margin), int(h * margin)
        fit = spec.get("fit", "cover")
        if fit == "stretch":
            big = im.resize((tw, th), Image.LANCZOS)
        else:
            k = max(tw / im.width, th / im.height) if fit == "cover" else min(tw / im.width, th / im.height)
            nw, nh = max(1, int(im.width * k)), max(1, int(im.height * k))
            big = im.resize((nw, nh), Image.LANCZOS)
        self.img = big
        self.has_alpha = big.getextrema()[3][0] < 255

    def draw(self, canvas: Image.Image, cam: tuple[float, float, float]) -> None:
        w, h = canvas.size
        cx, cy, zoom = cam
        zl = 1.0 + (zoom - 1.0) * (0.3 + 0.7 * min(1.5, self.parallax))
        bw, bh = self.img.size
        # crop window (in the oversized layer's pixels): the canvas-sized window shrinks with zoom, and slides with the camera
        win_w, win_h = w / zl, h / zl
        ox = -cx * w * self.parallax
        oy = -cy * h * self.parallax
        max_x, max_y = (bw - win_w) / 2, (bh - win_h) / 2
        ox, oy = max(-max_x, min(max_x, ox)), max(-max_y, min(max_y, oy))
        x0, y0 = bw / 2 - win_w / 2 - ox, bh / 2 - win_h / 2 - oy
        crop = self.img.resize((w, h), Image.BILINEAR, box=(x0, y0, x0 + win_w, y0 + win_h))
        if self.has_alpha:
            canvas.alpha_composite(crop)
        else:
            canvas.paste(crop, (0, 0))


def _blit(canvas: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    """alpha_composite with clipping at every canvas edge."""
    w, h = canvas.size
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(layer.width, w - x), min(layer.height, h - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    sub = layer.crop((sx0, sy0, sx1, sy1)) if (sx0 or sy0 or sx1 < layer.width or sy1 < layer.height) else layer
    canvas.alpha_composite(sub, (x + sx0, y + sy0))


class _Actor:
    def __init__(self, spec: dict, duration: float, w: int, h: int, zoom_max: float, media_root: Path | None):
        self.spec = spec
        self.rig = Rig.from_spec(spec["rig"], media_root)
        self.duration = duration
        self.timeline = motions.Timeline.from_spec(duration, spec.get("timeline"))
        self.cues = [tuple(c) for c in spec.get("mouth", [])]
        self.starts = [c[0] for c in self.cues]
        self.blinks = motions.blink_times(duration, int(spec.get("seed", 1))) if spec.get("blink", True) else []
        self.px = float(spec.get("height", 0.55)) * h / self.rig.size[1]      # canvas px per design px
        self.flip = -1.0 if spec.get("flip") else 1.0
        self.shadow = bool(spec.get("shadow", True))
        self.prescale = max(0.05, self.px * zoom_max)
        self._images: dict[str, Image.Image] = {}

    def image(self, part) -> Image.Image:
        im = self._images.get(part.name)
        if im is None:
            src = Image.open(part.image).convert("RGBA")
            k = min(1.0, self.prescale)
            if k < 0.999:
                src = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))), Image.LANCZOS)
            im = self._images[part.name] = src
        return im

    def draw(self, canvas: Image.Image, t: float, cam: tuple[float, float, float]) -> None:
        w, h = canvas.size
        cx, cy, zoom = cam
        sp = self.spec
        root = self.timeline.root_x(t) * self.px * self.flip
        wx, wy = float(sp.get("x", 0.5)) * w + root, float(sp.get("y", 0.93)) * h
        sx = w / 2 + zoom * (wx - w / 2 - cx * w)
        sy = h / 2 + zoom * (wy - h / 2 - cy * h)
        s = self.px * zoom
        if self.shadow:
            rw, rh = self.rig.size[0] * s * 0.22, self.rig.size[1] * s * 0.025
            sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse((sx - rw, sy - rh, sx + rw, sy + rh), fill=(0, 0, 0, 70))
            canvas.alpha_composite(sh)
        base = g.mul(g.translate(sx, sy), g.mul(g.scale(s * self.flip, s), g.translate(-self.rig.anchor[0], -self.rig.anchor[1])))
        pose = self.timeline.pose(t)
        mats = self.rig.world_matrices(base, pose)
        mouth = lipsync.shape_at(self.cues, t, self.starts) if self.cues else "X"
        eyes = "closed" if motions.is_blinking(self.blinks, t) else "open"
        for part in self.rig.visible_parts(mouth, eyes):
            im = self.image(part)
            k = min(1.0, self.prescale)
            # image pixels (pre-scaled by k) -> design px -> canvas
            m = g.mul(mats[part.name], g.scale(1.0 / k))
            x0, y0, x1, y1 = g.bbox(m, im.width, im.height)
            bx, by = math.floor(x0), math.floor(y0)
            bw, bh = math.ceil(x1) - bx + 1, math.ceil(y1) - by + 1
            if bw <= 0 or bh <= 0 or bx > w or by > h or bx + bw < 0 or by + bh < 0 or bw > 4 * w or bh > 4 * h:
                continue
            m2 = g.mul(g.translate(-bx, -by), m)
            layer = im.transform((bw, bh), Image.AFFINE, g.pil_inverse(m2), resample=Image.BICUBIC)
            _blit(canvas, layer, bx, by)


class PuppetRenderer:
    def __init__(self, scene: dict, media_root: Path | None = None):
        self.scene = scene
        self.w, self.h = int(scene["width"]), int(scene["height"])
        self.fps = int(scene.get("fps", 15))
        self.duration = float(scene["duration"])
        self.camera = scene.get("camera") or []
        zoom_max = max([1.0] + [float(k.get("zoom", 1.0)) for k in self.camera])
        self.color = hex_rgb(scene.get("color", "#202028"))
        layers = [_Layer(s, self.w, self.h) for s in (scene.get("background") or {}).get("layers", []) if Path(s.get("image", "")).is_file()]
        self.back = [layer for layer in layers if not layer.front]
        self.front = [layer for layer in layers if layer.front]
        self.actors = [_Actor(a, self.duration, self.w, self.h, zoom_max, media_root) for a in scene.get("actors", [])]

    @property
    def frames(self) -> int:
        return max(2, int(round(self.duration * self.fps)))

    def frame(self, t: float) -> Image.Image:
        cam = camera_at(self.camera, t)
        canvas = Image.new("RGBA", (self.w, self.h), self.color + (255,))
        for layer in self.back:
            layer.draw(canvas, cam)
        for a in self.actors:
            a.draw(canvas, t, cam)
        for layer in self.front:
            layer.draw(canvas, cam)
        return canvas

    def render(self, out_path: Path, *, ctx=None, on_progress=None, crf: int = 20, preset: str = "veryfast") -> dict:
        """Encode the whole shot to a silent H.264 clip. Cancellable through the job context."""
        ff, _ = ffmpeg.binaries()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.w}x{self.h}", "-r", str(self.fps),
               "-i", "-", "-an", "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", str(self.fps),
               "-movflags", "+faststart", str(out_path)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        n = self.frames
        try:
            for i in range(n):
                if ctx is not None and i % 6 == 0:
                    ctx.check()
                p.stdin.write(self.frame(i / self.fps).convert("RGB").tobytes())
                if on_progress and i % 6 == 0:
                    on_progress(i / n)
            p.stdin.close()
            err = p.stderr.read().decode("utf-8", "replace")
            if p.wait() != 0:
                raise ffmpeg.FFmpegError("ffmpeg failed while encoding the puppet shot: " + err[-400:])
        except BaseException:
            p.kill()
            raise
        return {"frames": n, "fps": self.fps, "duration": n / self.fps, "path": str(out_path)}
