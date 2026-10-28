"""Cut a part out of its background (Pillow only) and, when onnxruntime + the BiRefNet-lite model are installed, with AI.

* `remove_background`: flood fill from the image border with a colour tolerance (works for parts drawn on a flat white / chroma
  background, which is how the character-sheet parts are generated), edges feathered a little.
* `birefnet_alpha`: BiRefNet-lite ONNX (MIT) saliency mask - optional, needs `pip install onnxruntime numpy` and the model file
  (`Download-Models.bat --only birefnet`). Not required for any default path.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SENTINEL = (255, 0, 255)


def trim(img: Image.Image, pad: int = 2) -> tuple[Image.Image, tuple[int, int]]:
    """Crop to the non-transparent area. Returns (image, (left, top) in the original)."""
    bb = img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if not bb:
        return img, (0, 0)
    l, t, r, b = max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad)
    return img.crop((l, t, r, b)), (l, t)


def remove_background(img: Image.Image, tolerance: int = 38, feather: float = 1.2) -> Image.Image:
    """RGBA with the border-connected background made transparent."""
    rgb = img.convert("RGB")
    if rgb.getpixel((0, 0)) == SENTINEL:
        raise ValueError("unexpected sentinel colour in the corner")
    work = rgb.copy()
    w, h = work.size
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    for s in seeds:
        if work.getpixel(s) != SENTINEL:
            ImageDraw.floodfill(work, s, SENTINEL, thresh=tolerance)
    diff = ImageChops.difference(work, Image.new("RGB", work.size, SENTINEL)).convert("L")
    mask = diff.point(lambda v: 255 if v > 0 else 0)          # 255 = kept (not the sentinel)
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    out = img.convert("RGBA")
    out.putalpha(ImageChops.multiply(mask, out.getchannel("A")))
    return out


def birefnet_available() -> tuple[bool, str]:
    from instai.core import runtime

    model = runtime.models_root() / "birefnet" / "birefnet-lite.onnx"
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError:
        return False, "onnxruntime/numpy are not installed (optional: pip install onnxruntime numpy)"
    return (model.is_file(), "ready" if model.is_file() else "model missing (Download-Models.bat --only birefnet)")


def birefnet_alpha(img: Image.Image, session=None) -> Image.Image:
    """RGBA from the BiRefNet-lite saliency mask. `session` is injectable for tests (an object with .run and .get_inputs)."""
    import numpy as np

    if session is None:
        import onnxruntime as ort

        from instai.core import runtime

        session = ort.InferenceSession(str(runtime.models_root() / "birefnet" / "birefnet-lite.onnx"), providers=["CPUExecutionProvider"])
    rgb = img.convert("RGB")
    size = 1024
    arr = np.asarray(rgb.resize((size, size), Image.BILINEAR), dtype=np.float32) / 255.0
    arr = (arr - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    x = arr.transpose(2, 0, 1)[None].astype(np.float32)
    logits = np.asarray(session.run(None, {session.get_inputs()[0].name: x})[0]).reshape(size, size)
    prob = 1.0 / (1.0 + np.exp(-logits))
    mask = Image.fromarray((prob * 255).clip(0, 255).astype("uint8")).resize(rgb.size, Image.BILINEAR)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def cut_part(img: Image.Image, method: str = "auto") -> Image.Image:
    """auto = BiRefNet when available, else flood fill. Returns a trimmed RGBA part."""
    if method in ("auto", "birefnet") and birefnet_available()[0]:
        try:
            return trim(birefnet_alpha(img))[0]
        except Exception:  # noqa: BLE001 - fall back to the plain method
            if method == "birefnet":
                raise
    return trim(remove_background(img))[0]


def save_png(img: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path
