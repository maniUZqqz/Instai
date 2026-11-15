"""Ready-made "hook" formulas for covers (the cover title of an episode or a series) and the visual concept - the part of ideation that needs no AI.

When the AI is not available (the text model is off, no credit, "local only" ...) the ideas come from here: tested Persian and English formulas for a short, clickable
title built from the REAL facts of the episode (its title, number, hook line, cliffhanger, characters, dialogue, choices), one visual concept per layout and a
background prompt for the image model.

Safety rule: **no statistic, price, percentage or unverified claim is ever made up.** The only number that can appear is the episode number the producer already has.

The context is a plain dict (built from the database by ``instai.covers.service``; the engine never touches the database):
``{lang, kind (episode|series|season|banner), series, episode_number, episode_title, logline, hook, cliffhanger, premise, branch_point, characters[], channel,
dialogue[(speaker, line)], choices[a, b]}``.

SOURCE: rewritten from NMarketing:backend/apps/thumbs/hooks.py @ v3.02 (c23f861) (the idea ranking, the budget of words, the safety rule, the background prompts and
``fit_text`` are kept; the product / audience formulas became episode formulas; every text exists in Persian and English).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from . import phrases, typo

STOP_TAIL = " .؛،:!؟?-–—"
#: the image prompt must contain only Latin letters and simple punctuation
ASCII_PROMPT = re.compile(r"^[A-Za-z0-9 ,.'\-:;()/&+!?\"]+$")
MAX_TITLE_WORDS = 8
EN_STOP = frozenset("a an the of to in on at by for with from and or but as is are was were be been into onto over under about than that this these those his her its their".split())
RISKY = ("درصد", "تومان", "ریال", "تخفیف", "رایگان", "تضمین", "٪", "%", "$", "€", "percent", "free", "guarantee", "discount", "price")

#: the layouts best for each format (in order)
PLATFORM_STYLES = {
    "youtube": ("episode_card", "character_face", "question_hook", "cliffhanger", "number_list", "split_ba", "versus", "news_bold", "neon"),
    "aparat": ("episode_card", "character_face", "news_bold", "cliffhanger", "question_hook", "split_ba", "versus"),
    "telegram": ("news_bold", "episode_card", "character_face", "number_list", "neon"),
    "ig_portrait": ("episode_card", "magazine_cover", "sticker_outline", "minimal_luxury", "quote_card", "cliffhanger", "number_list", "character_face", "split_ba"),
    "ig_square": ("episode_card", "sticker_outline", "choice_split", "quote_card", "minimal_luxury", "character_face", "number_list", "versus"),
    "story": ("cliffhanger", "episode_card", "choice_split", "neon", "character_face", "sticker_outline", "magazine_cover", "question_hook", "quote_card", "number_list"),
    "poster": ("cinema_poster", "retro_poster", "magazine_cover", "episode_card", "neon", "minimal_luxury", "character_face"),
    "yt_banner": ("cinema_poster", "neon", "character_face", "question_hook", "episode_card", "versus"),
    "season_card": ("cinema_poster", "magazine_cover", "episode_card", "retro_poster", "neon", "character_face"),
}

#: the visual concept of each layout: (Persian, English); {t} = the topic
CONCEPTS = {
    "character_face": ("نمای نزدیک و خیلی بزرگِ شخصیتِ اصلیِ «{t}» با حالتِ هیجان یا تعجب؛ پس‌زمینهٔ پرنور با پرتوِ رنگی و فقط چند کلمهٔ درشت با لبهٔ ضخیم.",
                       "A very big close-up of the main character of \"{t}\" looking excited or surprised; a bright background with coloured rays and just a few bold words with a thick edge."),
    "split_ba": ("تصویر دوتکه: دنیای اصلی کم‌رنگ و تیره، دنیای تازه پرنور و رنگی؛ خطِ اریبِ جداکننده و یک عنوانِ کوتاه.",
                 "A two-part picture: the original world faded and dark, the new world bright and colourful; a slanted divider and a short title."),
    "number_list": ("یک عددِ غولیِ برجسته با حاشیه، عنوانِ کوتاه زیرش و شخصیتی کوچک‌تر در کنار؛ بیننده فوراً می‌فهمد این کدام قسمت است.",
                    "A giant raised number with an outline, a short title below it and a smaller character beside it; the viewer sees at once which episode this is."),
    "question_hook": ("علامتِ سؤالِ بزرگ پشتِ شخصیت، نورِ نقطه‌ایِ مرموز و عنوانی به شکلِ پرسش؛ شخصیت با نگاهِ کنجکاو یا تردید.",
                      "A big question mark behind the character, a mysterious spotlight and a title shaped as a question; the character looks curious or unsure."),
    "minimal_luxury": ("زمینهٔ تیره یا کرم، قابِ باریکِ طلایی، شخصیتِ «{t}» با نورِ ملایم و کلی فضای خالی؛ عنوانی آرام و باوقار.",
                       "A dark or cream background, a thin golden frame, the character of \"{t}\" in soft light and plenty of empty space; a calm, dignified title."),
    "cinema_poster": ("رنگ‌بندیِ فیروزه‌ای-نارنجیِ سینمایی، شخصیتِ بزرگ با لبهٔ نور، عنوانِ درشتِ بلوکی در سومِ پایین و سطرِ ریزِ اعتبارها.",
                      "Cinematic teal-orange grading, a big character with a rim light, a big block title in the lower third and a small credits line."),
    "sticker_outline": ("رنگ‌های شادِ پاپ، کنفتی، شخصیت با حاشیهٔ سفیدِ ضخیمِ استیکری و عنوانی کمی کج با دو لبه.",
                        "Cheerful pop colours, confetti, the character with a thick white sticker outline and a slightly tilted title with two edges."),
    "neon": ("زمینهٔ تیرهٔ شبانه با شبکهٔ کفِ پرسپکتیو، نورِ نئونیِ دورِ شخصیت و عنوانِ درخشان؛ حالِ علمی‌تخیلی و شب.",
             "A dark night background with a perspective floor grid, neon light round the character and a glowing title; a sci-fi and night mood."),
    "news_bold": ("تصویر در پس‌زمینه، نوارِ اریبِ تیره با لبهٔ قرمز، تیترِ سفیدِ درشت با یک کلمهٔ زرد و برچسبِ «ویژه».",
                  "The picture behind, a dark slanted band with a red edge, a big white headline with one yellow word and a \"SPECIAL\" label."),
    "versus": ("دو شخصیت رو‌به‌روی هم روی دو رنگِ متضاد، «VS» بزرگ در مرکز و نامِ هر طرف زیرِ تصویرش.",
               "Two characters facing each other on two contrasting colours, a big \"VS\" in the middle and each name under its picture."),
    "magazine_cover": ("جلدِ مجله دربارهٔ «{t}»: نامِ بزرگ در بالا، شخصیتی که سرش کمی روی نام می‌نشیند، یک تیترِ اصلی با نوارِ رنگی و یک تیترِ دوم در پایین.",
                       "A magazine cover about \"{t}\": a big name on top, a character whose head overlaps it a little, a main headline with a colour bar and a second headline below."),
    "retro_poster": ("پوسترِ چاپیِ قدیمی دربارهٔ «{t}»: کاغذِ کرم، خورشیدِ پرتوی با حلقه‌های هم‌مرکز پشتِ شخصیت، نوارِ عنوانِ لبه‌بریده و قابِ دوخطی.",
                     "An old printed poster about \"{t}\": cream paper, a rayed sun with concentric rings behind the character, a notched title ribbon and a double frame."),
    "quote_card": ("جمله‌ای از «{t}» با علامتِ نقل‌قولِ بزرگ، متنِ وسط‌چین با یک کلمهٔ رنگی، خطِ جداکننده و نامِ گوینده؛ شخصیتِ گوینده در دایره.",
                   "A line from \"{t}\" with a big quotation mark, centred text with one coloured word, a divider and the speaker's name; the speaker in a circle."),
    "episode_card": ("نامِ سریال بالا، نشانِ گردِ بزرگِ شمارهٔ قسمت، عنوانِ درشتِ «{t}» و جملهٔ قلاب؛ شخصیتِ ثابتِ سریال کنارِ متن، با رنگ‌های همان سریال.",
                     "The series name on top, a big round episode-number badge, the bold title \"{t}\" and the hook line; the series' fixed character beside the text, in the series' colours."),
    "cliffhanger": ("صحنه‌ای تقریباً سیاه، مخروطِ نور از بالا روی شخصیت و جمله‌ای که آخرِ خطش در تاریکی محو می‌شود؛ برچسبِ «ادامه دارد…».",
                    "An almost black scene, a cone of light from above on the character and a line whose end fades into the dark; a \"to be continued...\" label."),
    "choice_split": ("پرسش در بالا، دو نیمه با دو رنگِ متضاد، حرفِ «الف / ب» و برچسبِ هر گزینه و «یا» در مرکز.",
                     "The question on top, two halves in contrasting colours, an \"A / B\" letter and a plate for each option and \"OR\" in the middle."),
}

#: the background prompt of each layout (English: the image model does not read Persian and draws no text); always "no text and no people"
BG_PROMPTS = {
    "character_face": "vibrant studio backdrop with soft rays of light and a bold saturated colour gradient, strong contrast, empty space on both sides",
    "split_ba": "clean two-tone backdrop with a diagonal split of light, a bright side and a dull side, minimal",
    "number_list": "bold colourful abstract geometric background with halftone dots and diagonal stripes, flat pop-art style",
    "question_hook": "dark moody spotlight background with subtle fog and a glowing centre, mysterious atmosphere, deep shadows",
    "minimal_luxury": "dark elegant backdrop with soft golden bokeh light, minimal, smooth gradient, empty centre",
    "cinema_poster": "cinematic teal and orange atmospheric background, volumetric light beams, drifting fog, film grain, wide empty space",
    "sticker_outline": "playful bright pop background with confetti shapes and flat colours, cheerful, high saturation",
    "neon": "cyberpunk neon grid floor in perspective, dark purple and cyan glow, synthwave night sky",
    "news_bold": "dark blurred newsroom-like background with bokeh lights and a faint blue glow, shallow depth of field",
    "versus": "dramatic split lighting backdrop, cool blue on one side and warm red on the other, energy burst in the middle",
    "magazine_cover": "clean glossy backdrop with a soft light gradient and subtle paper texture, elegant magazine mood, empty space",
    "retro_poster": "vintage printed paper texture with a faded sunburst and subtle halftone grain, warm cream and muted colours, retro poster mood, empty centre",
    "quote_card": "soft out-of-focus abstract gradient background with gentle bokeh light, calm and moody, dark tones, plenty of empty space",
    "episode_card": "bold colourful abstract backdrop with diagonal bands and halftone dots, flat pop style, calm empty area on one side",
    "cliffhanger": "dark moody scene lit by a single cone of light from above, deep shadows, drifting fog, cinematic, a lot of empty dark space",
    "choice_split": "two contrasting colour fields split by a diagonal line, one warm one cool, soft light rays, minimal and clean",
}
BG_SUFFIX = ", no text, no letters, no logos, no watermark, no people, high quality"


def fa_digits(value) -> str:
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def digits(value, lang: str) -> str:
    return fa_digits(value) if lang == "fa" else str(value)


def preferred_styles(fmt: str) -> tuple[str, ...]:
    return PLATFORM_STYLES.get(fmt) or PLATFORM_STYLES["youtube"]


def bg_prompt(style: str, look: str = "", scene: str = "") -> str:
    """The background prompt: the layout's scene + the series look's image prompt + an optional scene line, then the "no text / no people" suffix."""
    base = BG_PROMPTS.get(style) or BG_PROMPTS["character_face"]
    extra = "".join(", " + x.strip(" ,") for x in (scene, look) if x and x.strip(" ,"))
    return base + extra + BG_SUFFIX


def _rot(seed: str, n: int) -> int:
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % max(1, n)


# ───────────────────────────── words (both languages)

def en_clip(text: str, max_words: int, max_chars: int = 0) -> tuple[str, str]:
    """English: (the head, the rest). The head never ends on an article / preposition / conjunction."""
    ws = re.sub(r"\s+", " ", re.sub(r"[*|]", " ", str(text or ""))).strip(STOP_TAIL).split()
    if not ws:
        return "", ""
    n = min(len(ws), max(1, max_words))
    while n > 1 and max_chars and len(" ".join(ws[:n])) > max_chars:
        n -= 1
    while n > 1 and ws[n - 1].lower().strip(STOP_TAIL) in EN_STOP:
        n -= 1
    return " ".join(ws[:n]), " ".join(ws[n:])


def en_mark(phrase: str) -> str:
    """English: mark ONE key word (the longest that is not a stop word) for the highlight colour."""
    ws = phrase.split()
    if not ws:
        return ""
    cand = [i for i, w in enumerate(ws) if w.lower().strip(STOP_TAIL) not in EN_STOP] or list(range(len(ws)))
    best = max(cand, key=lambda i: (len(ws[i].strip(STOP_TAIL)), -i))
    if len(ws) == 1:
        return f"*{ws[0]}*"
    return " ".join(f"*{w}*" if i == best else w for i, w in enumerate(ws))


def clip(text: str, words: int, lang: str, chars: int = 0) -> tuple[str, str]:
    return phrases.clip(text, words, chars) if lang == "fa" else en_clip(text, words, chars)


def mark(text: str, lang: str) -> str:
    return phrases.mark_key(text) if lang == "fa" else en_mark(text)


def short_topic(topic: str, max_words: int = 4, lang: str = "fa") -> str:
    """The topic shortened without ever cutting on an unfinished word."""
    if lang == "fa":
        return phrases.clip(phrases.split_paren(topic)[0], max_words)[0]
    return en_clip(topic, max_words)[0]


def first_clause(text: str, lang: str, words: int = 9, chars: int = 60) -> str:
    """The shortest complete and harmless clause of a longer text (a clause with a risky word is skipped)."""
    if lang == "fa":
        return phrases.first_clause(text, words, chars)
    for part in re.split(r"\s*[.!?;\n]+\s*|\s+[—–-]\s+|:\s+|,\s*", str(text or "")):
        part = part.strip(STOP_TAIL)
        if not part or any(w in part.lower() for w in RISKY):
            continue
        head, _ = en_clip(part, words, chars)
        if len(head.split()) >= 2:
            return head
    return ""


def fit_text(raw: str, limit: int) -> str:
    """Shorten the text to ``limit`` letters WITHOUT cutting a word: complete clauses first (up to ";" / "." / a dash), then the nearest word boundary (and then "...")."""
    s = re.sub(r"\s+", " ", str(raw or "")).strip()
    if len(s) <= limit:
        return s
    out = ""
    for part in re.split(r"(?<=[؛.!؟;])\s+|\s+[—–]\s+", s):
        cand = f"{out} {part}".strip() if out else part
        if len(cand) <= limit:
            out = cand
        else:
            break
    if out:
        return out.rstrip("؛; ").rstrip()
    cut = s[: max(1, limit - 1)]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    head, _ = phrases.clip(cut, 999)
    return (head or cut).rstrip(" ,،؛:-—") + "…"


# ───────────────────────────── the context

@dataclass
class Ctx:
    lang: str = "fa"
    kind: str = "episode"
    series: str = ""
    episode_number: int | None = None
    episode_title: str = ""
    logline: str = ""
    hook: str = ""
    cliffhanger: str = ""
    premise: str = ""
    branch_point: str = ""
    characters: tuple = ()
    channel: str = ""
    dialogue: tuple = ()
    choices: tuple = ()

    @property
    def fa(self) -> bool:
        return self.lang == "fa"

    @property
    def topic(self) -> str:
        return self.episode_title or self.series or self.hook or self.logline

    def ep_word(self) -> str:
        return "قسمت" if self.fa else "EP"

    def ep_badge(self) -> str:
        return f"{self.ep_word()} {digits(self.episode_number, self.lang)}" if self.episode_number else ""

    def ep_long(self) -> str:
        return (f"قسمت {fa_digits(self.episode_number)}" if self.fa else f"Episode {self.episode_number}") if self.episode_number else ""


def make_ctx(d: dict) -> Ctx:
    """A dict -> a clean Ctx (missing keys are empty; text is trimmed; at most 6 characters / 4 dialogue lines)."""
    def s(v, n=300):
        return re.sub(r"\s+", " ", str(v or "")).strip()[:n]

    try:
        no = int(d.get("episode_number")) if d.get("episode_number") not in (None, "", 0) else None
    except (TypeError, ValueError):
        no = None
    return Ctx(lang="en" if d.get("lang") == "en" else "fa", kind=d.get("kind") if d.get("kind") in ("episode", "series", "season", "banner") else "episode",
               series=s(d.get("series"), 120), episode_number=no, episode_title=s(d.get("episode_title"), 160), logline=s(d.get("logline"), 400), hook=s(d.get("hook"), 300),
               cliffhanger=s(d.get("cliffhanger"), 300), premise=s(d.get("premise"), 500), branch_point=s(d.get("branch_point"), 300),
               characters=tuple(s(x, 60) for x in (d.get("characters") or []) if s(x, 60))[:6], channel=s(d.get("channel"), 60),
               dialogue=tuple((s(a, 60), s(b, 200)) for a, b in ((x if isinstance(x, (list, tuple)) and len(x) == 2 else ("", x)) for x in (d.get("dialogue") or []))
                              if s(b, 200))[:4],
               choices=tuple(s(x, 60) for x in (d.get("choices") or []) if s(x, 60))[:2])


# ───────────────────────────── the formulas

@dataclass(frozen=True)
class Formula:
    key: str
    label_fa: str
    label_en: str
    style: str
    needs: tuple = ()            # facts the formula needs: number, hook, cliff, branch, choices, dialogue, cast2, series
    kinds: tuple = ("episode", "series", "season", "banner")


def _base(c: Ctx) -> dict:
    return {"title": "", "subtitle": "", "kicker": "", "number": "", "badge": "", "tagline": "", "credits": "", "channel": c.channel, "label_a": "", "label_b": ""}


def _head(c: Ctx, text: str, words: int = MAX_TITLE_WORDS) -> str:
    """The head of a phrase that fits a title (English needs about two more words than Persian for the same meaning)."""
    return clip(text, words + (0 if c.fa else 2), c.lang, 70)[0]


def _hook_line(c: Ctx) -> str:
    """The hook line for a subtitle: the script's hook, else the first clause of the logline."""
    src = c.hook or c.logline
    return first_clause(src, c.lang, 9, 62) if src else ""


def _f_episode_card(c: Ctx) -> dict:
    d = _base(c)
    title = c.episode_title or c.hook or c.series
    d.update(title=mark(_head(c, title, 7), c.lang), subtitle=_hook_line(c) if c.episode_title else "", kicker=c.series, number=digits(c.episode_number, c.lang) if c.episode_number else "")
    return d


def _f_cliffhanger(c: Ctx) -> dict:
    d = _base(c)
    line = c.cliffhanger or c.hook or c.episode_title
    head = _head(c, line, 9)
    d.update(title=mark(head.rstrip("؟?…. "), c.lang), kicker=" · ".join(x for x in (c.series, c.ep_long()) if x))
    return d


def _f_question(c: Ctx) -> dict:
    d = _base(c)
    t = c.hook or c.episode_title or c.series
    if re.search(r"[؟?]\s*$", t) or (c.fa and phrases.kind_of(t)[1]):
        head = _head(c, t, 9).rstrip("؟?")
        title = mark(head, c.lang) + ("؟" if c.fa else "?")
    else:
        m = mark(_head(c, c.episode_title or t, 4), c.lang)
        title = f"ماجرای {m} چه بود؟" if c.fa else f"What really happened with {m}?"
    d.update(title=title, kicker=c.series, subtitle=c.ep_long())
    return d


def _f_what_if(c: Ctx) -> dict:
    d = _base(c)
    d.update(title=mark(_head(c, c.episode_title or c.series, 6), c.lang), subtitle=_head(c, c.branch_point, 8), kicker=c.series,
             label_a="دنیای تازه" if c.fa else "THE NEW WORLD", label_b="دنیای اصلی" if c.fa else "THE ORIGINAL")
    return d


def _f_number(c: Ctx) -> dict:
    d = _base(c)
    d.update(title=_head(c, c.episode_title or c.hook or c.series, 6), subtitle=c.series, number=digits(c.episode_number, c.lang))
    return d


def _f_versus(c: Ctx) -> dict:
    d = _base(c)
    a, b = c.characters[0], c.characters[1]
    d.update(title=(f"{a} یا {b}؟" if c.fa else f"{a} or {b}?"), subtitle=_head(c, c.episode_title, 6), label_a=short_topic(a, 3, c.lang), label_b=short_topic(b, 3, c.lang))
    return d


def _f_choice(c: Ctx) -> dict:
    d = _base(c)
    q = c.hook or c.cliffhanger or c.episode_title
    head = _head(c, q, 9).rstrip("؟?")
    d.update(title=mark(head, c.lang) + ("؟" if c.fa else "?"), subtitle=c.series, label_a=c.choices[0], label_b=c.choices[1])
    return d


def _f_poster(c: Ctx) -> dict:
    d = _base(c)
    cast = " | ".join(c.characters[:4])
    credits = " | ".join(x for x in ((("شخصیت‌ها: " if c.fa else "Characters: ") + cast) if cast else "", (("کانال: " if c.fa else "Channel: ") + c.channel) if c.channel else "") if x)
    d.update(title=_head(c, c.series or c.episode_title, 5), tagline=first_clause(c.premise or c.logline, c.lang, 8, 56), subtitle=c.ep_long() if c.kind == "episode" else "",
             credits=credits)
    if c.kind == "episode" and c.episode_title:
        d["subtitle"] = (c.ep_long() + (": " if c.ep_long() else "") + _head(c, c.episode_title, 5)).strip()
    return d


def _f_quote(c: Ctx) -> dict:
    d = _base(c)
    who, line = c.dialogue[0]
    d.update(title=mark(_head(c, line, 14), c.lang), subtitle=who, kicker=c.series)
    return d


def _f_news(c: Ctx) -> dict:
    d = _base(c)
    d.update(title=mark(_head(c, c.episode_title or c.series, 7), c.lang), subtitle=_hook_line(c))
    return d


def _f_magazine(c: Ctx) -> dict:
    d = _base(c)
    d.update(title=_head(c, c.series or c.episode_title, 3), subtitle=mark(_head(c, c.episode_title or c.hook, 7), c.lang) if c.series else "", tagline=_hook_line(c),
             kicker=c.ep_long(), badge=c.ep_badge())
    return d


def _f_character(c: Ctx) -> dict:
    d = _base(c)
    d.update(title=mark(_head(c, c.episode_title or c.hook or c.series, 5), c.lang), subtitle=_hook_line(c), kicker=c.series, badge=c.ep_badge() or ("جدید" if c.fa else "NEW"))
    return d


def _f_plain(c: Ctx) -> dict:
    d = _base(c)
    d.update(title=mark(_head(c, c.episode_title or c.series or c.hook, 5), c.lang), subtitle=_hook_line(c), kicker=c.series)
    return d


def _f_retro(c: Ctx) -> dict:
    d = _f_plain(c)
    d.update(tagline=first_clause(c.premise or c.logline, c.lang, 6, 40), badge=c.ep_badge())
    return d


FORMULAS: tuple[tuple[Formula, object], ...] = (
    (Formula("episode_card", "کارتِ قسمت", "Episode card", "episode_card", ("series",), ("episode",)), _f_episode_card),
    (Formula("cliffhanger", "پایانِ معلق", "Cliffhanger", "cliffhanger", ("cliff_or_hook",), ("episode",)), _f_cliffhanger),
    (Formula("question", "سؤالِ کنجکاوی", "Curiosity question", "question_hook", ("topic",), ("episode",)), _f_question),
    (Formula("what_if", "اگر… (قبل و بعد)", "What if... (before / after)", "split_ba", ("branch",), ("episode", "series")), _f_what_if),
    (Formula("number", "شمارهٔ قسمت", "Episode number", "number_list", ("number",), ("episode",)), _f_number),
    (Formula("versus", "رویارویی دو شخصیت", "Two characters face off", "versus", ("cast2",), ("episode", "series")), _f_versus),
    (Formula("choice", "انتخابِ الف یا ب", "A or B choice", "choice_split", ("choices",), ("episode", "series")), _f_choice),
    (Formula("poster", "پوستر", "Poster", "cinema_poster", ("topic",), ("episode", "series", "season", "banner")), _f_poster),
    (Formula("quote", "دیالوگِ قسمت", "A line of the episode", "quote_card", ("dialogue",), ("episode",)), _f_quote),
    (Formula("news", "تیترِ ویژه", "Special headline", "news_bold", ("topic",), ("episode",)), _f_news),
    (Formula("magazine", "جلدِ مجله", "Magazine cover", "magazine_cover", ("series",), ("episode", "series", "season")), _f_magazine),
    (Formula("character", "چهرهٔ شخصیت", "Character face", "character_face", ("topic",), ("episode", "series", "season", "banner")), _f_character),
    (Formula("sticker", "استیکرِ شاد", "Cheerful sticker", "sticker_outline", ("topic",), ("episode", "series")), _f_plain),
    (Formula("neon", "حالِ شبانه", "Night mood", "neon", ("topic",), ("episode", "series", "season", "banner")), _f_plain),
    (Formula("minimal", "آرام و مینیمال", "Calm and minimal", "minimal_luxury", ("topic",), ("episode", "series", "season")), _f_plain),
    (Formula("retro", "پوسترِ قدیمی", "Retro poster", "retro_poster", ("topic",), ("episode", "series", "season")), _f_retro),
)


def _available(f: Formula, c: Ctx) -> bool:
    if c.kind not in f.kinds:
        return False
    for need in f.needs:
        if need == "series" and not (c.series or c.episode_title):
            return False
        if need == "topic" and not c.topic:
            return False
        if need == "number" and not c.episode_number:
            return False
        if need == "branch" and not (c.branch_point or c.logline):
            return False
        if need == "choices" and len(c.choices) < 2:
            return False
        if need == "dialogue" and not c.dialogue:
            return False
        if need == "cast2" and len(c.characters) < 2:
            return False
        if need == "cliff_or_hook" and not (c.cliffhanger or c.hook):
            return False
    return True


def rule_ideas(ctx: dict | Ctx, *, fmt: str = "youtube", count: int = 6, variation: int = 0) -> list[dict]:
    """The deterministic ideas (no AI): a list of idea dicts with different layouts, best first for the format."""
    c = ctx if isinstance(ctx, Ctx) else make_ctx(ctx)
    if not c.topic:
        return []
    pref = list(preferred_styles(fmt))

    def rank(item):
        f = item[0]
        return (pref.index(f.style) if f.style in pref else 90, _rot(f"{c.topic}|{f.key}|{variation}", 1000))

    ideas: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for f, fn in sorted((x for x in FORMULAS if _available(x[0], c)), key=rank):
        if len(ideas) >= count:
            break
        d = fn(c)
        if not typo.plain(d.get("title", "")):
            continue
        key = (typo.plain(d["title"]), f.style)
        if key in seen:
            continue
        seen.add(key)
        topic = short_topic(c.topic, 4, c.lang)
        d.update(style=f.style, formula=f.key, formula_label_fa=f.label_fa, formula_label_en=f.label_en, source="rules", mood="",
                 concept_fa=CONCEPTS[f.style][0].format(t=topic), concept_en=CONCEPTS[f.style][1].format(t=topic), bg_prompt_en=bg_prompt(f.style))
        ideas.append(d)
    return ideas
