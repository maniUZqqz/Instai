"""Persian digits inside a Persian sentence (the owner reads Persian only: «۱۲٫۵ گیگابایت», never «12.5 گیگابایت»).

`fa_numbers(text)` converts the NUMBERS of a sentence and leaves technical tokens alone: versions (3.10.12), words with digits (x86_64, qwen3:8b),
paths and addresses (127.0.0.1:9, tools/piper-2), file names, and a number that belongs to a Latin phrase («RTX 3060», «12 GB»). Clock times
(02:00-07:00) are converted too. The UI does the same with `f.num`; this is the server-side twin.
"""
from __future__ import annotations

import re

_TABLE = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
# a standalone number: not glued to a letter / digit / path character before it, not the start of a version (x.y.z) and not glued after it
_NUMBER = re.compile(r"(?<![\w./:\\-])(\d+)(?:\.(\d+))?(?![\w/:\\-]|\.\d)")
_CLOCK = re.compile(r"(?<![\w.:/\\])(\d{1,2}):(\d{2})(?![\w.:/\\])")
_LATIN = re.compile(r"[A-Za-z]")


def fa_digits(value) -> str:
    """Every digit of `value` in Persian digits (use on a bare number: «۱۲٫۵» for 12.5)."""
    return str(value).translate(_TABLE).replace(".", "٫")


def _latin_neighbour(text: str, start: int, end: int, kept_end: int) -> bool:
    """The number is part of a Latin phrase: the word before it (or the one after it) has Latin letters, or it follows a number that was kept."""
    before = text[:start].rstrip()
    if before and (text[before.rfind(" ") + 1:len(before)].isascii() and _LATIN.search(text[before.rfind(" ") + 1:len(before)]) or kept_end == len(before)):
        return True
    after = text[end:].lstrip().split(" ", 1)[0] if text[end:end + 1] == " " else ""
    return bool(after) and after.isascii() and bool(_LATIN.search(after)) and not after.startswith("(")


def fa_numbers(text: str) -> str:
    """The standalone numbers of a sentence in Persian digits; technical tokens (versions, ids, paths, URLs, Latin phrases) stay as they are."""
    if not text or not any(c.isdigit() for c in text):
        return text
    text = _CLOCK.sub(lambda m: fa_digits(m.group(0)), text)
    out, last, kept_end = [], 0, -1
    for m in _NUMBER.finditer(text):
        out.append(text[last:m.start()])
        if _latin_neighbour(text, m.start(), m.end(), kept_end):
            out.append(m.group(0))
            kept_end = m.end()
        else:
            out.append(fa_digits(m.group(0)))
        last = m.end()
    out.append(text[last:])
    return "".join(out)
