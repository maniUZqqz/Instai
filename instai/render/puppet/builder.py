"""Build a rig spec from separate layer images: a ZIP of PNGs, a PSD (optional `psd-tools`) or already-cut part images.

Layer names decide the role (`body`, `head`, `arm_l`, `arm_r`, `leg_l`, `leg_r`, `eyes_open`, `eyes_closed`, `brows_*`, `mouth_A` ... `mouth_X`,
`prop_*`). If every layer has the same size (a full-canvas export, what PSD/Procreate/Krita "export layers" gives) the position of each
part is read from where it sits in the canvas; otherwise a `rig.json` in the ZIP must give `pos` for each part.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from PIL import Image

from . import cutout
from .rig import MOUTH_SHAPES, RigError, default_z

ROLE_PARENT = {"head": "body", "arm_l": "body", "arm_r": "body"}
# where the joint of a part is, as a fraction of its own (trimmed) image: (x, y)
PIVOT_FRAC = {"body": (0.5, 0.97), "head": (0.5, 0.97), "arm": (0.5, 0.08), "leg": (0.5, 0.04)}


def classify(name: str) -> tuple[str, str | None, str | None]:
    """(clean name, group, state) from a layer name such as 'Mouth A', 'eyes-closed', 'arm_L'."""
    n = re.sub(r"[^A-Za-z0-9]+", "_", name.strip()).strip("_")
    low = n.lower()
    m = re.fullmatch(r"mouth_?([a-hx])", low)
    if m:
        s = m.group(1).upper()
        return f"mouth_{s}", "mouth", s
    m = re.fullmatch(r"(eyes?)_?(open|closed|blink)", low)
    if m:
        s = "closed" if m.group(2) in ("closed", "blink") else "open"
        return f"eyes_{s}", "eyes", s
    m = re.fullmatch(r"brows?_?(\w+)", low)
    if m:
        return f"brows_{m.group(1)}", "brows", m.group(1)
    low = {"arm_left": "arm_l", "arm_right": "arm_r", "leg_left": "leg_l", "leg_right": "leg_r", "larm": "arm_l", "rarm": "arm_r"}.get(low, low)
    return low, None, None


def _pivot(name: str, size: tuple[int, int]) -> tuple[float, float]:
    key = name.split("_")[0]
    fx, fy = PIVOT_FRAC.get(key, (0.5, 0.5))
    return round(size[0] * fx, 1), round(size[1] * fy, 1)


def _parent(name: str, group: str | None, have: set[str]) -> str | None:
    if group in ("mouth", "eyes", "brows") or name.startswith(("hair", "hat", "glasses")):
        return "head" if "head" in have else ("body" if "body" in have else None)
    if name in ROLE_PARENT:
        return ROLE_PARENT[name] if ROLE_PARENT[name] in have else None
    if name.startswith("prop"):
        return "body" if "body" in have else None
    return None


def rig_from_layers(layers: dict[str, Image.Image], out_dir: Path, media_root: Path, *, extra: dict | None = None) -> dict:
    """layers: {layer name: RGBA image}. Writes trimmed PNGs into out_dir and returns the rig spec."""
    extra = extra or {}
    if not layers:
        raise RigError("no layers")
    sizes = {im.size for im in layers.values()}
    full_canvas = len(sizes) == 1
    canvas = next(iter(sizes)) if full_canvas else tuple(extra.get("size") or (1024, 1024))
    parts: dict[str, dict] = {}
    canvas_pos: dict[str, tuple[float, float]] = {}      # where the part's top-left sits on the design canvas
    for raw_name, im in layers.items():
        name, group, state = classify(raw_name)
        if name in parts:
            continue
        im = im.convert("RGBA")
        given = (extra.get("parts") or {}).get(name) or {}
        trimmed, (ox, oy) = cutout.trim(im) if full_canvas else (im, (0, 0))
        path = cutout.save_png(trimmed, out_dir / f"{name}.png")
        parts[name] = {"image": str(path.relative_to(media_root)).replace("\\", "/"), "pivot": list(given.get("pivot") or _pivot(name, trimmed.size)),
                       "z": int(given.get("z", default_z(name))), "parent": given.get("parent", "__auto__"), "group": group, "state": state,
                       "size": list(trimmed.size)}
        canvas_pos[name] = tuple(given.get("canvas_pos") or (ox, oy))
        if "pos" in given:
            parts[name]["pos"] = list(given["pos"])
    have = set(parts)
    for name, p in parts.items():
        if p["parent"] == "__auto__":
            p["parent"] = _parent(name, p["group"], have)
        if "pos" in p:
            continue
        if not full_canvas and not (extra.get("parts") or {}).get(name, {}).get("canvas_pos"):
            raise RigError(f"layer {name}: layers differ in size, so a rig.json with 'pos' (or 'canvas_pos') per part is required")
        px, py = canvas_pos[name][0] + p["pivot"][0], canvas_pos[name][1] + p["pivot"][1]       # joint on the canvas
        if p["parent"]:
            par = canvas_pos[p["parent"]]
            p["pos"] = [round(px - par[0], 1), round(py - par[1], 1)]
        else:
            p["pos"] = [round(px, 1), round(py, 1)]
    for p in parts.values():
        p.pop("size", None)
    feet = None
    for n in ("leg_l", "leg_r", "body"):
        if n in parts:
            im = Image.open(media_root / parts[n]["image"])
            feet = max(feet or 0, canvas_pos[n][1] + im.height)
    spec = {"version": 1, "size": list(canvas), "anchor": list(extra.get("anchor") or (canvas[0] / 2, feet or canvas[1] * 0.97)), "parts": parts}
    if "body" not in parts and not any(p["parent"] is None for p in parts.values()):
        raise RigError("a rig needs at least a body (or another root part)")
    return spec


def layers_from_zip(data: bytes) -> tuple[dict[str, Image.Image], dict]:
    layers: dict[str, Image.Image] = {}
    extra: dict = {}
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise RigError("not a ZIP file") from e
    with z:
        for info in z.infolist():
            base = Path(info.filename).name
            if info.is_dir() or base.startswith(("._", ".")):
                continue
            if base.lower() == "rig.json":
                try:
                    extra = json.loads(z.read(info).decode("utf-8"))
                except ValueError as e:
                    raise RigError("rig.json is not valid JSON") from e
            elif base.lower().endswith(".png"):
                if info.file_size > 40 * 1024 * 1024:
                    raise RigError(f"{base} is too large")
                layers[Path(base).stem] = Image.open(io.BytesIO(z.read(info))).convert("RGBA")
    if not layers:
        raise RigError("the ZIP contains no PNG layers")
    return layers, extra


def layers_from_psd(data: bytes) -> dict[str, Image.Image]:
    """Needs the optional `psd-tools` package. Every visible pixel layer becomes a full-canvas RGBA image."""
    try:
        from psd_tools import PSDImage
    except ImportError as e:
        raise RigError("PSD import needs the optional psd-tools package; export the layers as PNG files in a ZIP instead") from e
    psd = PSDImage.open(io.BytesIO(data))
    out: dict[str, Image.Image] = {}
    for layer in psd.descendants():
        if layer.is_group() or not layer.has_pixels():
            continue
        full = Image.new("RGBA", psd.size, (0, 0, 0, 0))
        img = layer.composite()
        if img is not None:
            full.paste(img, (layer.left, layer.top))
            out[layer.name] = full
    if not out:
        raise RigError("the PSD has no pixel layers")
    return out


def completeness(spec: dict) -> dict:
    """What the rig can do, for the UI: which mouth shapes exist, whether it has legs/arms/eyes."""
    names = set(spec.get("parts", {}))
    mouths = sorted(n[-1] for n in names if re.fullmatch(r"mouth_[A-HX]", n))
    return {"mouth_shapes": mouths, "missing_mouth_shapes": [s for s in MOUTH_SHAPES if s not in mouths],
            "has_arms": {"arm_l", "arm_r"} & names != set(), "has_legs": {"leg_l", "leg_r"} & names != set(), "has_blink": {"eyes_open", "eyes_closed"} <= names,
            "parts": len(names), "ok": "body" in names or "head" in names}
