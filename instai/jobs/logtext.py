"""Job log lines in the interface language (audit 2026-11-14: the report and the queue showed «started (attempt 1/3) by <host>» in English).

A line written with a CODE and PARAMETERS (`queue.log_job(job, text, code="started", params={...})`) is rendered here in Persian or English
by the API (`text_fa` / `text_en`); the stored `message` stays the technical English text (search, old rows, free text). Old rows are never
rewritten: a row without a code is shown as it is. Numbers (ints / floats) become Persian digits in the Persian text.
"""
from __future__ import annotations

import re

from instai.core.fa_digits import fa_digits

TEXT: dict[str, tuple[str, str]] = {
    "queued": ("در صف قرار گرفت", "queued"),
    "started": ("اجرا شد (تلاش {attempt} از {max}) روی «{worker}»", "started (attempt {attempt}/{max}) by {worker}"),
    "succeeded": ("در {seconds} ثانیه تمام شد", "succeeded in {seconds}s"),
    "succeeded_plain": ("تمام شد", "succeeded"),
    "failed_retry": ("ناموفق (تلاش {attempt} از {max})؛ {delay} ثانیهٔ دیگر دوباره امتحان می‌شود: {detail}",
                     "failed (attempt {attempt}/{max}); retry in {delay}s: {detail}"),
    "failed": ("ناموفق: {detail}", "failed: {detail}"),
    "cancelled": ("لغو شد", "cancelled"),
    "cancelled_waiting": ("هنگام انتظار لغو شد", "cancelled while waiting"),
    "requeued": ("دوباره در صف قرار گرفت", "re-queued"),
    "waiting": ("در انتظار: {reason}", "waiting ({code}): {reason}"),
    "lease_lost_n": ("برنامهٔ کارگر ایستاد (بارِ {n})؛ کار دوباره در صف گذاشته شد", "lease expired (worker stopped?) for the {n}th time"),
    "lease_lost": ("برنامهٔ کارگر ایستاد؛ کار بدون صرفِ یک تلاش دوباره در صف گذاشته شد", "lease expired (worker stopped?); re-queued without using an attempt"),
    "rescheduled": ("زمان‌بندی تازه: {when}", "rescheduled: {when}"),
    "clips_skipped": ("کلیپ‌های ویدئویی ساخته نشد و به‌جایشان تصویرِ ثابت با حرکتِ دوربین می‌آید: {reason}",
                      "video clips skipped, a still with a camera move is used instead: {reason}"),
    "mixing": ("ترکیبِ {n} ردیفِ صدا", "mixing {n} track(s)"),
    "task_sent": ("کارِ {task} ({kind}) برای رایانهٔ «{worker}» فرستاده شد", "task {task} ({kind}) sent to worker {worker}"),
    "worker_failed": ("رایانهٔ «{worker}» ناموفق بود ({detail})؛ رایانهٔ دیگری امتحان می‌شود", "worker {worker} failed ({detail}); trying another device"),
    "composition": ("قطعهٔ «{id}»: {width}×{height}، {fps} فریم بر ثانیه، {frames} فریم", "composition {id}: {width}x{height} at {fps} fps, {frames} frames"),
    "dl_to_worker": ("دانلودِ «{packages}» روی رایانهٔ «{worker}» انجام می‌شود", "download of {packages} goes to worker PC {worker}"),
    "ollama_pull": ("مدلِ «{model}» از Ollama گرفته می‌شود", "pulling the Ollama model {model}"),
    "comfy_not_started": ("ComfyUI روشن نشد: {detail}", "ComfyUI could not be started: {detail}"),
    "bilingual": ("{fa}", "{en}"),
}

# technical notes the pipeline writes in English (provenance keeps them); the job log shows the Persian twin. (regex, Persian template with {1} {2} ...)
NOTE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^shot (\d+)\.(\d+): Rhubarb is not installed; amplitude-driven mouth used$"),
     "شاتِ {1}٫{2}: Rhubarb نصب نیست؛ دهانِ شخصیت از روی بلندیِ صدا حرکت می‌کند"),
    (re.compile(r"^shot (\d+)\.(\d+): Rhubarb failed \((.*)\); amplitude-driven mouth used instead$"),
     "شاتِ {1}٫{2}: Rhubarb کار نکرد ({3})؛ دهانِ شخصیت از روی بلندیِ صدا حرکت می‌کند"),
    (re.compile(r"^shot (\d+)\.(\d+): the rig is not approved yet \(draft rig used\)$"),
     "شاتِ {1}٫{2}: عروسکِ این شخصیت هنوز تأیید نشده؛ نسخهٔ پیش‌نویسِ آن به کار رفت"),
]


def note_fa(note: str) -> str:
    """The Persian twin of a technical English pipeline note, or '' when there is none."""
    for rx, tpl in NOTE_RULES:
        m = rx.match(note)
        if m:
            out = tpl
            for i, g in enumerate(m.groups(), 1):
                out = out.replace("{%d}" % i, fa_digits(g) if g.isdigit() else g)
            return out
    return ""


class _Safe(dict):
    def __missing__(self, key):          # a missing parameter must never break the page
        return ""


def render(code: str, params: dict | None, lang: str) -> str:
    """The line for `code` in 'fa' or 'en' ('' when the code is unknown: the caller shows the stored message)."""
    row = TEXT.get(code)
    if not row:
        return ""
    tpl = row[0] if lang == "fa" else row[1]
    p = _Safe()
    for k, v in (params or {}).items():
        p[k] = fa_digits(v) if (lang == "fa" and isinstance(v, (int, float)) and not isinstance(v, bool)) else ("" if v is None else str(v))
    try:
        return tpl.format_map(p)
    except (ValueError, IndexError):
        return ""


def texts(code: str, params: dict | None) -> tuple[str, str]:
    """(Persian, English) of a coded line; ('', '') for an old / free-text row."""
    if not code:
        return "", ""
    return render(code, params, "fa"), render(code, params, "en")
