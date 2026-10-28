"""The interface is bilingual (Persian RTL / English LTR): every text key used in the UI sources exists in BOTH dictionaries
(src/i18n/fa.ts, en.ts and every src/i18n/packs/*.ts), the two dictionaries have the same keys, and keys built at run time are covered."""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
KEY_LINE = re.compile(r"^\s*'([A-Za-z0-9_.\-]+)'\s*:\s*(.*)$")


def _keys(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = KEY_LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


_VALUE = re.compile(r"^\s*'((?:[^'\\]|\\.)*)'\s*,?\s*(?://.*)?$")
_ESC = re.compile(r"\\(.)")


def decode(raw: str) -> str:
    """The text of a dictionary line's right-hand side: 'a text',  ->  a text (escapes resolved; anything odd is returned as it is)."""
    m = _VALUE.match(raw)
    return _ESC.sub(r"\1", m.group(1)) if m else raw


def texts() -> tuple[dict[str, str], dict[str, str]]:
    fa, en = dictionaries()
    return {k: decode(v) for k, v in fa.items()}, {k: decode(v) for k, v in en.items()}


def dictionaries() -> tuple[dict[str, str], dict[str, str]]:
    fa = _keys((SRC / "i18n" / "fa.ts").read_text(encoding="utf-8"))
    en = _keys((SRC / "i18n" / "en.ts").read_text(encoding="utf-8"))
    for f in sorted((SRC / "i18n" / "packs").glob("*.ts")):
        text = f.read_text(encoding="utf-8")
        head, _, tail = text.partition("export const en")
        fa.update(_keys(head))
        en.update(_keys(tail))
    return fa, en


def _sources() -> list[tuple[Path, str]]:
    # src/studio/ is the production workstream's screens with their own dictionary (src/studio/i18n.ts); it checks itself
    own = SRC / "studio"
    return [(p, p.read_text(encoding="utf-8")) for p in SRC.rglob("*.ts*")
            if "i18n" not in p.parts and p.suffix in (".ts", ".tsx") and own not in p.parents]


STATIC = re.compile(r"""\b(?:t|tr)\(\s*['"]([A-Za-z0-9_.\-]+)['"](?!\s*\+)""")
CAST = re.compile(r"""as\s+['"]([a-z][A-Za-z0-9_.\-]+\.[A-Za-z0-9_.\-]+)['"]""")
DYNAMIC = re.compile(r"""\b(?:t|tr)\(\(?\s*['"]([A-Za-z0-9_.\-]+\.[A-Za-z0-9_\-]*)['"]\s*\+""")


def test_dictionaries_have_the_same_keys():
    fa, en = dictionaries()
    assert len(fa) > 1000
    missing_en = sorted(set(fa) - set(en))
    missing_fa = sorted(set(en) - set(fa))
    assert missing_en == [], f"keys without an English text: {missing_en[:40]}"
    assert missing_fa == [], f"keys without a Persian text: {missing_fa[:40]}"


def test_every_key_used_in_the_sources_exists():
    fa, _ = dictionaries()
    used: dict[str, str] = {}
    for p, text in _sources():
        for rx in (STATIC, CAST):
            for m in rx.finditer(text):
                used.setdefault(m.group(1), p.name)
    unknown = sorted(f"{k} ({f})" for k, f in used.items() if k not in fa)
    assert unknown == [], f"keys used but not defined: {unknown[:60]}"


def test_dynamic_key_prefixes_have_entries():
    fa, _ = dictionaries()
    missing = []
    for p, text in _sources():
        for m in DYNAMIC.finditer(text):
            prefix = m.group(1)
            if not any(k.startswith(prefix) for k in fa):
                missing.append(f"{prefix} ({p.name})")
    assert missing == [], f"dynamic key prefixes without any entry: {sorted(set(missing))}"


# values that run-time keys take (state machine, stages, kinds ...): each must exist in both languages
ENUMS = {
    "dev.status_": ["todo", "active", "review", "done", "skipped"],
    "dev.st_": ["developing", "approved"],
    "studio.stage_": ["script", "storyboard", "animatic", "design", "casting", "gate"],
    "studio.st_": ["todo", "ready", "stale", "approved", "auto"],
    "tpl.kind_": ["source", "research", "brainstorm", "profile", "map", "timeline", "factcheck", "bible", "composition", "gate"],
    "tpl.format_": ["anime_whatif", "recurring_character", "concept_explainer", "custom"],
    "lens.": ["divergence", "series_concept", "scenario", "gag_format", "topic", "analogy", "character_concept"],
    "idea.by_": ["ai", "human", "merged", "refined"],
    "idea.st_": ["approved", "rejected", "liked", "proposed", "merged"],
    "idea.f_": ["active", "approved", "rejected", "all"],
    "idea.f.": ["divergence_moment", "canon_outcome", "changed_outcome", "ripple_preview", "hook", "audience", "story_engine", "setup", "complication", "payoff", "gag", "trigger",
                "variation", "why_it_is_hard", "hook_question", "common_misconception", "analogy", "visual_metaphor", "where_it_breaks_down", "look", "flaw", "want"],
    "map.k_": ["divergence", "direct", "ripple", "character", "world", "theme"],
    "stance.": ["established", "contested", "speculative"],
    "design.k_": ["character", "expression", "background", "prop", "colour_script"],
    "retake.scope_": ["keyframe", "narration", "clip", "all"],
    "retake.st_": ["open", "done", "cancelled"],
    "animatic.st_": ["missing", "fresh", "stale"],
    "animatic.audio_": ["tts", "partial", "none"],
    "llm.group.": ["strategy", "brainstorm", "research", "bible", "script", "translate"],
    "llm.prov_": ["ollama", "openai", "fake"],
    "lib.tab_": ["styles", "themes", "templates"],
    "lib.role.": ["background", "primary", "secondary", "accent", "shadow", "highlight"],
    "src.prov_": ["anilist", "wikipedia", "fandom", "jikan"],
    "post.": ["assets", "assembly", "qc", "approval"],
    "tech.": ["still_kenburns", "parallax_25d", "puppet_2d", "motion_graphics", "wan_i2v", "wan_flf", "talking_video", "three_d"],
    "job.kind.": ["studio.source_search", "studio.ideas", "studio.idea_refine", "studio.idea_merge", "studio.research", "studio.map", "studio.timeline", "studio.profile",
                  "studio.bible", "studio.design", "studio.design_image", "studio.casting", "studio.translate", "studio.animatic", "story.strategy", "story.plan", "story.script",
                  "story.storyboard", "story.research", "story.continuity"],
    "error.code.": ["validation_error", "not_found", "conflict", "not_ready", "invalid_transition", "llm_invalid_output", "provider_unavailable"],
}


def test_run_time_keys_exist_in_both_languages():
    fa, en = dictionaries()
    missing = [f"{pre}{v}" for pre, vals in ENUMS.items() for v in vals if f"{pre}{v}" not in fa or f"{pre}{v}" not in en]
    assert missing == [], f"run-time keys missing: {missing}"


def test_english_texts_are_not_persian_and_persian_texts_are_not_english_only():
    fa, en = dictionaries()
    persian = re.compile(r"[؀-ۿ]")
    bad_en = [k for k, v in en.items() if persian.search(v) and not k.startswith(("lang.", "wiz.lang"))]
    # an English value may mention a Persian word on purpose (the language name); anything else is a copy-paste slip
    assert [k for k in bad_en if not re.search(r"فارسی|Persian", en[k])] == [], f"Persian text inside the English dictionary: {bad_en[:20]}"
