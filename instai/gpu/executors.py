"""Compute tasks that need a GPU, as pure functions of (payload, input files) -> (result, output files).

The same code runs on this PC (called by the router under the local GPU arbiter) and on a paired worker PC (called by the agent under
its own arbiter). Nothing here touches the database: inputs and outputs are files in two folders.

Task kinds
  comfy.graph   run a ComfyUI API graph. Input files are uploaded to ComfyUI; the graph refers to them as the string "@input:<file name>".
                payload: {graph, timeout, install: [{input, dest: "loras"}]}  ->  output files = what the graph saved (images / video)
  voice.tts     one line of speech. payload: {engine, text, voice, language, seed, reference_input}  -> speech.wav
  voice.sfx     one sound effect. payload: {prompt, seconds, seed}  -> sfx.wav
  voice.music   one music bed. payload: {prompt, seconds, seed, bpm}  -> music.wav
  bench.node    a short benchmark of this machine (image + speech); result = measured seconds
"""
from __future__ import annotations

import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from instai.core import runtime
from instai.providers.base import ProviderError

OCCUPANT = {"comfy.graph": "comfy", "voice.tts": "voice", "voice.sfx": "voice", "voice.music": "voice", "bench.node": "comfy", "download.pack": None}   # None: no GPU
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
INPUT_REF = re.compile(r"^@input:(.+)$")


class TaskCancelled(Exception):
    pass


@dataclass
class TaskIO:
    in_dir: Path
    out_dir: Path
    progress: Callable[[float, str], None] = lambda f, t="": None
    cancelled: Callable[[], bool] = lambda: False
    meta: dict = field(default_factory=dict)

    def input(self, name: str) -> Path:
        p = self.in_dir / Path(name).name
        if not p.is_file():
            raise ProviderError(f"input file {name} is not in the task package", retryable=False, code="bad_task")
        return p

    def check(self) -> None:
        if self.cancelled():
            raise TaskCancelled()


def substitute(obj, mapping: dict[str, str]):
    """Replace "@input:<name>" strings anywhere in a graph by the file name ComfyUI knows after the upload."""
    if isinstance(obj, str):
        m = INPUT_REF.match(obj)
        return mapping.get(m.group(1), obj) if m else obj
    if isinstance(obj, list):
        return [substitute(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: substitute(v, mapping) for k, v in obj.items()}
    return obj


def _live(**fields) -> None:
    """Tell the queue screen what this task is doing (no-op on a worker PC or outside a job)."""
    try:
        from instai.jobs.context import report_live
    except Exception:  # noqa: BLE001
        return
    report_live(**fields)


def _comfy_label(payload: dict) -> str:
    wid = payload.get("workflow") or ""
    try:
        from instai.providers.comfy.workflows import WORKFLOWS

        return WORKFLOWS[wid].title.split(" - ")[0] if wid in WORKFLOWS else str(wid)
    except Exception:  # noqa: BLE001
        return str(wid)


def run_comfy_graph(payload: dict, io: TaskIO) -> dict:
    from instai.providers.comfy.client import ComfyCancelled, ComfyClient

    from instai.providers.comfy import launcher

    client = ComfyClient(runtime.comfyui_url())
    _live(phase="starting_comfy" if not client.is_up() else "loading_model", provider="comfy", model=_comfy_label(payload), device=None)
    if not client.is_up():
        io.progress(0.01, "starting ComfyUI")
    # also checks that a ComfyUI that already runs uses the graphics card (a ComfyUI on the CPU would render for hours)
    client = ComfyClient(launcher.ensure_running(progress=lambda t: io.progress(0.01, t), cancelled=io.cancelled))
    info = launcher.device_info(client.base_url)
    if info and info.get("type"):
        _live(device="gpu" if info["type"] != "cpu" else "cpu", device_name=info.get("name"))
    mapping: dict[str, str] = {}
    for f in sorted(io.in_dir.iterdir()) if io.in_dir.is_dir() else []:
        if f.suffix.lower() in IMAGE_EXT:
            mapping[f.name] = client.upload_image(f, f"instai-{uuid.uuid4().hex[:6]}-{f.name}")
    for inst in payload.get("install", []):            # files that must sit inside ComfyUI's folder first (a LoRA, a training dataset)
        cd = runtime.comfyui_dir()
        if not cd:
            raise ProviderError("COMFYUI_DIR is not set on this PC, so files cannot be installed into ComfyUI", retryable=False, code="not_ready")
        rel = str(inst.get("dest") or "models/loras").replace("\\", "/").strip("/")
        if rel == "loras":
            rel = "models/loras"
        if ".." in rel.split("/") or not rel.startswith(("models/", "input/")):
            raise ProviderError(f"refusing to install into {rel}", retryable=False, code="bad_task")
        dst = Path(cd) / rel
        dst.mkdir(parents=True, exist_ok=True)
        src = io.input(inst["input"])
        if not (dst / src.name).exists() or (dst / src.name).stat().st_size != src.stat().st_size:
            shutil.copyfile(src, dst / src.name)
    graph = substitute(payload["graph"], mapping)
    io.progress(0.02, "queued in ComfyUI")
    try:
        pid, files = client.run(graph, timeout=float(payload.get("timeout") or 3600),
                                on_tick=lambda s: io.progress(min(0.95, 0.05 + s / max(60.0, float(payload.get("expected") or 600))), f"ComfyUI {int(s)}s"),
                                cancel=io.cancelled)
    except ComfyCancelled:
        raise TaskCancelled() from None
    saved = []
    io.out_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        name = f"{f.node_id}-{f.filename}"
        client.download(f, io.out_dir / name)
        saved.append({"name": name, "kind": f.kind, "node": f.node_id})
    for pattern in payload.get("collect", []):           # files a graph wrote straight into ComfyUI's folders (a trained LoRA)
        cd = runtime.comfyui_dir()
        found = sorted(Path(cd).glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True) if cd and ".." not in pattern else []
        if found:
            shutil.copyfile(found[0], io.out_dir / found[0].name)
            saved.append({"name": found[0].name, "kind": "file", "node": ""})
    if not saved and payload.get("expect_files", True):
        raise ProviderError("ComfyUI returned no output file", retryable=True)
    return {"files": saved, "prompt_id": pid}


def run_voice_tts(payload: dict, io: TaskIO) -> dict:
    from instai.providers.tts import get_tts

    tts = get_tts(None if payload.get("engine") in (None, "", "auto") else payload["engine"])
    ref = str(io.input(payload["reference_input"])) if payload.get("reference_input") else None
    io.progress(0.1, f"speaking with {tts.id}")
    _live(phase="speaking", provider=tts.id, model=tts.id, device={"gpu": "gpu", "net": "net"}.get(getattr(tts, "resource", "cpu"), "cpu"), step=None, steps=None)
    r = tts.synthesize(payload["text"], io.out_dir / "speech.wav", voice=payload.get("voice") or None, language=payload.get("language") or "fa",
                       seed=payload.get("seed"), reference=ref)
    return {"engine": r.engine, "voice": r.voice, "seconds": r.seconds, "sample_rate": r.sample_rate, "render_seconds": r.render_seconds,
            "files": [{"name": "speech.wav", "kind": "audio"}]}


def _run_generator(kind: str, payload: dict, io: TaskIO) -> dict:
    from instai.providers.audio import get_generator

    gen = get_generator(kind)
    name = "sfx.wav" if kind == "sfx" else "music.wav"
    io.progress(0.1, f"generating with {gen.id}")
    _live(phase="rendering", provider=gen.id, model=gen.id, device={"net": "net", "cpu": "cpu"}.get(getattr(gen, "resource", "gpu"), "gpu"), step=None, steps=None)
    r = gen.generate(payload["prompt"], float(payload.get("seconds") or 8), io.out_dir / name, seed=payload.get("seed"), bpm=payload.get("bpm"))
    return {"engine": r.engine, "seconds": r.seconds, "render_seconds": r.render_seconds, "licence": r.licence, "files": [{"name": name, "kind": "audio"}]}


def run_voice_sfx(payload: dict, io: TaskIO) -> dict:
    return _run_generator("sfx", payload, io)


def run_voice_music(payload: dict, io: TaskIO) -> dict:
    return _run_generator("music", payload, io)


def run_bench_node(payload: dict, io: TaskIO) -> dict:
    """What this PC measures about itself: GPU facts, one image (cold + warm) when ComfyUI can, one Persian speech line per ready engine."""
    from instai.core import hardware

    out: dict = {"gpu": hardware.gpu_status(), "skipped": {}, "image": None, "tts": {}}
    io.progress(0.05, "checking ComfyUI")
    info = hardware.comfy_object_info(runtime.comfyui_url(), force=True)
    if info is None:
        out["skipped"]["image"] = "ComfyUI is not running"
    else:
        from instai.providers.comfy.client import ComfyClient
        from instai.providers.comfy.workflows import get_workflow, workflow_availability

        av = next((w for w in workflow_availability(info) if w["id"] == "flux_dev_fp8_t2i"), None)
        if not av or not av["available"]:
            out["skipped"]["image"] = "the FLUX workflow is not ready on this PC"
        else:
            spec, client, times = get_workflow("flux_dev_fp8_t2i"), ComfyClient(runtime.comfyui_url()), []
            for i in range(2):                     # first = cold (models load), second = warm
                io.check()
                io.progress(0.2 + 0.3 * i, f"image {i + 1}/2")
                graph = spec.build({"prompt": "a calm mountain lake at dawn, soft light", "width": 576, "height": 1024, "steps": 12, "seed": 7})
                t0 = time.time()
                client.run(graph, timeout=1800, cancel=io.cancelled)
                times.append(round(time.time() - t0, 2))
            out["image"] = {"cold": times[0], "warm": times[1], "workflow": "flux_dev_fp8_t2i", "size": "576x1024", "steps": 12}
    from instai.providers.tts import MossTTS, PiperTTS

    for eng in (PiperTTS(), MossTTS()):
        ok, detail = eng.available()
        if not ok:
            out["skipped"][f"tts_{eng.id}"] = detail
            continue
        io.check()
        io.progress(0.7, f"speech with {eng.id}")
        try:
            r = eng.synthesize("سلام، این یک جملهٔ آزمایشی برای سنجش سرعت صدا روی این رایانه است.", io.out_dir / f"bench-{eng.id}.wav", language="fa", seed=1)
            out["tts"][eng.id] = {"seconds": round(r.render_seconds, 2), "audio_seconds": round(r.seconds, 2)}
        except Exception as e:  # noqa: BLE001
            out["skipped"][f"tts_{eng.id}"] = str(e)[:120]
    return out


_PCT = re.compile(r"(\d+(?:\.\d+)?)%")


def run_download(payload: dict, io: TaskIO) -> dict:
    """`download.pack`: fetch model packages/items on THIS PC (the worker PC) with the same downloader as Download-Models.bat
    (resumable, verified). Stopping it (cancel, or the main PC's night window closing) kills the process; the next run continues from the
    partial files. payload: {packages: [ids], mirror}"""
    import subprocess
    import sys

    from instai.core import runtime as rt

    ids = [p for p in payload.get("packages", []) if isinstance(p, str) and re.fullmatch(r"[\w.:-]+", p)]
    if not ids:
        return {"installed": []}
    root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, str(root / "scripts" / "download_models.py"), "--only", ",".join(ids), "--yes"]
    io.progress(0.01, "starting the downloader")
    p = subprocess.Popen(cmd, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    tail: list[str] = []

    def reader():
        for line in p.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            if not line:
                continue
            tail.append(line)
            del tail[:-30]
            m = _PCT.search(line)
            if m:
                io.progress(min(0.99, float(m.group(1)) / 100), line.strip()[:120])
    import threading

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        while p.poll() is None:
            time.sleep(0.5)
            if io.cancelled():
                raise TaskCancelled()
    except BaseException:
        p.kill()
        raise
    finally:
        t.join(timeout=2)
    if p.returncode != 0:
        raise ProviderError("the download did not finish: " + " | ".join(tail[-3:])[:300], retryable=True, code="download_failed",
                            fa="دانلود روی این رایانه کامل نشد؛ دوباره امتحان کنید (ادامه از همان‌جا).")
    return {"installed": ids}


EXECUTORS: dict[str, Callable[[dict, TaskIO], dict]] = {"comfy.graph": run_comfy_graph, "voice.tts": run_voice_tts, "voice.sfx": run_voice_sfx,
                                                         "voice.music": run_voice_music, "bench.node": run_bench_node, "download.pack": run_download}


def run(kind: str, payload: dict, io: TaskIO) -> dict:
    fn = EXECUTORS.get(kind)
    if fn is None:
        raise ProviderError(f"unknown task kind {kind}", retryable=False, code="bad_task")
    io.out_dir.mkdir(parents=True, exist_ok=True)
    return fn(payload, io)
