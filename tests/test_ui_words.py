"""No raw English key in the Persian screens of the studio pipeline: every word the server can send as a plain key (stick-figure options, expressions, colour-key roles,
colour names, ending types, sound cues, grade presets) has a Persian name in `frontend/src/pipeline/kit.tsx` (`word()`), and the English anchor reads correctly."""
from __future__ import annotations

import re
from pathlib import Path

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
    missing = sorted(k for k in wanted if k not in fa)
    assert missing == [], f"no Persian name in kit.tsx for: {missing}"
    assert all(re.search(r"[؀-ۿ]", v) for v in fa.values()), "every value is Persian"


def test_the_screens_use_word_for_the_keys_they_print():
    root = KIT.parent
    assert "word(lang, p.role" in (root / "Identity.tsx").read_text(encoding="utf-8")                        # colour key
    assert "word(lang, k)" in (root / "Choice.tsx").read_text(encoding="utf-8")                              # the endings line of the review
    ladder = (root / "Ladder.tsx").read_text(encoding="utf-8")
    assert "StyleLine" in ladder and "vocab(lib.data?.realism" in ladder                                     # the art style card shows names, not keys


def test_identity_words_use_a_and_an_correctly():
    spec = S.normalize({"limb_colour": "#e8a22b", "hat": "beanie", "hat_colour": "#e8a22b", "neck": "scarf", "neck_colour": "#f26b21", "head_fill": "#e8a22b"})
    text = S.anchor_text(spec)
    assert "an amber beanie" in text and "an orange scarf" in text and "an amber-limbed" in text and "an amber round head" in text
    assert " a amber" not in text and " a orange" not in text
    assert "a blue beanie" in S.anchor_text(S.normalize({"hat": "beanie", "hat_colour": "#2f7fd1"}))
