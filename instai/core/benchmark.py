"""Phase 0 benchmark: times, on THIS machine, one image, one Wan 2.2 480p 81-frame shot, one 10-second Persian TTS line and one
LLM script draft with 2-3 candidate models. A runner the owner starts (button in the UI, or START.bat on the first run on a GPU
machine). Nothing is estimated or faked: a step whose service is missing is recorded as "skipped" with the reason.
"""
from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from . import hardware, runtime, settings_store
from .models import BenchmarkResult, BenchmarkRun

IMAGE_PROMPT = ("anime style illustration, a young traveller with a blue cape standing on a rooftop at dusk, city lights below, "
                "soft cel shading, warm colours, clean composition, vertical frame")
PERSIAN_LINE = ("فرض کن در آن شب سرنوشت‌ساز، قهرمان داستان تصمیم دیگری می‌گرفت؛ شهر در سکوت فرو رفته بود و فقط صدای باد از میان برج‌ها می‌گذشت.")
LLM_PREFERRED = ["qwen3:8b", "qwen3.5:9b", "gemma3:12b", "qwen3:14b", "qwen3.5:4b", "gpt-oss:20b", "qwen3.5:27b", "qwen3:30b"]
LLM_META = {"format": "anime_whatif", "language": "fa", "series_title": "Benchmark", "premise": "A world where the hero chose another path.",
            "branch_point": "The hero spares the rival in the last battle.", "characters": ["Arta", "Nila"], "duration_sec": 45,
            "episode": {"number": 1, "title": "The other path", "logline": "Arta spares his rival and history bends.", "goal": "Show the first consequence",
                        "cliffhanger": "A stranger arrives with news."}}


def enqueue_run(options: dict | None = None) -> BenchmarkRun:
    from instai.jobs import queue

    run = BenchmarkRun.objects.create(status="queued", options=options or {}, machine=hardware.machine_fingerprint())
    queue.enqueue("bench.run", {"run_id": run.pk}, title="بنچمارک (فاز ۰)", idempotency_key=f"bench:{run.pk}", timeout_sec=4 * 3600, max_attempts=1)
    return run


def _record(run: BenchmarkRun, step: str, candidate: str, status: str, *, seconds=None, vram=None, message="", details=None) -> BenchmarkResult:
    return BenchmarkResult.objects.create(run=run, step=step, candidate=candidate, status=status, seconds=seconds,
                                          vram_peak_mb=vram or None, message=message[:500], details=details or {})


def run_benchmark(ctx, run: BenchmarkRun) -> dict:
    from instai.gpu.arbiter import ARBITER

    run.status = "running"
    run.machine = hardware.machine_fingerprint(hardware.detect_all(refresh=True)["items"])
    run.save()
    opts = run.options or {}
    steps = ["image", "video", "tts", "llm"]
    BenchmarkResult.objects.filter(run=run).delete()
    try:
        with ARBITER.hold(ctx, "bench") as lease:
            image_path: Path | None = None
            for n, step in enumerate(steps):
                ctx.check()
                ctx.progress(n / len(steps), f"benchmark: {step}")
                lease.peak_mb = 0
                try:
                    if step == "image":
                        image_path = _bench_image(ctx, run, lease)
                    elif step == "video":
                        if opts.get("skip_video"):
                            _record(run, "video", "wan22_i2v_a14b_fp8", "skipped", message="skipped by option (quick run)")
                        else:
                            _bench_video(ctx, run, lease, image_path)
                    elif step == "tts":
                        _bench_tts(ctx, run, lease)
                    else:
                        _bench_llm(ctx, run, lease)
                except Exception as e:  # noqa: BLE001 - one failing step must not hide the others
                    from .models import BenchmarkResult as R

                    if type(e).__name__ in ("JobCancelled", "JobTimeout"):
                        raise
                    _record(run, step, "", "failed", message=f"{type(e).__name__}: {e}")
        run.status = "done"
    except BaseException:
        run.status = "cancelled"
        raise
    finally:
        run.finished_at = timezone.now()
        run.save()
        _write_report(run)
    return {"run_id": run.pk, "results": run.results.count()}


# ------------------------------------------------------------------ steps

def _bench_image(ctx, run, lease) -> Path | None:
    from instai.providers.comfy.client import ComfyClient
    from instai.providers.comfy.workflows import get_workflow, workflow_availability

    wid = str(settings_store.effective("image_workflow"))
    info = hardware.comfy_object_info(force=True)
    if info is None:
        _record(run, "image", wid, "skipped", message="ComfyUI not found (not running at " + runtime.comfyui_url() + ")")
        return None
    av = next((w for w in workflow_availability(info) if w["id"] == wid), None)
    if not av or not av["available"]:
        _record(run, "image", wid, "skipped", message="workflow not ready: missing " + ", ".join((av or {}).get("missing_nodes", []) + (av or {}).get("missing_models", [])))
        return None
    lease.use("comfy")
    client, spec = ComfyClient(runtime.comfyui_url()), get_workflow(wid)
    times, last_file = [], None
    for i in range(2):  # first run loads the model (cold), second shows the steady state
        inputs = {"prompt": IMAGE_PROMPT, "seed": 12345, "width": 832, "height": 1472, "steps": 24}
        t0 = time.time()
        _, files = client.run(spec.build(inputs), timeout=1800, cancel=lambda: _cancelled(ctx), on_tick=lambda s: ctx.check())
        times.append(time.time() - t0)
        last_file = files[0] if files else last_file
    out = Path(tempfile.mkdtemp(prefix="bench-", dir=settings.MEDIA_ROOT)) / "bench.png"
    if last_file:
        client.download(last_file, out)
    _record(run, "image", wid, "ok", seconds=round(times[1], 1), vram=lease.peak_mb,
            details={"cold_seconds": round(times[0], 1), "warm_seconds": round(times[1], 1), "width": 832, "height": 1472, "steps": 24})
    return out if out.exists() else None


def _bench_video(ctx, run, lease, image_path: Path | None) -> None:
    from instai.providers.comfy.client import ComfyClient
    from instai.providers.comfy.workflows import get_workflow, workflow_availability

    wid = "wan22_i2v_a14b_fp8"
    info = hardware.comfy_object_info()
    if info is None:
        _record(run, "video", wid, "skipped", message="ComfyUI not found")
        return
    av = next((w for w in workflow_availability(info) if w["id"] == wid), None)
    if not av or not av["available"]:
        _record(run, "video", wid, "skipped", message="workflow not ready: missing " + ", ".join((av or {}).get("missing_nodes", []) + (av or {}).get("missing_models", [])))
        return
    if image_path is None:
        from instai.render.placeholders import make_placeholder

        image_path = make_placeholder(Path(tempfile.mkdtemp(prefix="bench-", dir=settings.MEDIA_ROOT)) / "start.png", 480, 832, "benchmark")
    lease.use("comfy")
    client, spec = ComfyClient(runtime.comfyui_url()), get_workflow(wid)
    name = client.upload_image(image_path, "instai-bench.png")
    inputs = {"prompt": "the traveller turns and the cape moves in the wind, gentle camera push-in", "image": name, "width": 480, "height": 832,
              "length": 81, "seed": 12345}
    t0 = time.time()
    client.run(spec.build(inputs), timeout=3 * 3600, cancel=lambda: _cancelled(ctx), on_tick=lambda s: ctx.check())
    secs = time.time() - t0
    _record(run, "video", wid, "ok", seconds=round(secs, 1), vram=lease.peak_mb,
            details={"frames": 81, "fps": 16, "width": 480, "height": 832, "note": "first run after load (cold); the brief estimated 480-600 s"})


def _bench_tts(ctx, run, lease) -> None:
    from instai.providers.tts import MossTTS, PiperTTS

    ran = False
    for eng in (PiperTTS(), MossTTS()):
        ok, detail = eng.available()
        if not ok:
            _record(run, "tts", eng.id, "skipped", message=detail)
            continue
        ran = True
        if eng.resource == "gpu":
            lease.use("tts")
        out = Path(tempfile.mkdtemp(prefix="bench-", dir=settings.MEDIA_ROOT)) / "line.wav"
        t0 = time.time()
        res = eng.synthesize(PERSIAN_LINE, out, language="fa", seed=1)
        secs = time.time() - t0
        _record(run, "tts", eng.id, "ok", seconds=round(secs, 2), vram=lease.peak_mb,
                details={"audio_seconds": round(res.seconds, 2), "real_time_factor": round(secs / max(res.seconds, 0.1), 2), "words": len(PERSIAN_LINE.split())})
    return None if ran else None


def _bench_llm(ctx, run, lease) -> None:
    from instai.agents import roles
    from instai.agents.runner import AgentError
    from instai.providers.ollama import OllamaProvider

    prov = OllamaProvider(runtime.ollama_url())
    h = prov.health()
    if not h["ok"] or not h["models"]:
        _record(run, "llm", "ollama", "skipped", message="Ollama not found or has no models")
        return
    names = h["models"]
    cands = [m for m in LLM_PREFERRED if m in names][:3] or names[:2]
    for m in cands:
        ctx.check()
        lease.use("llm", m)
        lease.peak_mb = 0
        p = OllamaProvider(runtime.ollama_url(), m)
        t0 = time.time()
        try:
            res = roles.scriptwriter(dict(LLM_META), provider=p)
            secs = time.time() - t0
            tps = res.completion_tokens / secs if secs and res.completion_tokens else None
            _record(run, "llm", m, "ok", seconds=round(secs, 1), vram=lease.peak_mb,
                    details={"attempts": res.attempts, "valid_json": True, "completion_tokens": res.completion_tokens,
                             "tokens_per_second": round(tps, 1) if tps else None, "blocks": len(res.data.get("blocks", []))})
        except AgentError as e:
            _record(run, "llm", m, "failed", seconds=round(time.time() - t0, 1), vram=lease.peak_mb, message=str(e)[:300],
                    details={"valid_json": False, "errors": e.errors[:3]})


def _cancelled(ctx) -> bool:
    from instai.jobs import queue

    return queue.is_cancel_requested(ctx.job.pk)


# ------------------------------------------------------------------ reports

def report_dict(run: BenchmarkRun) -> dict:
    return {"id": run.pk, "status": run.status, "created_at": run.created_at.isoformat(), "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "machine": run.machine, "options": run.options,
            "results": [{"step": r.step, "candidate": r.candidate, "status": r.status, "seconds": r.seconds, "vram_peak_mb": r.vram_peak_mb,
                         "message": r.message, "details": r.details} for r in run.results.all()]}


def report_markdown(run: BenchmarkRun) -> str:
    d = report_dict(run)
    m = d["machine"]
    lines = [f"## Benchmark run #{run.pk} - {d['created_at'][:16].replace('T', ' ')} UTC", "",
             f"Machine: {m.get('cpu')}; RAM {m.get('ram_gb')} GB; GPU {m.get('gpu') or 'none'} {m.get('vram_gb') or ''} GB; driver {m.get('driver') or '-'}; {m.get('os')}", "",
             "| Step | Candidate | Status | Seconds | Peak VRAM (MB) | Notes |", "|---|---|---|---|---|---|"]
    for r in d["results"]:
        notes = r["message"] or "; ".join(f"{k}={v}" for k, v in r["details"].items() if v not in (None, "", []))
        lines.append(f"| {r['step']} | {r['candidate']} | {r['status']} | {r['seconds'] if r['seconds'] is not None else ''} | "
                     f"{r['vram_peak_mb'] or ''} | {notes[:160]} |")
    return "\n".join(lines) + "\n"


def _write_report(run: BenchmarkRun) -> None:
    try:
        d = Path(settings.DATA_DIR) / "benchmarks"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"benchmark-{run.pk}.json").write_text(json.dumps(report_dict(run), indent=1, ensure_ascii=False), encoding="utf-8")
        (d / f"benchmark-{run.pk}.md").write_text(report_markdown(run), encoding="utf-8")
    except OSError:
        pass
