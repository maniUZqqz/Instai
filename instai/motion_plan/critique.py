"""The visual critique: 3 to 6 key frames + the plan => the owner's VISION model (Ollama, on the GPU) => problems + a patch => applied => fresh frames, at most 3 rounds.

SOURCE: ported from NMarketing:backend/apps/motion/critique.py @ motion v2, adapted for InstAI: the model is InstAI's own Ollama provider with the vision model the owner
installed (qwen3-vl ...); there is NO cloud fallback in InstAI - when Ollama is off the job WAITS (wait code `ollama_down`, nothing fails) and runs by itself when Ollama is
back; when Ollama is on but has no vision model the critique says so (state `unavailable`) and the rule checks of qa.py (always run) are all there is.

The result (the rounds with the frames before / after) stays on MotionPlan.critique and the page shows it; every patch is one reversible version of the plan (plans.py).
"""
from __future__ import annotations

import base64
import io
import json
import logging

from django.utils import timezone

from instai.agents.runner import extract_json
from instai.agents.jsonschema_lite import repair, validate
from instai.providers import fake, registry
from instai.providers.base import ProviderError

from . import patch as patch_mod
from . import plans, promptkit, qa, timeline
from .models import MotionPlan

log = logging.getLogger("instai.motion_plan")

MAX_ROUNDS = 3
MAX_FRAMES = 6

SYSTEM = """You are a strict art director reviewing frames of a motion-graphics video made from a SCENE PLAN (JSON). Each image is one frame; the list below tells which scene
(0-based index) each image shows, in order. Look for REAL visual problems only: text clipped or overflowing, two texts overlapping, low contrast, text too small to read on a phone,
unbalanced or empty layout, too many things at once, colours that clash with the style. If everything is fine answer verdict "ok" with no ops.
Reply with ONE JSON object {"verdict":"ok"|"fix","issues":[{"scene":int,"problem":"<one short sentence>","severity":"low"|"medium"|"high"}],"ops":[...]}.
Fix ONLY the scenes that have issues with a JSON PATCH (a few ops at most, never rewrite the whole plan, never invent facts). The patch language:
""" + promptkit.PATCH_GUIDE.split("Ops:", 1)[1].split("Reply with", 1)[0].strip()


def schema() -> dict:
    ops = promptkit.patch_schema()["properties"]["ops"]
    return {"type": "object", "properties": {
        "verdict": {"type": "string", "enum": ["ok", "fix"]},
        "issues": {"type": "array", "maxItems": 12, "items": {"type": "object", "properties": {
            "scene": {"type": "integer"}, "problem": {"type": "string"}, "severity": {"type": "string", "enum": ["low", "medium", "high"]}}, "required": ["scene", "problem"]}},
        "ops": ops}, "required": ["verdict"]}


def _fake_critique(meta: dict) -> dict:
    """The fake provider (tests, demo): the answer the test asks for in meta['critique'] (default: all fine)."""
    return dict(meta.get("critique") or {"verdict": "ok", "issues": [], "ops": []})


fake._TASKS["motion_critique"] = _fake_critique


# ───────────────────────────────────────────── the vision model

def vision_model(url: str) -> str:
    from instai.identity.check import _vision_model

    return _vision_model(url)


def vision_provider():
    """The provider that answers with pictures: a forced provider (tests), else InstAI's Ollama with the owner's vision model.
    Ollama off => ProviderError(ollama_down) (the job waits); Ollama on but no vision model => ProviderError(code=no_vision_model, not a wait)."""
    forced = registry._OVERRIDE
    if forced is not None:
        return forced
    from instai.core import settings_store
    from instai.providers.ollama import OllamaProvider

    url = str(settings_store.effective("ollama_url"))
    probe = OllamaProvider(url, "x")
    h = probe.health()
    if not h.get("ok"):
        raise ProviderError(f"Ollama is not reachable at {url}", code="ollama_down", fa=f"InstAI به Ollama وصل نشد ({url}). مطمئن شوید برنامهٔ Ollama روشن است.")
    model = vision_model(url)
    if not model:
        raise ProviderError("no vision model is installed in Ollama", retryable=False, code="no_vision_model",
                            fa="در Ollama مدل بینایی (مثلاً qwen3-vl) نصب نیست؛ از صفحهٔ «مدل‌ها» نصبش کنید. بازبینی با قاعده‌ها همیشه کار می‌کند.")
    return OllamaProvider(url, model)


def pick_frames(spec: dict, limit: int = MAX_FRAMES, kit: dict | None = None) -> list:
    """3 to 6 scenes: the first, the last and the ones with the most to read; the «late» frame (the end of the entrance) of each."""
    n = len(spec["scenes"])
    order = sorted(range(n), key=lambda i: -qa._scene_words(spec["scenes"][i]))
    chosen = {0, n - 1}
    for i in order:
        if len(chosen) >= min(limit, n):
            break
        chosen.add(i)
    keys = qa.key_frames(spec, per_scene=2, kit=kit)
    return [k for k in keys if k["scene"] in chosen and k["kind"] == "late"]


def _b64(shot) -> str:
    im = shot.get("_image")
    if im is None:
        raise ValueError("the picture of the frame is not available")
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=84)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def ask(prov, spec: dict, shots: list) -> dict:
    """One question to the vision model with the pictures. => {verdict, issues[], ops[]}. A broken answer is one round with verdict ok (nothing applied)."""
    listing = ", ".join(f"image {k + 1} = scene {s['scene']}" for k, s in enumerate(shots))
    user = f"Images: {listing}.\nPLAN:\n{promptkit.compact_plan(spec)}\nStyle: {spec.get('style') or 'default'}; size {spec.get('size')}; platform {spec.get('platform') or 'none'}."
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user, "images": [_b64(s) for s in shots]}]
    sch = schema()
    res = prov.generate(messages, schema=sch, temperature=0.2, max_tokens=1100, task="motion_critique", meta={"critique": getattr(prov, "scripted", None), "plan": spec})
    try:
        data = extract_json(res.text)
    except ValueError:
        return {"verdict": "ok", "issues": [], "ops": [], "note": "the answer was not JSON"}
    if not isinstance(data, dict):
        return {"verdict": "ok", "issues": [], "ops": [], "note": "the answer was not an object"}
    data = repair(data, sch)
    if validate({"verdict": data.get("verdict", "ok")}, {"type": "object", "properties": {"verdict": sch["properties"]["verdict"]}}):
        data["verdict"] = "ok"
    issues = [{"scene": int(i.get("scene", 0)), "problem": str(i.get("problem", ""))[:240], "severity": i.get("severity") if i.get("severity") in ("low", "medium", "high") else "medium"}
              for i in (data.get("issues") or []) if isinstance(i, dict)][:12]
    ops = data.get("ops") if isinstance(data.get("ops"), list) else []
    return {"verdict": "fix" if (data.get("verdict") == "fix" and ops) else "ok", "issues": issues, "ops": ops[: patch_mod.MAX_OPS]}


def apply_valid(spec: dict, ops: list, *, allowed_sources=None, kit=None) -> tuple:
    """Every op is tried alone; the valid ones are applied in order. => (new spec, ops applied, ops rejected)."""
    cur, ok, bad = spec, [], []
    for op in ops:
        try:
            cur = patch_mod.apply_patch(cur, [op], allowed_sources=allowed_sources, kit=kit)
            ok.append(op)
        except patch_mod.PatchError as exc:
            bad.append({"op": op, "why": str(exc), "why_en": exc.en})
    return cur, ok, bad


def _meta(shots: list) -> list:
    return [{"scene": s["scene"], "frame": s["frame"], "image_rel": s.get("image_rel", "")} for s in shots]


# ───────────────────────────────────────────── the run

def _save(plan: MotionPlan, state: dict) -> None:
    MotionPlan.objects.filter(pk=plan.pk).update(critique=json.loads(json.dumps(state, default=str)), updated_at=timezone.now())
    plan.critique = state


def _finish(plan, state, name: str, fa: str, en: str) -> dict:
    state.update(state=name, message=fa, message_en=en, finished_at=timezone.now().isoformat())
    _save(plan, state)
    return state


def run(plan: MotionPlan, *, measure, provider=None, kit: dict | None = None, max_rounds: int = MAX_ROUNDS, allowed_sources=None) -> dict:
    """One complete critique of a plan; writes the state into plan.critique and returns it. `measure(spec)` gives the frames (qa_browser.make_measure).
    A ProviderError from the provider (Ollama off) is NOT caught: the job waits and the whole run starts again when Ollama is back."""
    kit = kit or timeline.kit_of(plan.spec)
    state = {"state": "running", "message": "نقد تصویری در حال اجراست…", "message_en": "The visual critique is running...", "rounds": [], "started_at": timezone.now().isoformat()}
    _save(plan, state)
    try:
        prov = provider if provider is not None else vision_provider()
    except ProviderError as e:
        if e.code == "no_vision_model":
            return _finish(plan, state, "unavailable", e.fa or "مدل بینایی نصب نیست.", "No vision model is installed in Ollama (install qwen3-vl from the Models page); the rule checks still run.")
        raise
    rounds: list = []
    spec = plan.spec
    shots = measure(spec)
    for n in range(1, max_rounds + 1):
        res = ask(prov, spec, shots)
        rec = {"n": n, "verdict": res["verdict"], "issues": res["issues"], "ops": res["ops"], "applied": [], "rejected": [], "before": _meta(shots), "after": []}
        if res["verdict"] == "ok":
            rounds.append(rec)
            state["rounds"] = rounds
            return _finish(plan, state, "done", "مدل بینایی مشکلی ندید." if not res["issues"] else "مدل بینایی فقط ایرادهای جزئی دید.",
                           "The vision model saw no problem." if not res["issues"] else "The vision model saw only minor issues.")
        new, applied, rejected = apply_valid(spec, res["ops"], allowed_sources=allowed_sources, kit=kit)
        rec["applied"], rec["rejected"] = applied, rejected
        if not applied or new == spec:
            rounds.append(rec)
            state["rounds"] = rounds
            return _finish(plan, state, "done", "ایرادها گزارش شد ولی تغییر قابل‌اعمالی پیشنهاد نشد.", "Issues were reported but no applicable change was proposed.")
        label = f"critique round {n}: " + patch_mod.diff_text(patch_mod.diff_summary(spec, new), "en")[:110]
        plan = plans.commit(plan, new, label=label, source="critique", ops=applied)
        spec = plan.spec
        shots = measure(spec)
        rec["after"] = _meta(shots)
        rounds.append(rec)
        state["rounds"] = rounds
        _save(plan, state)
    return _finish(plan, state, "done", f"{max_rounds} دور نقد انجام شد.", f"{max_rounds} critique rounds were done.")
