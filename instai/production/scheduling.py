"""Scheduling maths (pure functions, unit-tested): render windows ("nights only") and publication slots.

All datetimes in and out are timezone-aware UTC; `offset_min` is the owner's local offset (Tehran = +210). Window definition:
{"days": ["sat", "sun"], "start": "22:00", "end": "07:00"} - `days` are the days the window STARTS on (empty = every day); an end earlier
than the start means the window runs over midnight into the next day. No windows at all = render any time.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone

from instai.core.errors import DomainError

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def validate_windows(ws) -> list[dict]:
    if ws in (None, ""):
        return []
    if not isinstance(ws, list):
        raise DomainError("validation_error", "پنجرهٔ رندر باید فهرست باشد.", http_status=400, details={"render_windows": ["invalid"]})
    out = []
    for w in ws:
        if not isinstance(w, dict) or not _HHMM.match(str(w.get("start", ""))) or not _HHMM.match(str(w.get("end", ""))):
            raise DomainError("validation_error", "هر پنجره باید ساعت شروع و پایان به شکل HH:MM داشته باشد.", http_status=400, details={"render_windows": ["invalid"]})
        days = [d for d in (w.get("days") or []) if d in WEEKDAYS]
        out.append({"days": days, "start": w["start"], "end": w["end"]})
    return out


def _t(s: str) -> time:
    return time(int(s[:2]), int(s[3:5]))


def to_local(dt: datetime, offset_min: int) -> datetime:
    return (dt.astimezone(timezone.utc) + timedelta(minutes=offset_min)).replace(tzinfo=None)


def to_utc(local: datetime, offset_min: int) -> datetime:
    return (local - timedelta(minutes=offset_min)).replace(tzinfo=timezone.utc)


def _intervals_around(windows: list[dict], local: datetime) -> list[tuple[datetime, datetime]]:
    """Window instances (local naive datetimes) that could contain or follow `local`: yesterday .. 8 days ahead."""
    out = []
    for back in range(-1, 9):
        day = (local + timedelta(days=back)).date()
        for w in windows:
            if w["days"] and WEEKDAYS[day.weekday()] not in w["days"]:
                continue
            s, e = _t(w["start"]), _t(w["end"])
            start = datetime.combine(day, s)
            end = datetime.combine(day, e) + (timedelta(days=1) if e <= s else timedelta())
            out.append((start, end))
    return sorted(out)


def window_open(windows: list[dict], now: datetime, offset_min: int = 210) -> bool:
    if not windows:
        return True
    local = to_local(now, offset_min)
    return any(s <= local < e for s, e in _intervals_around(windows, local))


def next_window_open(windows: list[dict], now: datetime, offset_min: int = 210) -> datetime:
    """The moment a render may start: now when a window is open (or none is defined), else the next window's start (UTC)."""
    if window_open(windows, now, offset_min):
        return now
    local = to_local(now, offset_min)
    for s, e in _intervals_around(windows, local):
        if s > local:
            return to_utc(s, offset_min)
    return now + timedelta(days=1)


def publication_slots(per_week: int, days: list[str], at: str, after: datetime, n: int, offset_min: int = 210) -> list[datetime]:
    """The next `n` publication times (UTC) after `after`: `per_week` posts a week on the chosen weekdays at `at` (local HH:MM)."""
    per_week = max(1, min(21, int(per_week or 1)))
    chosen = [d for d in WEEKDAYS if d in (days or [])] or ["sat", "mon", "wed"]
    if per_week < len(chosen):
        chosen = chosen[:per_week]
    elif per_week > len(chosen):                                   # more posts than named days: add the days farthest from the chosen ones
        spare = [d for d in WEEKDAYS if d not in chosen]
        while len(chosen) < min(7, per_week) and spare:
            spare.sort(key=lambda d: -min(abs(WEEKDAYS.index(d) - WEEKDAYS.index(c)) for c in chosen))
            chosen.append(spare.pop(0))
    hh = _t(at if _HHMM.match(at or "") else "20:00")
    local_after = to_local(after, offset_min)
    out: list[datetime] = []
    day = local_after.date()
    for i in range(0, 7 * (n // max(1, len(chosen)) + 3)):
        d = day + timedelta(days=i)
        if WEEKDAYS[d.weekday()] in chosen:
            cand = datetime.combine(d, hh)
            if cand > local_after:
                out.append(to_utc(cand, offset_min))
                if len(out) >= n:
                    break
    return out


def week_start(now: datetime, offset_min: int = 210) -> datetime:
    """Start (UTC) of the owner's current week (Saturday 00:00 local, the Persian week) - the period of the weekly budgets."""
    local = to_local(now, offset_min)
    back = (local.weekday() - 5) % 7                               # Saturday = weekday 5
    return to_utc(datetime.combine((local - timedelta(days=back)).date(), time(0, 0)), offset_min)
