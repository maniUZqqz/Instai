"""The short progress line of a running job («shot clip 3/5», «encoding», «keyframe 2/5») in Persian (audit «ia_core», second pass: the home page and the
queue showed these English words to an owner who reads Persian only).

The code that runs a job keeps writing plain English into `Job.progress_text` (it is a log of what the program does, stored as it was); this module is the
Persian twin the interface shows: `persian(text)` maps the known lines (exact words and «<word> i/n» patterns; the numbers become Persian digits) and
returns every other text unchanged (a file name, an npm or downloader output line, the name of a product). `describe.activity` carries both
(`note_fa` / `note_en`), so nothing about the stored row changes and old rows are translated too.
"""
from __future__ import annotations

import re

from instai.core.fa_digits import fa_digits

EXACT: dict[str, str] = {
    "starting": "در حال شروع", "done": "تمام شد", "rendering": "در حال ساخت", "encoding": "در حال کدگذاریِ ویدئو", "planning": "در حال برنامه‌ریزی",
    "anchor": "ساختِ تصویرِ مرجع", "loudness": "تنظیمِ بلندیِ صدا", "audio check": "بازرسیِ صدا", "quality checks": "بررسیِ کیفیت",
    "measuring before": "اندازه‌گیریِ پیش از آموزش", "training": "در حال آموزش", "measuring after": "اندازه‌گیریِ پس از آموزش",
    "joining, mixing, subtitles": "چسباندن، میکس و زیرنویس", "joining, subtitles": "چسباندن و زیرنویس",
    "boundary frames": "فریم‌های مرز", "colour match and fit": "هم‌رنگ‌سازی و جاسازی", "stitching": "دوختنِ دو سر",
    "starting ComfyUI": "در حال روشن کردنِ ComfyUI", "queued in ComfyUI": "در صفِ ComfyUI", "checking ComfyUI": "در حال بررسیِ ComfyUI",
    "starting the downloader": "در حال شروعِ دانلود", "asking the model": "در حال پرسیدن از مدل",
    "bundling the compositions": "در حال آماده‌سازیِ قطعه‌ها", "bundle ready": "قطعه‌ها آماده است",
    "strategy": "استراتژی", "series plan": "طرحِ سری", "script": "فیلم‌نامه", "storyboard": "استوری‌بورد", "queries": "پرسش‌های جست‌وجو", "claims": "بررسیِ ادعاها",
    "ideas": "ایده‌ها", "speaking": "در حال ساختِ صدا", "captions": "کپشن‌ها", "background": "پس‌زمینه", "search": "جست‌وجو", "brainstorm": "ایده‌پردازی",
    "collecting canon material": "در حال جمع‌کردنِ مواد دربارهٔ اثر", "analysing the canon": "در حال تحلیلِ اثر", "shot narration": "گفتارِ شات‌ها",
}
# (pattern, Persian template): {0}, {1} ... are the groups; a number group is written with Persian digits
RULES: list[tuple[re.Pattern, str]] = [(re.compile(rx), fa) for rx, fa in [
    (r"^stick keyframe (\d+)/(\d+)$", "کلیدِ عروسکِ چوبیِ {0} از {1}"),
    (r"^keyframe (\d+)/(\d+)$", "تصویرِ کلیدیِ {0} از {1}"),
    (r"^narration (\d+)/(\d+)$", "گفتارِ شاتِ {0} از {1}"),
    (r"^video (\d+)/(\d+)$", "ویدئوی شاتِ {0} از {1}"),
    (r"^shot clip (\d+)/(\d+)$", "کلیپِ شاتِ {0} از {1}"),
    (r"^clip (\d+)/(\d+)$", "کلیپِ {0} از {1}"),
    (r"^shot (\d+)/(\d+)$", "شاتِ {0} از {1}"),
    (r"^post (\d+)/(\d+)$", "پستِ {0} از {1}"),
    (r"^part (\d+)/(\d+)$", "بخشِ {0} از {1}"),
    (r"^image (\d+)/(\d+)$", "تصویرِ {0} از {1}"),
    (r"^(\d+)/(\d+) clips$", "{0} کلیپ از {1}"),
    (r"^ComfyUI (\d+)s$", "ComfyUI، {0} ثانیه"),
    (r"^speaking with (.+)$", "ساختِ صدا با {0}"),
    (r"^generating with (.+)$", "ساخت با {0}"),
    (r"^speech with (.+)$", "ساختِ صدا با {0}"),
    (r"^benchmark: (.+)$", "محک: {0}"),
    (r"^fetch: (.+)$", "دریافت: {0}"),
    (r"^(.+) \((\d+)/(\d+)\)$", "{0} ({1} از {2})"),
    (r"^(.{0,40}?)(\d+) / (\d+)$", "{0}فریمِ {1} از {2}"),
]]
_NUM = re.compile(r"^\d+$")


def persian(text: str) -> str:
    """The Persian line for a stored progress text; the text itself when it is not one of the known lines."""
    t = (text or "").strip()
    if not t:
        return ""
    if t in EXACT:
        return EXACT[t]
    for rx, tpl in RULES:
        m = rx.match(t)
        if m:
            return tpl.format(*[fa_digits(g) if _NUM.match(g) else g for g in m.groups()])
    return text
