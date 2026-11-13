"""Season planning for a mini-series channel (pure Python): a deterministic skeleton, the validator (hooks, cliffhangers, open-thread budget, recurring cast, variety)
and the posting schedule. The model writes the creative content; this module checks it and is the fallback when no model answers."""
from __future__ import annotations

import datetime as dt

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
HOOKS_FA = ["صدای آژیر از دور می‌آید و قهرمان تازه چشم باز می‌کند.", "قهرمان با یک کلید در دست، پشت یک در بسته ایستاده.", "زمین زیر پایش می‌لرزد؛ فقط ده ثانیه فرصت دارد.",
            "کسی روی دیوار با خون نوشته: «برنگرد».", "چراغ‌ها یکی‌یکی خاموش می‌شوند.", "نقشه‌ای که دیشب کشیده بود، حالا عوض شده است."]
HOOKS_EN = ["A siren wails in the distance as the hero wakes.", "The hero stands before a locked door with a key in hand.", "The ground shakes; there are only ten seconds.",
            "Someone has written 'don't come back' on the wall.", "The lights go out, one by one.", "The map drawn last night has changed."]
CLIFFS_FA = ["در باز می‌شود و کسی که پشتش ایستاده، آشناست.", "نگهبان می‌چرخد و قهرمان را می‌بیند.", "زمین زیر پای او خالی می‌شود.", "صدایی از پشت دیوار می‌گوید: «من می‌دانم تو کجایی».",
             "ماشین روشن می‌شود… اما کسی پشت فرمان نیست.", "نقشه از دست او می‌افتد؛ در آن نام یک دوست خط خورده است."]
CLIFFS_EN = ["The door opens, and the one behind it is familiar.", "The guard turns and sees the hero.", "The ground gives way.", "A voice behind the wall says, 'I know where you are.'",
             "The car starts… but no one is behind the wheel.", "The map falls; a friend's name is crossed out on it."]
LOCS = ["cell", "corridor", "yard", "street", "forest", "rooftop", "cave", "lab", "sewer", "bridge", "desert", "room"]


def _again(i: int, n: int) -> str:
    """A stable suffix so that a season longer than the template list never repeats a hook or a cliffhanger word for word."""
    k = (i - 1) // n
    return f" ({k + 1})" if k else ""


def skeleton_season(n: int, runtime: int, *, fa: bool = True, characters: list[str] | None = None, title: str = "", tag: str = "") -> dict:
    """A valid season of exactly `n` episodes (2..60): hook, escalation, twist, cliffhanger, payoff of the previous cliffhanger, threads opened and closed (never open
    more than 3 episodes, all closed by the finale). Generic placeholder text marked with `tag`; a model or the author rewrites it. Deterministic."""
    n = max(2, min(60, int(n)))
    names = [c for c in (characters or []) if c][:5]
    hooks, cliffs = (HOOKS_FA, CLIFFS_FA) if fa else (HOOKS_EN, CLIFFS_EN)
    eps = []
    for i in range(1, n + 1):
        last = i == n
        opens = [] if last else [f"t{i}"]
        closes = [f"t{j}" for j in range(1, n) if min(n, j + (2 if j % 3 == 1 else 1)) == i]
        logline = f"{tag} " + ("قهرمان یک مانع تازه را پشت سر می‌گذارد." if fa else "The hero gets past a new obstacle.")
        eps.append({"number": i, "title": (f"قسمت {i}" if fa else f"Episode {i}") + (f": {title}" if title else ""),
                    "hook": f"{tag} {hooks[(i - 1) % len(hooks)]}{_again(i, len(hooks))}".strip(), "logline": logline.strip(),
                    "escalation": "هر قدم خطرناک‌تر از قبلی است." if fa else "Every step is more dangerous than the last.", "twist": "نقشه به‌هم می‌ریزد." if fa else "The plan falls apart.",
                    "cliffhanger": (cliffs[(i - 1) % len(cliffs)] + _again(i, len(cliffs)) if not last else ("آزاد است… اما کسی او را می‌پاید." if fa else "He is free… but someone is watching.")),
                    "payoff_of_previous": ("" if i == 1 else (("پاسخ: " if fa else "Answer: ") + cliffs[(i - 2) % len(cliffs)])), "characters": names[:3], "location": LOCS[(i - 1) % len(LOCS)],
                    "runtime_sec": int(runtime), "opens": opens, "closes": sorted(set(closes))})
    return {"season_title": title or ("فصل ۱" if fa else "Season 1"), "season_arc": f"{tag} " + ("از گیر افتادن تا آزادی." if fa else "From being trapped to freedom."), "episodes": eps}


def threads(slate: list[dict]) -> list[dict]:
    """[{id, opened, closed, span}] computed from each episode's `opens` / `closes` (closed = None while still open)."""
    opened: dict[str, int] = {}
    closed: dict[str, int] = {}
    for e in sorted(slate, key=lambda e: e.get("number", 0)):
        for t in e.get("opens") or []:
            opened.setdefault(t, e["number"])
        for t in e.get("closes") or []:
            closed.setdefault(t, e["number"])
    out = []
    for t, a in sorted(opened.items(), key=lambda kv: kv[1]):
        b = closed.get(t)
        out.append({"id": t, "opened": a, "closed": b, "span": (b - a) if b else None})
    for t, b in closed.items():
        if t not in opened:
            out.append({"id": t, "opened": None, "closed": b, "span": None})
    return out


def issue(code: str, episode: int = 0, **detail) -> dict:
    return {"code": code, "episode": episode, **detail}


def validate(slate: list[dict], *, rules: dict | None = None, cast_names: list[str] | None = None, runtime: int = 30, genre_runtime: tuple[int, int] = (15, 60)) -> dict:
    """{ok, errors[], warnings[], threads[]}; codes are translated by the UI (channel.issue.<code>)."""
    rules = {"max_open_threads": 4, "max_thread_span": 4, **(rules or {})}
    errors: list[dict] = []
    warnings: list[dict] = []
    eps = sorted(slate, key=lambda e: e.get("number", 0))
    if not eps:
        return {"ok": False, "errors": [issue("no_episodes")], "warnings": [], "threads": []}
    if [e.get("number") for e in eps] != list(range(1, len(eps) + 1)):
        errors.append(issue("numbering"))
    hooks, cliffs = {}, {}
    for e in eps:
        n = e.get("number", 0)
        if not str(e.get("hook") or "").strip():
            errors.append(issue("missing_hook", n))
        else:
            hooks.setdefault(e["hook"].strip().lower(), []).append(n)
        if not str(e.get("cliffhanger") or "").strip():
            (warnings if n == len(eps) else errors).append(issue("missing_cliffhanger", n))
        else:
            cliffs.setdefault(e["cliffhanger"].strip().lower(), []).append(n)
        if n > 1 and not str(e.get("payoff_of_previous") or "").strip():
            warnings.append(issue("no_payoff_of_previous", n))
        rt = int(e.get("runtime_sec") or runtime)
        if not (genre_runtime[0] <= rt <= genre_runtime[1]):
            warnings.append(issue("runtime_off", n, runtime=rt))
        if not (e.get("characters") or []):
            warnings.append(issue("no_characters", n))
    for h, ns in hooks.items():
        if len(ns) > 1:
            warnings.append(issue("repeated_hook", ns[0], episodes=ns))
    for c, ns in cliffs.items():
        if len(ns) > 1:
            warnings.append(issue("repeated_cliffhanger", ns[0], episodes=ns))
    run = 1
    for a, b in zip(eps, eps[1:]):
        run = run + 1 if (a.get("location") and a.get("location") == b.get("location")) else 1
        if run >= 3:
            warnings.append(issue("location_repeat", b["number"], location=b.get("location")))
    th = threads(eps)
    last = eps[-1]["number"]
    for t in th:
        if t["closed"] is None:
            (warnings if t["opened"] == last else errors).append(issue("thread_never_closed", t["opened"] or 0, thread=t["id"]))
        elif t["opened"] is None:
            warnings.append(issue("thread_closed_unopened", t["closed"], thread=t["id"]))
        elif t["span"] is not None and t["span"] > rules["max_thread_span"]:
            warnings.append(issue("thread_too_long", t["opened"], thread=t["id"], span=t["span"]))
    for n in range(1, last + 1):
        open_now = [t for t in th if t["opened"] is not None and t["opened"] <= n and (t["closed"] is None or t["closed"] > n)]
        if len(open_now) > rules["max_open_threads"]:
            warnings.append(issue("too_many_open_threads", n, count=len(open_now)))
    appearing = {c for e in eps for c in (e.get("characters") or [])}
    for name in cast_names or []:
        if name not in appearing:
            warnings.append(issue("cast_never_appears", 0, character=name))
    return {"ok": not errors, "errors": errors, "warnings": warnings, "threads": th}


def schedule(start: str, days: list[str], time: str, count: int, *, utc_offset_minutes: int = 210) -> list[dict]:
    """The posting dates of `count` episodes: the chosen weekdays from `start` at `time` (local time of the page); [{number, local, utc}]."""
    days = [d for d in days if d in DAYS] or ["sat", "mon", "wed"]
    day = dt.date.fromisoformat(start)
    hh, mm = (str(time or "20:00") + ":00").split(":")[:2]
    out = []
    n = 0
    guard = 0
    while n < count and guard < 800:
        if DAYS[day.weekday()] in days:
            n += 1
            local = dt.datetime.combine(day, dt.time(int(hh), int(mm)))
            out.append({"number": n, "local": local.isoformat(timespec="minutes"),
                        "utc": (local - dt.timedelta(minutes=utc_offset_minutes)).replace(tzinfo=dt.timezone.utc).isoformat(timespec="minutes")})
        day += dt.timedelta(days=1)
        guard += 1
    return out
