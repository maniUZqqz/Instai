"""The acceptance run of the component library: ONE frame of every component in landscape, vertical and square through the REAL toolchain (Node + the bundled project + the
browser + the Persian font), then the rule checks of qa.py over the geometry the page reported for every frame, and a montage of the pictures per size.

Used by the PC self-test (instai/ops/pcselftest.py `motion_frames`), by tests/test_motion_pipeline.py (INSTAI_REMOTION_REAL=1) and by hand:
  python -m instai.motion_plan.selftest <out_dir> [--lang fa|en] [--style <key>] [--node <path> --browser <path> --mode headless-shell]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from . import components, fallback, motionlib, qa, qa_browser, specs

SIZES = ("landscape", "vertical", "square")


def plan_of(cid: str, size: str, lang: str, style: str = "") -> dict:
    """A one-scene plan of a component: its sample at its typical length, the series context, the platform's safe area, and the word timings of the pieces that follow the voice."""
    c = components.COMPONENTS[cid]
    sc = components.sample(cid, lang)
    sc["duration"] = c["dur"][1]
    text = sc.get("text") or sc.get("title") or ""
    if cid in ("kinetic_title", "captions") and text:
        sc["narration"] = text
        sc["cues"] = fallback.estimate_cues(text, c["dur"][1] * 0.8, start=0.3)
    series = {"title": sc.get("series") or ("سریال آزمایشی" if lang == "fa" else "Test series"), "episode": 1, "episode_title": "", "channel": "", "characters": []}
    return specs.normalize_spec({"style": style, "size": size, "lang": lang, "series": series, "platform": motionlib.DEFAULT_PLATFORM.get(size, ""), "scenes": [sc]}, max_total=300)


def run_every_component(out_dir: Path, *, lang: str = "fa", style: str = "", status: dict | None = None, ctx=None, only=None, sizes=SIZES) -> dict:
    """=> {rendered, render_errors[], findings[], montage[], seconds, components, sizes}. Raises RuntimeError when the toolchain is not ready (the self-test waits for it first)."""
    from instai.remotion import kit as kitmod
    from instai.remotion import toolchain

    st = status or toolchain.status()
    if not st.get("ready"):
        raise RuntimeError("the Remotion toolchain is not ready")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kit = kitmod.style_kit(style or None, None)
    ids = [c for c in components.COMPONENTS if not only or c in only]
    t0 = time.time()
    report: dict = {"rendered": 0, "render_errors": [], "findings": [], "montage": [], "components": ids, "sizes": list(sizes), "style": kit["key"]}
    for size in sizes:
        items, plans = [], {}
        for cid in ids:
            plan = plan_of(cid, size, lang, kit["key"])
            plans[cid] = plan
            # the end of the scene; the captions are only on screen while the words are said, so their frame is the middle of the entrance
            frames = [k for k in qa.key_frames(plan, per_scene=2, kit=kit) if k["kind"] == ("enter" if cid == "captions" else "late")]
            items.append({"name": f"{size}-{cid}", "composition": "ScenePlan", "props": {"kit": kit, "size": size, "spec": plan}, "frames": [{"name": f"{size}-{cid}", "frame": frames[0]["frame"]}]})
        work = out_dir / f"qa-{size}"
        shutil.rmtree(work, ignore_errors=True)
        job = {"qa": {"items": items, "out_dir": str(work), "scale": 0.5, "timeout_ms": 120000}}
        try:
            if ctx is not None:
                from instai.jobs.handlers import remotion as rh

                rh.run_renderer(ctx, st, job, work=work, label=f"{size} ", base=0.0, timeout=1800)
            else:
                _run_plain(st, job, work)
            data = json.loads((work / "results.json").read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 - a failed batch is a failed check, reported
            report["render_errors"].append(f"{size}: {str(e)[:300]}")
            continue
        pics = []
        for cid, row in zip(ids, data):
            try:
                shot = qa_browser.parse_results([row], [{"scene": 0, "kind": "late", "frame": row["shots"][0]["frame"]}], [row["shots"][0]["name"]], scale=0.5)[0]
            except Exception as e:  # noqa: BLE001
                report["render_errors"].append(f"{size}/{cid}: {str(e)[:200]}")
                continue
            report["rendered"] += 1
            pics.append((cid, shot["_path"]))
            for f in qa.geometry_findings(plans[cid], [shot], kit):
                report["findings"].append({**{k: v for k, v in f.items() if k != "box"}, "component": cid, "size": size, "box": f.get("box")})
        montage = out_dir / f"montage-{size}.png"
        _montage(pics, montage)
        report["montage"].append(str(montage))
    report["seconds"] = round(time.time() - t0, 1)
    return report


def _run_plain(st: dict, job: dict, work: Path) -> None:
    """The renderer without a job context (the command line, the tests): the same render.mjs, the same events."""
    import subprocess

    from instai.jobs.handlers import remotion as rh
    from instai.remotion import toolchain

    work.mkdir(parents=True, exist_ok=True)
    spec = {"browser": st["browser"]["path"], "chrome_mode": st["browser"].get("mode") or "headless-shell", "bundle_dir": str(toolchain.work_dir() / "bundles"), **job}
    (work / "job.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([st["node"]["path"], str(toolchain.PROJECT / "render.mjs"), str(work / "job.json")], cwd=str(toolchain.PROJECT), capture_output=True, text=True, timeout=1800,
                       env=rh.node_env(st["node"]["path"]), encoding="utf-8", errors="replace")
    events = []
    for line in (r.stdout or "").splitlines():
        if line.startswith(rh.EVENT):
            try:
                events.append(json.loads(line[len(rh.EVENT):]))
            except ValueError:
                pass
    if r.returncode != 0 or not any(e.get("event") == "done" for e in events):
        err = [e for e in events if e.get("event") == "error"]
        raise RuntimeError((err[-1].get("message") if err else (r.stderr or r.stdout or "")[-400:]) or "the renderer stopped without a message")


def _montage(pics: list, path: Path, cols: int = 5, tile_h: int = 360) -> None:
    from PIL import Image, ImageDraw

    if not pics:
        return
    ims = []
    for cid, p in pics:
        im = Image.open(p).convert("RGB")
        im.thumbnail((10000, tile_h))
        ims.append((cid, im))
    tw = max(i.width for _, i in ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 8) + 8, rows * (tile_h + 30) + 8), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for k, (cid, im) in enumerate(ims):
        x, y = 8 + (k % cols) * (tw + 8), 8 + (k // cols) * (tile_h + 30)
        d.text((x + 2, y + 2), cid, fill=(200, 200, 210))
        sheet.paste(im, (x, y + 16))
    sheet.save(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--lang", default="fa")
    ap.add_argument("--style", default="")
    ap.add_argument("--node")
    ap.add_argument("--browser")
    ap.add_argument("--mode", default="headless-shell")
    ap.add_argument("--only", default="")
    ap.add_argument("--sizes", default=",".join(SIZES))
    a = ap.parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instai.settings")
    os.environ.setdefault("INSTAI_DATA_DIR", tempfile.mkdtemp(prefix="instai-motion-"))
    import django

    django.setup()
    st = None
    if a.node and a.browser:
        st = {"ready": True, "node": {"path": a.node, "version": "manual", "source": "manual"}, "browser": {"path": a.browser, "mode": a.mode, "source": "manual"}, "packages": True}
    rep = run_every_component(Path(a.out_dir), lang=a.lang, style=a.style, status=st, only=[x for x in a.only.split(",") if x] or None, sizes=tuple(x for x in a.sizes.split(",") if x))
    print(json.dumps({k: v for k, v in rep.items() if k != "findings"}, ensure_ascii=False))
    for f in rep["findings"]:
        print(f"{f['severity']:5} {f['size']:9} {f['component']:14} {f['code']:14} {f['message_en']}")
    return 1 if any(f["severity"] == "error" for f in rep["findings"]) or rep["render_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
