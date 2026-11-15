"""The SCENE PLAN: the single source of truth of a motion-graphics shot; validation and cleaning on the server side.

SOURCE: ported from NMarketing:backend/apps/motion/specs.py @ motion v2, adapted for InstAI: the plan names an InstAI art style (the kit of the style
library) instead of NMarketing's catalogue, the size is one of the three sizes of remotion/src/catalog.ts, the brand / audio blocks became the series
context (title, episode, characters), errors and notes carry Persian AND English text, and the honesty rule of InstAI's explainers is enforced here:
every number component says «example» unless it names a verified source.

What a template form builds, a model writes and the owner edits in the scene cards or in the raw JSON: nothing outside this list reaches the renderer -
the component type (components.py), the keys of each component with their length limits, the number of scenes, the duration, the size, and the
transition / motion / easing names of motionlib.py.

Plan: version, style, theme, size, fps, lang, digits, platform (=> safe), series{title,episode,episode_title,channel,characters[]}, intensity, transition,
captions{on,position}, bare, scenes[]: type, duration, <the component's fields>, enter, exit, ease, spring, emphasis[], camera{move,amount}, transition,
tokens{accent,text,bg,font_scale,align}, overlays[]{type,at,dur,anchor,dx,dy,<fields>}, narration, cues[]{w,s,e}.
"""
from __future__ import annotations

import re

from . import components, motionlib, timeline

SCHEMA_VERSION = 1
SIZES = tuple(motionlib.SIZES)
DEFAULT_SIZE = "vertical"
MAX_SCENES = 14
MIN_SCENE_S, MAX_SCENE_S = 1.0, 30.0
MAX_TOTAL_S = 120.0
FPS_CHOICES = (24, 25, 30, 50, 60)
MAX_OVERLAYS = 4
MAX_CUES = 240
MAX_NARRATION = 700
ANCHORS = ("top", "upper", "center", "lower", "bottom", "top-start", "top-end", "bottom-start", "bottom-end")
CAPTION_POSITIONS = ("lower", "center", "upper", "bottom")
ITEM_MAX = components.ITEM_MAX
#: a picture a plan may name: one of the shot's own assets (resolved by the server into spec.assets), the keyframe, the series logo, or an inline data URI
REF_RE = re.compile(r"^(asset:\d{1,12}|keyframe|logo)$|^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]{16,}$")
HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")

#: ready-made chains the page offers as «quick starts» (a single component or a short story)
TEMPLATES = [
    {"id": "episode_intro", "fa": "شروع قسمت", "en": "Episode opening", "scenes": ["title", "kinetic_title"]},
    {"id": "explainer", "fa": "توضیح مفهوم", "en": "Concept explainer", "scenes": ["kinetic_title", "list", "stat", "social_cta"]},
    {"id": "what_if", "fa": "اگر چنین می‌شد؟", "en": "What if?", "scenes": ["title", "before_after", "quote", "social_cta"]},
    {"id": "data_story", "fa": "روایت داده", "en": "Data story", "scenes": ["title", "bar_chart", "donut", "social_cta"]},
    {"id": "recap", "fa": "جمع‌بندی و قسمت بعد", "en": "Recap and next episode", "scenes": ["checklist", "countdown", "social_cta"]},
]


class SpecError(ValueError):
    """A validation error; `str(e)` is Persian, `e.en` the English text."""

    def __init__(self, fa: str, en: str = ""):
        super().__init__(fa)
        self.fa = fa
        self.en = en or fa


def note(notes, fa: str, en: str) -> None:
    """Append a silent correction to `notes` ([{fa, en}]) once."""
    if notes is not None and not any(n["fa"] == fa for n in notes):
        notes.append({"fa": fa, "en": en})


def _s(v, n: int, field: str = "") -> str:
    if v is None:
        return ""
    if not isinstance(v, (str, int, float)) or isinstance(v, bool):
        raise SpecError(f"مقدار «{field}» باید متن باشد.", f"“{field}” must be text.")
    s = str(v).replace("\r", "").replace("\x00", "").strip()
    s = re.sub(r"[‪-‮⁦-⁩]", "", s)         # hidden bidi controls
    return s[:n]


def _ref(v, field: str) -> str:
    s = _s(v, 4_000_000, field)
    if not s:
        return ""
    if not REF_RE.match(s):
        raise SpecError(f"منبع تصویر «{field}» معتبر نیست (باید یکی از دارایی‌های همین قسمت یا لوگوی سریال باشد).",
                        f"The picture source of “{field}” is not valid (it must be one of this episode's assets or the series logo).")
    return s


def _num(v, lo: float, hi: float, default=None, notes=None, field: str = ""):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x or x in (float("inf"), float("-inf")):
        return default
    c = max(lo, min(hi, x))
    if c != x:
        note(notes, f"«{field}» به بازهٔ مجاز ({lo:g} تا {hi:g}) برگردانده شد.", f"“{field}” was brought back into its range ({lo:g} to {hi:g}).")
    return c


def _hex(v) -> str | None:
    if isinstance(v, str) and HEX_RE.match(v.strip()):
        t = v.strip()
        return (t if t.startswith("#") else "#" + t).lower()
    return None


# ───────────────────────────────────────────── one field of a component

def _field(spec: dict, v, name: str, notes=None):
    """The cleaned value, or None = leave this field out."""
    k = spec["kind"]
    if k == "str":
        return _s(v, spec["max"], name)
    if k == "ref":
        return _ref(v, name) or None
    if k == "bool":
        return bool(v)
    if k == "int":
        try:
            return int(max(spec["min"], min(spec["max"], int(float(v)))))
        except (TypeError, ValueError):
            return None
    if k == "num":
        return _num(v, spec["min"], spec["max"], None, notes, name)
    if k == "enum":
        t = _s(v, 40, name)
        if t in spec["choices"]:
            return t
        if t:
            note(notes, f"«{name}»: مقدار «{t}» مجاز نبود و کنار گذاشته شد.", f"“{name}”: the value “{t}” is not allowed and was dropped.")
        return None
    if k == "strs":
        if not isinstance(v, (list, tuple)):
            raise SpecError(f"«{name}» باید فهرست باشد.", f"“{name}” must be a list.")
        items = [_s(x, spec["item_max"], name) for x in v][: spec["max_items"]]
        return [x for x in items if x]
    if k == "objs":
        if not isinstance(v, (list, tuple)):
            raise SpecError(f"«{name}» باید فهرست باشد.", f"“{name}” must be a list.")
        out = []
        first = next(iter(spec["fields"]))
        for row in list(v)[: spec["max_items"]]:
            if isinstance(row, (str, int, float)) and not isinstance(row, bool):
                row = {first: row}
            if not isinstance(row, dict):
                continue
            o = {}
            for fn, fs in spec["fields"].items():
                if fn in row:
                    fv = _field(fs, row[fn], f"{name}.{fn}", notes)
                    if fv not in (None, "", []):
                        o[fn] = fv
            if o:
                out.append(o)
        return out
    return None


def _fields(comp: dict, sc: dict, notes=None) -> dict:
    out = {}
    for key, spec in comp["fields"].items():
        if key not in sc:
            continue
        v = _field(spec, sc[key], key, notes)
        if spec["kind"] in ("str", "ref") and not v:
            if spec["kind"] == "str" and key in sc and v == "":
                out[key] = ""
            continue
        if v is None:
            continue
        out[key] = v
    return out


def _has(out: dict, key: str) -> bool:
    v = out.get(key)
    return bool(v) or v == 0 and isinstance(v, (int, float)) and not isinstance(v, bool) and key in ("value", "score", "from")


def _check_need(comp: dict, out: dict, where: str, where_en: str) -> None:
    need = comp["need"]
    if need and not any(_has(out, k) for k in need):
        raise SpecError(f"{where} («{comp['label_fa']}») «{' یا '.join(need)}» ندارد.", f"{where_en} (“{comp['label_en']}”) has no {' or '.join(need)}.")


def _honesty(comp_id: str, out: dict, allowed_sources) -> None:
    """InstAI's explainer rule: a number on screen is an «example» unless the scene names a verified source. A source that is not in the episode's verified
    sources (when the caller knows them) is dropped; with no source the scene is marked example (the renderer cannot switch the chip off)."""
    if comp_id not in components.DATA_IDS:
        return
    src = str(out.get("source") or "").strip()
    if src and allowed_sources is not None and src not in allowed_sources:
        src = ""
    if src:
        out["source"] = src
        out.pop("example", None)
    else:
        out.pop("source", None)
        out["example"] = True


# ───────────────────────────────────────────── one scene

def _tokens(t, notes) -> dict:
    out: dict = {}
    if not isinstance(t, dict):
        return out
    for k in ("accent", "text", "bg"):
        if t.get(k) is not None:
            h = _hex(t[k])
            if h:
                out[k] = h
            else:
                note(notes, f"رنگ «{k}» معتبر نبود (باید #RRGGBB باشد).", f"The colour “{k}” was not valid (it must be #RRGGBB).")
    if t.get("font_scale") is not None:
        fs = _num(t["font_scale"], 0.6, 1.6, None, notes, "font_scale")
        if fs is not None:
            out["font_scale"] = round(fs, 2)
    if t.get("align") in motionlib.ALIGNS:
        out["align"] = t["align"]
    return out


def _cues(raw, dur: float) -> list:
    out = []
    if not isinstance(raw, (list, tuple)):
        return out
    for c in list(raw)[:MAX_CUES]:
        if not isinstance(c, dict):
            continue
        w = _s(c.get("w"), 40)
        s, e = _num(c.get("s"), 0, 600), _num(c.get("e"), 0, 600)
        if w and s is not None and e is not None and e >= s:
            out.append({"w": w, "s": round(s, 3), "e": round(e, 3)})
    return out


def normalize_overlay(ov, idx: int, dur: float, notes=None, allowed_sources=None) -> dict:
    if not isinstance(ov, dict):
        raise SpecError(f"رویهٔ {idx + 1} معتبر نیست.", f"Overlay {idx + 1} is not valid.")
    typ = _s(ov.get("type"), 24)
    comp = components.get(typ)
    if not comp or not comp["overlay"]:
        raise SpecError(f"«{typ}» را نمی‌شود روی صحنه گذاشت (مجاز: {'، '.join(components.OVERLAY_IDS)}).",
                        f"“{typ}” cannot be laid over a scene (allowed: {', '.join(components.OVERLAY_IDS)}).")
    out = {"type": typ}
    at = _num(ov.get("at"), 0, max(0.0, dur - 0.3), 0.0, notes, "at")
    out["at"] = round(at or 0.0, 2)
    if ov.get("dur") is not None:
        d = _num(ov["dur"], 0.5, MAX_SCENE_S, None, notes, "dur")
        if d is not None:
            out["dur"] = round(d, 2)
    anchor = _s(ov.get("anchor"), 20)
    if anchor in ANCHORS:
        out["anchor"] = anchor
    for k in ("dx", "dy"):
        if ov.get(k) is not None:
            x = _num(ov[k], -0.5, 0.5, None, notes, k)
            if x is not None:
                out[k] = round(x, 3)
    out.update(_fields(comp, ov, notes))
    _check_need(comp, out, f"رویهٔ {idx + 1}", f"Overlay {idx + 1}")
    _honesty(typ, out, allowed_sources)
    return out


def normalize_scene(sc: dict, idx: int = 0, notes=None, allowed_sources=None) -> dict:
    if not isinstance(sc, dict):
        raise SpecError(f"صحنهٔ {idx + 1} معتبر نیست.", f"Scene {idx + 1} is not valid.")
    typ = _s(sc.get("type"), 24) or "title"
    comp = components.get(typ)
    if comp is None:
        raise SpecError(f"نوع صحنهٔ «{typ}» را نمی‌شناسم (مجاز: {'، '.join(components.SCENE_IDS)}).",
                        f"Unknown scene type “{typ}” (allowed: {', '.join(components.SCENE_IDS)}).")
    try:
        dur0 = float(sc.get("duration", 4))
    except (TypeError, ValueError):
        raise SpecError(f"مدت صحنهٔ {idx + 1} عدد نیست.", f"The duration of scene {idx + 1} is not a number.")
    dur = max(MIN_SCENE_S, min(MAX_SCENE_S, dur0))
    if dur != dur0:
        note(notes, f"مدت صحنهٔ {idx + 1} به بازهٔ {MIN_SCENE_S:g} تا {MAX_SCENE_S:g} ثانیه برگردانده شد.",
             f"The duration of scene {idx + 1} was brought back into {MIN_SCENE_S:g} to {MAX_SCENE_S:g} seconds.")
    out: dict = {"type": typ, "duration": round(dur, 2)}
    out.update(_fields(comp, sc, notes))
    _check_need(comp, out, f"صحنهٔ {idx + 1}", f"Scene {idx + 1}")
    _honesty(typ, out, allowed_sources)
    # shared properties of every scene: the way it enters / leaves, curve, camera, transition, colours, overlays, narration
    for key, table in (("enter", motionlib.ENTER_KINDS), ("exit", motionlib.EXIT_KINDS), ("ease", motionlib.EASES), ("spring", motionlib.SPRINGS)):
        if sc.get(key) not in (None, ""):
            v = _s(sc[key], 30, key)
            if v in table:
                out[key] = v
            else:
                note(notes, f"صحنهٔ {idx + 1}: «{key}» = «{v}» را نمی‌شناسم و کنار گذاشتم.", f"Scene {idx + 1}: “{key}” = “{v}” is unknown and was dropped.")
    if sc.get("transition") not in (None, ""):
        v = _s(sc["transition"], 20, "transition")
        if v in motionlib.TRANS_KINDS:
            out["transition"] = v
        else:
            note(notes, f"صحنهٔ {idx + 1}: گذار «{v}» را نمی‌شناسم و کنار گذاشتم.", f"Scene {idx + 1}: the transition “{v}” is unknown and was dropped.")
    if isinstance(sc.get("emphasis"), (list, tuple)):
        em = [_s(w, 24, "emphasis") for w in sc["emphasis"][:8]]
        em = [w for w in em if w]
        if em:
            out["emphasis"] = em
    cam = sc.get("camera")
    if isinstance(cam, dict) and cam.get("move") in motionlib.CAMERA_MOVES and cam.get("move") != "none":
        out["camera"] = {"move": cam["move"], "amount": round(_num(cam.get("amount"), 0, 1, 0.5, notes, "camera.amount"), 2)}
    tok = _tokens(sc.get("tokens"), notes)
    if tok:
        out["tokens"] = tok
    if isinstance(sc.get("overlays"), (list, tuple)):
        ovs = [normalize_overlay(o, i, dur, notes, allowed_sources) for i, o in enumerate(sc["overlays"][:MAX_OVERLAYS])]
        if ovs:
            out["overlays"] = ovs
    if sc.get("narration"):
        nar = _s(sc["narration"], MAX_NARRATION, "narration")
        if nar:
            out["narration"] = nar
    cues = _cues(sc.get("cues"), dur)
    if cues:
        out["cues"] = cues
    return out


# ───────────────────────────────────────────── the series context

def normalize_series(s) -> dict:
    """{title, episode, episode_title, channel, characters[]}: who the episode is about. Always the same keys: normalisation is idempotent."""
    out: dict = {"title": "", "episode": 0, "episode_title": "", "channel": "", "characters": []}
    if not isinstance(s, dict):
        return out
    out["title"] = _s(s.get("title"), 80)
    try:
        out["episode"] = max(0, min(999, int(float(s.get("episode") or 0))))
    except (TypeError, ValueError):
        out["episode"] = 0
    out["episode_title"] = _s(s.get("episode_title"), 140)
    out["channel"] = _s(s.get("channel"), 80)
    chars = [_s(c, 40) for c in (s.get("characters") or [])[:8]] if isinstance(s.get("characters"), (list, tuple)) else []
    out["characters"] = [c for c in chars if c]
    return out


def total_seconds(spec: dict, kit: dict | None = None) -> float:
    return timeline.total_seconds(spec, kit) if spec.get("scenes") else 0.0


def normalize_spec(spec: dict, *, max_total: float = MAX_TOTAL_S, notes: list | None = None, allowed_sources=None, kit: dict | None = None) -> dict:
    """spec => the cleaned spec; a problem => SpecError. `notes` (a list) receives {fa, en} for every silent correction.
    `allowed_sources`: the titles of the episode's VERIFIED sources (None = trust a named source, as on the Remotion page)."""
    if not isinstance(spec, dict):
        raise SpecError("پارامترهای ویدیو معتبر نیستند.", "The video parameters are not valid.")
    ver = spec.get("version", 1)
    try:
        ver = int(ver)
    except (TypeError, ValueError):
        ver = 1
    if ver > SCHEMA_VERSION:
        raise SpecError(f"نسخهٔ طرح ({ver}) از نسخهٔ این برنامه ({SCHEMA_VERSION}) جدیدتر است.", f"The plan version ({ver}) is newer than this program's ({SCHEMA_VERSION}).")
    from instai.styles import library

    style = _s(spec.get("style"), 64)
    if style and not library.get_style(style):
        note(notes, f"سبک «{style}» پیدا نشد؛ سبک پیش‌فرض گذاشته شد.", f"The style “{style}” was not found; the default style is used.")
        style = ""
    theme = _s(spec.get("theme"), 64)
    size = _s(spec.get("size"), 12) or DEFAULT_SIZE
    if size not in SIZES:
        raise SpecError("اندازهٔ تصویر باید افقی، عمودی یا مربع باشد.", "The size must be landscape, vertical or square.")
    scenes_in = spec.get("scenes")
    if not isinstance(scenes_in, list) or not scenes_in:
        raise SpecError("دست‌کم یک صحنه لازم است.", "At least one scene is needed.")
    if len(scenes_in) > MAX_SCENES:
        raise SpecError(f"حداکثر {MAX_SCENES} صحنه.", f"At most {MAX_SCENES} scenes.")
    try:
        fps = int(spec.get("fps", 30))
    except (TypeError, ValueError):
        fps = 30
    if fps not in FPS_CHOICES:
        fps = 30
    lang = _s(spec.get("lang"), 2) or "fa"
    digits = _s(spec.get("digits"), 4) or "auto"
    out = {
        "version": SCHEMA_VERSION, "style": style, "theme": theme, "size": size, "fps": fps, "lang": lang if lang in ("fa", "en") else "fa",
        "digits": digits if digits in ("fa", "en", "auto") else "auto", "series": normalize_series(spec.get("series")),
        "scenes": [normalize_scene(s, i, notes, allowed_sources) for i, s in enumerate(scenes_in)],
    }
    try:
        k = float(spec.get("intensity", 1))
    except (TypeError, ValueError):
        k = 1.0
    out["intensity"] = round(max(0.5, min(1.5, k)), 2)
    tr = _s(spec.get("transition"), 20)
    if tr:
        if tr not in motionlib.TRANS_KINDS:
            raise SpecError(f"گذار «{tr}» را نمی‌شناسم.", f"Unknown transition “{tr}”.")
        out["transition"] = tr
    platform = _s(spec.get("platform"), 12)
    if platform:
        if platform in motionlib.PLATFORMS:
            out["platform"] = platform
            out["safe"] = motionlib.platform_safe(platform, size)
        else:
            note(notes, f"پلتفرم «{platform}» را نمی‌شناسم و کنار گذاشتم.", f"The platform “{platform}” is unknown and was dropped.")
    cap = spec.get("captions")
    if isinstance(cap, dict) and cap.get("on"):
        pos = _s(cap.get("position"), 10)
        out["captions"] = {"on": True, "position": pos if pos in CAPTION_POSITIONS else "lower"}
    if spec.get("bare"):
        out["bare"] = True                # no backdrop: a clip that is laid over a picture
    total = total_seconds(out, kit)
    if total > max_total + 0.01:
        raise SpecError(f"مدت کل ویدیو {total:.0f} ثانیه است؛ حداکثر {max_total:.0f} ثانیه مجاز است.", f"The video is {total:.0f} s long; at most {max_total:.0f} s are allowed.")
    out["total_s"] = round(total, 2)
    return out


def upgrade(spec: dict) -> dict:
    """Any older plan => the current version (only the version changes; every newer key is optional)."""
    return normalize_spec(spec)


def asset_refs(spec: dict) -> list:
    """Every picture reference of a plan (without repeats)."""
    refs: list = []
    for sc in spec.get("scenes") or []:
        for holder in [sc, *(sc.get("overlays") or [])]:
            comp = components.get(holder.get("type", ""))
            for key, fs in (comp["fields"].items() if comp else []):
                if fs["kind"] == "ref" and holder.get(key):
                    refs.append(holder[key])
    seen: set = set()
    return [r for r in refs if not (r in seen or seen.add(r))]


def sample_spec(style: str = "", template: str = "explainer", size: str = DEFAULT_SIZE, lang: str = "fa") -> dict:
    tpl = next((t for t in TEMPLATES if t["id"] == template), TEMPLATES[0])
    return {"version": SCHEMA_VERSION, "style": style, "size": size, "fps": 30, "lang": lang, "digits": "auto",
            "series": {"title": "", "episode": 0, "episode_title": "", "channel": "", "characters": []},
            "scenes": [components.sample(t, lang) for t in tpl["scenes"]]}


def word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text or "") if re.search(r"\w", w)])
