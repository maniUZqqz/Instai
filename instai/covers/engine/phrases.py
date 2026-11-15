"""Smart shortening of Persian phrases for a cover title and subtitle (no AI).

The problem of the first version: "the first 4 words" cut a phrase in the middle of a sentence (a title ending in a preposition or on "one"). Here:

* no phrase ends on an unfinished word (a preposition, "and", the object marker, "that", a word carrying the ezafe vowel ...);
* when the topic is long it is cut before the first preposition / conjunction and the rest of the sentence stays to become the subtitle;
* the content of a parenthesis is separated from the title ("Title (extra words)" -> title + subtitle);
* a topic that starts with a number ("7 mistakes in ...") keeps its number and no second number is added;
* a "clause" topic (how ..., why ..., is it ..., or one with a verb) is told apart from a "noun" topic, because patterns such as
  "learn {topic} from scratch" only make sense for a noun phrase.

SOURCE: ported from NMarketing:backend/apps/thumbs/phrases.py @ v3.02 (c23f861), adapted for series/episode covers
(the Persian rules are unchanged; the fitness compounds became animation ones).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import typo

_MARKS = re.compile("[ً-ْٰٔ]")
_EDGE = " .؛،:!؟?-–—«»\"'()[]{}*|"
#: words a phrase must not end on
FUNC = frozenset("""و یا که را با برای از در به تا بر بی بدون مثل مانند چون اگر هم نیز اما ولی پس نه
درباره دربارهٔ همراه بین روی زیر علیه طبق مثلِ بجز جز""".split())
#: words that come before a noun; a phrase does not end on them
DETERMINERS = frozenset("""یک این آن هر همه چند دو سه چهار پنج همین همان هیچ برخی بعضی تمام چه کدام چطور چگونه آیا فقط""".split())
#: the start of a new phrase; the best place to cut is right before these words
BOUNDARY = frozenset("""که با برای از در به تا بدون بی مثل مانند درباره دربارهٔ همراه بین""".split())
#: the conjunction: cutting before it breaks a coordinated group
COORD = frozenset("""و یا + &""".split())
#: two-word compounds that are one concept; a phrase is not cut between them
COMPOUNDS = frozenset({("هوش", "مصنوعی"), ("یادگیری", "ماشین"), ("شبکه", "اجتماعی"), ("داستان", "انتخابی"), ("خط", "زمانی"), ("جهان", "موازی"),
                       ("قسمت", "آخر"), ("پایان", "باز"), ("ادامه", "دارد")})
QUESTION_START = frozenset("آیا چرا چطور چگونه چه کدام کی کجا چند".split())
VERB_WORDS = frozenset("""کنیم کنید کنم کنند کند بکنیم بکنید بسازیم بسازید بسازد شویم شوید شوم شود بشویم بشوید بشود است هست هستند هستیم هستید
باشد باشید باشیم نیست دارد دارند دارید داریم کرد شد بود بدانیم بدهیم ببریم بگیریم برسیم ببینیم بخوریم بخریم بسوزانیم بسوزانید بدهید بشناسیم
بشناسید بیاموزیم بیاموزید بمانیم بنویسیم بنویسید بخوانیم بخوانید بیاوریم بیاورید بروید برویم بخوابیم بخوابید""".split())


def is_verb(word: str) -> bool:
    w = norm(word)
    if w in VERB_WORDS:
        return True
    if w.startswith(("می‌", "نمی‌")) and len(w) >= 5:
        return True
    return len(w) >= 6 and w.startswith("ب") and w.endswith(("یم", "ید"))


LIST_NOUNS = frozenset("""اشتباه اشتباهات نکته نکات روش روش‌ها راه راه‌ها ایده ایده‌ها دلیل دلیل‌ها حرکت حرکت‌ها تمرین تمرین‌ها قدم گام ترفند
ترفندها عادت عادت‌ها غذا غذاها خوراکی خوراکی‌ها مکمل مکمل‌ها مورد موردها باور باورها افسانه افسانه‌ها""".split())
_LEAD_NUM = re.compile(r"^\s*([۰-۹0-9]{1,3})\s+(\S+)\s*(.*)$", re.S)
_PREP_LEAD = re.compile(r"^(?:رایج\s+)?(در|برای|از|به|دربارهٔ|درباره|درباره‌ی|برایِ)\s+(.+)$", re.S)
_RISKY = ("درصد", "تومان", "ریال", "تخفیف", "رایگان", "تضمین", "٪", "%", "$", "€")
_QUOTES = re.compile("[«»\"“”]")
_PAREN = re.compile(r"\(([^()]*)\)|（([^()]*)）")


def norm(word: str) -> str:
    """A word without vowel marks / the ezafe mark and without punctuation on its sides (for comparing)."""
    return _MARKS.sub("", word).strip(_EDGE)


def is_func(word: str) -> bool:
    return norm(word) in FUNC


def dangling(word: str) -> bool:
    """The phrase would stay unfinished on this word: a preposition / conjunction, "+", a word that comes before a noun, or a word carrying the ezafe vowel."""
    w = word.strip(_EDGE)
    n = norm(w)
    return (n in FUNC or n in DETERMINERS or w in ("+", "&") or word.strip().endswith(("\u0650", "\u0654", "\u06c0")) or not n)


def _clean(text) -> str:
    t = _QUOTES.sub("", typo.clean(text))
    t = re.sub(r"[*|]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_DASH = re.compile(r"\s+[—–]\s+")
_CLAUSE_SPLIT = re.compile(r"\s*[؛;]\s*|(?<![0-9۰-۹])\s*[:：]\s+")


def split_paren(text, clause: bool = True) -> tuple[str, str]:
    """"A (B) - C" -> ("A", "B C"): the parenthesis and the part after a dash are split from the main phrase (for the subtitle)."""
    t = _clean(text)
    inner: list[str] = []

    def take(m):
        inner.append((m.group(1) or m.group(2) or "").strip())
        return " "

    t = _PAREN.sub(take, t)
    t = re.sub(r"[()（）]", " ", t)
    parts = _DASH.split(t)
    if len(parts) > 1:
        t = parts[0]
        inner.extend(x.strip() for x in parts[1:])
    # "Title; a description ..." / "Title: a description ...": the part before the semicolon / colon is the title and the rest the explanation (subtitle); otherwise the whole sentence
    # would be the title and be cut inside a compound. A time ("10:30") and sentences without an explanation are left alone.
    cut = _CLAUSE_SPLIT.search(t) if clause else None
    if cut and t[:cut.start()].strip(_EDGE) and len(t[cut.end():].split()) >= 2:
        inner.insert(0, t[cut.end():].strip())
        t = t[:cut.start()]
    return re.sub(r"\s+", " ", t).strip(_EDGE), " ".join(i for i in inner if i).strip(_EDGE)


def _chars(ws: list[str]) -> int:
    return len(" ".join(ws))


def clip(text: str, max_words: int, max_chars: int = 0) -> tuple[str, str]:
    """-> (the head of the phrase, the rest). The head never ends on an unfinished word; cutting before the start of a preposition is preferred
    ("a long noun phrase | for beginners at home") and a coordinated group is never cut in half (up to 2 words over the cap are allowed to keep it whole).

    ``max_words`` caps the number of words and ``max_chars`` (optional) the number of letters; when the whole text fits, the rest is empty."""
    ws = _clean(text).strip(_EDGE).split()
    if not ws:
        return "", ""
    n = min(len(ws), max(1, max_words))
    while n > 1 and max_chars and _chars(ws[:n]) > max_chars:
        n -= 1
    if n >= len(ws) and not dangling(ws[-1]):
        return " ".join(ws), ""

    def ok(k: int) -> bool:
        if 1 <= k < len(ws) and (norm(ws[k - 1]), norm(ws[k])) in COMPOUNDS:
            return False                                       # do not cut a two-word concept in half
        return 1 <= k <= len(ws) and not dangling(ws[k - 1])

    def klass(k: int) -> int:
        """0 = the end of the text or before a preposition (best), 1 = the middle of a group, 2 = before a conjunction (breaks a coordinated group), 3 = before a verb."""
        if k >= len(ws):
            return 0
        nxt = norm(ws[k])
        if is_verb(ws[k]):
            return 3                                           # do not separate the verb of this sentence from the sentence
        return 2 if (nxt in COORD or ws[k] in COORD) else (0 if nxt in BOUNDARY else 1)

    cap = max_chars * 1.25 if max_chars else 0
    cands = []
    for k in range(1, min(len(ws), n + 2) + 1):
        if not ok(k):
            continue
        if k > n and not (norm(ws[k - 2]) in COORD or ws[k - 2] in COORD or (k == n + 1 and is_verb(ws[k - 1]))):
            continue                                           # over the cap only to complete a coordinated group or to reach the verb
        if k > n and cap and _chars(ws[:k]) > cap:
            continue
        cands.append((klass(k), k))
    lo = max(1, n - 2)
    for want in (0, 1, 2):
        pool = [k for c, k in cands if c == want and k >= lo and (k >= 2 or n <= 2 or len(ws) == 1)]
        if pool:
            k = max(pool)
            return " ".join(ws[:k]), " ".join(ws[k:])
    if cands:
        k = max(k for _, k in cands)
        return " ".join(ws[:k]), " ".join(ws[k:])
    for k in range(1, len(ws) + 1):                           # the last resort: the first finished word
        if ok(k):
            return " ".join(ws[:k]), " ".join(ws[k:])
    return "", ""


def tail_phrase(rest: str, max_words: int = 6) -> str:
    """The rest of a cut sentence (e.g. "for beginners at home") for the subtitle; complete (no unfinished word), at least two words and without a leading "and"."""
    first = norm((rest or "").split()[0]) if (rest or "").split() else ""
    if not first or first in COORD or (rest or "").split()[0] in COORD:
        return ""
    head, _ = clip(rest, max_words, 40)
    return head if len(head.split()) >= 2 else ""


_STRONG = re.compile(r"\s*[.!؟?؛;\n]+\s*|\s+[—–]\s+|\s*—\s*|[:：]\s+|،\s*")


def first_clause(text, max_words: int = 10, max_chars: int = 64) -> str:
    """From a long description (e.g. the series premise) take the shortest complete and harmless part: the first clause (up to a full stop, a semicolon, a dash, a comma)
    and, when it is still long, up to the nearest natural boundary. A clause with a price / percentage / discount / guarantee is skipped (we make no claims)."""
    body = split_paren(text, clause=False)[0]
    for part in _STRONG.split(body):
        part = part.strip(_EDGE)
        if not part or any(w in part for w in _RISKY) or not typo.is_rtl(part):
            continue
        head, _ = clip(part, max_words, max_chars)
        if len(head.split()) >= 2:
            return head
    return ""


@dataclass
class Topic:
    full: str                 # the cleaned text (without parentheses and markers)
    main: str                 # the main phrase (the same as full, or after the leading number is removed)
    inner: str                # the content of the parenthesis
    kind: str                 # noun | clause
    lead_n: str = ""          # "7" in "7 mistakes in leg training"
    lead_noun: str = ""       # "mistakes"
    lead_prep: str = ""       # "in"
    question: bool = False


def kind_of(text: str) -> tuple[str, bool]:
    ws = _clean(text).split()
    if not ws:
        return "noun", False
    q = norm(ws[0]) in QUESTION_START or _clean(text).rstrip().endswith(("؟", "?"))
    verb = len(ws) >= 3 and is_verb(ws[-1])
    return ("clause" if (q or verb) else "noun"), q


def parse_topic(topic: str) -> Topic:
    main, inner = split_paren(topic)
    full = main
    kind, q = kind_of(main)
    t = Topic(full=full, main=main, inner=inner, kind=kind, question=q)
    m = _LEAD_NUM.match(main)
    if m and norm(m.group(2)) in LIST_NOUNS:
        rest = m.group(3).strip()
        pm = _PREP_LEAD.match(rest)
        t.lead_n = typo.to_fa_digits(m.group(1)).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        t.lead_noun = m.group(2)
        if pm:
            t.lead_prep, t.main = pm.group(1), pm.group(2).strip()
        else:
            t.lead_prep, t.main = "", rest
        t.kind, t.question = "noun", False
        if not t.main:
            t.main = t.lead_noun
    return t


def mark_key(phrase: str) -> str:
    """Mark only ONE key word of the phrase to be coloured ("a b c" -> "a *b* c"): the longest meaningful word."""
    words = _clean(phrase).split()
    if not words:
        return ""
    cand = [i for i, w in enumerate(words) if not dangling(w) and norm(w) not in QUESTION_START and norm(w) not in {"واقعاً", "خیلی"}]
    if not cand:
        cand = list(range(len(words)))
    best = max(cand, key=lambda i: (len(norm(words[i])), -i))
    if len(words) == 1:
        return f"*{words[0]}*"
    return " ".join(f"*{w}*" if i == best else w for i, w in enumerate(words))
