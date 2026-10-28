"""Generated placeholder images (Pillow only): the keyframes of demo mode and tests, and parallax test layers.
Not artwork: every placeholder says what it stands for, so nobody mistakes it for a result."""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

PALETTES = [((32, 44, 90), (200, 90, 120)), ((20, 70, 80), (240, 190, 90)), ((60, 30, 90), (90, 200, 200)), ((90, 40, 30), (240, 160, 120))]


def _font(size: int):
    try:
        return ImageFont.truetype(str(Path(__file__).parent / "fonts" / "Vazirmatn-Bold.ttf"), size)
    except OSError:
        return ImageFont.load_default()


def make_placeholder(path: str | Path, width: int, height: int, label: str, seed: str = "") -> Path:
    h = int(hashlib.sha256(f"{seed}|{label}".encode()).hexdigest()[:8], 16)
    c1, c2 = PALETTES[h % len(PALETTES)]
    img = ImageOps.colorize(Image.linear_gradient("L").resize((width, height)), c1, c2)  # vertical gradient
    d = ImageDraw.Draw(img)
    r = min(width, height) // 5
    cx, cy = width // 2 + (h % 7 - 3) * width // 20, height // 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255))
    d.rectangle([width // 10, height * 3 // 4, width * 9 // 10, height * 3 // 4 + height // 40], fill=(255, 255, 255))
    d.text((width // 2, height // 8), label, fill=(255, 255, 255), font=_font(max(14, width // 14)), anchor="mm")
    d.text((width // 2, height - height // 12), "placeholder", fill=(255, 255, 255), font=_font(max(12, width // 22)), anchor="mm")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return Path(path)


def make_parallax_layers(bg_path: str | Path, fg_path: str | Path, width: int, height: int, seed: str = "") -> tuple[Path, Path]:
    """Background gradient + a foreground RGBA cut-out (a disc) - what BiRefNet will produce from real keyframes in Phase 3."""
    make_placeholder(bg_path, width, height, "background", seed)
    fg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(fg)
    r = min(width, height) // 4
    d.ellipse([width // 2 - r, height // 2 - r, width // 2 + r, height // 2 + r], fill=(250, 220, 60, 255))
    fg.save(fg_path)
    return Path(bg_path), Path(fg_path)
