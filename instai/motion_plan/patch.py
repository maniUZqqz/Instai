"""Patch editing: «make the title bigger» changes only that scene / field - the JSON is the source of truth.

SOURCE: ported from NMarketing:backend/apps/motion/patch.py @ motion v2, adapted for InstAI: the top-level keys are InstAI's (no brand / audio), errors
and summaries carry Persian AND English text, and the plain-language rules understand a few English commands next to the Persian ones.

A patch is a list of operations on the plan. Every patch is validated again with specs.normalize_spec before it is applied (atomic: all or nothing) and
is reversible (plans.py keeps every version). Three sources make patches: the quick buttons of a scene, the chat (a model => patch; without a model =>
the rules in this file) and the automatic fixes of the QA (qa.py) / the visual critique (critique.py).

Operations:
  {"op":"set","path":"scenes/1/tokens/font_scale","value":1.2}      sets a value (path with /; a number = the index of a list item, from 0)
  {"op":"remove","path":"scenes/1/camera"}                           removes a key
  {"op":"scale","path":"scenes/1/tokens/font_scale","factor":1.15,"min":0.6,"max":1.6,"default":1}   multiplies a number
  {"op":"shift","path":"scenes/1/duration","by":1.5}                  moves a number
  {"op":"add_scene","at":2,"scene":{...}} · {"op":"remove_scene","index":2} · {"op":"move_scene","from":1,"to":3} · {"op":"duplicate_scene","index":1}
  {"op":"split_scene","index":1}                                      splits a many-item scene in two (first half / second half)
"""
from __future__ import annotations

import colorsys
import copy
import re

from . import components, motionlib, specs

MAX_OPS = 12
SPLITTABLE = ("list", "checklist")
TOP_KEYS = {"style", "theme", "size", "fps", "lang", "digits", "platform", "intensity", "transition", "series", "captions", "scenes"}


class PatchError(ValueError):
    """An invalid patch; `str(e)` is Persian, `e.en` the English text."""

    def __init__(self, fa: str, en: str = ""):
        super().__init__(fa)
        self.fa = fa
        self.en = en or fa


# ───────────────────────────────────────────── path

def _parts(path: str) -> list:
    if not isinstance(path, str) or not path.strip("/"):
        raise PatchError("مسیر تغییر خالی است.", "The path of the change is empty.")
    out: list = []
    for p in path.strip("/").split("/"):
        out.append(int(p) if re.fullmatch(r"\d{1,3}", p) else p)
    if out[0] not in TOP_KEYS:
        raise PatchError(f"مسیر «{path}» را نمی‌شناسم.", f"Unknown path “{path}”.")
    return out


def _walk(root, parts: list, create: bool):
    cur = root
    for i, p in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if isinstance(p, int):
            if not isinstance(cur, list) or p >= len(cur):
                raise PatchError(f"عنصر {p + 1} در مسیر وجود ندارد.", f"Item {p + 1} of the path does not exist.")
            cur = cur[p]
        else:
            if not isinstance(cur, dict):
                raise PatchError(f"مسیر «{'/'.join(map(str, parts))}» معتبر نیست.", f"The path “{'/'.join(map(str, parts))}” is not valid.")
            if p not in cur or cur[p] is None:
                if not create:
                    raise PatchError(f"«{p}» وجود ندارد.", f"“{p}” does not exist.")
                cur[p] = [] if isinstance(nxt, int) else {}
            cur = cur[p]
    return cur


def _get(root, parts: list, default=None):
    cur = root
    for p in parts:
        if isinstance(p, int):
            if not isinstance(cur, list) or p >= len(cur):
                return default
            cur = cur[p]
        else:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
    return cur


def _set(root, parts: list, value) -> None:
    cur = _walk(root, parts, True)
    last = parts[-1]
    if isinstance(last, int):
        if not isinstance(cur, list) or last > len(cur):
            raise PatchError("شمارهٔ عنصر در فهرست معتبر نیست.", "The item number in the list is not valid.")
        if last == len(cur):
            cur.append(value)
        else:
            cur[last] = value
    else:
        if not isinstance(cur, dict):
            raise PatchError("مسیر معتبر نیست.", "The path is not valid.")
        cur[last] = value


def _remove(root, parts: list) -> None:
    cur = _walk(root, parts, False)
    last = parts[-1]
    if isinstance(last, int):
        if isinstance(cur, list) and last < len(cur):
            del cur[last]
    elif isinstance(cur, dict):
        cur.pop(last, None)


# ───────────────────────────────────────────── operations

def _idx(plan: dict, v, name="index") -> int:
    try:
        i = int(v)
    except (TypeError, ValueError):
        raise PatchError(f"«{name}» عدد نیست.", f"“{name}” is not a number.")
    if not 0 <= i < len(plan["scenes"]):
        raise PatchError(f"صحنهٔ {i + 1} وجود ندارد (طرح {len(plan['scenes'])} صحنه دارد).", f"Scene {i + 1} does not exist (the plan has {len(plan['scenes'])} scenes).")
    return i


def split_scene(sc: dict) -> list:
    """A many-item scene => two scenes of the same type (half the items each); a scene without enough items => the same scene."""
    if sc.get("type") not in SPLITTABLE:        # a chart or a sequence loses its meaning in halves: only independent items are split
        return [sc]
    comp = components.get(sc.get("type", ""))
    key = (comp or {}).get("items")
    if not key and comp:
        key = next((k for k, f in comp["fields"].items() if f["kind"] in ("strs", "objs")), None)
    items = sc.get(key) if key else None
    if not isinstance(items, list) or len(items) < 2:
        return [sc]
    half = (len(items) + 1) // 2
    a, b = copy.deepcopy(sc), copy.deepcopy(sc)
    a[key], b[key] = items[:half], items[half:]
    for part in (a, b):
        part["duration"] = max(specs.MIN_SCENE_S + 2.0, round(float(sc.get("duration", 5)) * 0.62, 1))
        part.pop("cues", None)
    if "narration" in sc:
        words = sc["narration"].split()
        mid = max(1, len(words) // 2)
        a["narration"], b["narration"] = " ".join(words[:mid]), " ".join(words[mid:])
        if not b["narration"]:
            b.pop("narration")
    b.pop("overlays", None)
    return [a, b]


def _apply_one(plan: dict, op: dict) -> None:
    kind = op.get("op")
    if kind == "set":
        _set(plan, _parts(op.get("path")), copy.deepcopy(op.get("value")))
    elif kind == "remove":
        _remove(plan, _parts(op.get("path")))
    elif kind in ("scale", "shift"):
        parts = _parts(op.get("path"))
        cur = _get(plan, parts, None)
        if not isinstance(cur, (int, float)) or isinstance(cur, bool):
            cur = op.get("default")
        if not isinstance(cur, (int, float)):
            raise PatchError("این مقدار عدد نیست.", "This value is not a number.")
        try:
            new = cur * float(op["factor"]) if kind == "scale" else cur + float(op["by"])
        except (KeyError, TypeError, ValueError):
            raise PatchError("ضریب یا مقدار تغییر معتبر نیست.", "The factor or amount of the change is not valid.")
        lo, hi = op.get("min"), op.get("max")
        if isinstance(lo, (int, float)):
            new = max(lo, new)
        if isinstance(hi, (int, float)):
            new = min(hi, new)
        _set(plan, parts, round(new, 3))
    elif kind == "add_scene":
        sc = op.get("scene")
        if not isinstance(sc, dict):
            raise PatchError("صحنهٔ افزودنی معتبر نیست.", "The scene to add is not valid.")
        at = op.get("at", len(plan["scenes"]))
        at = max(0, min(len(plan["scenes"]), int(at)))
        plan["scenes"].insert(at, copy.deepcopy(sc))
    elif kind == "remove_scene":
        if len(plan["scenes"]) <= 1:
            raise PatchError("آخرین صحنه را نمی‌شود حذف کرد.", "The last scene cannot be removed.")
        del plan["scenes"][_idx(plan, op.get("index"))]
    elif kind == "move_scene":
        a, b = _idx(plan, op.get("from"), "from"), _idx(plan, op.get("to"), "to")
        plan["scenes"].insert(b, plan["scenes"].pop(a))
    elif kind == "duplicate_scene":
        i = _idx(plan, op.get("index"))
        c = copy.deepcopy(plan["scenes"][i])
        c.pop("cues", None)
        plan["scenes"].insert(i + 1, c)
    elif kind == "split_scene":
        i = _idx(plan, op.get("index"))
        parts = split_scene(plan["scenes"][i])
        if len(parts) < 2:
            raise PatchError("این صحنه آیتم کافی برای تقسیم ندارد.", "This scene has too few items to split.")
        plan["scenes"][i:i + 1] = parts
    else:
        raise PatchError(f"عملیات «{kind}» را نمی‌شناسم.", f"Unknown operation “{kind}”.")


def apply_patch(spec: dict, ops, *, max_total: float = specs.MAX_TOTAL_S, notes: list | None = None, allowed_sources=None, kit: dict | None = None) -> dict:
    """The new validated plan; the input spec stays untouched. An error => PatchError (nothing is applied)."""
    if isinstance(ops, dict):
        ops = [ops]
    if not isinstance(ops, list) or not ops:
        raise PatchError("تغییری برای اعمال داده نشد.", "No change was given.")
    if len(ops) > MAX_OPS:
        raise PatchError(f"در هر بار حداکثر {MAX_OPS} تغییر.", f"At most {MAX_OPS} changes at a time.")
    work = copy.deepcopy({k: v for k, v in spec.items() if k not in ("total_s", "safe")})
    for op in ops:
        if not isinstance(op, dict):
            raise PatchError("هر تغییر باید یک شیء باشد.", "Every change must be an object.")
        _apply_one(work, op)
    try:
        out = specs.normalize_spec(work, max_total=max_total, notes=notes, allowed_sources=allowed_sources, kit=kit)
    except specs.SpecError as exc:
        raise PatchError(f"پس از اعمال تغییر طرح معتبر نبود: {exc}", f"After the change the plan was not valid: {exc.en}") from exc
    if _strip(out) == _strip(spec):
        raise PatchError("این تغییر چیزی را عوض نکرد (فیلد نامعتبر یا مقدار تکراری).", "This change changed nothing (an invalid field or the same value).")
    return out


def _strip(s: dict) -> dict:
    return {k: v for k, v in s.items() if k not in ("total_s", "safe")}


def diff_summary(before: dict, after: dict) -> list:
    """A short list of what changed: [{fa, en}]."""
    out = []
    if len(before["scenes"]) != len(after["scenes"]):
        out.append({"fa": f"تعداد صحنه‌ها {len(before['scenes'])} ⇐ {len(after['scenes'])}", "en": f"scenes {len(before['scenes'])} -> {len(after['scenes'])}"})
    for i, (a, b) in enumerate(zip(before["scenes"], after["scenes"])):
        ch = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        if ch:
            out.append({"fa": f"صحنهٔ {i + 1}: " + "، ".join(ch), "en": f"scene {i + 1}: " + ", ".join(ch)})
    for k in ("style", "theme", "size", "platform", "transition", "intensity", "captions", "series"):
        if before.get(k) != after.get(k):
            out.append({"fa": f"«{k}» عوض شد", "en": f"“{k}” changed"})
    return out


def diff_text(summary: list, lang: str = "fa") -> str:
    return ("; " if lang == "en" else "؛ ").join(x[lang if lang in ("fa", "en") else "fa"] for x in summary)


# ───────────────────────────────────────────── plain-language rules (no model needed)

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
ORDINALS = {"اول": 1, "اولین": 1, "یکم": 1, "دوم": 2, "دومین": 2, "سوم": 3, "سومین": 3, "چهارم": 4, "چهارمین": 4, "پنجم": 5, "پنجمین": 5,
            "ششم": 6, "ششمین": 6, "هفتم": 7, "هشتم": 8, "نهم": 9, "دهم": 10}
EN_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
COLOR_WORDS = {
    "قرمز": ("#e63946", "red"), "نارنجی": ("#f77f00", "orange"), "زرد": ("#ffbe0b", "yellow"), "سبز": ("#2a9d5c", "green"), "آبی": ("#1d6fd1", "blue"),
    "بنفش": ("#7b2cbf", "purple"), "صورتی": ("#ef476f", "pink"), "فیروزه": ("#126f85", "teal"), "سفید": ("#ffffff", "white"), "مشکی": ("#111111", "black"),
    "سیاه": ("#111111", "black"), "طلایی": ("#d4a017", "gold"), "نقره": ("#b8c0cc", "silver"), "خاکستری": ("#6b7280", "grey"),
}
EN_COLORS = {"red": "#e63946", "orange": "#f77f00", "yellow": "#ffbe0b", "green": "#2a9d5c", "blue": "#1d6fd1", "purple": "#7b2cbf", "pink": "#ef476f",
             "teal": "#126f85", "white": "#ffffff", "black": "#111111", "gold": "#d4a017", "silver": "#b8c0cc", "grey": "#6b7280", "gray": "#6b7280"}


def _norm(t: str) -> str:
    t = (t or "").translate(_FA_DIGITS)
    t = t.replace("ي", "ی").replace("ك", "ک").replace("‌", " ").replace("‍", "")
    t = re.sub(r"[ً-ٟ]", "", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def _targets(text: str, n: int) -> list:
    """Which scenes? «scene two», «scene 3», «last scene», «all scenes» (and the Persian forms); default: all (or the first when a title is meant)."""
    t = _norm(text)
    if re.search(r"(همه|تمام|هر)\s*(ی)?\s*صحنه", t) or "همه جا" in t or re.search(r"\ball (the )?scenes\b|\bevery scene\b|\beverywhere\b", t):
        return list(range(n))
    if re.search(r"آخر(ین)?\s*(ی)?\s*صحنه|صحنه\s*(ی)?\s*آخر|\blast scene\b", t):
        return [n - 1]
    m = (re.search(r"صحنه\s*(?:ی|ء)?\s*(\d{1,2})", t) or re.search(r"(\d{1,2})\s*(?:م|ُم)?\s*صحنه", t) or re.search(r"\bscene\s*(\d{1,2})\b", t)
         or re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\s+scene\b", t))
    if m and 1 <= int(m.group(1)) <= n:
        return [int(m.group(1)) - 1]
    for w, k in ORDINALS.items():
        if re.search(rf"(?:صحنه\s*(?:ی|ء)?\s*{w}\b|\b{w}\s*(?:ین)?\s*صحنه)", t) and k <= n:
            return [k - 1]
    for w, k in EN_ORDINALS.items():
        if re.search(rf"\b{w} scene\b|\bscene {w}\b", t) and k <= n:
            return [k - 1]
    if re.search(r"(تیتر|عنوان)|\btitle\b|\bheadline\b", t):          # «bigger title» = the title of the video = the first scene
        return [0]
    return []


def _warm(hexc: str, amount: float) -> str:
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    goal = 0.08 if amount > 0 else 0.55            # warmer = toward orange (hue 0.08); cooler = toward teal (hue 0.55)
    d = ((goal - h + 0.5) % 1.0) - 0.5
    h = (h + d * min(1.0, abs(amount))) % 1.0
    s = max(s, 0.55)
    v = max(v, 0.6)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def rules_patch(text: str, plan: dict, lang: str = "fa") -> dict:
    """A command in Persian or English => {"ops": [...], "say": "one sentence", "say_fa", "say_en"} or {"ops": [], "say": "I did not understand ..."}. Common phrases only."""
    t = _norm(text)
    n = len(plan["scenes"])
    tg = _targets(t, n)
    ops: list = []
    say = ("", "")
    over_fa = "همهٔ صحنه‌ها" if not tg else ("صحنهٔ " + "، ".join(str(i + 1) for i in tg))
    over_en = "all scenes" if not tg else ("scene " + ", ".join(str(i + 1) for i in tg))
    ids = tg or list(range(n))

    def per(fn):
        for i in ids:
            fn(i)

    if re.search(r"(حذف|پاک)\s*(کن|شود|بشه)?.*صحنه|صحنه.*(حذف|پاک)|\b(remove|delete)\b.*\bscene\b", t) and tg and n > 1:
        for i in sorted(tg, reverse=True):
            ops.append({"op": "remove_scene", "index": i})
        say = (f"{over_fa} حذف شد.", f"Removed {over_en}.")
    elif re.search(r"(تکرار|کپی|دوباره بیاور)|\b(duplicate|copy|repeat)\b", t) and tg:
        ops.append({"op": "duplicate_scene", "index": tg[0]})
        say = (f"{over_fa} تکرار شد.", f"Duplicated {over_en}.")
    elif re.search(r"(جابه ?جا|عوض|ببر|بیار|منتقل)|\b(swap|move)\b", t) and re.search(r"صحنه|scene", t) and not re.search(r"(بزرگ|کوچک|رنگ|bigger|smaller|colou?r)", t):
        nums = [int(x) for x in re.findall(r"\d{1,2}", t)]
        words = [k for w, k in ORDINALS.items() if re.search(rf"\b{w}\b", t)] + [k for w, k in EN_ORDINALS.items() if re.search(rf"\b{w}\b", t)]
        pair = (nums + words)[:2]
        if re.search(r"(اول|ابتدا|شروع)|\b(start|beginning)\b", t) and len(pair) >= 1 and not (len(pair) == 2 and pair[1] != 1):
            pair = [pair[0], 1]
        elif re.search(r"(آخر|انتها|پایان)|\b(end|last)\b", t) and len(pair) >= 1:
            pair = [pair[0], n]
        if len(pair) == 2 and all(1 <= p <= n for p in pair) and pair[0] != pair[1]:
            ops.append({"op": "move_scene", "from": pair[0] - 1, "to": pair[1] - 1})
            say = (f"صحنهٔ {pair[0]} به جای صحنهٔ {pair[1]} رفت.", f"Scene {pair[0]} moved to the place of scene {pair[1]}.")
    if not ops and re.search(r"بزرگ ?تر|درشت ?تر|بیشتر.*(اندازه|فونت)|اندازه.*بیشتر|\b(bigger|larger)\b", t):
        per(lambda i: ops.append({"op": "scale", "path": f"scenes/{i}/tokens/font_scale", "factor": 1.18, "min": 0.6, "max": 1.6, "default": 1}))
        say = (f"متن {over_fa} بزرگ‌تر شد.", f"The text of {over_en} is bigger.")
    elif not ops and re.search(r"کوچک ?تر|ریز ?تر|\bsmaller\b", t):
        per(lambda i: ops.append({"op": "scale", "path": f"scenes/{i}/tokens/font_scale", "factor": 0.85, "min": 0.6, "max": 1.6, "default": 1}))
        say = (f"متن {over_fa} کوچک‌تر شد.", f"The text of {over_en} is smaller.")
    elif not ops and re.search(r"گرم ?تر|\bwarmer\b", t):
        for i in ids:
            cur = (plan["scenes"][i].get("tokens") or {}).get("accent") or "#126f85"
            ops.append({"op": "set", "path": f"scenes/{i}/tokens/accent", "value": _warm(cur, 0.85)})
        say = (f"رنگ تأکید {over_fa} گرم‌تر شد.", f"The accent colour of {over_en} is warmer.")
    elif not ops and re.search(r"سرد ?تر|\b(cooler|colder)\b", t):
        for i in ids:
            cur = (plan["scenes"][i].get("tokens") or {}).get("accent") or "#d4a017"
            ops.append({"op": "set", "path": f"scenes/{i}/tokens/accent", "value": _warm(cur, -0.7)})
        say = (f"رنگ تأکید {over_fa} سردتر شد.", f"The accent colour of {over_en} is cooler.")
    elif not ops and re.search(r"رنگ|colou?r", t):
        found = next(((w, hx, en) for w, (hx, en) in COLOR_WORDS.items() if w in t), None) or next(((w, hx, w) for w, hx in EN_COLORS.items() if re.search(rf"\b{w}\b", t)), None)
        if found:
            w, hx, en_name = found
            what = "bg" if re.search(r"(زمینه|پس ?زمینه|بک ?گراند)|\b(background|backdrop)\b", t) else "text" if re.search(r"(متن|نوشته|تیتر|فونت)|\b(text|font)\b", t) else "accent"
            per(lambda i: ops.append({"op": "set", "path": f"scenes/{i}/tokens/{what}", "value": hx}))
            fa_what = "زمینه" if what == "bg" else "متن" if what == "text" else "تأکید"
            say = (f"رنگ {fa_what} {over_fa} {w} شد.", f"The {'background' if what == 'bg' else what} colour of {over_en} is {en_name}.")
    secs = re.search(r"(\d+(?:\.\d+)?)\s*(?:ثانیه|seconds?|secs?|s)\b", t)
    amount = min(10.0, float(secs.group(1))) if secs and float(secs.group(1)) > 0 else None
    if not ops and re.search(r"(طولانی ?تر|بیشتر نگه|مدت.*(بیشتر|زیاد)|ثانیه.*بیشتر|بیشتر.*ثانیه|کندتر|آهسته ?تر)|\b(longer|slower)\b", t):
        by = amount or 1.5
        per(lambda i: ops.append({"op": "shift", "path": f"scenes/{i}/duration", "by": by, "min": 1, "max": 30}))
        say = (f"مدت {over_fa} {by:g} ثانیه بیشتر شد.", f"{over_en.capitalize()} now last {by:g} s longer.")
    elif not ops and re.search(r"(کوتاه ?تر|تندتر|سریع ?تر|مدت.*(کمتر|کم)|ثانیه.*کمتر|کمتر.*ثانیه)|\b(shorter|faster|quicker)\b", t):
        by = amount or 1.0
        per(lambda i: ops.append({"op": "shift", "path": f"scenes/{i}/duration", "by": -by, "min": 1, "max": 30}))
        say = (f"مدت {over_fa} {by:g} ثانیه کمتر شد.", f"{over_en.capitalize()} now last {by:g} s less.")
    if not ops and re.search(r"(بدون|حذف).*(حرکت ?دوربین|دوربین)|\b(no|remove)\b.*\bcamera\b", t):
        per(lambda i: ops.append({"op": "remove", "path": f"scenes/{i}/camera"}))
        say = (f"حرکت دوربین {over_fa} برداشته شد.", f"The camera move of {over_en} was removed.")
    elif not ops and re.search(r"(دوربین|زوم|نزدیک)|\b(camera|zoom)\b", t):
        mv = "pull-out" if re.search(r"(دور ?تر|دور شو|دور کن|عقب)|\b(out|away|back)\b", t) else "pan-right" if re.search(r"پن|\bpan\b", t) else "push-in"
        per(lambda i: ops.append({"op": "set", "path": f"scenes/{i}/camera", "value": {"move": mv, "amount": 0.6}}))
        say = (f"دوربین در {over_fa} حرکت می‌کند ({mv}).", f"The camera moves in {over_en} ({mv}).")
    if not ops and re.search(r"(زیرنویس)|\b(captions?|subtitles?)\b", t):
        on = not re.search(r"(بدون|حذف|بردار|خاموش)|\b(no|remove|off|without)\b", t)
        ops.append({"op": "set", "path": "captions", "value": {"on": on, "position": "lower"}})
        say = ("زیرنویس کلمه‌به‌کلمه تنظیم شد.", "The word-by-word captions are set.")
    if not ops:
        for key, pid in (("ریلز|\\breels\\b", "reels"), ("استوری|\\bstory\\b", "story"), ("تیک ?تاک|\\btiktok\\b", "tiktok"), ("شورتس|\\bshorts\\b", "shorts")):
            if re.search(key, t):
                ops.append({"op": "set", "path": "platform", "value": pid})
                say = (f"چیدمان برای {motionlib.platform_label(pid, 'fa')} تنظیم شد (فاصله از نوارهای برنامه).",
                       f"The layout is set for {motionlib.platform_label(pid, 'en')} (clear of the app's bars).")
                break
    if not ops:
        fa = "منظورتان را نفهمیدم. مثلاً بگویید: «تیتر بزرگ‌تر شود»، «رنگ صحنهٔ دوم گرم‌تر»، «صحنهٔ سوم ۲ ثانیه بیشتر»، «زیرنویس اضافه کن»."
        en = "I did not understand. For example: “bigger title”, “warmer colour in scene 2”, “scene 3 longer”, “captions on”."
        return {"ops": [], "say": en if lang == "en" else fa, "say_fa": fa, "say_en": en}
    return {"ops": ops[:MAX_OPS], "say": say[1] if lang == "en" else say[0], "say_fa": say[0], "say_en": say[1]}
