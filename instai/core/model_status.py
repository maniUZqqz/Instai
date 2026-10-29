"""What InstAI needs vs what this PC already has (the search itself is core/discovery.py).

* the Models screen: what was found and where, what is missing and which features each missing piece blocks;
* small lookups for the providers (ComfyUI folder, the voice engines' folders, Piper) - always from the cached scan, never slow;
* optional downloads ("offers", e.g. better anime models): listed with size, licence and why, and fetched ONLY after the owner confirms
  in the UI (the API refuses a download without `confirm: true`). Files ComfyUI can already see are never downloaded again.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import discovery, runtime, settings_store

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = ROOT / "manifests"
# which ComfyUI models folder a loader reads (for the "put it here" hint; ComfyUI also reads the old names unet/ and clip/)
LOADER_KIND = {"CheckpointLoaderSimple": "checkpoints", "UNETLoader": "diffusion_models", "UnetLoaderGGUF": "unet", "CLIPLoader": "text_encoders",
               "VAELoader": "vae", "LoraLoaderModelOnly": "loras", "LoraLoader": "loras", "CLIPVisionLoader": "clip_vision"}


# ------------------------------------------------------------------ the scan with this installation's settings

def manual_paths() -> list[str]:
    v = settings_store.get_setting("model_paths") or []
    return [str(p).strip() for p in v if str(p).strip()] if isinstance(v, list) else []


def wanted_names() -> set[str]:
    from instai.providers.comfy.workflows import MODEL_ALIASES, WORKFLOWS

    names: set[str] = set()
    for w in WORKFLOWS.values():
        for _, _, f in w.required_models:
            names.add(f.lower())
            names.update(a.lower() for a in MODEL_ALIASES.get(f, []))
    return names


def scan_kwargs() -> dict:
    pref = runtime.explicit_comfyui_dir()
    return {"manual": manual_paths() + ([pref] if pref else []), "comfy_url": runtime.comfyui_url(), "ollama_url": runtime.ollama_url(),
            "preferred_comfy": pref, "wanted": sorted(wanted_names()), "extra": [str(runtime.models_root())]}


def current(force: bool = False) -> dict:
    """The cached scan (data/discovery.json). `force` rescans now (the Rescan button, after a download)."""
    return discovery.get(force=force, **scan_kwargs())


def voice(key: str) -> dict:
    return (current().get("voice") or {}).get(key) or {}


def piper() -> dict:
    return current().get("piper") or {}


# ------------------------------------------------------------------ manifests (the downloader's data) and the registry

def manifests() -> tuple[dict, list]:
    packages: dict[str, dict] = {}
    items: list[dict] = []
    for path in sorted(MANIFESTS.glob("*.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        for pid, p in m.get("packages", {}).items():
            packages[pid] = {**(p if isinstance(p, dict) else {"title": p}), "group": m.get("group", "")}
        items += [{**it, "group": m.get("group", "")} for it in m.get("items", [])]
    return packages, items


def _dest_name(dest: str) -> str:
    return dest.replace("\\", "/").rsplit("/", 1)[-1]


def comfy_registry() -> list[dict]:
    """Every ComfyUI model file a workflow of InstAI loads, with its aliases, folder, download package and the workflows that need it."""
    from instai.providers.comfy.workflows import MODEL_ALIASES, WORKFLOWS

    _, items = manifests()
    by_name = {_dest_name(it["dest"]).lower(): it for it in items if it.get("kind") == "file" and str(it.get("dest", "")).startswith("{COMFYUI}")}
    reg: dict[str, dict] = {}
    for w in WORKFLOWS.values():
        for node, _key, fname in w.required_models:
            e = reg.get(fname)
            if e is None:
                names = [fname, *MODEL_ALIASES.get(fname, [])]
                it = next((by_name[n.lower()] for n in names if n.lower() in by_name), None) or {}
                e = reg[fname] = {"id": "comfy:" + fname, "kind": "comfy", "file": fname, "aliases": MODEL_ALIASES.get(fname, []),
                                  "folder": LOADER_KIND.get(node, ""), "title": it.get("title") or fname, "package": it.get("package"),
                                  "size": it.get("size"), "uses": []}
            if w.id not in e["uses"]:
                e["uses"].append(w.id)
    return list(reg.values())


def comfy_rows(d: dict) -> list[dict]:
    visible = discovery.comfy_visible_files(d)
    sel = discovery.selected_comfy(d)
    others: dict[str, dict] = {}
    for c in (d.get("comfyui") or {}).get("installs", []):
        if not sel or c["root"] != sel["root"]:
            for low, e in (c.get("files") or {}).items():
                others.setdefault(low, e)
    rows = []
    for e in comfy_registry():
        names = [e["file"], *e["aliases"]]
        hit = next((visible[n.lower()] for n in names if n.lower() in visible), None)
        other = None if hit else next((others[n.lower()] for n in names if n.lower() in others), None)
        size_ok = not (hit and hit.get("size") and e.get("size") and hit["size"] != e["size"] and hit["name"].lower() == e["file"].lower())
        rows.append({**e, "found": bool(hit), "path": (hit or {}).get("path"), "listed": (hit or {}).get("listed"), "found_as": (hit or {}).get("name"),
                     "size_ok": size_ok, "elsewhere": (other or {}).get("path")})
    return rows


def custom_node_present(d: dict, node: str) -> bool | None:
    """True/False when it can be told (the running ComfyUI's node list, else its custom_nodes folder); None when unknown."""
    from instai.providers.comfy.workflows import CUSTOM_NODE_PACKS

    api = (d.get("comfyui") or {}).get("api") or {}
    if api.get("up"):
        return node in set(api.get("node_names") or [])
    pack = CUSTOM_NODE_PACKS.get(node)
    sel = discovery.selected_comfy(d)
    if not pack or not sel:
        return None
    return any(pack["folder_hint"] in n.lower() for n in sel.get("custom_nodes") or [])


def workflow_status(d: dict, rows: list[dict] | None = None) -> list[dict]:
    """Can each workflow run on this PC (the running ComfyUI's lists, else the files on disk)?"""
    from instai.providers.comfy.workflows import CUSTOM_NODE_PACKS, WORKFLOWS

    rows = comfy_rows(d) if rows is None else rows
    found = {r["file"]: r for r in rows}
    api = (d.get("comfyui") or {}).get("api") or {}
    names = set(api.get("node_names") or [])
    out = []
    for w in WORKFLOWS.values():
        missing = [f for _, _, f in w.required_models if not found.get(f, {}).get("found")]
        nodes = []
        for n in w.required_nodes:
            if n in CUSTOM_NODE_PACKS:
                if custom_node_present(d, n) is False:
                    nodes.append(n)
            elif api.get("up") and n not in names:
                nodes.append(n)
        out.append({"id": w.id, "kind": w.kind, "title": w.title, "ready": not missing and not nodes, "missing_models": missing, "missing_nodes": nodes,
                    "node_packages": sorted({CUSTOM_NODE_PACKS[n]["package"] for n in nodes if n in CUSTOM_NODE_PACKS}),
                    "packages": sorted({found[f]["package"] for f in missing if found.get(f, {}).get("package")}), "licence": w.licence,
                    "vram_gb": w.vram_gb})
    return out


def comfy_startable(d: dict) -> bool:
    from instai.providers.comfy import launcher

    sel = discovery.selected_comfy(d)
    return bool(sel and launcher.command(sel))


def workflows_ready_on_disk() -> dict[str, dict]:
    """For routing while ComfyUI is NOT running but InstAI can start it: {workflow id: {available, missing}} from the files on disk."""
    d = current()
    if not comfy_startable(d):
        return {}
    return {w["id"]: {"available": w["ready"], "missing": (w["missing_models"] + w["missing_nodes"])[:4], "startable": True} for w in workflow_status(d)}


# ------------------------------------------------------------------ the downloader's view (subprocess: the script is stdlib-only)

def package_status() -> dict:
    try:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "download_models.py"), "--status"], capture_output=True, text=True, timeout=60,
                           cwd=str(ROOT), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return json.loads(p.stdout or "{}")
    except Exception:  # noqa: BLE001
        return {}


def offers(pkg: dict | None = None) -> list[dict]:
    """Optional downloads that make InstAI better (manifests: packages with an "offer" block). Nothing is fetched from here."""
    packages, items = manifests()
    by_id = {it["id"]: it for it in items}
    pkg = package_status() if pkg is None else pkg
    out = []
    for pid, p in packages.items():
        o = p.get("offer")
        if not o:
            continue
        st = pkg.get(pid, {})
        needs = [{"id": n, "title": packages[n].get("title", n), "complete": bool(pkg.get(n, {}).get("complete")),
                  "missing_size": int(pkg.get(n, {}).get("missing_size") or 0), "licence": packages[n].get("licence", "")}
                 for n in o.get("needs", []) if n in packages]
        for iid in o.get("needs_items", []):          # single shared files (e.g. the Wan text encoder) instead of a whole package
            it = by_id.get(iid)
            if not it:
                continue
            missing = iid in (pkg.get(it.get("package", ""), {}).get("missing_ids") or [])
            needs.append({"id": iid, "title": it.get("title", iid), "complete": not missing, "missing_size": int(it.get("size") or 0) if missing else 0,
                          "licence": packages.get(it.get("package", ""), {}).get("licence", "")})
        out.append({"id": pid, "name": o.get("name") or p.get("title"), "group": o.get("group", ""), "title": p.get("title", ""),
                    "why": o.get("why") or {}, "licence": p.get("licence", ""), "licence_url": o.get("licence_url", ""),
                    "commercial": o.get("commercial", "unknown"), "vram": o.get("vram", ""), "workflow": o.get("workflow", ""),
                    "note": o.get("note") or {}, "complete": bool(st.get("complete")), "size": int(st.get("size") or 0),
                    "missing_size": int(st.get("missing_size") or 0) + sum(n["missing_size"] for n in needs if not n["complete"]),
                    "needs": needs, "restart_comfyui": bool(o.get("restart_comfyui"))})
    return out


# ------------------------------------------------------------------ the Models screen

def _voice_rows(d: dict) -> list[dict]:
    from instai.providers.audio import services

    keys = list(services.SERVICES)
    with ThreadPoolExecutor(max_workers=len(keys)) as ex:
        health = dict(zip(keys, ex.map(lambda k: _threaded(services.health, k, 0.6), keys)))
    rows = []
    for key in keys:
        spec, v, h = services.SERVICES[key], (d.get("voice") or {}).get(key) or {}, health[key]
        p = services.paths(key)
        miss = services.missing(key)
        rows.append({"id": "voice:" + key, "kind": "voice", "title": spec["label"], "found": not miss or h["status"] == "ready",
                     "running": h["status"] == "ready", "url": services.service_url(key), "path": p["models_dir"], "python": p["python"],
                     "vendor": p["vendor_dir"], "missing": miss[:6], "package": spec["package"], "licence": spec["licence"], "uses": ["voice_" + key],
                     "other_dirs": v.get("other_models_dirs") or []})
    return rows


def _piper_row(d: dict) -> dict:
    from instai.providers.tts import PiperTTS

    p = PiperTTS()
    ok, detail = p.available()
    exe = runtime.find_tool("piper")
    return {"id": "piper", "kind": "voice", "title": "Piper (CPU)", "found": ok, "path": exe, "voice": p.voice, "voices": [v["id"] for v in p.voices("")][:30],
            "detail": detail, "package": "piper", "uses": ["voice_piper"], "voice_dirs": (d.get("piper") or {}).get("voice_dirs") or []}


def _ollama_row(d: dict) -> dict:
    from . import hardware

    o = d.get("ollama") or {}
    live = hardware.check_ollama()
    models = [m["name"] for m in (live.get("data") or {}).get("models", [])] if live["status"] != "missing" else []
    return {"id": "ollama", "kind": "ollama", "title": "Ollama", "found": bool(models or o.get("on_disk")), "running": live["status"] != "missing",
            "url": runtime.ollama_url(), "models": models or o.get("on_disk") or [], "path": o.get("models_dir") or o.get("exe"), "exe": o.get("exe"),
            "uses": ["text"]}


def payload(force: bool = False) -> dict:
    d = current(force=force)
    rows = comfy_rows(d)
    wf = workflow_status(d, rows)
    sel = discovery.selected_comfy(d)
    api = (d.get("comfyui") or {}).get("api") or {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_voice, f_ollama, f_pkg = ex.submit(_threaded, _voice_rows, d), ex.submit(_threaded, _ollama_row, d), ex.submit(package_status)
        voice_rows, ollama, pkg = f_voice.result(), f_ollama.result(), f_pkg.result()
    piper_row = _piper_row(d)
    from instai.providers.comfy import launcher

    installs = []
    for c in (d.get("comfyui") or {}).get("installs", []):
        installs.append({"root": c["root"], "portable": c.get("portable"), "launcher": c.get("launcher"), "python": c.get("python"),
                         "desktop": c.get("desktop"), "selected": bool(sel and c["root"] == sel["root"]), "files": len(c.get("files") or {}),
                         "model_roots": [r for r in c.get("model_roots") or [] if r.get("exists")][:40], "extra_yaml": c.get("extra_yaml") or [],
                         "custom_nodes": len(c.get("custom_nodes") or []), "port": c.get("port")})
    features = [{"id": w["id"], "group": _group(w), "ready": w["ready"], "missing": w["missing_models"], "missing_nodes": w["missing_nodes"],
                 "packages": sorted(set(w["packages"]) | set(w["node_packages"]))} for w in wf]
    for r in voice_rows:
        features.append({"id": r["uses"][0], "group": "voice", "ready": r["found"], "missing": r["missing"], "missing_nodes": [], "packages": [r["package"]]})
    features.append({"id": "voice_piper", "group": "voice", "ready": piper_row["found"], "missing": [] if piper_row["found"] else [piper_row["detail"]],
                     "missing_nodes": [], "packages": ["piper"]})
    features.append({"id": "text", "group": "text", "ready": ollama["running"] and bool(ollama["models"]),
                     "missing": [] if ollama["running"] else ["Ollama (not running)"], "missing_nodes": [], "packages": []})
    try:
        free = discovery_free_gb(sel)
    except OSError:
        free = None
    return {
        "scanned_at": d.get("scanned_at"), "seconds": d.get("seconds"), "dirs": d.get("dirs"), "stopped": d.get("stopped"), "defaults": d.get("defaults"),
        "roots": d.get("roots", [])[:40], "manual": manual_paths(), "comfyui_dir": runtime.explicit_comfyui_dir(),
        "comfyui": {"installs": installs, "url": runtime.comfyui_url(), "running": bool(api.get("up")), "nodes": api.get("nodes", 0),
                    "startable": comfy_startable(d), "started_by_instai": launcher.running_ours(), "selected": sel["root"] if sel else None},
        "items": rows + voice_rows + [piper_row, ollama], "features": features, "offers": offers(pkg), "nm_homes": d.get("nm_homes", []),
        "free_gb": free,
    }


def _threaded(fn, *args):
    """Run in a helper thread and close that thread's database connection afterwards (settings are read from the database)."""
    from django.db import connections

    try:
        return fn(*args)
    finally:
        connections.close_all()


def _group(w: dict) -> str:
    if w["id"] in ("anisora_v32_i2v_gguf", "animegen_i2v_gguf", "sdxl_anime_t2i"):
        return "anime"
    return "video" if w["kind"] == "video" else ("train" if w["kind"] == "train" else "image")


def discovery_free_gb(sel: dict | None) -> float | None:
    import shutil

    p = (sel or {}).get("root") or str(ROOT)
    while p and not os.path.exists(p):
        p = os.path.dirname(p)
    return round(shutil.disk_usage(p).free / 1e9, 1) if p else None
