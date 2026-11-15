"""Measuring real frames: the same render bundle (Remotion) in QA mode, with the browser InstAI found on this PC (never a download).

SOURCE: ported from NMarketing:backend/apps/motion/qa_browser.py @ motion v2, adapted for InstAI: the work goes through remotion/render.mjs (the `qa` mode) and the
InstAI job context instead of NMarketing's runner / site lock.

make_measure(...) => a function that takes a plan and returns the «shots» qa.geometry_findings judges:
  every shot = {scene, kind (enter|late), frame, W, H, scale, safe, boxes[], _image (PIL), image_rel (for the page)}.
Two frames per scene (qa.key_frames), at half size (540 x 960) to stay light. It works only when the Remotion toolchain is ready; otherwise the rule checks
of qa.static_findings still run (qa.run_loop copes with a measure that raises).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from django.conf import settings

from . import qa

QA_SCALE = 0.5


def media_dir_for(plan_id: int, tag: str = "qa") -> Path:
    return Path(settings.MEDIA_ROOT) / "motion" / str(plan_id) / tag


def rel_of(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(settings.MEDIA_ROOT).resolve())).replace("\\", "/")
    except ValueError:
        return ""


def parse_results(data: list, frames: list, names: list, *, scale: float, media_dir: Path | None = None, item: int = 0) -> list:
    """The QA results of one plan (render.mjs results.json) => shots. A frame that gave no geometry is an error (the page did not settle)."""
    shots_by_name = {s["name"]: s for s in (data[item]["shots"] if data else [])}
    out = []
    for nm, f in zip(names, frames):
        s = shots_by_name.get(nm)
        g = (s or {}).get("geometry") or {}
        if not s or not g or g.get("error"):
            raise RuntimeError(f"no geometry came from frame {f['frame']} ({(g or {}).get('error', 'empty')})")
        img = qa.open_image(s["image"])
        rel = ""
        if media_dir is not None:
            media_dir.mkdir(parents=True, exist_ok=True)
            dest = media_dir / f"{nm}.jpg"
            shutil.copyfile(s["image"], dest)
            rel = rel_of(dest)
        out.append({"scene": f["scene"], "kind": f["kind"], "frame": f["frame"], "W": g["W"], "H": g["H"], "scale": scale, "safe": g.get("safe") or {},
                    "platform": g.get("platform", ""), "boxes": g.get("boxes") or [], "_image": img, "image_rel": rel, "_path": s["image"], "name": nm})
    return out


def make_measure(ctx, st: dict, *, kit: dict, size: str, work: Path, shot=None, media_dir: Path | None = None, prefix: str = "r", per_scene: int = 2,
                 scale: float = QA_SCALE, frames_fn=None):
    """=> measure(spec). Every call is one round of measuring (the files are named prefix + the round number). `frames_fn(spec)` may choose the frames itself."""
    from instai.jobs.handlers import remotion as rh

    from . import shots as shots_mod

    calls = {"n": 0}

    def measure(spec: dict) -> list:
        calls["n"] += 1
        n = calls["n"]
        out_dir = Path(work) / f"qa{n}"
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True)
        frames = (frames_fn or (lambda s: qa.key_frames(s, per_scene, kit)))(spec)
        names = [f"{prefix}{n}-s{f['scene']}-{f['kind']}" for f in frames]
        spec_in = {k: v for k, v in spec.items() if k not in ("total_s",)}
        spec_in["assets"] = shots_mod.resolve_assets(spec_in, shot)
        job = {"qa": {"items": [{"name": "plan", "composition": "ScenePlan", "props": {"kit": kit, "size": size, "spec": spec_in},
                                 "frames": [{"name": nm, "frame": f["frame"]} for nm, f in zip(names, frames)]}], "out_dir": str(out_dir), "scale": scale, "timeout_ms": 90000}}
        rh.run_renderer(ctx, st, job, work=out_dir, label="QA ", base=0.0, timeout=900)
        data = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
        return parse_results(data, frames, names, scale=scale, media_dir=media_dir)

    return measure
