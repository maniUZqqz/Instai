"""One-press tests for every model on the Models page, each with a plain pass / warn / fail and the reason.

  ollama:<model>     a short prompt; time, tokens per second and how much of the model is on the GPU (Ollama /api/ps size_vram vs size)
  comfy:<file>       a tiny generation (256 px, few steps / 5 frames) with the cheapest ready workflow that loads this file
  voice:moss|sfx|music, piper   a short sample you can play
A test runs as a job (kind `models.test`): it waits its turn at the GPU arbiter like real work and shows live progress in the queue.
A failing test is a RESULT (verdict "fail" with the reason), not a crashed job. Only cancel / timeout end a test as a job error.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from instai.providers.base import ProviderError

from . import hardware, runtime

TEST_PROMPT_FA = "فقط یک جمله‌ی کوتاه فارسی بنویس که با «سلام» شروع شود."
VOICE_TEXT_FA = "سلام، این یک نمونهٔ کوتاه برای آزمایش صدا است."
SLOW_TOKENS_PER_SECOND = 3.0


def _fa(n) -> str:
    return str(n).translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫"))


def parse_id(test_id: str) -> tuple[str, str] | None:
    """('ollama', model) | ('comfy', file) | ('voice', key) for a valid test id, else None."""
    from instai.providers.audio import services

    tid = str(test_id or "").strip()
    if tid == "piper":
        return "voice", "piper"
    kind, _, key = tid.partition(":")
    if kind in ("ollama", "comfy") and key:
        return kind, key
    if kind == "voice" and key in services.SERVICES:
        return "voice", key
    return None


def resource_for(payload: dict) -> str:
    p = parse_id(payload.get("id", ""))
    if not p or p == ("voice", "piper"):
        return "cpu"
    return "gpu"


def title_for(test_id: str) -> str:
    p = parse_id(test_id)
    name = p[1] if p else test_id
    if p and p[0] == "voice":
        from instai.providers.audio import services

        name = "Piper" if name == "piper" else services.SERVICES[name]["label"]
    return f"تست مدل: {name}"


# ------------------------------------------------------------------ result shape

def _m(key: str, value, unit: str = "") -> dict:
    return {"key": key, "value": value, "unit": unit}


def _result(verdict: str, fa: str, en: str, *, metrics: list[dict] | None = None, sample: str = "", media: dict | None = None,
            device: str = "—", gpu_pct: int | None = None) -> dict:
    return {"verdict": verdict, "ok": verdict != "fail", "reason_fa": fa, "reason_en": en, "metrics": metrics or [], "sample": sample, "media": media,
            "device": {"label": device, "gpu_pct": gpu_pct}}


def _fail(err: Exception | str, **kw) -> dict:
    if isinstance(err, ProviderError):
        return _result("fail", err.fa or str(err), str(err), **kw)
    return _result("fail", f"آزمایش ناموفق بود: {err}", f"The test failed: {err}", **kw)


# ------------------------------------------------------------------ Ollama

def run_ollama(ctx, model: str) -> dict:
    from instai.gpu.arbiter import ARBITER
    from instai.providers.ollama import OllamaProvider

    gpu = hardware.gpu_status()
    prov = OllamaProvider(runtime.ollama_url(), model)
    ctx.progress(0.05, "starting")
    with ARBITER.hold(ctx, "llm", model):
        ctx.progress(0.2, "asking the model")
        res = prov.generate([{"role": "user", "content": TEST_PROMPT_FA}], max_tokens=64, temperature=0.2)
    raw = res.raw or {}
    pct, place = raw.get("gpu_pct"), raw.get("placement")
    tps = res.tokens_per_second
    tokens = res.completion_tokens
    metrics = [_m("seconds", round(res.seconds, 1), "s")]
    if raw.get("load_seconds"):
        metrics.append(_m("load_seconds", raw["load_seconds"], "s"))
    if raw.get("first_token_seconds") is not None:
        metrics.append(_m("first_token_seconds", raw["first_token_seconds"], "s"))
    if tokens:
        metrics.append(_m("tokens", tokens))
    if tps:
        metrics.append(_m("tokens_per_second", tps, "tok/s"))
    if raw.get("size_mb"):
        metrics.append(_m("size_mb", raw["size_mb"], "MB"))
    if raw.get("vram_mb") is not None and raw.get("size_mb"):
        metrics.append(_m("vram_mb", raw["vram_mb"], "MB"))
    if pct is not None:
        metrics.append(_m("gpu_pct", pct, "%"))
    label = {"gpu": "GPU", "mixed": "GPU + CPU", "cpu": "CPU"}.get(place or "", "—")
    kw = dict(metrics=metrics, sample=res.text[:300], device=label, gpu_pct=pct)
    speed_fa = f" سرعت: {_fa(tps)} توکن در ثانیه." if tps else ""
    speed_en = f" Speed: {tps} tokens/s." if tps else ""
    if not tokens and not res.text:
        return _result("fail", "مدل جوابی نداد.", "The model returned nothing.", **kw)
    if gpu and place == "cpu":
        return _result("fail", f"مدل کار کرد ولی تقریباً کاملاً روی CPU اجرا شد (فقط {_fa(pct)}٪ روی کارت گرافیک)؛ برای همین کند است و GPU بی‌کار می‌ماند. "
                               "مدل کوچک‌تری مثل qwen3:8b انتخاب کنید." + speed_fa,
                       f"The model worked but ran almost entirely on the CPU (only {pct}% on the graphics card), which is why it is slow and the GPU stays idle. "
                       "Choose a smaller model such as qwen3:8b." + speed_en, **kw)
    if gpu and place == "mixed":
        return _result("warn", f"کار می‌کند ولی فقط {_fa(pct)}٪ مدل روی کارت گرافیک است و بقیه روی CPU؛ کندتر از حد ممکن است. "
                               "مدل کوچک‌تری انتخاب کنید که کامل جا شود." + speed_fa,
                       f"It works but only {pct}% of the model is on the graphics card and the rest runs on the CPU; slower than it could be. "
                       "Choose a smaller model that fits completely." + speed_en, **kw)
    if not gpu:
        return _result("warn", "مدل کار کرد، ولی کارت گرافیک NVIDIA دیده نشد (nvidia-smi)؛ پس معلوم نیست روی GPU اجرا شده باشد." + speed_fa,
                       "The model worked, but no NVIDIA graphics card was seen (nvidia-smi), so it may not have used the GPU." + speed_en, **kw)
    if tps and tps < SLOW_TOKENS_PER_SECOND:
        return _result("warn", f"روی GPU است ولی خیلی کند است ({_fa(tps)} توکن در ثانیه)." , f"It is on the GPU but very slow ({tps} tokens/s).", **kw)
    where_fa = f" و {_fa(pct)}٪ مدل روی کارت گرافیک است" if pct is not None else ""
    where_en = f"; {pct}% of the model is on the graphics card" if pct is not None else ""
    return _result("pass", f"درست کار کرد در {_fa(round(res.seconds, 1))} ثانیه{where_fa}." + speed_fa, f"It works: {round(res.seconds, 1)} s{where_en}." + speed_en, **kw)


# ------------------------------------------------------------------ ComfyUI

def _test_png(path: Path, size: int = 256) -> None:
    from PIL import Image

    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = (x * 255 // size, y * 255 // size, 140)
    img.save(path, "PNG")


def _register_media(ctx, src: Path, kind: str, test_id: str, extra: dict) -> dict:
    from instai.assets import storage as asset_storage

    rel = f"model-tests/job{ctx.job.pk}-{src.name}"
    a = asset_storage.register(src, rel, kind=kind, role="other", provenance={"purpose": "model_test", "test": test_id, **extra})
    return {"type": kind, "url": a.url, "name": src.name}


def pick_workflow(file: str) -> tuple[str | None, str, str]:
    """(workflow id, '', '') for the cheapest READY image/video workflow that loads this file; (None, reason_fa, reason_en) otherwise."""
    from instai.providers.comfy.workflows import WORKFLOWS

    from . import model_status

    d = model_status.current()
    rows = model_status.comfy_rows(d)
    row = next((r for r in rows if r["file"].lower() == file.lower() or file.lower() in [a.lower() for a in r["aliases"]]), None)
    if row is None:
        return None, "این فایل در فهرست مدل‌های InstAI نیست.", "This file is not in InstAI's model list."
    if not row["found"]:
        return None, "این فایل روی این رایانه پیدا نشد؛ اول آن را نصب کنید.", "This file was not found on this PC; install it first."
    cands = [u for u in row["uses"] if u in WORKFLOWS and WORKFLOWS[u].kind in ("image", "video")]
    if not cands:
        return None, "این فایل جدا قابل آزمایش نیست؛ همراه یک مدل اصلی آزمایش می‌شود.", "This file cannot be tested alone; it is tested together with a main model."
    status = {w["id"]: w for w in model_status.workflow_status(d, rows)}
    ready = sorted((u for u in cands if status[u]["ready"]), key=lambda u: (WORKFLOWS[u].kind != "image", cands.index(u)))
    if ready:
        return ready[0], "", ""
    w = status[cands[0]]
    miss = ", ".join((w["missing_models"] + w["missing_nodes"])[:4])
    return None, f"گردش‌کارِ «{cands[0]}» آماده نیست؛ چیزهایی که کم است: {miss}", f"The workflow '{cands[0]}' is not ready; missing: {miss}"


def run_comfy(ctx, file: str) -> dict:
    from instai.gpu import compute
    from instai.providers.comfy import launcher
    from instai.providers.comfy.workflows import get_workflow

    wid, fa, en = pick_workflow(file)
    if wid is None:
        return _result("fail", fa, en)
    spec = get_workflow(wid)
    props = spec.input_schema.get("properties", {})
    work = Path(tempfile.mkdtemp(prefix="modeltest-", dir=runtime.media_root()))
    files: dict[str, Path] = {}
    inputs: dict = {"prompt": "a small red apple on a wooden table, soft light", "seed": 7, "filename_prefix": "instai-test"}
    if "width" in props:
        inputs.update(width=256, height=256)
    if spec.kind == "image" and "steps" in props:
        inputs["steps"] = 4
    if spec.kind == "video" and "length" in props:
        inputs["length"] = int(props["length"].get("minimum", 5))
    if "image" in props:
        png = work / "instai-test.png"
        _test_png(png)
        files[png.name] = png
        inputs["image"] = "@input:" + png.name
        if "image_end" in props:
            inputs["image_end"] = "@input:" + png.name
    ctx.progress(0.05, "starting")
    try:
        t0 = time.time()
        res = compute.run_task(ctx, "comfy.graph", {"graph": spec.build(inputs), "workflow": wid, "timeout": 3600, "expected": spec.expected_seconds},
                               inputs=files, remote_ok=False)
        secs = round(time.time() - t0, 1)
        try:
            from instai.gpu.executors import IMAGE_EXT

            pics = res.of_kind(*IMAGE_EXT)
            vids = res.of_kind(".mp4", ".webm", ".mov", ".gif")
            out = (vids or pics or [None])[0]
            if out is None:
                return _result("fail", "ComfyUI تمام شد ولی خروجی نداد.", "ComfyUI finished but returned no output.")
            media = _register_media(ctx, out, "video" if vids else "image", f"comfy:{file}", {"workflow": wid})
        finally:
            res.cleanup()
    except ProviderError as e:
        return _fail(e)
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
    info = launcher.device_info(runtime.comfyui_url())
    dev = (info or {}).get("type")
    label = {"cuda": "GPU", "cpu": "CPU"}.get(dev or "", "—")
    metrics = [_m("seconds", secs, "s"), _m("workflow", wid)]
    if "width" in inputs:
        metrics += [_m("width", inputs["width"]), _m("height", inputs["height"])]
    if "steps" in inputs:
        metrics.append(_m("steps", inputs["steps"]))
    if "length" in inputs:
        metrics.append(_m("length", inputs["length"]))
    what_fa, what_en = ("ویدئوی کوتاه", "a short video") if media["type"] == "video" else ("یک تصویر کوچک", "a small image")
    if dev == "cpu":
        return _result("fail", f"{what_fa} ساخته شد ولی روی CPU، نه کارت گرافیک ({_fa(secs)} ثانیه).", f"{what_en.capitalize()} was made, but on the CPU, not the graphics card ({secs} s).",
                       metrics=metrics, media=media, device=label)
    return _result("pass", f"{what_fa} با «{wid}» ساخته شد در {_fa(secs)} ثانیه" + (" روی کارت گرافیک." if dev == "cuda" else "."),
                   f"{what_en.capitalize()} was made with '{wid}' in {secs} s" + (" on the graphics card." if dev == "cuda" else "."), metrics=metrics, media=media, device=label)


# ------------------------------------------------------------------ voices

def _wav_seconds(p: Path) -> float:
    import wave

    try:
        with wave.open(str(p), "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:  # noqa: BLE001
        return 0.0


def run_voice(ctx, key: str) -> dict:
    from instai.gpu import compute
    from instai.providers.audio import services
    from instai.providers.tts import PiperTTS

    ctx.progress(0.05, "starting")
    work = Path(tempfile.mkdtemp(prefix="modeltest-", dir=runtime.media_root()))
    t0 = time.time()
    try:
        if key == "piper":
            tts = PiperTTS()
            ok, detail = tts.available()
            if not ok:
                return _result("fail", f"Piper آماده نیست: {detail}", f"Piper is not ready: {detail}")
            out = work / "sample.wav"
            r = tts.synthesize(VOICE_TEXT_FA, out, language="fa", seed=1)
            engine, render = r.engine, r.render_seconds
            device = "CPU"
        else:
            kind, payload = {"moss": ("voice.tts", {"engine": "moss", "text": VOICE_TEXT_FA, "language": "fa", "seed": 1}),
                             "sfx": ("voice.sfx", {"prompt": "a wooden door closing, short", "seconds": 3, "seed": 1}),
                             "music": ("voice.music", {"prompt": "calm piano, short intro", "seconds": 4, "seed": 1, "bpm": 90})}[key]
            res = compute.run_task(ctx, kind, payload, remote_ok=False)
            try:
                wavs = res.of_kind(".wav", ".mp3", ".flac", ".ogg")
                if not wavs:
                    return _result("fail", "موتور تمام شد ولی فایل صوتی نساخت.", "The engine finished but made no audio file.")
                out = work / wavs[0].name
                out.write_bytes(wavs[0].read_bytes())
            finally:
                res.cleanup()
            engine, render = res.result.get("engine") or key, res.result.get("render_seconds")
            dev = str(services.health(key, 1.0).get("device") or "").lower()
            device = "GPU" if "cuda" in dev else ("CPU" if "cpu" in dev else "—")
        secs = round(time.time() - t0, 1)
        audio_secs = round(_wav_seconds(out), 1) if out.suffix.lower() == ".wav" else None
        if out.stat().st_size < 1000 or (audio_secs is not None and audio_secs < 0.2):
            return _result("fail", "فایل صوتی خالی یا بسیار کوتاه بود.", "The audio file was empty or far too short.", device=device)
        media = _register_media(ctx, out, "audio", f"voice:{key}" if key != "piper" else "piper", {"engine": engine})
    except ProviderError as e:
        return _fail(e)
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
    metrics = [_m("seconds", secs, "s")]
    if render:
        metrics.append(_m("render_seconds", round(float(render), 1), "s"))
    if audio_secs:
        metrics.append(_m("audio_seconds", audio_secs, "s"))
    metrics.append(_m("engine", str(engine)))
    if device == "CPU" and key != "piper":
        return _result("warn", f"صدا ساخته شد ولی این موتور روی CPU کار می‌کند، نه کارت گرافیک؛ کند است. نمونه را گوش دهید ({_fa(secs)} ثانیه).",
                       f"The audio was made but this engine works on the CPU, not the graphics card; slow. Listen to the sample ({secs} s).", metrics=metrics, media=media, device=device)
    return _result("pass", f"نمونهٔ صدا ساخته شد ({_fa(secs)} ثانیه). آن را پخش کنید و گوش بدهید.", f"The sample was made ({secs} s). Play it and listen.",
                   metrics=metrics, media=media, device=device)


# ------------------------------------------------------------------ entry point (the job handler)

def run(ctx, test_id: str) -> dict:
    """Run one test and return its result dict (stored as the job result). A failed test is a result, not an exception."""
    from instai.jobs.context import JobCancelled, JobTimeout

    p = parse_id(test_id)
    if p is None:
        return {**_result("fail", "شناسهٔ تست نامعتبر است.", "The test id is not valid."), "id": test_id, "kind": "unknown", "seconds": 0}
    kind, key = p
    t0 = time.time()
    try:
        res = {"ollama": run_ollama, "comfy": run_comfy, "voice": run_voice}[kind](ctx, key)
    except (JobCancelled, JobTimeout):
        raise
    except ProviderError as e:
        res = _fail(e)
    except Exception as e:  # noqa: BLE001 - one broken test must not look like a crashed queue
        res = _fail(f"{type(e).__name__}: {str(e)[:200]}")
    res.update(id=test_id, kind=kind, seconds=round(time.time() - t0, 1))
    return res
