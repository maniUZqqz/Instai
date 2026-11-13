"""styles.preview: make real sample images of the built-in styles with the image model (ComfyUI), one by one, resumable."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.core import settings_store
from instai.core.errors import DomainError
from instai.jobs.registry import handler
from instai.providers.base import ProviderError
from instai.styles import library, previews
from instai.styles.models import StylePreview

_WAIT_CODES = ("worker_offline", "worker_lost", "comfy_down", "gpu_busy", "ollama_down")


def _resource(payload: dict) -> str:
    return "cpu" if str(settings_store.effective("image_engine")) == "placeholder" else "gpu"


@handler("styles.preview", resource=_resource, timeout=14400)
def styles_preview(ctx):
    from instai.gpu import compute
    from instai.providers.comfy.workflows import get_workflow

    if str(settings_store.effective("image_engine")) == "placeholder":
        raise DomainError("not_ready", "حالت آزمایشی روشن است و تصویر واقعی ساخته نمی‌شود؛ در «تنظیمات» موتور تصویر را روی ComfyUI بگذارید.",
                          message_en="Demo mode is on and no real image can be made; set the image engine to ComfyUI in Settings.")
    wid = str(settings_store.effective("image_workflow"))
    if not compute.workflow_available(wid):
        raise ProviderError("ComfyUI is not available (or the image workflow is not ready on any PC)", retryable=True, code="comfy_down", wait="comfy_down",
                            fa="ComfyUI در دسترس نیست (یا گردش‌کار تصویر روی هیچ‌یک از رایانه‌ها آماده نیست)؛ کار منتظر می‌ماند و با آماده شدنش ادامه می‌یابد.")
    spec = get_workflow(wid)
    keys = previews.pending(wid, [str(k) for k in (ctx.payload.get("keys") or [])] or None, bool(ctx.payload.get("force")))
    done = 0
    failed: list[str] = []
    for i, key in enumerate(keys):
        ctx.check()
        ctx.progress(i / max(1, len(keys)), f"{key} ({i + 1}/{len(keys)})")
        st = library.get_style(key)
        if not st:
            continue
        pos, neg = previews.prompt_for(st)
        w, h = previews.SIZE
        inputs = {"prompt": pos, "negative_prompt": neg, "width": w, "height": h, "seed": previews.seed_for(key), "steps": previews.steps_for(st)}
        tmpdir = Path(tempfile.mkdtemp(prefix="stylepv-", dir=settings.MEDIA_ROOT))
        try:
            res = compute.run_task(ctx, "comfy.graph", {"graph": spec.build(inputs), "workflow": wid, "timeout": 1800, "expected": spec.expected_seconds})
            try:
                pics = res.of_kind(".png", ".jpg", ".jpeg", ".webp")
                if not pics:
                    raise ProviderError("ComfyUI returned no image", retryable=True)
                tmp = tmpdir / "preview.png"
                shutil.move(str(pics[0]), tmp)
                asset = asset_storage.register(tmp, f"styles/{key}/sample-{previews.prompt_hash(st, wid)[:8]}.png", kind="image", role="reference",
                                               provenance={**spec.provenance(inputs), "provider": "comfyui", "device": res.device, "style": key, "job_id": ctx.job.pk,
                                                           "note": "sample image of a built-in style, made from its sample prompt"})
            finally:
                res.cleanup()
            StylePreview.objects.update_or_create(style_key=key, defaults={"asset": asset, "prompt_hash": previews.prompt_hash(st, wid), "device": res.device})
            library.clear_cache()
            done += 1
        except ProviderError as e:
            if e.wait or e.code in _WAIT_CODES:
                raise                                     # not the style's fault: the whole job waits and resumes (finished styles are kept)
            failed.append(key)
            ctx.log(f"{key}: {e}", "warning")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    if failed and not done:
        raise ProviderError("no sample image could be made: " + ", ".join(failed[:6]), retryable=True)
    return {"made": done, "failed": failed, "skipped": len(keys) - done - len(failed)}
