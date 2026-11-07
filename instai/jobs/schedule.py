"""Clock rules for scheduled work (downloads): "now", "at 03:30" and "inside the night window 02:00-07:00".

Times are the LOCAL time of the computer InstAI runs on (the owner's Windows clock, Iran: UTC+3:30); the database keeps UTC.
Everything takes an optional `now` (aware datetime) so tests are deterministic; `local_offset` can be replaced in tests.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils import timezone

MODES = ("default", "now", "at", "window")
DEFAULT_WINDOW = "02:00-07:00"
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


class ScheduleError(ValueError):
    """Bad time input; `str(e)` is a plain Persian sentence for the owner, `en` the English one."""

    def __init__(self, fa: str, en: str = ""):
        super().__init__(fa)
        self.en = en or fa


_CHOOSE_FA = "زمان دانلود را درست انتخاب کنید («الان»، «در ساعتِ …» یا «در بازهٔ شبانه»)."
_CHOOSE_EN = "Choose when to download: now, at a time, or in the night window."


def fa_num(v) -> str:
    return str(v).translate(_FA)


def _ascii(text) -> str:
    return str(text or "").translate(_DIGITS).strip()


def local_offset(at: datetime | None = None) -> timedelta:
    """UTC offset of this computer's clock at that moment (DST aware through the OS)."""
    at = at or timezone.now()
    off = at.astimezone().utcoffset()
    return off if off is not None else timedelta(0)


def local_now(now: datetime | None = None) -> datetime:
    """Wall-clock "now" as a datetime whose hour/minute are the local ones (aware, fixed offset)."""
    now = now or timezone.now()
    return now.astimezone(dt_timezone(local_offset(now)))


def parse_window(window: str):
    """"02:00-07:00" -> (start minute, end minute), or None when empty/invalid. start == end is invalid (no window)."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", _ascii(window))
    if not m:
        return None
    ah, am, bh, bm = (int(x) for x in m.groups())
    if not (0 <= ah < 24 and 0 <= bh < 24 and 0 <= am < 60 and 0 <= bm < 60):
        return None
    start, end = ah * 60 + am, bh * 60 + bm
    return (start, end) if start != end else None


def norm_window(window: str) -> str:
    p = parse_window(window)
    return f"{p[0] // 60:02d}:{p[0] % 60:02d}-{p[1] // 60:02d}:{p[1] % 60:02d}" if p else ""


def in_window(window: str, now: datetime | None = None) -> bool:
    """Is it inside the window now (local time)? An empty/invalid window means always. A window over midnight (22:00-04:00) works."""
    p = parse_window(window)
    if not p:
        return True
    start, end = p
    t = local_now(now)
    minute = t.hour * 60 + t.minute
    return (start <= minute < end) if start < end else (minute >= start or minute < end)


def _to_utc(local: datetime) -> datetime:
    return local.astimezone(dt_timezone.utc)


def next_window_start(window: str, now: datetime | None = None) -> datetime:
    """The next moment (UTC) the window opens; right now when it is open."""
    now = now or timezone.now()
    p = parse_window(window)
    if not p or in_window(window, now):
        return now
    t = local_now(now)
    base = t.replace(hour=p[0] // 60, minute=p[0] % 60, second=0, microsecond=0)
    if base <= t:
        base += timedelta(days=1)
    return _to_utc(base)


def window_end(window: str, now: datetime | None = None) -> datetime | None:
    """When the CURRENT window closes (UTC); None when there is no window or it is closed now."""
    now = now or timezone.now()
    p = parse_window(window)
    if not p or not in_window(window, now):
        return None
    t = local_now(now)
    base = t.replace(hour=p[1] // 60, minute=p[1] % 60, second=0, microsecond=0)
    if base <= t:
        base += timedelta(days=1)
    return _to_utc(base)


def next_clock_time(hhmm: str, now: datetime | None = None) -> datetime | None:
    """"03:30" -> the next moment (UTC) the local clock shows it; None when invalid."""
    now = now or timezone.now()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", _ascii(hhmm))
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None
    t = local_now(now)
    base = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if base <= t:
        base += timedelta(days=1)
    return _to_utc(base)


def config() -> dict:
    """The saved defaults (Downloads page): {download_mode: now|window, download_window, max_wait_hours, retention_days}."""
    from instai.core import settings_store

    raw = settings_store.get_setting("ops_config") or {}
    raw = raw if isinstance(raw, dict) else {}
    win = norm_window(raw.get("download_window") or "") or DEFAULT_WINDOW
    mode = raw.get("download_mode") if raw.get("download_mode") in ("now", "window") else "now"
    try:
        wait = max(0.0, float(raw.get("max_wait_hours") or 0))
    except (TypeError, ValueError):
        wait = 0.0
    try:
        keep = min(365, max(1, int(raw.get("retention_days") or 30)))
    except (TypeError, ValueError):
        keep = 30
    return {"download_mode": mode, "download_window": win, "max_wait_hours": wait, "retention_days": keep}


def resolve(when=None, cfg: dict | None = None, now: datetime | None = None) -> dict:
    """What the owner chose -> {"not_before": datetime | None, "window": "02:00-07:00" | ""}.

    `when` is None/"" (the saved default), "now", "03:30", or {"mode": default|now|at|window, "time": "03:30", "window": "01:00-05:00"}.
    """
    now = now or timezone.now()
    if when in (None, ""):
        mode, hhmm, win = "default", "", ""
    elif isinstance(when, str):
        t = _ascii(when).lower()
        mode, hhmm, win = ("at", t, "") if ":" in t and t[:1].isdigit() else (t, "", "")
    elif isinstance(when, dict):
        mode, hhmm, win = _ascii(when.get("mode") or "default").lower(), _ascii(when.get("time")), _ascii(when.get("window"))
    else:
        raise ScheduleError(_CHOOSE_FA, _CHOOSE_EN)
    if mode not in MODES:
        raise ScheduleError(_CHOOSE_FA, _CHOOSE_EN)
    cfg = cfg or config()
    if mode == "default":
        return {"not_before": None, "window": cfg["download_window"] if cfg["download_mode"] == "window" else ""}
    if mode == "now":
        return {"not_before": None, "window": ""}
    if mode == "at":
        if not hhmm:
            raise ScheduleError("ساعت شروع را بنویسید، مثلاً ۰۳:۳۰.", "Write the start time, for example 03:30.")
        moment = next_clock_time(hhmm, now)
        if moment is None:
            raise ScheduleError("ساعت را مثل ۰۳:۳۰ بنویسید (ساعت ۰ تا ۲۳، دقیقه ۰ تا ۵۹).", "Write the time like 03:30 (hours 0-23, minutes 0-59).")
        return {"not_before": moment, "window": ""}
    if win:
        norm = norm_window(win)
        if not norm:
            raise ScheduleError("بازه را مثل ۰۲:۰۰-۰۷:۰۰ بنویسید (ساعت شروع و پایان فرق داشته باشد).", "Write the window like 02:00-07:00 (start and end must differ).")
        return {"not_before": None, "window": norm}
    return {"not_before": None, "window": cfg["download_window"]}


def first_moment(not_before: datetime | None, window: str, now: datetime | None = None) -> datetime | None:
    """When can the work first start? None = right now (no time chosen, or the window is open)."""
    now = now or timezone.now()
    moment = not_before if (not_before and not_before > now) else None
    if window and not in_window(window, now):
        opens = next_window_start(window, now)
        moment = max(moment, opens) if moment else opens
    return moment


def clock_text(moment: datetime, now: datetime | None = None) -> str:
    """"امروز ۰۲:۰۰" / "فردا ۰۲:۰۰" / "۳ روز دیگر، ۰۲:۰۰" (local time)."""
    now = now or timezone.now()
    t, n = local_now(moment), local_now(now)
    day = (t.date() - n.date()).days
    hhmm = fa_num(f"{t.hour:02d}:{t.minute:02d}")
    if day <= 0:
        return f"امروز {hhmm}"
    if day == 1:
        return f"فردا {hhmm}"
    return f"{fa_num(day)} روز دیگر، {hhmm}"


def clock_text_en(moment: datetime, now: datetime | None = None) -> str:
    now = now or timezone.now()
    t, n = local_now(moment), local_now(now)
    day = (t.date() - n.date()).days
    hhmm = f"{t.hour:02d}:{t.minute:02d}"
    return f"today {hhmm}" if day <= 0 else (f"tomorrow {hhmm}" if day == 1 else f"in {day} days, {hhmm}")
