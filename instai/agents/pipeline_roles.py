"""Agent roles of the animation-studio pipeline: the writing and planning stages of the ladder (logline, treatment, beat sheet, dialogue, shot list,
layout, sound design, grade), the character identity anchor, the choice-story planner and the mini-series season planner.

Same rules as agents/roles.py: a role is ONE validated call_json that returns a plain dict and never touches the database. The text of every
role is written for the real production practice named in docs/STUDIO_PIPELINE.md (logline -> treatment -> beat sheet -> script -> dialogue ->
shot list -> storyboard/animatic -> model sheets -> layout -> key art -> animation -> compositing -> sound design -> narration -> edit -> grade -> delivery).
"""
from __future__ import annotations

from typing import Any

from . import pipeline_fake  # noqa: F401 - registers the fake-provider outputs of these tasks
from . import pipeline_schemas as P
from .roles import _base_system, _j
from .runner import AgentResult, call_json

SHOT_SIZES = "ECU (extreme close-up), CU (close-up), MCU, MS (medium), MWS, WS (wide), EWS (establishing wide)"
ANGLES = "eye-level, low angle, high angle, over-the-shoulder, top-down, dutch"
MOVES = "static, push-in, pull-out, pan left/right, tilt up/down, tracking, handheld shake"
TRANSITIONS = "cut, match cut, smash cut, dissolve, whip pan, fade"


def _system(role: str, meta: dict, extra: str) -> str:
    look = meta.get("look") or {}
    look_line = ("\nVisual look of the project (everything must be producible in it): " + ", ".join(f"{k}={v}" for k, v in look.items() if v)) if look else ""
    return _base_system(role, meta) + look_line + "\n" + extra


def _ctx(meta: dict, keys: tuple[str, ...]) -> str:
    return "Context:\n" + _j({k: meta.get(k) for k in keys if meta.get(k) not in (None, "", [], {})})


def _instruction(meta: dict) -> str:
    ins = str(meta.get("instruction") or "").strip()
    return f"\nThe director's note for this version (obey it): {ins}" if ins else ""


# ------------------------------------------------------------------ character identity

def identity_anchor(meta: dict, provider=None) -> AgentResult:
    extra = ("\nWrite the IDENTITY ANCHOR of ONE character: a single compact English description (at most 60 words) that an image model can read in every "
             "prompt so the character looks identical every time: silhouette and proportions, head/face shape, hair, skin or fill colour, outfit and accessories "
             "WITH their colours, and the art-style words. Use concrete visual facts only (no personality, no story). 'avoid' lists what must never change or appear. "
             "'visual_hooks' are 2-4 recognisable design elements. 'palette' lists the 3-6 signature colours as hex with a role (hair, outfit, accent...). "
             "The character is ORIGINAL: never name a franchise or a real person.")
    user = _ctx(meta, ("character", "look", "existing_anchor", "instruction"))
    return call_json("identity_anchor", P.IDENTITY_ANCHOR, system=_system("character designer", meta, extra), user=user, meta=meta, provider=provider, max_tokens=900)


# ------------------------------------------------------------------ development stages (series)

def logline_writer(meta: dict, provider=None) -> AgentResult:
    extra = ("\nWrite the LOGLINE of the series: ONE sentence (at most 35 words) that names the protagonist, the want, the obstacle and the stakes, and makes a stranger "
             "want to watch. Then 'hook' (the one-line promise to the audience), 'stakes' (what is lost if the hero fails) and up to 3 'alternatives' with different angles."
             + _instruction(meta))
    return call_json("logline", P.LOGLINE, system=_system("story editor", meta, extra), user=_ctx(meta, ("title", "premise", "idea", "audience", "tone", "characters",
                                                                                                         "approved_ideas", "existing", "channel")),
                     meta=meta, provider=provider, max_tokens=900)


def treatment_writer(meta: dict, provider=None) -> AgentResult:
    extra = ("\nWrite the TREATMENT: the whole story in present tense as prose, 3-6 short paragraphs in 'synopsis' (beginning, escalation, midpoint turn, crisis, ending or "
             "season-ending cliffhanger), then 'acts' (name + one-paragraph summary of each act), the 'tone' and the 'themes'. Build ONLY on the approved logline; do not "
             "contradict it." + _instruction(meta))
    return call_json("treatment", P.TREATMENT, system=_system("story architect", meta, extra), user=_ctx(meta, ("title", "logline", "premise", "characters", "tone",
                                                                                                                "episodes_count", "episode_length_sec", "existing", "channel")),
                     meta=meta, provider=provider, max_tokens=2500)


# ------------------------------------------------------------------ episode stages

def beat_sheet_writer(meta: dict, provider=None) -> AgentResult:
    secs = int(meta.get("duration_sec") or 45)
    extra = (f"\nWrite the BEAT SHEET of ONE short episode of about {secs} seconds: 5-9 beats, each a story event (not a camera direction): hook, setup, inciting problem, "
             "escalation, midpoint turn, crisis, resolution or cliffhanger, and a closing line. Give every beat 'seconds' (they must sum to about the episode length) and "
             "'purpose' (what the viewer should feel). The first beat must hook within the first 2-3 seconds; the last beat must pull the viewer to the next episode. "
             "Keep continuity with the previous episodes' summaries." + _instruction(meta))
    return call_json("beat_sheet", P.BEAT_SHEET, system=_system("story editor", meta, extra), user=_ctx(meta, ("series_title", "logline", "treatment", "episode", "characters",
                                                                                                             "previous_summaries", "memory", "channel", "duration_sec")),
                     meta=meta, provider=provider, max_tokens=1800)


def dialogue_writer(meta: dict, provider=None) -> AgentResult:
    lang = meta.get("language") or "fa"
    extra = (f"\nWrite the DIALOGUE pass of the approved script: every spoken line in order, as the characters would really say it (short, speakable, natural {lang}). "
             "For each line give the speaker, the text, the 'emotion' (one word), the 'subtext' (what the character really means, one short phrase) and 'pause_after' in "
             "seconds. Keep the story and the facts of the script; improve rhythm, voice and clarity; every character must sound different. Narrator lines are allowed "
             "(speaker = the narrator)." + _instruction(meta))
    return call_json("dialogue", P.DIALOGUE, system=_system("dialogue writer", meta, extra), user=_ctx(meta, ("script", "beats", "characters", "memory", "duration_sec")),
                     meta=meta, provider=provider, max_tokens=3500)


def shot_list_writer(meta: dict, provider=None) -> AgentResult:
    extra = ("\nAs director of photography write the SHOT LIST for the approved dialogue: one entry per shot in order. For each: 'scene' (1-based scene number), 'size' "
             f"(one of: {SHOT_SIZES}), 'angle' ({ANGLES}), 'movement' ({MOVES}), 'characters' (names in frame), 'action' (what is seen, one sentence), 'seconds' "
             f"(1.5-8), 'transition' into the next shot ({TRANSITIONS}) and 'notes'. Vary the sizes, open on the hook, put the key reveal in a close-up, keep the 180-degree "
             "rule inside a scene, and make the total length match the episode. Every spoken line of the dialogue must fall inside some shot." + _instruction(meta))
    return call_json("shot_list", P.SHOT_LIST, system=_system("director of photography", meta, extra), user=_ctx(meta, ("dialogue", "script", "characters", "duration_sec", "location_notes")),
                     meta=meta, provider=provider, max_tokens=4000)


def layout_artist(meta: dict, provider=None) -> AgentResult:
    extra = ("\nAs layout artist write the LAYOUT of every shot of the approved storyboard: 'shot' (1-based index in order), 'background' (the location and what is in it), 'staging' "
             "(where each character stands and what they do, left/right/foreground/background), 'camera' (lens feel and framing in one phrase), 'lighting' (key light, mood) and "
             "'props'. Characters and props must match the model sheets; do not invent new characters." + _instruction(meta))
    return call_json("layout", P.LAYOUT, system=_system("layout artist", meta, extra), user=_ctx(meta, ("shots", "characters", "design_sheets", "colour_script")),
                     meta=meta, provider=provider, max_tokens=4000)


def sound_designer(meta: dict, provider=None) -> AgentResult:
    extra = ("\nAs sound designer write the CUE SHEET of the episode: 'ambience' beds per location, 'foley' (footsteps, cloth, doors, props), 'sfx' (impacts, whooshes, stingers "
             "on the beats and the cliffhanger), 'music' cues (mood, tempo, instruments, where it enters and leaves) and deliberate 'silence' before the reveal. Each cue: kind, "
             "'shot' (1-based, 0 = the whole episode), start_sec, end_sec, a plain description, an ENGLISH 'prompt' a sound generator can use, 'gain_db' (ambience -30..-24, music "
             "-24..-18, sfx -14..-8) and 'duck' (true for beds that must dip under speech). 'mix_notes' says how dialogue, music and effects share the level; "
             "'loudness_target' is the integrated loudness in LUFS (about -16 for social video)." + _instruction(meta))
    return call_json("sound_design", P.SOUND_DESIGN, system=_system("sound designer", meta, extra), user=_ctx(meta, ("shots", "beats", "dialogue", "mood", "duration_sec", "locations")),
                     meta=meta, provider=provider, max_tokens=3500)


def colourist(meta: dict, provider=None) -> AgentResult:
    extra = ("\nAs colourist write the GRADE PLAN: for each scene a 'preset' (one of: neutral, warm_dusk, cold_night, high_contrast, faded, vivid, desaturated, tension), the 'mood', "
             "3-5 hex 'palette' colours of the scene (from the colour script) and short 'notes'. Keep one consistent look across scenes; change the grade only for story reasons. "
             "'global_notes' says what must never change (skin or fill colours of the characters)." + _instruction(meta))
    return call_json("grade", P.GRADE, system=_system("colourist", meta, extra), user=_ctx(meta, ("scenes", "colour_script", "look", "mood")), meta=meta, provider=provider,
                     max_tokens=2000)


# ------------------------------------------------------------------ choice stories and channels

def choice_planner(meta: dict, provider=None) -> AgentResult:
    n = int(meta.get("post_count") or 14)
    extra = (f"\nPlan an INTERACTIVE CHOICE STORY for social posts: about {n} posts as a branching graph. Each post is one picture + short text. The first post is id 'p1' "
             "(kind start). 'story' posts lead on with exactly one choice (label 'continue'); 'choice' posts end with 2 (rarely 3) choices; 'ending' posts have no choices and "
             "set 'ending' to good, bad, secret or neutral. Every choice 'to' is the id of ANOTHER post in the list. Rules: no dead ends (only endings stop), every post "
             "reachable from p1, mostly forward-moving (later posts only), a few bad endings that come early as funny or scary failures, at least one good ending, and branches "
             "that merge back so the story is not a pure tree. 'text' is 1-3 short sentences (max 220 characters) of narration or dialogue; 'location', 'pose' and 'expression' "
             "describe the picture (pose: stand, run, hide, point, shock, think, sit, hands_up...; expression: neutral, happy, sad, angry, scared, surprised, smirk). "
             "Choice labels are short (max 28 characters) and the player must feel a real dilemma." + _instruction(meta))
    return call_json("choice_plan", P.CHOICE_PLAN, system=_system("interactive story designer", meta, extra),
                     user=_ctx(meta, ("title", "premise", "genre", "characters", "post_count", "tone", "existing_posts", "instruction")), meta=meta, provider=provider, max_tokens=5000)


def choice_caption_writer(meta: dict, provider=None) -> AgentResult:
    extra = ("\nWrite the CAPTION of each post of a choice story, in the working language. The caption restates the situation in one or two lines, then asks the choice. "
             "Do NOT write post numbers yourself: write the placeholder {go:ID} where the number of post ID must appear (for example 'if you choose A go to post {go:p4}'); the system fills in "
             "the real numbers. Add up to 6 hashtags for the first post only. 'alt' is a short description of the picture for accessibility.")
    return call_json("choice_posts", P.CHOICE_POSTS, system=_system("social copywriter", meta, extra), user=_ctx(meta, ("title", "posts", "tone")), meta=meta, provider=provider,
                     max_tokens=4500)


def season_planner(meta: dict, provider=None) -> AgentResult:
    n = int(meta.get("episodes_count") or 8)
    secs = int(meta.get("runtime_sec") or 30)
    extra = (f"\nPlan a MINI-SERIES SEASON of exactly {n} short episodes of about {secs} seconds in the format of vertical stick-figure survival/escape series: a HOOK in the first 2 seconds, "
             "fast escalation, one twist, and a CLIFFHANGER in the last 3 seconds that the next episode answers in its first seconds ('payoff_of_previous'). Episode 1 introduces the "
             "protagonist and the threat; the season arc rises to a finale that resolves the main question but may open the next season. Use ONLY the given recurring characters "
             "and the original world; never copy a real series, character or catchphrase. Track threads: 'opens' lists new open questions an episode raises, 'closes' the ones it answers; "
             "no thread stays open for more than 4 episodes, and every thread is closed by the finale. Vary the locations and the kind of danger from episode to episode."
             + _instruction(meta))

    def semantic(d: dict) -> list[str]:
        nums = sorted(e["number"] for e in d["episodes"])
        errs = []
        if nums != list(range(1, len(nums) + 1)):
            errs.append("episode numbers must be consecutive starting at 1")
        if len(d["episodes"]) != n:
            errs.append(f"expected {n} episodes, got {len(d['episodes'])}")
        return errs

    return call_json("season_plan", P.SEASON_PLAN, system=_system("showrunner", meta, extra),
                     user=_ctx(meta, ("title", "premise", "genre_notes", "characters", "episodes_count", "runtime_sec", "memory", "existing", "tone")), meta=meta, provider=provider,
                     max_tokens=5000, semantic=semantic)


ROLES: dict[str, Any] = {
    "identity_anchor": identity_anchor, "logline": logline_writer, "treatment": treatment_writer, "beat_sheet": beat_sheet_writer, "dialogue": dialogue_writer,
    "shot_list": shot_list_writer, "layout": layout_artist, "sound_design": sound_designer, "grade": colourist, "choice_plan": choice_planner,
    "choice_posts": choice_caption_writer, "season_plan": season_planner,
}
