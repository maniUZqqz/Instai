"""Agent roles of the studio pipeline: development (brainstorm, canon research, consequence map, timeline, character and series bibles)
and pre-production (design sheets, voice casting, translation). Same rules as agents/roles.py: a role is one validated call_json,
returns plain dicts and never touches the database; instai/studio/services.py persists the results.
"""
from __future__ import annotations

from typing import Any

from . import studio_fake  # noqa: F401 - registers the fake-provider outputs of these tasks
from . import studio_schemas as S
from .roles import FORMAT_GUIDE, _base_system, _j
from .runner import AgentResult, call_json

LENS_GUIDE = {
    "divergence": ("Propose DIVERGENCE POINTS for a What-If retelling of the source story: ONE specific canon moment (a decision, a battle outcome, a role "
                   "swap, an event that never happens) that goes differently. Use only moments that exist in the canon research. "
                   "details = {divergence_moment, canon_outcome, changed_outcome, ripple_preview}."),
    "series_concept": ("Propose distinct SERIES CONCEPTS for this page: a premise a viewer understands in one sentence plus the engine that makes many "
                       "episodes possible. details = {hook, audience, story_engine}."),
    "scenario": ("Propose EPISODE SCENARIOS for the recurring character: a situation with a setup, a complication and a payoff, each different from "
                 "the others. details = {setup, complication, payoff}."),
    "gag_format": ("Propose RUNNING GAGS, catchphrases and recurring SEGMENTS that can repeat across episodes without getting stale. "
                   "details = {gag, trigger, variation}."),
    "topic": ("Propose TOPICS to explain simply: concepts people find intimidating. details = {why_it_is_hard, hook_question, common_misconception}."),
    "analogy": ("Propose ANALOGIES and VISUAL METAPHORS that explain the concept simply. details = {analogy, visual_metaphor, where_it_breaks_down}."),
    "character_concept": ("Propose CHARACTER CONCEPTS: look, personality, a flaw and a want. details = {look, flaw, want}."),
}


def _look_line(meta: dict) -> str:
    look = meta.get("look") or {}
    if not look:
        return ""
    return ("\nVisual look of the page (keep ideas producible in it): " + ", ".join(f"{k}={v}" for k, v in look.items() if v))


def _system(role: str, meta: dict, extra: str) -> str:
    return _base_system(role, meta) + _look_line(meta) + "\n" + extra


# ------------------------------------------------------------------ brainstorm

def brainstormer(meta: dict, provider=None) -> AgentResult:
    lens = meta.get("lens") if meta.get("lens") in LENS_GUIDE else "series_concept"
    n = max(1, min(12, int(meta.get("count") or 6)))
    extra = (f"\nYou are in a development room. {LENS_GUIDE[lens]}\nReturn exactly {n} ideas. Each idea has a short title, a one-sentence logline and "
             "'why_it_works' (one sentence a producer would accept). Ideas must differ from each other and from every idea listed under "
             "'existing_ideas' or 'rejected'. If 'liked_ideas' are given, generate more in their spirit (not copies). Obey the user's "
             "'instruction' if present.")
    if meta.get("is_fan_content"):
        extra += " The series is fan content about an existing franchise: stay faithful to the canon research and never invent canon facts."
    else:
        extra += " Prefer ORIGINAL characters and worlds ('inspired by' at most); never copy franchise names, characters or artwork."
    user = "Context:\n" + _j({k: meta.get(k) for k in ("page_name", "idea", "audience", "tone", "title", "premise", "source", "canon", "approved_ideas",
                                                       "existing_ideas", "liked_ideas", "rejected", "instruction", "characters", "content_rules")
                             if meta.get(k) not in (None, "", [], {})})

    def semantic(d: dict) -> list[str]:
        titles = [i["title"].strip().lower() for i in d["ideas"]]
        return ["ideas must have different titles"] if len(set(titles)) < len(titles) else []

    def transform(d: dict) -> dict:
        d["ideas"] = d.get("ideas", [])[:n]
        for i in d["ideas"]:
            i["details"] = {str(k): str(v) for k, v in (i.get("details") or {}).items() if v not in (None, "")}
        return d

    return call_json("ideas", S.IDEAS, system=_system("brainstorm facilitator and story editor", meta, extra), user=user, meta={**meta, "lens": lens, "count": n},
                     provider=provider, max_tokens=3500, semantic=semantic, transform=transform)


def idea_editor(meta: dict, provider=None) -> AgentResult:
    extra = ("\nRewrite ONE idea card following the user's instruction. Keep what the instruction does not touch. Keep the same 'details' keys. "
             "Return the full revised card.")
    user = "Card:\n" + _j(meta.get("idea")) + "\nInstruction: " + str(meta.get("instruction") or "improve it") + "\nContext:\n" + _j(
        {k: meta.get(k) for k in ("title", "premise", "canon", "lens") if meta.get(k)})
    return call_json("idea_refine", S.IDEA, system=_system("story editor", meta, extra), user=user, meta=meta, provider=provider, max_tokens=1500)


def idea_merger(meta: dict, provider=None) -> AgentResult:
    extra = ("\nMerge the given idea cards into ONE stronger card that keeps the best parts of each and has no contradictions. "
             "Keep the same 'details' keys as the cards. Return the merged card.")
    user = "Cards to merge:\n" + _j(meta.get("ideas")) + "\nInstruction: " + str(meta.get("instruction") or "") + "\nContext:\n" + _j(
        {k: meta.get(k) for k in ("title", "premise", "canon", "lens") if meta.get(k)})
    return call_json("idea_merge", S.IDEA, system=_system("story editor", meta, extra), user=user, meta=meta, provider=provider, max_tokens=1500)


# ------------------------------------------------------------------ research

def canon_researcher(meta: dict, provider=None) -> AgentResult:
    extra = ("\nYou prepare CANON RESEARCH about an existing series for the writers. Use ONLY the numbered source extracts given; do not add anything "
             "from memory. Every character, arc, event and world rule must list the 'source_ids' that support it. If the extracts are thin, say "
             "so under 'caveats' instead of inventing. The notes are internal research: paraphrase, never copy long passages.")
    user = "Series: " + str((meta.get("source") or {}).get("title") or meta.get("title") or "") + "\nSources:\n" + _j(meta.get("sources") or [])

    def transform(d: dict) -> dict:
        valid = {s["id"] for s in meta.get("sources") or []}
        for group in ("characters", "arcs", "key_events", "world_rules"):
            for item in d.get(group, []):
                item["source_ids"] = [i for i in item.get("source_ids", []) if i in valid]
        return d

    return call_json("canon", S.CANON, system=_system("canon researcher", meta, extra), user=user, meta=meta, provider=provider, max_tokens=5000,
                     transform=transform)


# ------------------------------------------------------------------ consequence map, timeline

def consequence_mapper(meta: dict, provider=None) -> AgentResult:
    extra = ("\nBuild a CONSEQUENCE MAP (butterfly effect) for a What-If. Node 'n1' (kind 'divergence', parent '') is the approved divergence point. "
             "Then direct consequences (kind 'direct'), second-order ripples (kind 'ripple'), character changes (kind 'character') and world changes "
             "(kind 'world'). Every other node has a 'parent' that is the id of an earlier node. Give 8-16 nodes; set 'episode_hint' (episode number) "
             "where the consequence would be shown. Respect the canon research: change only what the divergence changes, and explain why.")
    user = "Context:\n" + _j({k: meta.get(k) for k in ("title", "premise", "divergence", "canon", "instruction", "episodes_count", "existing_nodes")
                             if meta.get(k) not in (None, "", [], {})})

    def semantic(d: dict) -> list[str]:
        ids = [n["id"] for n in d["nodes"]]
        errs = []
        if len(set(ids)) != len(ids):
            errs.append("node ids must be unique")
        seen: set[str] = set()
        for n in d["nodes"]:
            if n.get("parent") and n["parent"] not in seen:
                errs.append(f"node {n['id']}: parent {n['parent']} must be an earlier node")
            seen.add(n["id"])
        return errs

    return call_json("consequence_map", S.MAP, system=_system("story architect", meta, extra), user=user, meta=meta, provider=provider, max_tokens=4000,
                     semantic=semantic)


def timeline_builder(meta: dict, provider=None) -> AgentResult:
    extra = ("\nBuild an ALTERNATIVE TIMELINE: rows in chronological order. 'canon' = what happens in the original story at that time ('' if nothing), "
             "'alternate' = what happens in the changed world. Start at the divergence and follow the consequence map; keep it consistent with the canon "
             "research before the divergence.")
    user = "Context:\n" + _j({k: meta.get(k) for k in ("title", "divergence", "map", "canon_events", "instruction") if meta.get(k) not in (None, "", [], {})})
    return call_json("timeline", S.TIMELINE, system=_system("continuity supervisor", meta, extra), user=user, meta=meta, provider=provider, max_tokens=3500)


# ------------------------------------------------------------------ character and series bibles

def character_designer(meta: dict, provider=None) -> AgentResult:
    extra = ("\nTurn the owner's character design brief into a CHARACTER BIBLE: for each character a clear silhouette idea (appearance), personality, "
             "motivations/flaw, abilities, catchphrases, 2-4 'visual_hooks' (recognisable design elements an artist can keep consistent) and voice notes. "
             "Characters are original unless the brief names a franchise character AND the series is fan content.")
    user = "Brief:\n" + str(meta.get("brief") or "") + "\nContext:\n" + _j({k: meta.get(k) for k in ("page_name", "idea", "audience", "tone", "characters", "approved_ideas")
                                                                         if meta.get(k) not in (None, "", [], {})})
    return call_json("character_bible", S.CHARACTER_BIBLE, system=_system("character designer", meta, extra), user=user, meta=meta, provider=provider,
                     max_tokens=3500)


def bible_writer(meta: dict, provider=None) -> AgentResult:
    n = int(meta.get("episodes_count") or 5)
    extra = (f"\nWrite the SERIES BIBLE: title, logline, premise, world rules, characters, tone, themes, arcs (grouped story movements), "
             f"episode_count ({n}) and episode_length_sec. For a What-If also fill branch_point and alternative_timeline. Build on the APPROVED ideas, "
             "the canon research, the consequence map and the timeline; do not contradict them. Add 'visual_notes' that fit the page's look and "
             "'content_rules' (including neutrality rules for explainers).")
    user = "Development material:\n" + _j({k: meta.get(k) for k in ("page_name", "idea", "audience", "tone", "title", "premise", "source", "approved_ideas", "canon",
                                                                      "map", "timeline", "characters", "claims", "content_rules", "instruction", "episode_length_sec",
                                                                      "is_fan_content", "existing_bible") if meta.get(k) not in (None, "", [], {})})

    def transform(d: dict) -> dict:
        d["episode_count"] = n if not d.get("episode_count") else d["episode_count"]
        return d

    return call_json("bible", S.BIBLE, system=_system("series creator and head writer", meta, extra), user=user, meta=meta, provider=provider,
                     max_tokens=5000, transform=transform)


# ------------------------------------------------------------------ pre-production

def design_director(meta: dict, provider=None) -> AgentResult:
    extra = ("\nAs art director, write the DESIGN SHEETS the artists need for this episode: for every speaking/visible character one 'character' sheet "
             "(a turnaround model sheet prompt: front, 3/4, side, back, neutral pose on a plain background, with the recurring visual hooks), one "
             "'expression' sheet for main characters, a 'background' per location, key 'prop's, and ONE 'colour_script' entry per scene describing "
             "palette, light and mood (put 3-5 hex colours in 'palette'). Prompts are in English for the image model, consistent with the visual style "
             "text given; 'notes' is for the human artists in the working language.")
    user = "Episode material:\n" + _j({k: meta.get(k) for k in ("title", "visual_style", "negative", "look", "characters_detail", "scenes", "episode") if meta.get(k)})
    return call_json("design", S.DESIGN, system=_system("art director", meta, extra), user=user, meta=meta, provider=provider, max_tokens=5000)


def voice_caster(meta: dict, provider=None) -> AgentResult:
    extra = ("\nAs casting director choose ONE voice per character from the 'voices' list (use its exact 'id' as voice_id) that fits the character's "
             "age, personality and the language. Give a one-sentence reason. Never invent voice ids.")
    user = "Casting:\n" + _j({k: meta.get(k) for k in ("characters_detail", "voices", "language") if meta.get(k)})
    ids = {v["id"] for v in meta.get("voices") or []}

    def semantic(d: dict) -> list[str]:
        return [f"voice_id {c['voice_id']!r} is not in the list" for c in d["casting"] if ids and c["voice_id"] not in ids]

    return call_json("casting", S.CASTING, system=_system("casting director", meta, extra), user=user, meta=meta, provider=provider, max_tokens=1500,
                     semantic=semantic)


def translator(meta: dict, provider=None) -> AgentResult:
    target = {"fa": "Persian (Farsi, natural spoken style)", "en": "English"}.get(meta.get("target_language"), meta.get("target_language"))
    extra = (f"\nTranslate the episode script into {target}. Keep the same blocks (same count, same order, same speakers' names unless a name has a "
             "standard form in the target language), keep it speakable and natural, keep the tone, hook and cliffhanger. Do not add or drop information.")
    user = "Script:\n" + _j(meta.get("script"))
    n = len((meta.get("script") or {}).get("blocks") or [])

    def semantic(d: dict) -> list[str]:
        return [f"expected {n} blocks, got {len(d['blocks'])}"] if n and len(d["blocks"]) != n else []

    res = call_json("translate", S.TRANSLATION, system=_system("translator", {**meta, "language": meta.get("target_language")}, extra), user=user,
                    meta=meta, provider=provider, max_tokens=4000, semantic=semantic)
    return res


def shot_translator(meta: dict, provider=None) -> AgentResult:
    target = {"fa": "Persian (Farsi, natural spoken style)", "en": "English"}.get(meta.get("target_language"), meta.get("target_language"))
    extra = f"\nTranslate each narration line into {target}. Return the same ids; keep each line speakable and about the same length."
    user = "Lines:\n" + _j(meta.get("lines"))
    ids = {str(x["id"]) for x in meta.get("lines") or []}

    def semantic(d: dict) -> list[str]:
        got = {str(x["id"]) for x in d["lines"]}
        return [f"missing ids: {sorted(ids - got)[:5]}"] if ids - got else []

    return call_json("translate_shots", S.SHOT_LINES, system=_system("translator", {**meta, "language": meta.get("target_language")}, extra), user=user,
                     meta=meta, provider=provider, max_tokens=4000, semantic=semantic)
