"""The Remotion toolchain as the app sees it: what is installed (Node.js, npm packages, a browser), the setup run in progress, the project's files.

The installing itself is `scripts/setup_remotion.py` (stdlib only, runs before and beside the app); this module loads it by path, so there is one copy
of that logic, and adds what only the app needs: the page's status, the code files the page shows, and the safe path of every file."""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

from django.conf import settings

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "remotion"
COMPOSITIONS = ("TitleCard", "KineticText", "Explainer", "LowerThird")      # remotion/src/catalog.ts (a test compares the two lists)
SIZES = {"landscape": (1920, 1080), "vertical": (1080, 1920), "square": (1080, 1080)}
SHARED_FILES = ("src/kit/theme.ts", "src/kit/motion.ts", "src/kit/Stage.tsx", "src/catalog.ts", "render.mjs")
_MOD = None


def setup_module():
    """scripts/setup_remotion.py as a module (loaded once)."""
    global _MOD
    if _MOD is None:
        spec = importlib.util.spec_from_file_location("instai_setup_remotion", ROOT / "scripts" / "setup_remotion.py")
        _MOD = importlib.util.module_from_spec(spec)           # type: ignore[arg-type]
        spec.loader.exec_module(_MOD)                          # type: ignore[union-attr]
    return _MOD


def work_dir() -> Path:
    return Path(settings.DATA_DIR) / "remotion"


_NOW: dict = {"at": 0.0, "val": None}
NOW_TTL = 6.0


def _now_cached(m) -> dict:
    """`status_now()` starts `node -v` and looks for a browser: the page polls the status every few seconds while the setup runs, so the answer is
    reused for a few seconds (the status FILE the setup writes is read fresh every time)."""
    t = time.time()
    if _NOW["val"] is None or t - _NOW["at"] > NOW_TTL:
        _NOW.update(val=m.status_now(), at=t)
    return _NOW["val"]


def clear_cache() -> None:
    _NOW.update(val=None, at=0.0)


def status() -> dict:
    """{ready, node, packages, browser, state, phase, message_fa, message_en, error, remotion, project} for the page. Installs nothing."""
    m = setup_module()
    now = _now_cached(m)
    saved = m.read_status()
    state = saved.get("state") or ("ready" if now["ready"] else "idle")
    if now["ready"]:
        state = "ready"
    elif state == "ready":
        state = "idle"                                          # something was removed since
    running = state == "running" and os.path.exists(m.folders()["lock"])
    if state == "running" and not running:
        state = "idle"
    out = {
        "ready": now["ready"], "node": now["node"], "packages": now["packages"], "browser": now["browser"], "state": state,
        "phase": saved.get("phase", ""), "message_fa": saved.get("message_fa", ""), "message_en": saved.get("message_en", ""),
        "error": saved.get("error", "") if state == "error" else "", "remotion": saved.get("remotion"), "updated_at": saved.get("updated_at", ""),
        "project": PROJECT.is_dir(), "auto": m.env_value("INSTAI_REMOTION_AUTO") not in ("0", "false", "no"),
        "node_version_wanted": m.NODE_VERSION,
    }
    return out


def read_file(rel: str) -> str:
    """A file of the remotion project for the code view. Only files under remotion/src, remotion/render.mjs and package.json; never node_modules."""
    p = (PROJECT / rel).resolve()
    allowed = [(PROJECT / "src").resolve(), (PROJECT / "render.mjs").resolve(), (PROJECT / "package.json").resolve()]
    if not any(p == a or a in p.parents for a in allowed) or not p.is_file():
        raise FileNotFoundError(rel)
    return p.read_text(encoding="utf-8")


def code_files() -> dict:
    """{compositions: [{id, file, code}], shared: [{name, file, code}]} read from disk (always what is installed, never a copy)."""
    comps = []
    for cid in COMPOSITIONS:
        rel = f"src/compositions/{cid}.tsx"
        try:
            comps.append({"id": cid, "file": rel, "code": read_file(rel)})
        except FileNotFoundError:
            comps.append({"id": cid, "file": rel, "code": ""})
    shared = []
    for rel in SHARED_FILES:
        try:
            shared.append({"name": rel.split("/")[-1], "file": rel, "code": read_file(rel)})
        except FileNotFoundError:
            pass
    return {"compositions": comps, "shared": shared}


def job_json_path(job_id: int) -> Path:
    return work_dir() / "jobs" / str(job_id) / "job.json"


def write_job_json(job_id: int, spec: dict) -> Path:
    p = job_json_path(job_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return p
