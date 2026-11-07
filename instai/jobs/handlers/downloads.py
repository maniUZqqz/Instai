"""Downloads: model/tool packs (`downloads.run`, on this PC or on a paired worker PC) and Ollama models (`downloads.ollama`).

Both are ordinary queue jobs, so they can be scheduled (now / at 03:30 / inside the night window), they wait for the computer or for
Ollama instead of failing, and a window that closes (or Cancel) stops them cleanly: the downloader and Ollama both continue from the
partial files the next time. See instai/ops/downloads.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from instai.jobs.registry import handler
from instai.providers.base import ProviderError

ROOT = Path(__file__).resolve().parents[3]
_PCT = re.compile(r"(\d+(?:\.\d+)?)%")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,98}$")


@handler("downloads.run", resource="net", timeout=24 * 3600)
def run(ctx):
    packages = [p for p in ctx.payload.get("packages", []) if re.fullmatch(r"[\w.:-]+", p)]   # package ids or single item ids
    if not packages:
        return {"installed": []}
    target = ctx.payload.get("target")
    if target not in (None, "", "local"):
        return _run_on_worker(ctx, int(target), packages)
    cmd = [sys.executable, str(ROOT / "scripts" / "download_models.py"), "--only", ",".join(packages), "--yes"]
    ctx.log("running: download_models --only " + ",".join(packages))

    def on_line(line: str) -> None:
        if line.strip():
            ctx.log(line[:300])
        m = _PCT.search(line)
        if m:
            ctx.progress(float(m.group(1)) / 100, line.strip()[:120])

    # run_cmd checks cancel / timeout / the night window every 0.25 s and kills the downloader when one of them says stop
    rc, tail = ctx.run_cmd(cmd, cwd=str(ROOT), on_line=on_line, timeout=24 * 3600)
    try:                      # what is installed now (both processes pick the new data/discovery.json up)
        from instai.core import model_status

        model_status.current(force=True)
    except Exception:  # noqa: BLE001
        pass
    if rc != 0:
        raise ProviderError("دانلود کامل نشد؛ جزئیات در گزارش کار است. دوباره امتحان کنید (ادامه از همان‌جا).", retryable=True, code="download_failed")
    return {"installed": packages, "target": "local"}


def _run_on_worker(ctx, worker_id: int, packages: list[str]) -> dict:
    """The same download on a paired worker PC: a `download.pack` task pinned to it. It waits while that PC is off."""
    from django.utils import timezone

    from instai.gpu import compute
    from instai.jobs.models import WorkerNode

    w = WorkerNode.objects.filter(pk=worker_id, enabled=True).first()
    if w is None:
        raise ProviderError("the worker PC was removed or disabled", retryable=False, code="not_ready",
                            fa="رایانهٔ مقصد حذف یا غیرفعال شده است؛ دانلود را دوباره برای یک رایانهٔ دیگر بگذارید.")
    online = bool(w.last_seen and (timezone.now() - w.last_seen).total_seconds() < compute.ONLINE_SECONDS)
    if not online:
        raise ProviderError(f"worker PC {w.name} is offline", retryable=True, code="worker_offline",
                            fa=f"رایانهٔ «{w.name}» خاموش یا بدون ارتباط است؛ دانلود می‌ماند و وقتی روشن شد (و بازهٔ زمانی آمد) انجام می‌شود.")
    if "downloads" not in (w.capabilities or []):
        raise ProviderError(f"worker PC {w.name} runs an older InstAI that cannot download", retryable=False, code="not_ready",
                            fa=f"برنامهٔ رایانهٔ «{w.name}» قدیمی است و دانلود را نمی‌شناسد. آن را به‌روز کنید و START-WORKER.bat را دوباره بزنید.")
    ctx.log(f"download of {', '.join(packages)} goes to worker PC {w.name}")
    cand = compute.Candidate(w.name, False, False, w.vram_free_mb, w.vram_total_mb, None, w.pk)
    res = compute._run_remote(ctx, cand, "download.pack", {"packages": packages, "timeout": 24 * 3600}, None, ["downloads"], 0, 24 * 3600)
    res.cleanup()
    return {"installed": packages, "target": w.name}


@handler("downloads.ollama", resource="net", timeout=24 * 3600)
def run_ollama(ctx):
    from instai.core import runtime
    from instai.providers.ollama import OllamaProvider

    model = str(ctx.payload.get("model") or "").strip()
    if not _MODEL.match(model):
        raise ProviderError("bad Ollama model name", retryable=False, code="validation_error", fa="نام مدل Ollama درست نیست.")
    ctx.log(f"pulling the Ollama model {model}")
    ctx.live(phase="downloading", model=model, provider="ollama", force=True)

    def stop() -> bool:
        ctx.check()                      # raises on Cancel, on the job timeout, and when the night window closes
        return False

    OllamaProvider(runtime.ollama_url()).pull(model, on_progress=lambda f, t: ctx.progress(f, t), should_stop=stop)
    return {"model": model}
