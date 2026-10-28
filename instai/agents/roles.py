"""Logical agent roles (strategist, story architect, scriptwriter, researcher, storyboarder, continuity manager).

These are roles, not separate models: each is one validated call_json with its own prompt, schema and guard rails.
They return plain dicts and never touch the database; story/services.py persists the results.
"""
from __future__ import annotations

import json
from typing import Any

from . import schemas
from .runner import AgentResult, call_json
from .storyboard_builder import CHEAPEST_FIRST, shots_from_script, words

LANG_NAME = {"fa": "Persian (Farsi, natural spoken style)", "en": "English"}

FORMAT_GUIDE = {
    "anime_whatif": ("Format: Anime 'What-If'. Retell a story as if one key event had gone differently (another decision, a swapped role, "
                     "a different battle outcome, an event that never happened). Always define premise, branch point, alternative timeline, "
                     "episode goals and cliffhangers. Prefer ORIGINAL characters and 'inspired-by' worlds; never copy franchise names, "
                     "characters or artwork unless the series is explicitly marked as fan content."),
    "recurring_character": ("Format: recurring 2D cartoon character in many scenarios (everyday comedy, activities, recurring jokes, short "
                            "stories). Keep personality, catchphrases and look consistent across episodes."),
    "concept_explainer": ("Format: concept explainer. Explain hard ideas in simple words with analogies and visual metaphors. Be neutral and "
                          "sourced: separate established facts from contested views and speculation, label contested claims, no propaganda, "
                          "no invented sources or statistics."),
    "custom": "Format: custom content page. Follow the owner's idea closely.",
}


def _lang(meta: dict) -> str:
    return LANG_NAME.get((meta.get("language") or "fa")[:2], meta.get("language") or "Persian")


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _base_system(role: str, meta: dict) -> str:
    return (f"You are the {role} of a content studio that produces short vertical animated videos for a social-media page.\n"
            f"{FORMAT_GUIDE.get(meta.get('format') or 'custom', '')}\n"
            f"Write every user-facing text in {_lang(meta)}. Keep JSON keys in English exactly as the schema says.")


# ------------------------------------------------------------------ strategist

def strategist(meta: dict, provider=None) -> AgentResult:
    system = _base_system("strategist", meta) + ("\nTurn the owner's idea into a content strategy: positioning, audience insight, tone, "
                                                 "content pillars, 1-4 series ideas (with branch point for What-If), a realistic posting plan, "
                                                 "hashtags, risks, and (for story formats) 1-4 original characters.")
    user = "Page and idea:\n" + _j({k: meta.get(k) for k in ("page_name", "format", "language", "idea", "niche", "audience", "tone",
                                                            "episodes_count", "episode_length_sec") if meta.get(k) not in (None, "")})
    return call_json("strategy", schemas.STRATEGY, system=system, user=user, meta=meta, provider=provider, max_tokens=3000)


# ------------------------------------------------------------------ story architect

def story_architect(meta: dict, provider=None) -> AgentResult:
    n = int(meta.get("episodes_count") or 5)
    system = _base_system("story architect", meta) + (
        f"\nDesign a series plan with exactly {n} episodes numbered 1..{n}, grouped into arcs (field 'arc' = 1-based arc number). "
        "Each episode needs a title, logline, goal and (except the last) a cliffhanger that leads into the next one. Respect the content "
        "rules and the continuity memory; never contradict established facts.")
    user = "Series context:\n" + _j({k: meta.get(k) for k in ("title", "premise", "branch_point", "alternative_timeline", "characters",
                                                              "content_rules", "episode_length_sec", "idea", "memory", "is_fan_content", "bible")
                                    if meta.get(k) not in (None, "", [])})

    def semantic(d: dict) -> list[str]:
        nums = sorted(e["number"] for e in d["episodes"])
        errs = []
        if nums != list(range(1, len(nums) + 1)):
            errs.append("episode numbers must be consecutive starting at 1")
        arcs = len(d["arcs"])
        errs += [f"episode {e['number']}: arc {e['arc']} does not exist" for e in d["episodes"] if e.get("arc", 1) > arcs]
        if len(d["episodes"]) != n:
            errs.append(f"expected {n} episodes, got {len(d['episodes'])}")
        return errs

    def transform(d: dict) -> dict:
        for e in d.get("episodes", []):
            e.setdefault("arc", 1)
            e.setdefault("duration_sec", int(meta.get("episode_length_sec") or 45))
        return d

    return call_json("series_plan", schemas.SERIES_PLAN, system=system, user=user, meta=meta, provider=provider, max_tokens=5000,
                     semantic=semantic, transform=transform)


# ------------------------------------------------------------------ scriptwriter

def reading_stats(script: dict, language: str, target_sec: int) -> dict:
    wps = 2.4 if language.startswith("fa") else 2.6
    text = " ".join([b.get("text", "") for b in script.get("blocks", [])] + [script.get("cta", "") or ""])
    n = words(text)
    est = round(n / wps, 1)
    warnings = []
    if script.get("hook") in (None, ""):
        warnings.append("missing_hook")
    if not script.get("cta"):
        warnings.append("missing_cta")
    if target_sec and est > target_sec * 1.25:
        warnings.append("too_long")
    if target_sec and est < target_sec * 0.6:
        warnings.append("too_short")
    if n / max(est, 1) > 3.2:
        warnings.append("reading_too_fast")
    return {"word_count": n, "est_duration_sec": est, "target_sec": target_sec, "wps": wps, "warnings": warnings, "ok": not warnings}


def scriptwriter(meta: dict, provider=None) -> AgentResult:
    target = int(meta.get("duration_sec") or 45)
    lang = (meta.get("language") or "fa")
    wps = 2.4 if lang.startswith("fa") else 2.6
    system = _base_system("scriptwriter", meta) + (
        f"\nWrite ONE episode script of about {target} seconds of narration (about {int(target * wps)} words total at {wps} words/second). "
        "Start with a strong hook in the first block, keep sentences short and speakable, end with the episode's cliffhanger/CTA. "
        "'blocks' are consecutive spoken lines; 'speaker' is a character name or the narrator. Stay consistent with the continuity memory "
        "and the content rules. For explainers use only the given research claims; label contested ones; do not invent facts or sources.")
    user = "Episode context:\n" + _j({k: meta.get(k) for k in ("series_title", "premise", "branch_point", "alternative_timeline", "episode",
                                                               "characters", "content_rules", "memory", "claims", "duration_sec",
                                                               "previous_summaries", "bible") if meta.get(k) not in (None, "", [])})

    def semantic(d: dict) -> list[str]:
        st = reading_stats(d, lang, target)
        errs = []
        if st["est_duration_sec"] > target * 1.6:
            errs.append(f"script is far too long ({st['word_count']} words, about {st['est_duration_sec']} s; target {target} s)")
        if st["est_duration_sec"] < target * 0.4:
            errs.append(f"script is far too short ({st['word_count']} words; target about {int(target * wps)})")
        return errs

    res = call_json("script", schemas.SCRIPT, system=system, user=user, meta=meta, provider=provider, max_tokens=4000, semantic=semantic)
    res.data.setdefault("language", lang[:2])
    for i, b in enumerate(res.data["blocks"], 1):
        b["id"] = i
    return res


# ------------------------------------------------------------------ researcher (two small steps; sources come from a fetcher)

def researcher_queries(meta: dict, provider=None) -> AgentResult:
    system = _base_system("researcher", meta) + "\nList up to 6 short search queries (encyclopedia style) to ground an explainer episode, and the key points it must cover."
    user = "Topic context:\n" + _j({k: meta.get(k) for k in ("topic", "series_title", "premise", "episode") if meta.get(k)})
    return call_json("research_queries", schemas.RESEARCH_QUERIES, system=system, user=user, meta=meta, provider=provider, max_tokens=800)


def researcher_claims(meta: dict, provider=None) -> AgentResult:
    system = _base_system("researcher and fact-checker", meta) + (
        "\nFrom ONLY the numbered source extracts given, write the claims the episode may state. Mark each claim 'established' (clearly "
        "supported), 'contested' (sources disagree or it is a debated interpretation) or 'speculative'. List the supporting source ids. "
        "A claim without any source id must not be 'established'. Also give simple analogies and visual metaphors.")
    user = "Sources:\n" + _j(meta.get("sources") or []) + "\nTopic: " + str(meta.get("topic") or "")

    def transform(d: dict) -> dict:
        valid = {s["id"] for s in meta.get("sources") or []}
        for c in d.get("claims", []):
            c["source_ids"] = [i for i in c.get("source_ids", []) if i in valid]
            if not c["source_ids"] and c.get("stance") == "established":
                c["stance"] = "speculative"
        return d

    return call_json("research_claims", schemas.RESEARCH_CLAIMS, system=system, user=user, meta=meta, provider=provider, max_tokens=3000,
                     transform=transform)


# ------------------------------------------------------------------ storyboarder

def _norm(s: str) -> list[str]:
    return [w for w in (s or "").replace("،", " ").replace(".", " ").split() if w]


def coverage(script: dict, storyboard: dict) -> float:
    spoken = _norm(" ".join(b.get("text", "") for b in script.get("blocks", [])))
    if not spoken:
        return 1.0
    sb = _norm(" ".join(sh.get("narration", "") for sc in storyboard.get("scenes", []) for sh in sc.get("shots", [])))
    pool: dict[str, int] = {}
    for w in sb:
        pool[w] = pool.get(w, 0) + 1
    hit = 0
    for w in spoken:
        if pool.get(w, 0) > 0:
            pool[w] -= 1
            hit += 1
    return hit / len(spoken)


def normalize_storyboard(sb: dict, allowed: list[str]) -> dict:
    """Guard rails: techniques outside the page's allowed list are replaced by the cheapest allowed one; durations clamped."""
    fallback = next((t for t in CHEAPEST_FIRST if t in allowed), "still_kenburns") if allowed else None
    for sc in sb.get("scenes", []):
        sc.setdefault("characters", [])
        for sh in sc.get("shots", []):
            if allowed and sh.get("technique") not in allowed:
                sh["technique"] = fallback
            sh["duration_sec"] = max(1.0, min(20.0, float(sh.get("duration_sec") or 4)))
            sh.setdefault("camera", {"move": "zoom_in", "intensity": 0.5})
            if "move" not in sh["camera"]:
                sh["camera"]["move"] = "zoom_in"
            sh.setdefault("narration", "")
            sh.setdefault("speaker", "")
    return sb


def storyboarder(meta: dict, provider=None) -> tuple[AgentResult, dict]:
    """Returns (agent result, info). If the model's storyboard does not cover the script after retries, a deterministic
    storyboard is built from the script instead (info['fallback'] = True) so the pipeline never stalls on a weak model."""
    script = meta.get("script") or {}
    allowed = meta.get("allowed_techniques") or []
    system = _base_system("storyboarder", meta) + (
        "\nTurn the approved script into scenes and shots. Every spoken word of the script must appear in some shot's 'narration', in order. "
        "For each shot choose the CHEAPEST technique that looks right: still_kenburns (image + camera move), parallax_25d, puppet_2d "
        "(recurring character / cartoon presenter), motion_graphics (diagrams for explainers), wan_i2v (only for a few hero moments), "
        "wan_flf (transitions), talking_video, three_d. Shots are 2-8 seconds; image_prompt describes ONE vertical 9:16 frame, "
        "in English, consistent with the visual style and the character appearance.")
    if allowed:
        system += f"\nAllowed techniques for this page: {allowed}."
    user = "Storyboard input:\n" + _j({k: meta.get(k) for k in ("script", "characters", "visual_style", "format", "duration_sec") if meta.get(k)})

    def semantic(d: dict) -> list[str]:
        cov = coverage(script, d)
        return [f"the shots' narration covers only {int(cov * 100)}% of the script; every script line must be spoken in some shot"] if cov < 0.85 else []

    info = {"fallback": False}
    try:
        res = call_json("storyboard", schemas.STORYBOARD, system=system, user=user, meta=meta, provider=provider, max_tokens=6000,
                        semantic=semantic, transform=lambda d: normalize_storyboard(d, allowed))
    except Exception as e:  # noqa: BLE001 - only AgentError means "weak output"; provider errors must propagate
        from .runner import AgentError

        if not isinstance(e, AgentError):
            raise
        data = shots_from_script(script, fmt=meta.get("format") or "custom", language=meta.get("language") or "fa", allowed=allowed,
                                 style=meta.get("visual_style") or "", characters=meta.get("characters") or [])
        res = AgentResult(data=normalize_storyboard(data, allowed), attempts=0, notes=["fallback: deterministic storyboard from the script"])
        info["fallback"] = True
        info["errors"] = e.errors
    return res, info


# ------------------------------------------------------------------ continuity manager

def continuity_manager(meta: dict, provider=None) -> AgentResult:
    system = _base_system("continuity manager", meta) + (
        "\nRead the finished episode script and the current story memory. Extract ONLY what the episode newly established: a one-paragraph "
        "episode summary, new facts, changed character states, relationship changes, timeline events, open threads (new, or "
        "status 'resolved' for threads this episode closes) and future goals. Do not repeat facts already in memory.")
    user = "Input:\n" + _j({k: meta.get(k) for k in ("episode", "script", "memory", "characters") if meta.get(k)})
    return call_json("continuity", schemas.CONTINUITY, system=system, user=user, meta=meta, provider=provider, max_tokens=2500)
