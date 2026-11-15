"""Remotion jobs: `remotion.setup` (Node.js, npm packages, a browser: scripts/setup_remotion.py) and `remotion.render` (one composition -> an mp4 / png).

A render that is asked for before the toolchain is ready WAITS (wait code `remotion_setup`, nothing fails) and starts the setup in the background;
it runs by itself when the setup has finished. The rendered file is registered as an Asset (Library) and linked in the job's result."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from instai.jobs.registry import handler
from instai.providers.base import ProviderError

ROOT = Path(__file__).resolve().parents[3]
EVENT = "INSTAI_REMOTION "
SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")

# the plain Persian reason for the errors Remotion / Chrome are known for
HINTS = [
    (re.compile(r"browser.*(not found|could not|executable)|Failed to launch|spawn .* ENOENT", re.I),
     "مرورگر لازم برای ساخت ویدئو پیدا نشد یا باز نشد. صفحهٔ Remotion وضعیت مرورگر را نشان می‌دهد؛ دکمهٔ «نصب دوباره» آن را آماده می‌کند."),
    (re.compile(r"ENOSPC|no space", re.I), "فضای دیسک پر شد؛ جا باز کنید و دوباره امتحان کنید."),
    (re.compile(r"out of memory|heap|ENOMEM", re.I), "حافظهٔ رایانه کم آمد؛ برنامه‌های سنگین را ببندید یا اندازهٔ خروجی را کوچک‌تر کنید."),
    (re.compile(r"font|Vazirmatn", re.I), "بارگذاری فونت فارسی به مشکل خورد؛ فایل‌های remotion/public/fonts را بررسی کنید."),
]


def node_env(node_path: str) -> dict:
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(os.path.abspath(node_path)) + os.pathsep + env.get("PATH", "")
    env["NODE_OPTIONS"] = (env.get("NODE_OPTIONS", "") + " --max-old-space-size=3072").strip()
    return env


def explain(message: str) -> str:
    for rx, fa in HINTS:
        if rx.search(message or ""):
            return fa
    return ""


@handler("remotion.setup", resource="net", timeout=2 * 3600)
def setup(ctx):
    cmd = [sys.executable, str(ROOT / "scripts" / "setup_remotion.py")]
    ctx.log("running: setup_remotion.py")
    ctx.live(phase="installing")

    def on_line(line: str) -> None:
        if line.strip():
            ctx.log(line[:300])
        m = re.search(r"(\d+)%", line)
        if m:
            ctx.progress(min(0.95, float(m.group(1)) / 100), line.strip()[:120])

    rc, tail = ctx.run_cmd(cmd, cwd=str(ROOT), on_line=on_line, timeout=2 * 3600)
    from instai.remotion import toolchain

    st = toolchain.status()
    if rc != 0:
        why = st.get("error") or tail[-300:]
        raise ProviderError("Remotion setup failed: " + why, retryable=True, code="remotion_setup_failed",
                            fa="نصب Remotion کامل نشد. دلیلش: " + (st.get("error_fa") or "جزئیات در گزارش کار است.") + " — دوباره امتحان کنید؛ از همان‌جا ادامه می‌دهد.")
    if not st["ready"] and st["state"] == "running":      # the START.bat run in the background holds the lock: wait for it instead of reporting "done"
        raise ProviderError("the Remotion setup of START.bat is still running", code="remotion_setup", wait="remotion_setup",
                            fa="نصب Remotion از قبل (با START.bat) در پس‌زمینه در حال انجام است؛ این کار منتظر پایان آن می‌ماند.")
    return {"ready": bool(st["ready"])}


def kick_setup() -> None:
    """Start the setup detached (it is idempotent and takes a lock: two calls do not run twice)."""
    try:
        subprocess.Popen([sys.executable, str(ROOT / "scripts" / "setup_remotion.py"), "--background"], cwd=str(ROOT), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        pass


def require_toolchain() -> dict:
    """The toolchain status when everything is there; else the job WAITS (nothing fails) and the setup starts by itself."""
    from instai.remotion import toolchain

    st = toolchain.status()
    if not st["ready"]:
        kick_setup()
        why = "Remotion هنوز آماده نیست" + (": " + st["message_fa"] if st.get("message_fa") else ".")
        raise ProviderError("Remotion is not ready yet: " + (st.get("message_en") or "setup pending"), code="remotion_setup", wait="remotion_setup", fa=why)
    return st


def run_renderer(ctx, st: dict, spec: dict, *, work: Path, label: str = "", base: float = 0.2, timeout: int = 2 * 3600) -> dict:
    """Run `render.mjs` on a job spec (a video, a still, or a QA batch) and follow its events. => the `done` event. A failure is a ProviderError with a Persian line."""
    from instai.remotion import toolchain

    node, browser = st["node"], st["browser"]
    spec = {"browser": browser["path"], "chrome_mode": browser["mode"], "hw_accel": True, "bundle_dir": str(toolchain.work_dir() / "bundles"), **spec}
    work.mkdir(parents=True, exist_ok=True)
    job_json = work / "job.json"
    job_json.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    state: dict = {"done": None, "error": None, "comp": None}

    def on_line(line: str) -> None:
        if not line.startswith(EVENT):
            if line.strip():
                ctx.log(line[:300], "info")
            return
        try:
            ev = json.loads(line[len(EVENT):])
        except ValueError:
            return
        kind = ev.get("event")
        if kind == "bundle":
            ctx.progress(min(base, ev.get("progress", 0) / 500), "bundling the compositions" if not ev.get("cached") else "bundle ready")
        elif kind == "phase":
            ctx.live(phase=ev.get("phase"))
        elif kind == "composition":
            state["comp"] = ev
            ctx.log_t("composition", id=ev['id'], width=ev['width'], height=ev['height'], fps=ev['fps'], frames=ev['frames'])
        elif kind == "progress":
            ctx.live(phase="rendering", step=ev.get("rendered"), steps=ev.get("frames"))
            ctx.progress(base + (0.98 - base) * float(ev.get("progress") or 0), f"{label}{ev.get('rendered')} / {ev.get('frames')}")
        elif kind == "qa_progress":
            ctx.live(phase="measuring", step=ev.get("done"), steps=ev.get("total"))
        elif kind == "done":
            state["done"] = ev
        elif kind == "error":
            state["error"] = ev

    rc, tail = ctx.run_cmd([node["path"], str(toolchain.PROJECT / "render.mjs"), str(job_json)], cwd=str(toolchain.PROJECT), on_line=on_line, timeout=timeout, env=node_env(node["path"]))
    if rc != 0 or not state["done"]:
        msg = (state["error"] or {}).get("message") or tail[-400:] or "the renderer stopped without a message"
        fa = explain(msg)
        raise ProviderError("Remotion render failed: " + msg[:500], retryable=False, code="remotion_render_failed",
                            fa=("ساخت ویدئو با Remotion کامل نشد. " + fa) if fa else "ساخت ویدئو با Remotion کامل نشد؛ جزئیات فنی در گزارش کار است.")
    return {**state["done"], "composition_info": state["comp"]}


@handler("remotion.render", resource="cpu", timeout=2 * 3600)
def render(ctx):
    from instai.assets import storage
    from instai.remotion import kit as kitmod
    from instai.remotion import toolchain

    p = ctx.payload
    if p.get("shot_id"):           # one motion-graphics shot of an episode: the plan, the checks, the clip (instai/motion_plan/jobs.py)
        from instai.motion_plan import jobs as motion_jobs

        return motion_jobs.render_shot(ctx)
    comp = p.get("composition")
    if comp not in toolchain.COMPOSITIONS:
        raise ProviderError("unknown composition", retryable=False, code="validation_error", fa="این قالب Remotion را نمی‌شناسم.")
    st = require_toolchain()
    node, browser = st["node"], st["browser"]
    kit = kitmod.style_kit(p.get("style"), p.get("theme"))
    size = p.get("size") if p.get("size") in toolchain.SIZES else "landscape"
    props = {**(p.get("props") or {}), "kit": kit, "size": size}
    still = p.get("still")
    ext = "png" if still is not None else "mp4"
    work = toolchain.work_dir() / "jobs" / str(ctx.job.pk)
    work.mkdir(parents=True, exist_ok=True)
    out = work / f"{SAFE_NAME.sub('', comp) or 'video'}.{ext}"
    spec = {"composition": comp, "props": props, "out": str(out), "crf": int(p.get("crf") or 18)}
    if still is not None:
        spec["still"] = int(still)
    t0 = time.time()
    ctx.live(phase="rendering", provider="remotion", device="cpu", model=f"{comp} · {kit['key']}")
    d = run_renderer(ctx, st, spec, work=work)
    if not out.is_file():
        raise ProviderError("Remotion render failed: no output file", retryable=False, code="remotion_render_failed", fa="ساخت ویدئو با Remotion کامل نشد؛ جزئیات فنی در گزارش کار است.")
    rel = f"remotion/{ctx.job.pk}/{out.name}"
    asset = storage.register(out, rel, kind="video" if ext == "mp4" else "image", role="export" if ext == "mp4" else "preview",
                             provenance={"engine": "remotion", "composition": comp, "style": kit["key"], "theme": kit.get("theme_key", ""), "size": size,
                                         "props": {k: v for k, v in props.items() if k != "kit"}, "job_id": ctx.job.pk,
                                         "browser": os.path.basename(browser["path"]), "node": node["version"]})
    ctx.progress(1.0, "done")
    return {"asset_id": asset.pk, "url": asset.url, "kind": ext, "composition": comp, "style": kit["key"], "size": size, "width": d.get("width"),
            "height": d.get("height"), "fps": d.get("fps"), "frames": d.get("frames"), "seconds": round(time.time() - t0, 1), "bytes": asset.size_bytes}
