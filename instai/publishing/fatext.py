"""Small Persian-text helpers for the checks that read Persian prose (caption lint, hashtags).

SOURCE: ported from NMarketing:backend/apps/common/fatext.py (en_digits, fa_digits, normalize) @ v3.02 (c23f861); the shop-rule helpers (negated phrases, Jalali
dates) are left out.

The same sentence can be typed in several byte-different ways: Persian or Arabic-Indic or Latin digits, with or without a half-space (ZWNJ), with Arabic ي/ك from an
old keyboard, with a kasra mark. `normalize` gives the form the checks compare in; it is never shown to a person."""
from __future__ import annotations

import re

_FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_EN_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

# ZWNJ, ZWJ, LRM/RLM, tatweel, and the Arabic short-vowel / kasra marks.
_STRIP = re.compile("[‌‍‎‏ـً-ٰٟ]")
_PERCENT = str.maketrans({"٪": "%"})
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})
_SPACES = re.compile(r"\s+")


def en_digits(text: str) -> str:
    """Persian and Arabic-Indic digits -> ASCII digits."""
    return (text or "").translate(_FA_TO_EN)


def fa_digits(text) -> str:
    """ASCII digits -> Persian digits (for text a person will read)."""
    return str(text if text is not None else "").translate(_EN_TO_FA)


def normalize(text: str) -> str:
    """A comparison form: casefolded, ASCII digits, no half-spaces or marks, Persian letters unified, single spaces."""
    t = en_digits(text or "")
    t = _STRIP.sub("", t)
    t = t.translate(_LETTERS).translate(_PERCENT)
    t = re.sub(r"(\d)\s+%", r"\1%", t)
    return _SPACES.sub(" ", t).casefold().strip()
