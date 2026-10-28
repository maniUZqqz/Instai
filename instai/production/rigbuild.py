"""Draft puppet rig from an approved character sheet: every part is generated as an isolated image conditioned on the sheet (Qwen-Image-Edit or
FLUX img2img through the GPU router), cut out of its plain background (BiRefNet-lite if installed, else flood fill), resized to standard
proportions and placed with a default layout. The result is a DRAFT: the owner checks the parts in the rig editor and moves pivots
if needed before approving it. Parts from a PSD / PNG-layer upload (builder.py) are the precise alternative."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from PIL import Image

from instai.assets import storage as asset_storage
from instai.gpu import compute
from instai.providers.base import ProviderError
from instai.providers.comfy.workflows import get_workflow
from instai.render.puppet import cutout
from instai.render.puppet.rig import MOUTH_SHAPES, default_z

from . import hero

BASE = "isolated on a plain pure white background, flat colours, clean lineart, no shadow, no text, centered, the exact same character design as the reference"
PART_PROMPTS = {
    "body": "only the torso and clothes of this character, no head, no arms, no legs, front view",
    "head": "only the head and neck of this character, front view, eyes looking forward, closed relaxed mouth",
    "arm_l": "only one arm of this character hanging straight down with the hand, front view, vertical",
    "arm_r": "only one arm of this character hanging straight down with the hand, front view, vertical",
    "leg_l": "only one leg with the shoe of this character, standing straight, front view, vertical",
    "leg_r": "only one leg with the shoe of this character, standing straight, front view, vertical",
    "eyes_open": "only the pair of open eyes of this character, horizontal strip, no face around them",
    "eyes_closed": "only the pair of closed eyes (blink) of this character, horizontal strip, no face around them",
    "brows_neutral": "only the pair of eyebrows of this character, horizontal strip",
}
MOUTH_PROMPTS = {"A": "closed lips, flat mouth", "B": "mouth slightly open showing the top teeth", "C": "mouth open medium", "D": "mouth wide open saying ah",
                 "E": "round mouth saying oh", "F": "small puckered mouth saying oo", "G": "upper teeth touching the lower lip saying f", "H": "mouth open with the tongue raised saying l",
                 "X": "relaxed closed mouth"}
# target width of each part in the standard 600x900 design canvas
WIDTHS = {"body": 220, "head": 280, "arm_l": 60, "arm_r": 60, "leg_l": 70, "leg_r": 70, "eyes_open": 160, "eyes_closed": 160, "brows_neutral": 170}
for s in MOUTH_SHAPES:
    WIDTHS[f"mouth_{s}"] = 90
DESIGN, ANCHOR = (600, 900), (300, 880)
# placement as fractions of the PARENT image (x, y) where the child's joint sits; roots in design pixels
CHILD_AT = {"head": ("body", 0.5, 0.083), "arm_l": ("body", 0.09, 0.19), "arm_r": ("body", 0.91, 0.19), "eyes_open": ("head", 0.5, 0.5), "eyes_closed": ("head", 0.5, 0.5),
            "brows_neutral": ("head", 0.5, 0.35)}
for s in MOUTH_SHAPES:
    CHILD_AT[f"mouth_{s}"] = ("head", 0.5, 0.757)
ROOT_AT = {"leg_l": (262, 660), "leg_r": (338, 660), "body": (300, 672)}
PIVOT = {"body": (0.5, 0.965), "head": (0.5, 0.96), "arm_l": (0.5, 0.1), "arm_r": (0.5, 0.1), "leg_l": (0.5, 0.04), "leg_r": (0.5, 0.04)}


def layout(images: dict[str, Image.Image], folder: Path, media_root: Path) -> dict:
    """Resize every part to its standard width and write the rig spec with the default layout."""
    sized: dict[str, Image.Image] = {}
    for name, im in images.items():
        if name not in WIDTHS:
            continue
        w = WIDTHS[name]
        sized[name] = im.resize((w, max(1, int(round(im.height * w / im.width)))), Image.LANCZOS)
    parts: dict[str, dict] = {}
    for name, im in sized.items():
        path = folder / f"{name}.png"
        folder.mkdir(parents=True, exist_ok=True)
        im.save(path)
        px, py = PIVOT.get(name, (0.5, 0.5))
        entry = {"image": str(path.relative_to(media_root)).replace("\\", "/"), "pivot": [round(im.width * px, 1), round(im.height * py, 1)], "z": default_z(name), "parent": None,
                 "group": None, "state": None}
        if name in CHILD_AT:
            parent, fx, fy = CHILD_AT[name]
            if parent not in sized:
                parent = None
            else:
                entry["parent"] = parent
                entry["pos"] = [round(sized[parent].width * fx, 1), round(sized[parent].height * fy, 1)]
        if name not in CHILD_AT or entry["parent"] is None:
            entry["pos"] = list(ROOT_AT.get(name, (300, 450)))
        if name.startswith("mouth_"):
            entry.update(group="mouth", state=name[-1], pivot=[round(im.width / 2, 1), round(im.height / 2, 1)])
        elif name.startswith("eyes_"):
            entry.update(group="eyes", state=name.split("_")[1], pivot=[round(im.width / 2, 1), round(im.height / 2, 1)])
        elif name.startswith("brows_"):
            entry.update(group="brows", state="neutral", pivot=[round(im.width / 2, 1), round(im.height / 2, 1)])
        parts[name] = entry
    return {"version": 1, "size": list(DESIGN), "anchor": list(ANCHOR), "parts": parts}


def from_sheet(ctx, character, sheet_path: Path, folder: Path, media_root: Path) -> tuple[dict, dict]:
    """Generate and cut out every part. Returns (rig spec, report {parts, device, seconds, cutout, notes})."""
    wid = hero.reference_workflow()
    if wid is None:
        raise ProviderError("To make parts from the sheet a PC needs Qwen-Image-Edit or FLUX (img2img). Install one, or upload PNG layers / a PSD instead.", retryable=False, code="not_ready")
    spec_wf = get_workflow(wid)
    names = list(PART_PROMPTS) + [f"mouth_{s}" for s in MOUTH_SHAPES]
    method = "birefnet" if cutout.birefnet_available()[0] else "flood-fill"
    work = Path(tempfile.mkdtemp(prefix="rigparts-", dir=settings.MEDIA_ROOT))
    devices: list[str] = []
    done = {"n": 0}

    def one(name: str):
        what = PART_PROMPTS.get(name) or f"close-up of only the mouth of this character, {MOUTH_PROMPTS[name[-1]]}"
        inputs = {"prompt": f"{what}, {BASE}", "image": "@input:ref.png", "seed": 1000 + names.index(name), "negative_prompt": "background, shadow, scene, extra limbs, text"}
        if wid == "flux_dev_fp8_img2img":
            inputs.update(width=768, height=768, denoise=0.8, steps=24)
        res = compute.run_task(ctx, "comfy.graph", {"graph": spec_wf.build(inputs), "workflow": wid, "timeout": 900, "expected": spec_wf.expected_seconds},
                               inputs={"ref.png": sheet_path})
        try:
            pics = res.of_kind(*hero.IMAGE_SUFFIX)
            if not pics:
                raise ProviderError("no image returned for the part " + name, retryable=True)
            with Image.open(pics[0]) as im:
                part = cutout.cut_part(im.convert("RGB"), "auto")
        finally:
            res.cleanup()
        devices.append(res.device)
        done["n"] += 1
        ctx.progress(done["n"] / len(names), f"part {done['n']}/{len(names)}")
        return name, part
    try:
        results = compute.fan_out(ctx, names, one, kind="comfy.graph", payload={"workflow": wid})
        spec = layout(dict(results), folder, media_root)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return spec, {"parts": len(names), "workflow": wid, "cutout": method, "devices": sorted(set(devices)),
                  "notes": ["draft rig: check every part and the pivots in the rig editor before approving it"]}
