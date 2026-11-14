"""Hashtags the way Instagram wants them, and repair of glued ones.

SOURCE: ported from NMarketing:backend/apps/content/hashtags.py @ v3.02 (c23f861), adapted for series/episode producers: NMarketing's fitness / coaching / software
word list is replaced by a generic everyday-Persian list (stories, series, video, learning, money, travel ...) and the page's OWN vocabulary (its niche, pillars,
hashtags, series, episode and character names - `page_vocabulary`).

Instagram ends a hashtag at the first space, so «#هوش مصنوعی» tags only «#هوش». Persian writers join the words with an underscore («#هوش_مصنوعی») or a half-space.
A local model often glues them with nothing at all («#سریالکوتاه», «#PDFآموزشی») and the tag then matches no real search.

`repair` splits a glued tag only when EVERY piece is a known word, so a legitimate single word («ماجراجویی») is never cut and an unknown word is left exactly as
written. Nothing here calls a model; it works when the AI is off. Nothing here writes to the stored hashtags: the package ships the repaired form and the lint says
what was repaired.
"""
from __future__ import annotations

import re

from .fatext import normalize

#: everyday words of an animation / series / explainer channel. Compared in the `normalize` form (no half-space, no kasra). Extending the list can only make a split
#: more likely to be right; a word that is not listed is never cut. Words of fewer than three letters are left out on purpose (they glue into almost anything).
GENERIC_WORDS = """
انیمیشن انیمه کارتون کارتونی سریال سریالی قسمت فصل داستان داستانی کوتاه بلند فیلم ویدیو ویدئو ریلز استوری پست کپشن محتوا
شخصیت ماجراجویی ماجرا ترسناک کمدی طنز خنده شوخی علمی تخیلی فانتزی معمایی معما راز رازآلود جنایی هیجان هیجانی
زندگی عشق دوستی خانواده کودک کودکان نوجوان بزرگسال مدرسه دانشگاه شهر روستا طبیعت حیوانات حیوان گربه جنگل دریا کوه آسمان فضا ستاره ماه خورشید سفر
دنیا جهان زمان آینده گذشته تاریخ تاریخی علم دانش آموزش آموزشی توضیح مفاهیم مفهوم ساده سریع نکته نکات ایده ایده‌ها بررسی تحلیل معرفی
اقتصاد پول ثروت درآمد سرمایه سرمایه‌گذاری بازار قیمت تورم موفقیت انگیزه انگیزشی روانشناسی ذهن فکر تصمیم انتخاب انتخابی تعاملی بازی
هوش مصنوعی ساخته شده ساخت طراحی تولید نرم افزار برنامه فناوری تکنولوژی دیجیتال آنلاین رایگان تازه جدید برتر
ایران ایرانی فارسی تهران اصفهان شیراز تبریز مشهد پارسی
هر روز روزانه هفته هفتگی ماه ماهانه سال سالانه شب صبح
چه می‌شد اگر چرا چطور چگونه
""".split()

_LATIN = re.compile(r"([A-Za-z0-9]+)")
_MIN_LEN = 6
#: a tag this long with no separator, that we could not explain, is worth a warning
_LONG = 13
_WORD_SPLIT = re.compile(r"[^\w‌]+", re.UNICODE)

_BASE = frozenset(w for w in (normalize(x) for x in GENERIC_WORDS) if len(w) >= 3)


def words_of(*texts) -> frozenset:
    """A word list from free text (the page's niche, a series title ...): every word of three letters or more, in the comparison form; `_` and `#` separate words."""
    out: set[str] = set()
    for t in texts:
        for w in _WORD_SPLIT.split(str(t or "").replace("_", " ").replace("#", " ")):
            n = normalize(w)
            if len(n) >= 3 and not _LATIN.fullmatch(n):
                out.add(n)
    return frozenset(out)


def _words(extra) -> frozenset:
    return _BASE | extra if extra else _BASE


def _segment(word: str, words: frozenset) -> list[str] | None:
    """Fewest-pieces split of `word` into known words, or None."""
    n = len(word)
    best: list[list[str] | None] = [None] * (n + 1)
    best[0] = []
    for end in range(1, n + 1):
        for start in range(end):
            piece = word[start:end]
            if best[start] is None or piece not in words:
                continue
            cand = best[start] + [piece]
            if best[end] is None or len(cand) < len(best[end]):
                best[end] = cand
    return best[n]


def _cut_like(raw: str, pieces: list[str]) -> list[str]:
    """Cut `raw` where its normalised form was cut, so the repaired tag keeps the writer's own spelling (kasra, ي/ی ...) in each piece."""
    out, i = [], 0
    for piece in pieces:
        need, chunk = len(piece), ""
        while i < len(raw) and need > 0:
            chunk += raw[i]
            need -= len(normalize(raw[i]))
            i += 1
        while i < len(raw) and normalize(raw[i]) == "":  # marks belong to the piece before them
            chunk += raw[i]
            i += 1
        out.append(chunk.replace("‌", ""))
    return out


def clean(tag) -> str:
    """«# هوش  مصنوعی» -> «هوش_مصنوعی» (no leading #, spaces become underscores)."""
    word = str(tag or "").strip().lstrip("#").strip()
    return re.sub(r"[\s_]+", "_", word).strip("_")


def repair(tag, extra=frozenset()) -> str:
    """The tag, split at word boundaries if it was glued; a leading # is kept. `extra` = the page's own words (`words_of`).

    «سریالکوتاه» -> «سریال_کوتاه», «PDFآموزشی» -> «PDF_آموزشی»; «ماجراجویی», «هوش_مصنوعی» and unknown words come back unchanged."""
    words = _words(extra)
    prefix = "#" if str(tag or "").lstrip().startswith("#") else ""
    word = clean(tag)
    if not word:
        return ""
    parts: list[str] = []
    for chunk in word.split("_"):
        for run in (r for r in _LATIN.split(chunk) if r):
            if _LATIN.fullmatch(run):  # a Latin run next to Persian is its own word
                parts.append(run)
                continue
            norm = normalize(run)
            seg = None if len(norm) < _MIN_LEN or norm in words else _segment(norm, words)
            parts.extend(_cut_like(run, seg) if seg and len(seg) >= 2 else [run])
    return prefix + "_".join(p for p in parts if p)


def parse(value) -> list[str]:
    """What a person typed or a model stored -> a list of tags. A list is taken as is; text with «#» is split on the hashtags; other text is split on commas and new
    lines (so «سریال کوتاه» stays ONE tag)."""
    if isinstance(value, (list, tuple)):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    text = str(value or "")
    if "#" in text:
        return re.findall(r"#[^\s#،,]+", text)
    return [t.strip() for t in re.split(r"[,،\n]+", text) if t.strip()]


def repair_all(value, extra=frozenset()) -> list[str]:
    """`repair` over a stored list (or typed text); empty results dropped."""
    return [r for r in (repair(t, extra) for t in parse(value)) if r]


def is_glued(tag, extra=frozenset()) -> bool:
    """A long tag with no separator that `repair` could not explain: probably several words stuck together that this module does not know how to split."""
    words = _words(extra)
    word = clean(tag)
    norm = normalize(word)
    return (len(norm) >= _LONG and "_" not in word and "‌" not in str(tag) and not _LATIN.fullmatch(word) and norm not in words
            and clean(repair(tag, extra)) == word)


def page_vocabulary(page, series=None, episode=None) -> frozenset:
    """The page's own words: its niche, theme, name, pillars and hashtags, the series and episode titles and the character names."""
    texts: list = []
    try:
        ident, strat, pub = page.profile("identity"), page.profile("strategy"), page.profile("publishing")
        texts += [page.name, ident.get("niche"), ident.get("theme"), ident.get("display_name"), ident.get("audience")]
        texts += list(strat.get("pillars") or []) + list(strat.get("hashtags") or []) + list(pub.get("hashtags") or [])
        texts += [c.name for c in page.characters.all()]
    except Exception:  # noqa: BLE001 - a missing profile row is not an error
        pass
    for obj in (series, episode):
        if obj is not None:
            texts.append(getattr(obj, "title", ""))
    return words_of(*texts)
