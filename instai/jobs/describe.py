"""The queue says exactly what is happening: for every job, in plain Persian (and English), WHAT step it is, WHAT IT IS FOR (page, series,
episode, shot), WHICH model on WHICH device (GPU / CPU), and a live line (tokens so far, sampler step x of y).

`activity(job)` is a pure function of the job row (kind, payload, links, `live` written by the running code through JobContext.live, the waiting
reason). It never does slow work; the few lookups (series title) are memoised in the optional `cache` so a list of jobs costs one query per series.
"""
from __future__ import annotations

import re

from django.utils import timezone

# kind -> (Persian, English): the step in plain words
KIND_TEXT: dict[str, tuple[str, str]] = {
    "story.strategy": ("پیشنهاد استراتژی صفحه", "Page strategy proposal"),
    "story.plan": ("طرح مجموعه و قسمت‌ها", "Series and episode plan"),
    "story.script": ("نوشتن فیلم‌نامه", "Writing the script"),
    "story.storyboard": ("ساخت استوری‌بورد", "Building the storyboard"),
    "story.research": ("پژوهش و منبع‌یابی", "Research and sources"),
    "story.continuity": ("به‌روزرسانی حافظهٔ داستان", "Updating the story memory"),
    "studio.source_search": ("جست‌وجوی سریال", "Series search"),
    "studio.ideas": ("ایده‌پردازی", "Brainstorming ideas"),
    "studio.idea_refine": ("بازنویسی ایده", "Rewriting an idea"),
    "studio.idea_merge": ("ادغام ایده‌ها", "Merging ideas"),
    "studio.research": ("پژوهش دربارهٔ سریال", "Researching the series"),
    "studio.map": ("نقشهٔ پیامدها", "Consequence map"),
    "studio.timeline": ("خط زمانی جایگزین", "Alternative timeline"),
    "studio.profile": ("کتاب شخصیت", "Character bible"),
    "studio.bible": ("کتاب سریال", "Series bible"),
    "studio.design": ("برگه‌های طراحی", "Design sheets"),
    "studio.design_image": ("تصویر برگهٔ طراحی", "Design sheet image"),
    "studio.casting": ("پیشنهاد انتخاب صدا", "Voice casting suggestion"),
    "studio.translate": ("ترجمهٔ قسمت", "Episode translation"),
    "studio.animatic": ("ساخت انیماتیک", "Building the animatic"),
    "prod.keyframes": ("ساخت تصویرهای کلیدی", "Making the keyframe images"),
    "prod.tts": ("ساخت صدای گویندگی", "Recording the narration"),
    "prod.clips": ("ساخت کلیپ‌های ویدئویی", "Making the video clips"),
    "prod.assemble": ("مونتاژ نهایی ویدئو", "Assembling the final video"),
    "bench.run": ("سنجش سرعت رایانه", "Measuring this PC's speed"),
    "downloads.run": ("دانلود مدل", "Downloading a model"),
    "compare.run": ("مقایسهٔ مدل‌ها", "Comparing models"),
    "lora.train": ("آموزش LoRA شخصیت", "Training the character LoRA"),
    "retake.run": ("بازسازی بخشی از ویدئو", "Re-making part of the video"),
    "audio.generate": ("ساخت موسیقی یا افکت صوتی", "Making music or sound effects"),
    "rig.from_sheet": ("ساخت عروسک دوبعدی از برگهٔ طراحی", "Building the 2D puppet from the sheet"),
    "rig.preview": ("پیش‌نمایش عروسک", "Puppet preview"),
    "voice.preview": ("نمونهٔ صدا", "Voice sample"),
    "publish.export": ("آماده‌سازی بستهٔ انتشار", "Preparing the publishing package"),
    "publish.send": ("ارسال برای انتشار", "Sending for publishing"),
    "models.test": ("تست مدل", "Model test"),
    "downloads.ollama": ("دانلود مدل Ollama", "Downloading an Ollama model"),
    "remotion.setup": ("آماده‌سازی Remotion (ویدئو با کد)", "Setting up Remotion (video with code)"),
    "remotion.render": ("ساخت ویدئو با Remotion", "Rendering a video with Remotion"),
}

PHASE_FA = {
    "loading_model": "در حال بارگذاری مدل در حافظه…",
    "prefill": "مدل متن شما را می‌خواند؛ اولین کلمه هنوز نیامده.",
    "starting_comfy": "در حال روشن کردن ComfyUI (ممکن است یک دقیقه طول بکشد)…",
    "speaking": "در حال ساخت صدا…",
    "rendering": "در حال ساخت…",
    "retry": "ارتباط قطع شد؛ دوباره تلاش می‌شود…",
    "parsing": "پاسخ مدل در حال بررسی است…",
}
PHASE_EN = {
    "loading_model": "Loading the model into memory…",
    "prefill": "The model is reading your text; the first word has not come yet.",
    "starting_comfy": "Starting ComfyUI (may take a minute)…",
    "speaking": "Making the voice…",
    "rendering": "Working…",
    "retry": "The connection broke; trying again…",
    "parsing": "Checking the model's answer…",
}
_FA_DIGITS = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")
_GPU_BUSY = re.compile(r"GPU busy: another program uses ([\d.]+) GB", re.I)


def fa_num(v) -> str:
    return str(v).translate(_FA_DIGITS)


def _num(v, digits: int = 0) -> str:
    return f"{v:.{digits}f}" if digits else str(int(round(v)))


def _waiting_fa(reason: str) -> str:
    low = reason.lower()
    m = _GPU_BUSY.search(reason)
    if m:
        return f"برنامهٔ دیگری {fa_num(m.group(1))} گیگابایت از حافظهٔ کارت گرافیک را گرفته؛ منتظر آزاد شدن آن."
    if "another gpu job" in low:
        return "منتظر تمام شدن کار دیگری که الان از کارت گرافیک استفاده می‌کند."
    if low.startswith("waiting for a free gpu"):
        return "منتظر آزاد شدن یک کارت گرافیک."
    if low.startswith("waiting for worker"):
        return "منتظر برداشتن کار توسط رایانهٔ دوم."
    if low.startswith("loading "):
        return "در حال بارگذاری مدل صدا…"
    return reason


def _lookups(job, cache: dict) -> dict:
    """page name, series title, episode number/title of the job (memoised)."""
    out = {"page": "", "series": "", "episode": None, "episode_title": ""}
    ep = getattr(job, "episode", None) if job.episode_id else None
    page = getattr(job, "page", None) if job.page_id else None
    series_title = ""
    if ep is not None:
        s = getattr(ep, "series", None)
        series_title = getattr(s, "title", "") or ""
        out["episode"], out["episode_title"] = ep.number, getattr(ep, "title", "") or ""
        if page is None and s is not None:
            page = getattr(s, "page", None)
    sid = (job.payload or {}).get("series_id") if isinstance(job.payload, dict) else None
    if not series_title and sid:
        key = ("series", sid)
        if key not in cache:
            try:
                from instai.story.models import Series

                row = Series.objects.filter(pk=sid).select_related("page").first()
                cache[key] = (row.title, row.page.name) if row else ("", "")
            except Exception:  # noqa: BLE001
                cache[key] = ("", "")
        series_title = cache[key][0]
        if page is None and cache[key][1]:
            out["page"] = cache[key][1]
    out["series"] = series_title
    if page is not None:
        out["page"] = getattr(page, "name", "") or out["page"]
    return out


def _for_text(info: dict, live: dict) -> tuple[str, str]:
    fa, en = [], []
    if info["page"]:
        fa.append(f"صفحهٔ «{info['page']}»")
        en.append(f"page “{info['page']}”")
    if info["series"]:
        fa.append(f"سریال «{info['series']}»")
        en.append(f"series “{info['series']}”")
    if info["episode"] is not None:
        t = f" «{info['episode_title']}»" if info["episode_title"] else ""
        te = f" “{info['episode_title']}”" if info["episode_title"] else ""
        fa.append(f"قسمت {fa_num(info['episode'])}{t}")
        en.append(f"episode {info['episode']}{te}")
    if live.get("shots"):
        fa.append(f"شات {fa_num(live.get('shot') or 0)} از {fa_num(live['shots'])}")
        en.append(f"shot {live.get('shot') or 0} of {live['shots']}")
    return " · ".join(fa), " · ".join(en)


def _device(job, live: dict) -> tuple[str, str, str, bool]:
    """(device, persian text, english text, warn). `device` is what the running code reported; before that it is the planned resource."""
    dev = live.get("device") or ""
    pct = live.get("gpu_pct")
    if dev == "gpu":
        return "gpu", "روی کارت گرافیک (GPU)", "on the graphics card (GPU)", False
    if dev == "mixed":
        p = fa_num(pct if pct is not None else "؟")
        return "mixed", f"فقط {p}٪ مدل روی GPU است و بقیه روی CPU کار می‌کند؛ کند است", \
            f"only {pct if pct is not None else '?'}% of the model is on the GPU, the rest runs on the CPU; slow", True
    if dev == "cpu":
        if job.resource == "gpu":
            return "cpu", "روی CPU، نه کارت گرافیک؛ خیلی کند است", "on the CPU, not the graphics card; very slow", True
        return "cpu", "روی CPU", "on the CPU", False
    if dev == "net":
        return "net", "از راه اینترنت (API)", "over the internet (API)", False
    # not reported yet: what the job is planned to use
    if job.resource == "gpu":
        return "gpu", "قرار است روی کارت گرافیک اجرا شود", "will run on the graphics card", False
    if job.resource == "net":
        return "net", "از راه اینترنت (API)", "over the internet (API)", False
    return "cpu", "روی CPU", "on the CPU", False


def _title(job, live: dict) -> tuple[str, str]:
    fa, en = KIND_TEXT.get(job.kind, (job.title or job.kind, job.title or job.kind))
    if job.kind == "models.test":
        name = str((job.payload or {}).get("id") or "").split(":", 1)[-1]
        if name:
            fa, en = f"{fa} «{name}»", f"{en} “{name}”"
    return fa, en


def _line(job, live: dict, now) -> tuple[str, str, str]:
    """(phase, persian live line, english live line)."""
    if job.status == "queued":
        if job.wait_code and job.waiting_reason:         # waiting for a computer / service / the night window: not a failure
            from .queue import WAIT_TEXT_EN

            return "waiting_" + job.wait_code, job.waiting_reason, WAIT_TEXT_EN.get(job.wait_code, job.waiting_reason)
        if job.attempts and job.error:
            return "queued", "تلاش قبلی ناموفق بود؛ به‌زودی دوباره امتحان می‌شود.", "The last try failed; it will be tried again soon."
        return "queued", "در صف؛ منتظر نوبت.", "Queued; waiting for its turn."
    if job.status != "running":
        return "done", "", ""
    waiting = (job.waiting_reason or "").strip()
    if waiting:
        return "waiting_gpu", _waiting_fa(waiting), waiting
    phase = live.get("phase") or ""
    fa_parts: list[str] = []
    en_parts: list[str] = []
    attempt, attempts = live.get("attempt"), live.get("attempts")
    if attempt and attempts and attempt > 1:
        fa_parts.append(f"تلاش {fa_num(attempt)} از {fa_num(attempts)} (پاسخ قبلی معتبر نبود)")
        en_parts.append(f"try {attempt} of {attempts} (the previous answer was not valid)")
    if phase == "generating":
        t = int(live.get("tokens") or 0)
        tps = live.get("tps")
        fa_parts.append(f"{fa_num(t)} توکن تا الان نوشته شد" + (f" · {fa_num(_num(tps, 1))} توکن در ثانیه" if tps else ""))
        en_parts.append(f"{t} tokens written so far" + (f" · {_num(tps, 1)} tokens/s" if tps else ""))
    elif phase == "sampling" and live.get("steps"):
        fa_parts.append(f"گام {fa_num(live.get('step') or 0)} از {fa_num(live['steps'])}")
        en_parts.append(f"step {live.get('step') or 0} of {live['steps']}")
    elif phase in PHASE_FA:
        fa_parts.append(PHASE_FA[phase])
        en_parts.append(PHASE_EN[phase])
    elif job.progress_text:
        fa_parts.append(job.progress_text)
        en_parts.append(job.progress_text)
    return phase or "running", " · ".join(fa_parts), " · ".join(en_parts)


def activity(job, cache: dict | None = None) -> dict:
    """The plain-language state of one job (see the module docstring); safe on every job, finished ones included."""
    cache = {} if cache is None else cache
    live = job.live if isinstance(getattr(job, "live", None), dict) else {}
    now = timezone.now()
    info = _lookups(job, cache)
    t_fa, t_en = _title(job, live)
    for_fa, for_en = _for_text(info, live)
    device, d_fa, d_en, warn = _device(job, live)
    if job.status not in ("queued", "running") and not live.get("device"):
        device, d_fa, d_en, warn = "", "", "", False          # a finished job only says what it actually used
    phase, line_fa, line_en = _line(job, live, now)
    eta = live.get("eta_sec") if job.status == "running" else None
    if eta is None and job.status == "running" and job.estimated_sec and job.started_at:
        eta = max(0.0, job.estimated_sec - (now - job.started_at).total_seconds())
    return {"title_fa": t_fa, "title_en": t_en, "for_fa": for_fa, "for_en": for_en, "phase": phase, "model": live.get("model") or "",
            "device": device, "device_fa": d_fa, "device_en": d_en, "warn": warn, "line_fa": line_fa, "line_en": line_en,
            "step": live.get("step"), "steps": live.get("steps"), "tokens": live.get("tokens"), "tps": live.get("tps"),
            "eta_sec": round(eta) if eta is not None else None}
