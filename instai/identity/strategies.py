"""The consistency strategies, in order of strength, and which of them can run on this machine right now.

A strategy is HOW a picture of a locked character is made so the character stays identical. The order of `auto` is: the character is drawn by
code (perfect by construction), then reference-conditioned editing with the approved sheets (the Apache-licensed counterpart of IP-Adapter /
PuLID-style conditioning: the model SEES the sheet), then a trained LoRA, then the cheapest universal one - identity words + palette + a
fixed identity seed. Face-ID adapters (IP-Adapter FaceID, PuLID, InstantID) are NOT used: they need InsightFace weights that are
non-commercial and they only understand real faces, not cartoon, anime or stick characters.
"""
from __future__ import annotations

from instai.gpu import compute

ORDER = ["stick_rig", "multiref_edit", "sheet_edit", "lora", "anchor_seed"]

CATALOGUE: dict[str, dict] = {
    "stick_rig": {
        "title_fa": "ترسیم با کد (آدمک چوبی)", "title_en": "Drawn by code (stick figure)",
        "how_fa": "شخصیت از روی مشخصاتش (رنگ، کلاه، شال...) کشیده می‌شود؛ پس در هر ژست، صحنه و ویدئو دقیقاً همان است. بدون کارت گرافیک.",
        "how_en": "The character is drawn from its spec (colours, cap, scarf...), so it is the same in every pose, scene and video. No graphics card.",
        "gpu": False, "licence": "own code", "workflows": [],
    },
    "multiref_edit": {
        "title_fa": "ویرایش با چند تصویر مرجع (Qwen-Image-Edit)", "title_en": "Multi-reference edit (Qwen-Image-Edit)",
        "how_fa": "برگهٔ مدل تأییدشدهٔ هر شخصیت (تا سه نفر) به مدل داده می‌شود و تصویر تازه روی همان‌ها ساخته می‌شود. معادلِ بازِ IP-Adapter/PuLID.",
        "how_en": "Each character's approved model sheet (up to three) is shown to the model, which draws the new picture from them. The open counterpart of IP-Adapter/PuLID.",
        "gpu": True, "licence": "Apache-2.0", "workflows": ["qwen_image_edit_multiref"],
    },
    "sheet_edit": {
        "title_fa": "ویرایش از روی برگهٔ مدل", "title_en": "Edit from the model sheet",
        "how_fa": "تصویر جدید از روی برگهٔ مدل یک شخصیت ساخته می‌شود (Qwen-Image-Edit یا FLUX img2img).",
        "how_en": "The new picture is made from one character's model sheet (Qwen-Image-Edit or FLUX img2img).",
        "gpu": True, "licence": "Apache-2.0 / FLUX [dev] non-commercial (see docs/MODELS.md)", "workflows": ["qwen_image_edit_ref", "flux_dev_fp8_img2img"],
    },
    "lora": {
        "title_fa": "LoRAِ آموزش‌دیدهٔ شخصیت", "title_en": "Trained character LoRA",
        "how_fa": "یک LoRA روی تصویرهای مرجع آموزش داده می‌شود و بعد از تأیید شما در هر تصویر به کار می‌رود.",
        "how_en": "A LoRA trained on the reference pictures, used in every picture once you approve it.",
        "gpu": True, "licence": "FLUX [dev] non-commercial (see docs/MODELS.md)", "workflows": ["flux_dev_fp8_t2i_lora"],
    },
    "anchor_seed": {
        "title_fa": "کلمات هویت + رنگ‌های ثابت + دانهٔ ثابت", "title_en": "Identity words + fixed colours + fixed seed",
        "how_fa": "ساده‌ترین راه: توصیف ثابتِ شخصیت و رنگ‌هایش در هر درخواست می‌آید و دانهٔ تصادفی ثابت است. کمک می‌کند، اما قول نمی‌دهد.",
        "how_en": "The simplest route: the same description and colours go into every request, with a fixed random seed. It helps but does not guarantee.",
        "gpu": True, "licence": "n/a", "workflows": [],
    },
}
NOT_USED = [
    {"key": "ipadapter_faceid", "title_en": "IP-Adapter FaceID / InstantID", "title_fa": "IP-Adapter FaceID / InstantID",
     "reason_en": "Needs InsightFace face weights (non-commercial licence) and only understands real faces.",
     "reason_fa": "به وزن‌های InsightFace نیاز دارد (مجوز غیرتجاری) و فقط چهرهٔ واقعی را می‌شناسد."},
    {"key": "pulid", "title_en": "PuLID", "title_fa": "PuLID",
     "reason_en": "Same InsightFace dependency; designed for photographic faces. The multi-reference edit gives the same 'the model sees the reference' effect under Apache-2.0.",
     "reason_fa": "همان وابستگی به InsightFace و مخصوص چهرهٔ عکاسی است. ویرایش چندمرجعی همان اثر را با مجوز Apache می‌دهد."},
]


def _workflow_ok(ids: list[str]) -> bool:
    try:
        return any(compute.workflow_available(w) for w in ids)
    except Exception:  # noqa: BLE001 - detection must never break a screen
        return False


def availability(*, has_stick: bool, has_refs: bool, has_lora: bool) -> list[dict]:
    """Every strategy with `available` and the reason when not (reasons are codes the UI translates)."""
    out = []
    for key in ORDER:
        c = CATALOGUE[key]
        reason = ""
        if key == "stick_rig":
            ok, reason = has_stick, "" if has_stick else "no_stick_spec"
        elif key == "multiref_edit":
            ok = has_refs and _workflow_ok(c["workflows"])
            reason = "" if ok else ("no_approved_sheet" if not has_refs else "workflow_missing")
        elif key == "sheet_edit":
            ok = has_refs and _workflow_ok(c["workflows"])
            reason = "" if ok else ("no_approved_sheet" if not has_refs else "workflow_missing")
        elif key == "lora":
            ok = has_lora and _workflow_ok(c["workflows"])
            reason = "" if ok else ("no_approved_lora" if not has_lora else "workflow_missing")
        else:
            ok = True
        out.append({"key": key, "available": bool(ok), "reason": reason, **{k: c[k] for k in ("title_fa", "title_en", "how_fa", "how_en", "gpu", "licence")}})
    return out


def pick(preferred: str, avail: list[dict]) -> tuple[str, str]:
    """(strategy key, note code): the preferred one when available, else the strongest available one."""
    by = {a["key"]: a for a in avail}
    if preferred and preferred != "auto" and by.get(preferred, {}).get("available"):
        return preferred, "as_chosen"
    for key in ORDER:
        if by[key]["available"]:
            return key, ("fallback" if preferred not in ("", "auto") else "auto")
    return "anchor_seed", "auto"
