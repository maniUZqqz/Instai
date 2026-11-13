"""Identity jobs: write the identity anchor with the text model; make the model sheets (turnaround and expressions) with the image model."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from instai.agents import llm
from instai.agents import pipeline_roles as roles
from instai.assets import storage as asset_storage
from instai.core import settings_store
from instai.jobs import describe
from instai.jobs.registry import handler
from instai.pages.models import Character, CharacterReference

from . import service

describe.KIND_TEXT.update({"identity.anchor": ("نوشتن هویت شخصیت", "Writing the character identity"),
                           "identity.sheets": ("ساخت برگهٔ مدل شخصیت", "Making the character model sheets")})

TURNAROUND = ("character model sheet, turnaround: the same character in front view, three-quarter view, side view and back view, neutral standing pose, full body, plain light "
              "background, flat even lighting, consistent proportions")
EXPRESSIONS = "character expression sheet: six head studies of the same character, neutral, happy, angry, sad, surprised and scared, plain light background, consistent design"


def _char(payload: dict) -> Character | None:
    return Character.objects.filter(pk=payload.get("character_id")).select_related("page").first()


def _anchor_resource(payload: dict) -> str:
    c = _char(payload)
    return llm.resource_for(c.page if c else None, "identity_anchor")


@handler("identity.anchor", resource=_anchor_resource, timeout=900)
def anchor(ctx):
    c = Character.objects.select_related("page").get(pk=ctx.payload["character_id"])
    lock = service.ensure_lock(c)
    from instai.styles import library

    lk = library.look_of(c.page, service.look_series(c.page, ctx.payload.get("series_id")))      # the art style chosen once for the series, else the page's own
    st = library.get_style(lk["style_key"]) or {}
    lang = str(ctx.payload.get("language") or "")[:2]
    meta = {"language": lang if lang in ("fa", "en") else c.page.language, "format": c.page.format,
            "character": {"name": c.name, "role": c.role, "appearance": c.appearance, "personality": c.personality, "profile": c.profile},
            "look": {"style": st.get("name_en", lk["style_key"]), "realism": lk.get("realism", "")}, "existing_anchor": lock.anchor}
    ctx.progress(0.3, "anchor")
    res = roles.identity_anchor(meta, provider=llm.resolve(c.page, "identity_anchor"))
    d = res.data
    pal = [{"role": p.get("role") or "colour", "hex": p["hex"], "name": ""} for p in d.get("palette") or [] if p.get("hex")]
    if lock.status != "locked":
        service.edit_lock(c, {"anchor": d["anchor"], "avoid": d.get("avoid") or lock.avoid, **({"palette": pal} if pal else {})})
    return {"anchor": d["anchor"], "hooks": d.get("visual_hooks", []), "provider": res.provider, "locked": lock.status == "locked"}


def _resource(payload: dict) -> str:
    return "cpu" if str(settings_store.effective("image_engine")) == "placeholder" else "gpu"


@handler("identity.sheets", resource=_resource, timeout=3 * 3600)
def sheets(ctx):
    """Two pictures per character through the GPU router (the same image workflow as the keyframes): a turnaround and an expression sheet. They are DRAFT
    references: the owner looks at them, picks the best and locks the identity."""
    from instai.gpu import compute
    from instai.production import hero
    from instai.providers.base import ProviderError
    from instai.providers.comfy.workflows import get_workflow
    from instai.render.placeholders import make_placeholder
    from instai.styles import library

    c = Character.objects.select_related("page").get(pk=ctx.payload["character_id"])
    lock = service.ensure_lock(c)
    look = library.compose_for(c.page, service.look_series(c.page, ctx.payload.get("series_id")))   # the same art style as every other picture of the series
    engine = str(settings_store.effective("image_engine") or "auto")
    wid = str(settings_store.effective("image_workflow"))
    made = {}
    for n, (kind, label, prefix) in enumerate((("sheet", "turnaround", TURNAROUND), ("expression", "expressions", EXPRESSIONS))):
        ctx.check()
        ctx.progress(n / 2, label)
        tmp = Path(tempfile.mkdtemp(prefix="idsheet-", dir=settings.MEDIA_ROOT)) / "sheet.png"
        prompt = ", ".join(x for x in (prefix, lock.anchor, look.get("positive", "")) if x)
        neg = ", ".join(x for x in (look.get("negative", ""), service.IDENTITY_NEGATIVE, lock.avoid) if x)
        if engine == "placeholder":
            make_placeholder(tmp, 1536, 896, f"{c.name} {label}", seed=f"{c.pk}-{kind}")
            prov = {"engine": "placeholder", "note": "demo mode: placeholder, not an AI image"}
        else:
            if not compute.workflow_available(wid):
                raise ProviderError("ComfyUI در دسترس نیست (یا گردش‌کار تصویر آماده نیست).", retryable=False, code="not_ready")
            spec = get_workflow(wid)
            inputs = {"prompt": prompt, "negative_prompt": neg, "width": 1536, "height": 896, "seed": lock.seed or None, "steps": 28}
            res = compute.run_task(ctx, "comfy.graph", {"graph": spec.build(inputs), "workflow": wid, "timeout": 1800, "expected": spec.expected_seconds})
            try:
                pics = res.of_kind(*hero.IMAGE_SUFFIX)
                if not pics:
                    raise ProviderError("ComfyUI returned no image", retryable=True)
                shutil.move(str(pics[0]), tmp)
            finally:
                res.cleanup()
            prov = {**spec.provenance(inputs), "engine": "comfyui", "device": res.device}
        prev = CharacterReference.objects.filter(character=c, kind=kind, label__startswith="AI ").count() + 1
        rel = f"characters/{c.pk}/ai-{kind}-{prev}.png"
        a = asset_storage.register(tmp, rel, kind="image", role="reference", page=c.page, provenance={**prov, "purpose": "model_sheet", "prompt": prompt})
        ref = CharacterReference.objects.create(character=c, kind=kind, label=f"AI {label} {prev}", asset=a, approved=False)
        made[kind] = ref.pk
        shutil.rmtree(tmp.parent, ignore_errors=True)
    if lock.status != "locked":
        lock.refs = {**lock.refs, **{("sheet" if k == "sheet" else "expressions"): v for k, v in made.items()}}
        lock.source = lock.source if lock.source == "stick" else "image"
        lock.save(update_fields=["refs", "source", "updated_at"])
    return {"references": made}
