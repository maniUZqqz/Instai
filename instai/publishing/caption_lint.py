"""A quality gate for the caption of a post, before the owner copies it into the app.

SOURCE: ported from NMarketing:backend/apps/content/caption_guard.py @ v3.02 (c23f861), adapted for series/episode producers: the shop's rules are gone (the
"never say" list, price reminders), the image-prompt vocabulary is InstAI's (storyboard and style prompts), the hashtag repair knows the page's own words, and every
warning comes in Persian AND English. The platform limits are NEW and labelled approximate.

A local model that writes Persian copy is fast and tireless and now and then wrong in ways a tired owner does not see at 11 p.m.: a number that lost its last digit
(«۶۰۰٬۰۰»), the same line printed twice, an instruction meant for the image model that ended up in the post, a caption that stops in the middle of a sentence.
None of that is worth blocking a post over, but all of it is worth SAYING before it is copied.

So this module never rewrites and never rejects. It reads a caption and returns plain warnings (`level: "warn"`) and notes (`level: "note"`: approximate platform
limits); the screen shows them next to the text and the owner decides. Every rule is arithmetic or a short list - no model is asked, so it works when the AI is off.
"""
from __future__ import annotations

import re

from . import hashtags as hashtag_tools
from .fatext import en_digits, fa_digits, normalize

#: a number whose thousands separator is followed by 1-2 digits, i.e. one that lost its last zero(s): «600,00» «۶۰۰٬۰۰»
_BROKEN_NUMBER = re.compile(r"(?<![\d.,٬،])(\d{1,3}[,٬،]\d{1,2})(?![\d,٬،])")

_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆↔-↪⌚-⏿️]")
#: more than this many emoji in one caption reads as noise, not warmth
MAX_EMOJI = 6
#: a repeated phrase shorter than this is probably a connective, not a copy-paste
MIN_REPEAT_CHARS = 8

#: words that belong in an instruction to an IMAGE model, not in a post (compared in the `normalize` form). InstAI's own prompts are English («vertical 9:16, clean
#: composition» is in the storyboard fallback), so both the English fragments and the Persian words for "prompt" are listed.
_PROMPT_LEAK = re.compile(
    r"(بدون\s*(?:آدم|انسان|متن)|(?:تصویر|عکس)\s*زمینه|پرامپت|دستور\s*ساخت\s*(?:تصویر|عکس)|\bprompt\b|negative\s+prompt|vertical\s+9\s*:\s*16|clean\s+composition|"
    r"highly\s+detailed|ultra[\s-]*detailed|\bmasterpiece\b|\b8k\b|\bcinematic\s+lighting\b|--ar\s+\d|\bkeyframe\b|نمای\s*کلوز)")

#: a long text should end where a sentence ends (or on an emoji)
_SENTENCE_END = tuple(".!؟?…)»\"'")
_LONG_MIN_CHARS = 120

#: APPROXIMATE limits of the networks (they change; the screens say so). Instagram: caption about 2200 characters with about 30 hashtags. YouTube: title about 100,
#: description about 5000, tags about 500 characters in all.
LIMITS = {"instagram": {"caption": 2200, "tags": 30}, "youtube": {"title": 100, "description": 5000, "tags_chars": 500}}


def _warn(out: list, seen: set, code: str, fa: str, en: str, key: str = "", level: str = "warn") -> None:
    if (code, key) not in seen:
        seen.add((code, key))
        out.append({"code": code, "level": level, "message": fa, "message_en": en})


def _sentences(text: str) -> list[str]:
    parts = [p.strip(" \t\n.!؟?،,;؛…-—") for p in re.split(r"[.!؟?\n]+", normalize(text))]
    return [p for p in parts if p]


def _repeated_sentence(text: str) -> str | None:
    """A sentence/phrase that appears twice (the classic «لینک در بایو. لینک در بایو», or the same call to action at the top and at the bottom), or None."""
    seen: set[str] = set()
    for p in _sentences(text):
        if len(p) < MIN_REPEAT_CHARS:
            continue
        if p in seen:
            return p
        seen.add(p)
    return None


def check(caption: str, tags: list | None = None, *, networks: list[str] | tuple = (), title: str = "", extra_words=frozenset()) -> list[dict]:
    """Warnings for one caption and its hashtags: `[{code, level, message, message_en}]`, possibly empty.

    `networks` = the network keys the page posts to (`render/delivery.py`): the approximate limits are checked only for the families that apply. `title` = the
    episode title (YouTube's title limit). `extra_words` = the page's own vocabulary for the hashtag repair (`hashtags.page_vocabulary`)."""
    text = caption or ""
    tags = [t for t in (tags or []) if isinstance(t, str) and t.strip()]
    out: list[dict] = []
    seen: set = set()
    plain = en_digits(text)
    for m in _BROKEN_NUMBER.finditer(plain):
        _warn(out, seen, "broken_number", f"عددِ ناقص: «{fa_digits(m.group(1))}» - احتمالاً صفرِ آخر افتاده است.",
              f"A number looks cut short: '{m.group(1)}' - the last zero is probably missing.", m.group(1))
    rep = _repeated_sentence(text)
    if rep:
        _warn(out, seen, "repeated", f"یک جمله دو بار آمده: «{rep}» (مثلاً دعوت به کار دوبار نوشته شده).", f"A sentence appears twice: '{rep}' (for example the call to action is written twice).", rep)
    leak = _PROMPT_LEAK.search(normalize(text))
    if leak:
        _warn(out, seen, "image_prompt", f"به نظر می‌رسد دستورِ ساختِ تصویر وارد متن شده: «{leak.group(1)}» - از متنِ پست حذفش کنید.",
              f"An instruction meant for the image model seems to have got into the post: '{leak.group(1)}' - take it out of the text.", leak.group(1))
    emoji = len(_EMOJI.findall(text))
    if emoji > MAX_EMOJI:
        _warn(out, seen, "emoji", f"ایموجی زیاد است ({fa_digits(emoji)}).", f"There are many emoji ({emoji}).")
    body = text.rstrip()
    if len(body) >= _LONG_MIN_CHARS and not body.endswith(_SENTENCE_END) and not _EMOJI.search(body[-1]):
        _warn(out, seen, "truncated", "متن ناتمام به نظر می‌رسد (جمله به نقطه نرسیده) - پیش از انتشار تکمیلش کنید.",
              "The text looks unfinished (the last sentence does not end) - complete it before posting.")
    tag_keys: dict[str, str] = {}
    for tag in tags:
        fixed = hashtag_tools.repair(tag, extra_words)
        if hashtag_tools.clean(fixed) != hashtag_tools.clean(tag):
            _warn(out, seen, "glued_hashtag", f"هشتگِ چسبیده: «{tag}» ← «{fixed}» (در بسته اصلاح‌شده می‌آید؛ برای دائمی‌شدن در تنظیمات ویرایشش کنید).",
                  f"A glued hashtag: '{tag}' -> '{fixed}' (the package carries the repaired form; edit it in the settings to make it permanent).", tag)
        elif hashtag_tools.is_glued(tag, extra_words):
            _warn(out, seen, "glued_hashtag", f"هشتگِ بلند بدونِ «_»: «{tag}» - اگر چند واژه است با «_» جدایشان کنید.",
                  f"A long hashtag without '_': '{tag}' - if it is several words, separate them with '_'.", tag)
        key = normalize(hashtag_tools.clean(fixed))
        if key in tag_keys:
            _warn(out, seen, "duplicate_hashtag", f"هشتگِ تکراری: «{tag}».", f"A duplicate hashtag: '{tag}'.", key)
        tag_keys[key] = tag
    # --- approximate platform limits (notes, never blockers)
    from instai.render import delivery

    groups = {delivery.NETWORKS[n]["group"] for n in networks if n in delivery.NETWORKS}
    if "instagram" in groups:
        lim = LIMITS["instagram"]
        full = text + ("\n\n" + " ".join("#" + hashtag_tools.clean(t) for t in tags) if tags else "")
        if len(full) > lim["caption"]:
            _warn(out, seen, "ig_caption_long", f"کپشن با هشتگ‌ها {fa_digits(len(full))} نویسه است؛ اینستاگرام حدود {fa_digits(lim['caption'])} نویسه می‌پذیرد (تقریبی).",
                  f"The caption with its hashtags is {len(full)} characters; Instagram takes about {lim['caption']} (approximate).", level="note")
        if len(tags) > lim["tags"]:
            _warn(out, seen, "ig_tags_many", f"{fa_digits(len(tags))} هشتگ دارید؛ اینستاگرام حدود {fa_digits(lim['tags'])} هشتگ می‌پذیرد (تقریبی).",
                  f"There are {len(tags)} hashtags; Instagram takes about {lim['tags']} (approximate).", level="note")
    if "youtube" in groups:
        lim = LIMITS["youtube"]
        first_line = text.strip().split("\n")[0] if text.strip() else ""
        t = title or first_line
        if len(t) > lim["title"]:
            _warn(out, seen, "yt_title_long", f"عنوان {fa_digits(len(t))} نویسه است؛ یوتیوب حدود {fa_digits(lim['title'])} نویسه می‌پذیرد (تقریبی).",
                  f"The title is {len(t)} characters; YouTube takes about {lim['title']} (approximate).", level="note")
        if len(text) > lim["description"]:
            _warn(out, seen, "yt_description_long", f"توضیح {fa_digits(len(text))} نویسه است؛ یوتیوب حدود {fa_digits(lim['description'])} نویسه می‌پذیرد (تقریبی).",
                  f"The description is {len(text)} characters; YouTube takes about {lim['description']} (approximate).", level="note")
        chars = sum(len(hashtag_tools.clean(x)) for x in tags)
        if chars > lim["tags_chars"]:
            _warn(out, seen, "yt_tags_long", f"مجموع نویسه‌های برچسب‌ها {fa_digits(chars)} است؛ یوتیوب حدود {fa_digits(lim['tags_chars'])} می‌پذیرد (تقریبی).",
                  f"The tags add up to {chars} characters; YouTube takes about {lim['tags_chars']} (approximate).", level="note")
    return out
