"""No raw English key in the Persian screens of the studio pipeline: every word the server can send as a plain key (stick-figure options, expressions, colour-key roles,
colour names, ending types, sound cues, grade presets) has a Persian name in `frontend/src/pipeline/kit.tsx` (`word()`), and the English anchor reads correctly."""
from __future__ import annotations

import re
from pathlib import Path

from instai.channel.conventions import CAST_ROLES
from instai.render.stick import spec as S
from instai.studio import ladder_stages

KIT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "pipeline" / "kit.tsx"


def _persian_words() -> dict[str, str]:
    text = KIT.read_text(encoding="utf-8")
    block = text[text.index("const WORDS_FA"):text.index("/** `word(lang")]
    return dict(re.findall(r"\b([a-z_]+): '([^']+)'", block))


def test_every_key_the_server_sends_has_a_persian_name():
    fa = _persian_words()
    wanted = set()
    for vals in (S.HEAD_STYLES, S.EYE_STYLES, S.HATS, S.HAIRS, S.NECK, S.EXTRAS, S.PROPS, S.EXPRESSIONS, ladder_stages.CUES, ladder_stages.PRESETS):
        wanted.update(vals)
    wanted.update(S.PALETTE_NAMES.values())                                   # the colour names of the identity words
    wanted.update(("limbs", "head", "outline", "hat", "hair", "neck", "extra"))   # the roles of the colour key (spec.palette)
    wanted.update(("good", "bad", "secret", "neutral"))                      # the ending types of a choice story
    wanted.update(CAST_ROLES)                                                 # the role of a character (channel cast, page characters)
    wanted.add("hero")                                                        # the role the model-less planner gives its first character
    missing = sorted(k for k in wanted if k not in fa)
    assert missing == [], f"no Persian name in kit.tsx for: {missing}"
    assert all(re.search(r"[؀-ۿ]", v) for v in fa.values()), "every value is Persian"


def test_the_screens_use_word_for_the_keys_they_print():
    root = KIT.parent
    assert "word(lang, p.role" in (root / "Identity.tsx").read_text(encoding="utf-8")                        # colour key
    assert "word(lang, k)" in (root / "Choice.tsx").read_text(encoding="utf-8")                              # the endings line of the review
    ladder = (root / "Ladder.tsx").read_text(encoding="utf-8")
    assert "StyleLine" in ladder and "vocab(lib.data?.realism" in ladder                                     # the art style card shows names, not keys


def test_the_model_sheet_prints_the_same_persian_words_as_the_screens():
    """Review of 0.11.0: the drawn model sheet of a Persian series had English labels (neutral, happy, 'limbs · blue', 'MODEL SHEET'). `spec.FA_WORDS` names every word the
    sheet prints and must agree, character for character, with the screens' `WORDS_FA`."""
    fa = _persian_words()
    printed = set(S.EXPRESSIONS) | set(S.PALETTE_NAMES.values()) | {"limbs", "head", "outline", "hat", "hair", "neck", "extra"}
    assert printed <= set(S.FA_WORDS), sorted(printed - set(S.FA_WORDS))
    assert {k: v for k, v in S.FA_WORDS.items() if fa.get(k) != v} == {}, "the sheet and the screens name a word differently"
    assert S.fa_word("blue") == "آبی" and S.fa_word("not-a-word") == "not-a-word"


def test_the_screens_name_a_character_role_and_the_ladder_labels_every_field():
    """Review of 0.11.0: the character list printed the raw role 'hero'; the ladder editors showed no label and no column header because `pick()` read `fa`/`en` while the
    server sends `label_fa`/`label_en`."""
    root = KIT.parent
    chars = (root.parent / "pages" / "workspace" / "CharactersTab.tsx").read_text(encoding="utf-8")
    assert "word(lang, c.role)" in chars and "· {c.role}" not in chars
    ladder = (root / "Ladder.tsx").read_text(encoding="utf-8")
    assert "pick(f as any)" not in ladder and "pick(c as any)" not in ladder, "a field or column label must be read with pick(x, 'label')"
    assert ladder.count("pick(f as any, 'label')") >= 3 and ladder.count("pick(c as any, 'label')") >= 5
    for st in ladder_stages.STAGES:
        for f in st["fields"]:
            assert f["label_fa"] and f["label_en"], (st["key"], f["key"])
            for c in f.get("columns") or []:
                assert c["label_fa"] and c["label_en"], (st["key"], f["key"], c["key"])
    choice = (root / "Choice.tsx").read_text(encoding="utf-8")
    assert "· ${node.id}" not in choice, "a post's title is never its internal id"
    assert not re.search(r"\{p\.counts\.\w+ \?\? 0\}", ladder), "the counts of the ladder header follow the language's digits (n())"


def test_identity_words_use_a_and_an_correctly():
    spec = S.normalize({"limb_colour": "#e8a22b", "hat": "beanie", "hat_colour": "#e8a22b", "neck": "scarf", "neck_colour": "#f26b21", "head_fill": "#e8a22b"})
    text = S.anchor_text(spec)
    assert "an amber beanie" in text and "an orange scarf" in text and "an amber-limbed" in text and "an amber round head" in text
    assert " a amber" not in text and " a orange" not in text
    assert "a blue beanie" in S.anchor_text(S.normalize({"hat": "beanie", "hat_colour": "#2f7fd1"}))
