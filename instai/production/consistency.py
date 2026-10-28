"""Character-consistency checks by image embedding.

The built-in embedding is deliberately light (no model, no extra dependency): a colour histogram of the "interesting" pixels (not
near-white, not near-black, so plain sheet backgrounds do not matter) concatenated with a small structure thumbnail. It only catches BIG
drift - a clip whose character turned another colour, a washed-out clip, a different subject. A stronger embedder (a CLIP/DINO model through
onnxruntime, or a vision LLM through Ollama) can be plugged in with `set_embedder`; the thresholds are heuristics and are marked as such in the
report until they have been calibrated on real clips on the owner's machine (docs/DECISIONS.md).
"""
from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from PIL import Image, ImageFilter

DRIFT_OK = 0.88          # similarity of a late clip frame to the shot reference keyframe (heuristic: a green recolour of a character scores 0.82, an identical clip 1.0)
SHEET_OK = 0.45          # palette similarity of the keyframe to the approved character sheet (sheet layout differs from a scene)
HIST_BINS = (8, 3, 3)

Embedder = Callable[[Image.Image], list[float]]


def hist_embedding(img: Image.Image) -> list[float]:
    im = img.convert("RGB")
    im.thumbnail((96, 96))
    im = im.filter(ImageFilter.GaussianBlur(1.5))        # codec noise and anti-aliased edges must not move pixels between histogram bins
    hsv = im.convert("HSV")
    px, hp = list(im.getdata()), list(hsv.getdata())
    bins = [0.0] * (HIST_BINS[0] * HIST_BINS[1] * HIST_BINS[2])
    total = 0
    for (r, g, b), (h, s, v) in zip(px, hp):
        if min(r, g, b) > 238 or max(r, g, b) < 40:      # plain white / black backgrounds carry no information
            continue
        i = (h * HIST_BINS[0] // 256) * HIST_BINS[1] * HIST_BINS[2] + (s * HIST_BINS[1] // 256) * HIST_BINS[2] + (v * HIST_BINS[2] // 256)
        bins[i] += 1
        total += 1
    if total:
        bins = [x / total for x in bins]
    thumb = list(im.convert("L").resize((6, 6), Image.BILINEAR).getdata())
    mean = sum(thumb) / 36.0
    structure = [(x - mean) / 128.0 for x in thumb]
    return [x * 2.0 for x in bins] + [x * 0.25 for x in structure]


_EMBEDDER: Embedder = hist_embedding


def set_embedder(fn: Embedder | None) -> None:
    global _EMBEDDER
    _EMBEDDER = fn or hist_embedding


def cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 0.0
    return max(0.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (na * nb)))


def similarity(a: Image.Image, b: Image.Image) -> float:
    return round(cosine(_EMBEDDER(a), _EMBEDDER(b)), 4)


def palette_similarity(a: Image.Image, b: Image.Image) -> float:
    """Colour-only similarity (the structure part is ignored): for comparing a scene with a character sheet."""
    ha, hb = hist_embedding(a), hist_embedding(b)
    n = HIST_BINS[0] * HIST_BINS[1] * HIST_BINS[2]
    return round(cosine(ha[:n], hb[:n]), 4)


def sample_frames(video: Path, count: int = 5, width: int = 192) -> list[Image.Image]:
    """`count` frames spread over the clip (first excluded, last included), small."""
    from instai.render import ffmpeg

    dur = ffmpeg.probe(video)["duration"] or 1.0
    ff, _ = ffmpeg.binaries()
    out: list[Image.Image] = []
    tmp = Path(tempfile.mkdtemp(prefix="cons-"))
    try:
        for i in range(1, count + 1):
            t = max(0.0, dur * i / count - 0.05)
            f = tmp / f"f{i}.png"
            subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={width}:-2", str(f)],
                           capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if f.exists():
                with Image.open(f) as im:
                    out.append(im.convert("RGB").copy())
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    return out


def check_clip(video: Path, keyframe: Path, sheet: Path | None = None, samples: int = 5) -> dict:
    """{drift, drift_min_frame, sheet, ok, thresholds, notes[]}: does the clip still look like its reference keyframe (and the sheet's colours)?"""
    frames = sample_frames(video, samples)
    notes: list[str] = []
    if not frames:
        return {"ok": False, "drift": None, "sheet": None, "notes": ["no frames could be read from the clip"], "thresholds": {"drift": DRIFT_OK, "sheet": SHEET_OK}}
    with Image.open(keyframe) as k:
        kf = k.convert("RGB").copy()
    sims = [similarity(f, kf) for f in frames]
    drift = min(sims)
    res: dict = {"drift": round(drift, 3), "per_frame": [round(s, 3) for s in sims], "sheet": None, "thresholds": {"drift": DRIFT_OK, "sheet": SHEET_OK},
                 "embedder": "histogram+structure (built-in, weak: catches big drift only)"}
    ok = drift >= DRIFT_OK
    if not ok:
        notes.append(f"the clip drifts from its keyframe (similarity {drift:.2f} < {DRIFT_OK})")
    if sheet is not None and Path(sheet).exists():
        with Image.open(sheet) as s_:
            sh = s_.convert("RGB").copy()
        ps = palette_similarity(kf, sh)
        res["sheet"] = ps
        if ps < SHEET_OK:
            ok = False
            notes.append(f"the keyframe's colours differ from the approved character sheet (palette similarity {ps:.2f} < {SHEET_OK})")
    res["ok"], res["notes"] = ok, notes
    return res
