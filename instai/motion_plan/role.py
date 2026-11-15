"""The agent role that writes a SCENE PLAN from the narration of one shot, and the one that edits a plan from a request («make the title bigger»).

Same rules as agents/roles.py: a role is ONE validated call_json that returns a plain dict and never touches the database. The answer is NOT trusted: it goes
through specs.normalize_spec (known components only, every text limited, every colour a hex, the honesty rule applied) - and when the model is weak or
unreachable, fallback.make_plan builds the plan from the narration with no model at all, so a motion-graphics shot never waits for a model to be drawn.

A task `motion_plan` / `motion_patch` also exists for the fake provider (tests, demo mode): its answers are the deterministic ones.
"""
from __future__ import annotations

import logging

from instai.agents.runner import AgentError, call_json
from instai.providers import fake
from instai.providers.base import ProviderError

from . import fallback, promptkit, specs, timeline
from . import patch as patch_mod

log = logging.getLogger("instai.motion_plan")


def _fake_plan(meta: dict) -> dict:
    """The fake provider's answer to a `motion_plan` request: the deterministic plan (the same function the fallback uses)."""
    kit = meta.get("kit") or None
    plan = fallback.make_plan(str(meta.get("narration") or ""), float(meta.get("seconds") or 6), lang=meta.get("lang") or "fa", style=meta.get("style") or "", theme=meta.get("theme") or "",
                              size=meta.get("size") or "vertical", series=meta.get("series") or {}, platform=meta.get("platform") or "", sources=meta.get("sources"), kit=kit)
    for sc in plan["scenes"]:                         # only the components every prompt offers (the plan must pass the schema of the request)
        if sc["type"] == "steps":
            sc.update(type="list", items=[x["title"] for x in sc.pop("steps", []) if x.get("title")] or [sc.get("narration", "")[:100]], numbered=True)
    return plan


def _fake_patch(meta: dict) -> dict:
    r = patch_mod.rules_patch(str(meta.get("request") or ""), meta.get("plan") or {"scenes": [{}]}, meta.get("lang") or "fa")
    return {"say": r["say"], "ops": r["ops"]}


fake._TASKS.update({"motion_plan": _fake_plan, "motion_patch": _fake_patch})


def write_plan(narration: str, *, seconds: float, kit: dict, style: str = "", theme: str = "", size: str = "vertical", lang: str = "fa", series: dict | None = None,
               platform: str = "", sources=None, allowed_sources=None, provider=None) -> tuple[dict, dict]:
    """=> (plan, info). The plan is validated and its total is `seconds` long (the scenes are re-timed to the shot). info = {origin: 'ai'|'fallback', why?: str, model?, attempts?}.
    A provider that cannot answer (Ollama off, model missing, the answer unusable after the retries) gives the deterministic plan: never an error."""
    ids = None
    meta = {"narration": narration, "seconds": seconds, "lang": lang, "style": style, "theme": theme, "size": size, "series": series or {}, "platform": platform,
            "sources": sources, "kit": kit}
    try:
        prompt = promptkit.build_prompt(narration, kit=kit, size=size, lang=lang, seconds=seconds, series=series, platform=platform, ids=ids)
        res = call_json("motion_plan", prompt["schema"], system=prompt["system"], user=prompt["user"], meta=meta, provider=provider, max_tokens=1500, temperature=0.5)
        data = res.data
        scenes = [s for s in (data.get("scenes") or []) if isinstance(s, dict)]
        if not scenes:
            raise AgentError("motion_plan: no scenes", errors=["no scenes"])
        plan = specs.normalize_spec({"style": style, "theme": theme, "size": size, "lang": lang, "series": series or {}, "platform": platform, "scenes": scenes},
                                    max_total=specs.MAX_TOTAL_S * 2, allowed_sources=allowed_sources, kit=kit)
        plan = retime(plan, seconds, kit)
        return plan, {"origin": "ai", "model": res.model, "attempts": res.attempts}
    except (AgentError, specs.SpecError) as e:       # a weak answer: the deterministic plan (never stall on a model)
        why = f"{type(e).__name__}: {e}"
        log.info("motion plan: the model answer was not usable (%s); the deterministic plan is used", why[:200])
    except ProviderError as e:                       # Ollama off / no model / API trouble: the plan does not need one
        why = f"provider: {e}"
        log.info("motion plan: no model (%s); the deterministic plan is used", why[:200])
    plan = fallback.make_plan(narration, seconds, lang=lang, style=style, theme=theme, size=size, series=series, platform=platform, sources=sources, kit=kit,
                              allowed_sources=allowed_sources)
    return plan, {"origin": "fallback", "why": why[:300]}


def retime(plan: dict, seconds: float, kit: dict) -> dict:
    """Scale the scene durations so the plan's total (transitions overlap) equals the shot's length; word timings are estimated from the narration pieces."""
    scenes = [dict(s) for s in plan["scenes"]]
    base = {k: v for k, v in plan.items() if k not in ("scenes", "total_s", "safe")}
    secs = [max(1.0, float(s.get("duration") or 3)) for s in scenes]
    for _ in range(4):
        for s, d in zip(scenes, secs):
            s["duration"] = round(max(1.0, min(specs.MAX_SCENE_S, d)), 2)
        tot = timeline.total_seconds({**base, "scenes": scenes}, kit)
        if abs(tot - seconds) < 0.06:
            break
        secs = [d * seconds / max(0.1, tot) for d in secs]
    tl = timeline.compute({**base, "scenes": scenes}, kit=kit)
    spoken, words_total = 0.0, sum(max(1, len((s.get("narration") or "").split())) for s in scenes)
    for s, st, fr in zip(scenes, tl["starts"], tl["frames"]):
        nar = s.get("narration") or ""
        span = seconds * max(1, len(nar.split())) / max(1, words_total)
        if nar and not s.get("cues"):
            s["cues"] = fallback.estimate_cues(nar, min(span, fr / tl["fps"]), start=max(0.05, spoken - st / tl["fps"] + 0.05))
        spoken += span
    return specs.normalize_spec({**base, "scenes": scenes}, max_total=max(seconds + 2, specs.MAX_TOTAL_S), kit=kit)


def write_patch(plan: dict, request: str, *, lang: str = "fa", provider=None) -> dict:
    """A request («make the title bigger») => {"ops": [...], "say": "...", "by": "model"|"rules"}. The rules of patch.rules_patch answer without a model; a model is
    asked only when they do not understand and a provider is reachable. Every op is checked by patch.apply_patch later (nothing is trusted)."""
    r = patch_mod.rules_patch(request, plan, lang)
    if r["ops"]:
        return {**r, "by": "rules"}
    try:
        prompt = promptkit.build_patch_prompt(plan, request)
        res = call_json("motion_patch", prompt["schema"], system=prompt["system"], user=prompt["user"], meta={"request": request, "plan": plan, "lang": lang},
                        provider=provider, max_tokens=700, temperature=0.2)
        ops = [o for o in (res.data.get("ops") or []) if isinstance(o, dict)][: patch_mod.MAX_OPS]
        if ops:
            return {"ops": ops, "say": str(res.data.get("say") or "")[:240], "say_fa": "", "say_en": "", "by": "model"}
    except (AgentError, ProviderError) as e:
        log.info("motion patch: no model answer (%s)", str(e)[:200])
    return {**r, "by": "rules"}
