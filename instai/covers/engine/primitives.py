"""Low-level picture parts: gradients, rays, halftone, shadows, sticker outline, the layered canvas.

All Pillow + numpy (+ cv2 when present, otherwise a Pillow fallback). No Django and no network, so it is fast and easy to test.
Coordinates and sizes are pixels; scaling (preview vs full output) is the job of the upper layer (``render.Ctx``).

SOURCE: ported from NMarketing:backend/apps/thumbs/primitives.py @ v3.02 (c23f861), adapted for series/episode covers.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

try:  # pragma: no cover - cv2 is optional
    import cv2
except Exception:  # noqa: BLE001
    cv2 = None


# ───────────────────────────── colour

def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgba(h: str, a: int = 255) -> tuple[int, int, int, int]:
    r, g, b = rgb(h)
    return r, g, b, max(0, min(255, int(a)))


def lerp_hex(a: str, b: str, t: float) -> str:
    ra, rb = rgb(a), rgb(b)
    return "#%02x%02x%02x" % tuple(int(round(ra[i] + (rb[i] - ra[i]) * t)) for i in range(3))


# ───────────────────────────── gradients and lights

def _stops_array(stops) -> tuple[np.ndarray, np.ndarray]:
    pos = np.array([s[0] for s in stops], dtype=np.float32)
    cols = np.array([rgb(s[1]) for s in stops], dtype=np.float32)
    return pos, cols


def _apply_stops(t: np.ndarray, stops) -> np.ndarray:
    pos, cols = _stops_array(stops)
    flat = np.clip(t, 0.0, 1.0).reshape(-1)
    out = np.stack([np.interp(flat, pos, cols[:, i]) for i in range(3)], axis=1)
    return out.reshape(t.shape + (3,))


def gradient(size: tuple[int, int], stops, angle: float = 90.0) -> Image.Image:
    """Linear gradient. ``angle`` is the direction of travel: 0 = left to right, 90 = top to bottom (y points down)."""
    w, h = size
    a = math.radians(angle)
    dx, dy = math.cos(a), math.sin(a)
    xs = (np.arange(w, dtype=np.float32) - w / 2.0)[None, :]
    ys = (np.arange(h, dtype=np.float32) - h / 2.0)[:, None]
    proj = xs * dx + ys * dy
    half = abs(w / 2.0 * dx) + abs(h / 2.0 * dy) or 1.0
    t = (proj / half + 1.0) / 2.0
    arr = _apply_stops(t, stops)
    return Image.fromarray(arr.astype(np.uint8))


def radial(size: tuple[int, int], center: tuple[float, float], radius: float, stops) -> Image.Image:
    """Radial gradient; ``center`` and ``radius`` in pixels (t=1 at the radius)."""
    w, h = size
    xs = (np.arange(w, dtype=np.float32) - center[0])[None, :]
    ys = (np.arange(h, dtype=np.float32) - center[1])[:, None]
    t = np.sqrt(xs * xs + ys * ys) / max(1.0, radius)
    return Image.fromarray(_apply_stops(t, stops).astype(np.uint8))


def glow_blob(size: tuple[int, int], center: tuple[float, float], radius: float, color: str, strength: float = 0.8,
              power: float = 1.8) -> Image.Image:
    """Soft light blob (RGBA): one colour, alpha falls smoothly from the centre to the edge."""
    w, h = size
    xs = (np.arange(w, dtype=np.float32) - center[0])[None, :]
    ys = (np.arange(h, dtype=np.float32) - center[1])[:, None]
    t = np.clip(np.sqrt(xs * xs + ys * ys) / max(1.0, radius), 0.0, 1.0)
    a = (1.0 - t) ** power * strength
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = rgb(color)
    out[..., 3] = np.clip(a * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def rays(size: tuple[int, int], center: tuple[float, float], n: int, color: str, alpha: float = 0.18, rot: float = 0.0,
         fade: float = 1.0) -> Image.Image:
    """Sun rays (RGBA): n alternating wedges that fade softly towards the edge."""
    w, h = size
    xs = (np.arange(w, dtype=np.float32) - center[0])[None, :]
    ys = (np.arange(h, dtype=np.float32) - center[1])[:, None]
    theta = np.arctan2(ys, xs) + math.radians(rot)
    seg = (theta + math.pi) / (2 * math.pi) * n
    wedge = (np.floor(seg).astype(np.int32) % 2 == 0).astype(np.float32)
    dist = np.sqrt(xs * xs + ys * ys) / (math.hypot(w, h) * 0.75)
    fade_a = np.clip(1.0 - dist * fade, 0.0, 1.0) ** 0.8
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = rgb(color)
    out[..., 3] = np.clip(wedge * fade_a * alpha * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def halftone(size: tuple[int, int], color: str, alpha: float = 0.25, spacing: float = 18.0, angle: float = 30.0,
             direction: float | None = 90.0, floor_amp: float = 0.12, ceil_amp: float = 0.48) -> Image.Image:
    """Halftone dots (RGBA). ``direction``: the direction in which the dots grow (None = uniform)."""
    w, h = size
    xs = np.arange(w, dtype=np.float32)[None, :]
    ys = np.arange(h, dtype=np.float32)[:, None]
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    u = (xs * ca + ys * sa) / spacing
    v = (-xs * sa + ys * ca) / spacing
    fu, fv = u - np.round(u), v - np.round(v)
    d = np.sqrt(fu * fu + fv * fv)
    if direction is None:
        amp = np.full((h, w), (floor_amp + ceil_amp) / 2.0, dtype=np.float32)
    else:
        dr = math.radians(direction)
        t = ((xs - w / 2) * math.cos(dr) + (ys - h / 2) * math.sin(dr)) / (0.5 * (abs(w * math.cos(dr)) + abs(h * math.sin(dr))) or 1.0)
        amp = floor_amp + (ceil_amp - floor_amp) * np.clip((t + 1) / 2, 0, 1)
    cov = np.clip((amp - d) * spacing + 0.5, 0.0, 1.0)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = rgb(color)
    out[..., 3] = np.clip(cov * alpha * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def stripes(size: tuple[int, int], color: str, alpha: float = 0.1, width: float = 40.0, angle: float = 35.0) -> Image.Image:
    w, h = size
    xs = np.arange(w, dtype=np.float32)[None, :]
    ys = np.arange(h, dtype=np.float32)[:, None]
    a = math.radians(angle)
    v = (xs * math.cos(a) + ys * math.sin(a)) / width
    m = (np.floor(v).astype(np.int32) % 2 == 0).astype(np.float32)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = rgb(color)
    out[..., 3] = np.clip(m * alpha * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def grain(img: Image.Image, amount: float = 0.05, seed: int = 1) -> Image.Image:
    """Film grain over an RGB picture (additive, no colour shift)."""
    rng = np.random.default_rng(seed)
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    n = rng.normal(0.0, amount * 255.0, a.shape[:2]).astype(np.float32)[..., None]
    return Image.fromarray(np.clip(a + n, 0, 255).astype(np.uint8))


def vignette(img: Image.Image, strength: float = 0.45, power: float = 2.2) -> Image.Image:
    w, h = img.size
    xs = (np.arange(w, dtype=np.float32) - w / 2.0)[None, :] / (w / 2.0)
    ys = (np.arange(h, dtype=np.float32) - h / 2.0)[:, None] / (h / 2.0)
    d = np.clip(np.sqrt(xs * xs + ys * ys) / 1.35, 0, 1) ** power
    a = np.asarray(img.convert("RGB"), dtype=np.float32) * (1.0 - strength * d)[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def edge_ramp(size: tuple[int, int], side: str, extent: float, start: float = 0.0, power: float = 1.0) -> Image.Image:
    """L mask that starts at alpha 255 on ``side`` (top/bottom/left/right) and falls to 0 after ``extent`` (a fraction of the dimension)."""
    w, h = size
    if side in ("top", "bottom"):
        t = (np.arange(h, dtype=np.float32) / max(1.0, h - 1))[:, None] * np.ones((1, w), dtype=np.float32)
        if side == "bottom":
            t = 1.0 - t
    else:
        t = (np.arange(w, dtype=np.float32) / max(1.0, w - 1))[None, :] * np.ones((h, 1), dtype=np.float32)
        if side == "right":
            t = 1.0 - t
    v = 1.0 - np.clip((t - start) / max(1e-6, extent), 0.0, 1.0)
    return Image.fromarray(np.clip((v ** power) * 255.0, 0, 255).astype(np.uint8))


# ───────────────────────────── crop and size

def cover(img: Image.Image, size: tuple[int, int], focus: tuple[float, float] = (0.5, 0.5)) -> Image.Image:
    """Fill ``size`` completely with a crop (like CSS object-fit: cover)."""
    w, h = size
    iw, ih = img.size
    s = max(w / iw, h / ih)
    nw, nh = max(w, int(math.ceil(iw * s))), max(h, int(math.ceil(ih * s)))
    r = img.resize((nw, nh), Image.Resampling.LANCZOS)
    x = int(round((nw - w) * min(1.0, max(0.0, focus[0]))))
    y = int(round((nh - h) * min(1.0, max(0.0, focus[1]))))
    return r.crop((x, y, x + w, y + h))


def contain(img: Image.Image, box_w: float, box_h: float) -> Image.Image:
    iw, ih = img.size
    s = min(box_w / iw, box_h / ih)
    return img.resize((max(1, int(round(iw * s))), max(1, int(round(ih * s)))), Image.Resampling.LANCZOS)


def alpha_bbox(img: Image.Image, threshold: int = 12) -> tuple[int, int, int, int] | None:
    if img.mode != "RGBA":
        return (0, 0) + img.size
    a = img.getchannel("A").point(lambda v: 255 if v > threshold else 0)
    return a.getbbox()


def crop_to_alpha(img: Image.Image, pad: int = 0) -> Image.Image:
    img = img.convert("RGBA")
    bb = alpha_bbox(img)
    if not bb:
        return img
    x0, y0, x1, y1 = bb
    return img.crop((max(0, x0 - pad), max(0, y0 - pad), min(img.width, x1 + pad), min(img.height, y1 + pad)))


def has_cutout(img: Image.Image, min_clear: float = 0.04) -> bool:
    """Does the picture really have a transparent background (not merely a fully opaque alpha channel)?"""
    if img.mode != "RGBA":
        return False
    a = np.asarray(img.getchannel("A"))
    return float((a < 20).mean()) >= min_clear


def is_blank(img: Image.Image, edge_frac: float = 0.006, step: float = 10.0) -> bool:
    """A picture "without a subject": a flat colour, a plain gradient or a low-detail decorative background (like a placeholder picture that is only a gradient with a few
    faint stripes and no object in it).

    Two measures on a small copy:
    1) second-order difference (64x64): zero for a flat colour and a linear gradient; only the real edge of an object / a face raises it. Under 0.6% edge pixels = plain.
    2) local contrast (96x96, difference to a blurred copy): decorative backgrounds average about 2 and have under 5.5% high-contrast pixels, while
       even a small object (18% of the width) on a plain background gives about 3.6 and real photos more than 5.5 (measured on real photos).
    An object on a white background has an edge round itself, so it does not count as plain."""
    rgb = img.convert("RGB")
    a = np.asarray(rgb.resize((64, 64), Image.Resampling.BILINEAR), dtype=np.float32)
    d2x = np.abs(a[:, 2:] - 2 * a[:, 1:-1] + a[:, :-2]).max(axis=2)
    d2y = np.abs(a[2:] - 2 * a[1:-1] + a[:-2]).max(axis=2)
    if (float((d2x > step).mean()) + float((d2y > step).mean())) / 2 < edge_frac:
        return True
    s = rgb.resize((96, 96), Image.Resampling.BILINEAR)
    d = np.abs(np.asarray(s, dtype=np.float32) - np.asarray(s.filter(ImageFilter.GaussianBlur(6)), dtype=np.float32)).max(axis=2)
    return float(d.mean()) < 2.6 and float((d > 12).mean()) < 0.055


# ───────────────────────────── masks and shapes

def aa_mask(size: tuple[int, int], draw_fn, ss: int = 3) -> Image.Image:
    """L mask with a smooth edge: ``draw_fn(draw, k)`` draws on a canvas k times larger (supersampling)."""
    w, h = size
    big = Image.new("L", (max(1, w * ss), max(1, h * ss)), 0)
    draw_fn(ImageDraw.Draw(big), ss)
    return big.resize((w, h), Image.Resampling.LANCZOS)


def rounded_mask(size: tuple[int, int], radius: float) -> Image.Image:
    return aa_mask(size, lambda d, k: d.rounded_rectangle([0, 0, size[0] * k - 1, size[1] * k - 1], radius=radius * k, fill=255))


def polygon_mask(size: tuple[int, int], pts: list[tuple[float, float]]) -> Image.Image:
    return aa_mask(size, lambda d, k: d.polygon([(x * k, y * k) for x, y in pts], fill=255))


def star_points(cx: float, cy: float, r_out: float, r_in: float, n: int, rot: float = 0.0) -> list[tuple[float, float]]:
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot) + math.pi * i / n - math.pi / 2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def dilate(mask: Image.Image, px: float) -> Image.Image:
    """Grow an L mask by px pixels (circular)."""
    px = int(round(px))
    if px <= 0:
        return mask
    px = min(px, 120)
    if cv2 is not None:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))
        return Image.fromarray(cv2.dilate(np.asarray(mask), k))
    out = mask
    steps = max(1, px // 3)
    for _ in range(steps):                      # slow but always works
        out = out.filter(ImageFilter.MaxFilter(7))
    return out


def solid(size: tuple[int, int], color: str, mask: Image.Image | None = None, alpha: float = 1.0) -> Image.Image:
    r, g, b = rgb(color)
    im = Image.new("RGBA", size, (r, g, b, 255))
    a = mask if mask is not None else Image.new("L", size, 255)
    if alpha < 1.0:
        a = a.point(lambda v: int(v * alpha))
    im.putalpha(a)
    return im


def blur_alpha(mask: Image.Image, r: float) -> Image.Image:
    return mask.filter(ImageFilter.GaussianBlur(max(0.1, r)))


def stylized(mask: Image.Image, fill: str | Image.Image | None, outline: str | None = None, ow: float = 0.0,
             shadow: tuple[float, float, float, str, float] | None = None, glow: tuple[str, float, float] | None = None
             ) -> tuple[Image.Image, tuple[int, int]]:
    """L mask -> (RGBA picture with outline/shadow/glow, the offset the padding added).

    shadow = (dx, dy, blur, color, opacity)  ·  glow = (color, radius, strength)
    The picture is the mask size plus the padding; the offset is that padding (to align it again)."""
    w, h = mask.size
    reach = ow + (glow[1] * 2.5 if glow else 0)
    if shadow:
        reach = max(reach, abs(shadow[0]) + abs(shadow[1]) + shadow[2] * 2.5)
    pad = int(math.ceil(reach)) + 4
    big = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    big.paste(mask, (pad, pad))
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    if shadow:
        dx, dy, bl, sc, so = shadow
        base = dilate(big, ow) if ow > 0 else big
        sh = ImageChops.offset(base, int(round(dx)), int(round(dy))).filter(ImageFilter.GaussianBlur(max(0.1, bl)))
        out = Image.alpha_composite(out, solid(big.size, sc, sh, so))
    if glow:
        gc, gr, gs = glow
        base = dilate(big, ow) if ow > 0 else big
        gl = base.filter(ImageFilter.GaussianBlur(max(0.1, gr)))
        out = Image.alpha_composite(out, solid(big.size, gc, gl, min(1.0, gs)))
    if outline and ow > 0:
        out = Image.alpha_composite(out, solid(big.size, outline, dilate(big, ow)))
    if fill is not None:
        if isinstance(fill, str):
            out = Image.alpha_composite(out, solid(big.size, fill, big))
        else:
            f = fill.convert("RGBA")
            canvas = Image.new("RGBA", big.size, (0, 0, 0, 0))
            canvas.paste(f.resize(mask.size), (pad, pad))
            canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), big))
            out = Image.alpha_composite(out, canvas)
    return out, (pad, pad)


def sticker(img: Image.Image, ow: float, outline: str = "#ffffff", shadow: tuple[float, float, float, str, float] | None = None,
            glow: tuple[str, float, float] | None = None, rim: str | None = None) -> tuple[Image.Image, tuple[int, int]]:
    """Make an RGBA (a cut-out subject) sticker-like: wide outline + shadow/glow. -> (picture, offset of the padding)."""
    img = img.convert("RGBA")
    a = img.getchannel("A")
    reach = ow + (glow[1] * 2.5 if glow else 0)
    if shadow:
        reach = max(reach, abs(shadow[0]) + abs(shadow[1]) + shadow[2] * 2.5)
    pad = int(math.ceil(reach)) + 4
    size = (img.width + 2 * pad, img.height + 2 * pad)
    big_a = Image.new("L", size, 0)
    big_a.paste(a, (pad, pad))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    base = dilate(big_a, ow) if ow > 0 else big_a
    if shadow:
        dx, dy, bl, sc, so = shadow
        sh = ImageChops.offset(base, int(round(dx)), int(round(dy))).filter(ImageFilter.GaussianBlur(max(0.1, bl)))
        out = Image.alpha_composite(out, solid(size, sc, sh, so))
    if glow:
        gc, gr, gs = glow
        out = Image.alpha_composite(out, solid(size, gc, base.filter(ImageFilter.GaussianBlur(max(0.1, gr))), min(1.0, gs)))
    if ow > 0:
        out = Image.alpha_composite(out, solid(size, outline, base))
    body = Image.new("RGBA", size, (0, 0, 0, 0))
    body.paste(img, (pad, pad))
    if rim:                                           # coloured light edge on the subject itself (neon half-shadow)
        edge = ImageChops.subtract(big_a, big_a.filter(ImageFilter.GaussianBlur(max(1.5, ow * 0.5))))
        rim_img = solid(size, rim, edge)
        body = Image.alpha_composite(body, rim_img)
    out = Image.alpha_composite(out, body)
    return out, (pad, pad)


def soft_shadow(size: tuple[int, int], mask: Image.Image, dx: float, dy: float, blur: float, color: str = "#000000",
                opacity: float = 0.5) -> Image.Image:
    sh = ImageChops.offset(mask, int(round(dx)), int(round(dy))).filter(ImageFilter.GaussianBlur(max(0.1, blur)))
    return solid(size, color, sh, opacity)


def with_opacity(img: Image.Image, opacity: float) -> Image.Image:
    img = img.convert("RGBA")
    if opacity >= 1.0:
        return img
    a = img.getchannel("A").point(lambda v: int(v * max(0.0, opacity)))
    out = img.copy()
    out.putalpha(a)
    return out


# ───────────────────────────── colour effects on a photo

def tint_duotone(img: Image.Image, dark: str, light: str, strength: float = 1.0) -> Image.Image:
    g = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    d, l = np.array(rgb(dark), dtype=np.float32), np.array(rgb(light), dtype=np.float32)
    duo = d[None, None, :] * (1 - g[..., None]) + l[None, None, :] * g[..., None]
    base = np.asarray(img.convert("RGB"), dtype=np.float32)
    return Image.fromarray(np.clip(base * (1 - strength) + duo * strength, 0, 255).astype(np.uint8), "RGB")


def grade_teal_orange(img: Image.Image, strength: float = 0.5) -> Image.Image:
    """Cinematic grade: shadows to teal, highlights to warm orange."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    lum = (a[..., 0] * 0.3 + a[..., 1] * 0.59 + a[..., 2] * 0.11)[..., None]
    teal = np.array([0.05, 0.38, 0.45], dtype=np.float32)
    warm = np.array([1.0, 0.62, 0.3], dtype=np.float32)
    tone = teal * (1 - lum) + warm * lum
    out = a * (1 - strength * 0.5) + (a * tone * 1.6) * (strength * 0.5)
    return Image.fromarray(np.clip(out * 255.0, 0, 255).astype(np.uint8))


def adjust(img: Image.Image, brightness: float = 1.0, saturation: float = 1.0, contrast: float = 1.0) -> Image.Image:
    from PIL import ImageEnhance

    out = img.convert("RGB")
    if saturation != 1.0:
        out = ImageEnhance.Color(out).enhance(saturation)
    if contrast != 1.0:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    if brightness != 1.0:
        out = ImageEnhance.Brightness(out).enhance(brightness)
    return out


def darken(img: Image.Image, amount: float, color: str = "#000000") -> Image.Image:
    return Image.blend(img.convert("RGB"), Image.new("RGB", img.size, rgb(color)), max(0.0, min(1.0, amount)))


# ───────────────────────────── the layered canvas

@dataclass
class Composer:
    """An RGB canvas that places layers on top of each other in order and keeps one report row per layer (name, kind, real box).

    ``keep=True`` -> every layer (cropped to its box) is kept for a layered export."""
    size: tuple[int, int]
    keep: bool = False
    canvas: Image.Image = field(init=False)
    report: list[dict] = field(default_factory=list)
    layers: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.canvas = Image.new("RGB", self.size, (0, 0, 0))

    def add(self, name: str, kind: str, img: Image.Image, xy: tuple[int, int] = (0, 0), *, blend: str = "normal",
            opacity: float = 1.0, record: bool = True) -> tuple[int, int, int, int] | None:
        """Place a layer. -> the real box of the visible pixels (x0,y0,x1,y1) on the canvas, or None when nothing is visible."""
        img = img if img.mode in ("RGB", "RGBA") else img.convert("RGBA")
        x, y = int(round(xy[0])), int(round(xy[1]))
        W, H = self.size
        # crop to the shared area
        sx0, sy0 = max(0, -x), max(0, -y)
        dx0, dy0 = max(0, x), max(0, y)
        dx1, dy1 = min(W, x + img.width), min(H, y + img.height)
        if dx1 <= dx0 or dy1 <= dy0:
            return None
        part = img.crop((sx0, sy0, sx0 + (dx1 - dx0), sy0 + (dy1 - dy0)))
        box = (dx0, dy0, dx1, dy1)
        if blend == "normal" and opacity >= 0.999:
            if part.mode == "RGBA":
                self.canvas.paste(part.convert("RGB"), (dx0, dy0), part.getchannel("A"))
            else:
                self.canvas.paste(part, (dx0, dy0))
        else:
            self._blend(part, box, blend, opacity)
        bbox = None
        if part.mode == "RGBA":
            vis = part.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
            if vis:
                bbox = (dx0 + vis[0], dy0 + vis[1], dx0 + vis[2], dy0 + vis[3])
        else:
            bbox = box
        if record and bbox:
            self.report.append({"name": name, "kind": kind, "bbox": list(bbox), "blend": blend, "opacity": round(opacity, 3)})
        if self.keep and bbox:
            self.layers.append({"name": name, "kind": kind, "img": img.convert("RGBA"), "xy": (x, y), "blend": blend,
                                "opacity": opacity})
        return bbox

    def _blend(self, part: Image.Image, box, mode: str, opacity: float) -> None:
        base = np.asarray(self.canvas.crop(box), dtype=np.float32) / 255.0
        lay = np.asarray(part.convert("RGBA"), dtype=np.float32) / 255.0
        a = (lay[..., 3:4] * opacity)
        c = lay[..., :3]
        if mode == "screen":
            mixed = 1.0 - (1.0 - base) * (1.0 - c)
        elif mode == "multiply":
            mixed = base * c
        elif mode == "add":
            mixed = np.minimum(1.0, base + c)
        elif mode == "overlay":
            mixed = np.where(base < 0.5, 2 * base * c, 1 - 2 * (1 - base) * (1 - c))
        else:
            mixed = c
        out = base * (1 - a) + mixed * a
        self.canvas.paste(Image.fromarray(np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)), (box[0], box[1]))

    def replace(self, img: Image.Image) -> None:
        """Replace the whole canvas (like film grain or a vignette that sits on everything)."""
        self.canvas = img.convert("RGB") if img.size == self.size else img.convert("RGB").resize(self.size)
