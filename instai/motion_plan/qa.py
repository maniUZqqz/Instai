"""Rule-based quality control (no model) and the loop «measure => fix => measure again».

SOURCE: ported from NMarketing:backend/apps/motion/qa.py @ motion v2, adapted for InstAI: the colours come from the style KIT (colors.palette_from_kit,
the same eight roles the renderer draws), there is no brand, every finding carries Persian AND English text, and the platforms are InstAI's.

Two layers:
  1) static_findings(spec) - from the plan itself, without a browser: reading time (about 0.32 s per Persian word), the least duration of a piece, crowding
     (words / items / overlays at once), the accent colour against the background, the length of the narration against the scene.
  2) geometry_findings(spec, shots) - from real frames: every shot = the geometry of every text block / box the page reported (INSTAI_QA, remotion/src/
     components/qa.tsx) + the picture of the same frame. Overflow and clipping, overlapping texts, the platform's safe area, the least font size and the
     WCAG contrast measured from the pixels behind the text.

Every finding carries an automatic fix (a list of patch.py operations): make the text smaller or bigger, make the scene longer, a readable colour, move an
overlay into the safe area, split a crowded scene. run_loop measures again after every round (at most 3) and returns the whole report.
"""
from __future__ import annotations

import math
from pathlib import Path

from . import colors, components, motionlib, specs, timeline
from . import patch as patch_mod

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}
LABELS = {
    "too_short": ("مدت صحنه کم است", "The scene is too short"), "crowded": ("صحنه شلوغ است", "The scene is crowded"),
    "overflow": ("متن از قاب یا کادر بیرون زده", "Text spills out of the frame or its box"), "overlap": ("دو متن روی هم افتاده‌اند", "Two texts overlap"),
    "safe_zone": ("بیرون از ناحیهٔ امن پلتفرم", "Outside the platform's safe area"), "small_text": ("متن خیلی ریز است", "The text is too small"),
    "low_contrast": ("کنتراست متن کم است", "The text contrast is low"), "accent_contrast": ("رنگ تأکید روی زمینه کم‌رنگ است", "The accent colour is faint on the background"),
    "speech_longer": ("گفتار از صحنه بلندتر است", "The speech is longer than the scene"), "platform_missing": ("پلتفرم انتخاب نشده", "No platform chosen"),
    "overlays_busy": ("رویه‌های هم‌زمان زیاد", "Too many overlays at once"),
}
READ_TOLERANCE = 0.65       # a viewer reads a little faster than the average: only a clearly too short scene is flagged
PRIORITY = ["too_short", "speech_longer", "overflow", "overlap", "safe_zone", "low_contrast", "accent_contrast", "small_text", "crowded", "overlays_busy"]
FA_NUM = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
SIDES = {"left": "چپ", "right": "راست", "top": "بالا", "bottom": "پایین"}


def fa(n) -> str:
    return str(n).translate(FA_NUM)


def parse_color(c):
    return colors.parse(c)


contrast = colors.contrast
best_text_color = colors.best_text_color
hexof = colors.hexof


def _finding(code, severity, scene, msg, ops=None, **extra) -> dict:
    """msg = (persian, english)."""
    lab = LABELS.get(code, (code, code))
    return {"code": code, "label": lab[0], "label_en": lab[1], "severity": severity, "scene": scene, "message": msg[0], "message_en": msg[1], "ops": ops or [],
            "auto": bool(ops), **extra}


def _scene_words(sc: dict) -> int:
    comp = components.get(sc.get("type", ""))
    if not comp:
        return 0
    total = 0
    for key in comp["read"]:
        v = sc.get(key)
        if isinstance(v, str):
            total += specs.word_count(v)
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, str):
                    total += specs.word_count(it)
                elif isinstance(it, dict):
                    for x in it.values():
                        if isinstance(x, str):
                            total += specs.word_count(x)
                        elif isinstance(x, list):
                            total += sum(specs.word_count(y) for y in x if isinstance(y, str))
    for ov in sc.get("overlays") or []:
        oc = components.get(ov.get("type", "")) or {}
        total += sum(specs.word_count(str(ov.get(k) or "")) for k in oc.get("read", ()) if isinstance(ov.get(k), str))
    return total


def reading_needed(sc: dict, lang: str = "fa") -> float:
    """The seconds this scene needs to be read: the entrance + the words x the rate; the least of each component; and the scene's speech."""
    comp = components.get(sc.get("type", "")) or {"dur": (2, 3, 6)}
    rate = motionlib.READ_S_PER_WORD if lang == "fa" else motionlib.READ_S_PER_WORD_EN
    n = _scene_words(sc)
    need = motionlib.ENTRANCE_S + n * rate
    if sc.get("type") in ("title", "stat", "social_cta", "logo", "kinetic_title", "countdown", "counter", "sticker"):
        need = max(need, comp["dur"][0])          # the busy pieces want their own least
    else:
        need = max(need, comp["dur"][0] * 0.8)
    return round(need, 2)


def speech_needed(sc: dict) -> float:
    cues = sc.get("cues") or []
    if cues:
        return round(max(c["e"] for c in cues) + 0.45, 2)
    nar = sc.get("narration") or ""
    return round(specs.word_count(nar) * 0.38 + 0.6, 2) if nar else 0.0


def _items_count(sc: dict) -> int:
    comp = components.get(sc.get("type", "")) or {}
    key = comp.get("items")
    if key and isinstance(sc.get(key), list):
        return len(sc[key])
    return max((len(v) for k, v in sc.items() if isinstance(v, list) and k not in ("overlays", "cues", "emphasis")), default=0)


def simultaneous(sc: dict) -> int:
    """An estimate of the moving things at once: items + overlays + the parallax camera."""
    n = _items_count(sc) + 2 * len(sc.get("overlays") or []) + (3 if (sc.get("camera") or {}).get("move") == "parallax" else 0)
    return n + (2 if sc.get("title") or sc.get("text") else 1)


def _can_split(sc: dict) -> bool:
    return len(patch_mod.split_scene(sc)) == 2


# ───────────────────────────────────────────── layer 1: from the plan itself

def static_findings(spec: dict, kit: dict | None = None) -> list:
    out: list = []
    lang = spec.get("lang", "fa")
    kit = kit or timeline.kit_of(spec)
    pal = colors.palette_from_kit(kit)
    for i, sc in enumerate(spec.get("scenes") or []):
        n = i + 1
        dur = float(sc.get("duration") or 4)
        need = reading_needed(sc, lang)
        sp = speech_needed(sc)
        if sp and sp > dur + 0.05:
            new = min(specs.MAX_SCENE_S, math.ceil(max(sp, need) * 2) / 2)
            out.append(_finding("speech_longer", "error", i, (
                f"صحنهٔ {fa(n)}: گفتار {fa(round(sp, 1))} ثانیه است ولی صحنه {fa(round(dur, 1))} ثانیه؛ مدت به {fa(new)} ثانیه می‌رسد.",
                f"Scene {n}: the speech is {sp:.1f} s but the scene is {dur:.1f} s; it becomes {new:g} s."),
                [{"op": "set", "path": f"scenes/{i}/duration", "value": new}], needed=sp, duration=dur))
        elif need > dur + READ_TOLERANCE:
            new = min(specs.MAX_SCENE_S, math.ceil(need * 2) / 2)
            out.append(_finding("too_short", "warn", i, (
                f"صحنهٔ {fa(n)}: برای خواندن متن دست‌کم {fa(round(need, 1))} ثانیه لازم است ({fa(_scene_words(sc))} کلمه)؛ مدت از {fa(round(dur, 1))} به {fa(new)} ثانیه می‌رسد.",
                f"Scene {n}: at least {need:.1f} s are needed to read the text ({_scene_words(sc)} words); the duration goes from {dur:.1f} to {new:g} s."),
                [{"op": "set", "path": f"scenes/{i}/duration", "value": new}], needed=need, duration=dur))
        words = _scene_words(sc)
        sim = simultaneous(sc)
        if words > motionlib.MAX_WORDS_PER_SCENE or sim > motionlib.MAX_SIMULTANEOUS:
            splittable = _can_split(sc)
            ops = [{"op": "split_scene", "index": i}] if splittable else ([{"op": "remove", "path": f"scenes/{i}/overlays"}] if sc.get("overlays") else [])
            out.append(_finding("crowded", "warn", i, (
                f"صحنهٔ {fa(n)} شلوغ است ({fa(words)} کلمه، حدود {fa(sim)} عنصر هم‌زمان)" + ("؛ به دو صحنه تقسیم می‌شود." if splittable else "."),
                f"Scene {n} is crowded ({words} words, about {sim} things at once)" + ("; it is split in two." if splittable else ".")), ops, words=words, simultaneous=sim))
        if len(sc.get("overlays") or []) >= 3 and not (words > motionlib.MAX_WORDS_PER_SCENE):
            out.append(_finding("overlays_busy", "info", i, (f"صحنهٔ {fa(n)} {fa(len(sc['overlays']))} رویهٔ هم‌زمان دارد؛ ساده‌ترش کنید.",
                                                             f"Scene {n} has {len(sc['overlays'])} overlays at once; keep it simpler.")))
        tok = sc.get("tokens") or {}
        acc = parse_color(tok.get("accent") or pal["accent"])
        bg = parse_color(tok.get("bg") or pal["bg"])
        if acc and bg and contrast(acc, bg) < 1.9:
            hx, ratio = best_text_color(bg, ("#ffffff", "#111111", "#ffbe0b", "#126f85", "#e63946"))
            out.append(_finding("accent_contrast", "warn", i, (
                f"صحنهٔ {fa(n)}: رنگ تأکید روی زمینه کم‌رنگ است (کنتراست {fa(round(contrast(acc, bg), 1))})؛ رنگ خواناتر گذاشته می‌شود.",
                f"Scene {n}: the accent colour is faint on the background (contrast {contrast(acc, bg):.1f}); a more readable colour is used."),
                [{"op": "set", "path": f"scenes/{i}/tokens/accent", "value": hx}], ratio=round(contrast(acc, bg), 2)))
    if not spec.get("platform") and spec.get("size") in ("vertical", "square"):
        pid = motionlib.DEFAULT_PLATFORM.get(spec["size"], "")
        out.append(_finding("platform_missing", "info", None, (
            f"پلتفرم انتشار انتخاب نشده؛ متن‌ها با ناحیهٔ امن {motionlib.platform_label(pid, 'fa')} کنترل نمی‌شوند.",
            f"No platform is chosen; the texts are not checked against the safe area of {motionlib.platform_label(pid, 'en')}."),
            [{"op": "set", "path": "platform", "value": pid}]) | {"auto": False})
    return out


# ───────────────────────────────────────────── the frames to measure

def key_frames(spec: dict, per_scene: int = 2, kit: dict | None = None) -> list:
    """Two frames per scene, away from the transitions: «enter» (the entrance has settled) and «late» (the end of the scene, before its exit)."""
    t = timeline.compute(spec, kit=kit)
    fps, scenes, out = t["fps"], spec.get("scenes") or [], []
    n = len(scenes)
    for i in range(n):
        start, length = t["starts"][i], t["frames"][i]
        tin = t["tfs"][i - 1] if i > 0 else 0
        tout = t["tfs"][i] if i < n - 1 else 0
        a, b = tin + 1, length - tout - 2
        if b <= a:
            a, b = 1, max(2, length - 2)
        enter_f = a + min(int((b - a) * 0.5), int(fps * (1.3 + 0.12 * min(8, _items_count(scenes[i])))))
        late_f = a + int((b - a) * 0.92)
        late_f = max(late_f, enter_f + 1)
        out.append({"scene": i, "kind": "enter", "frame": start + enter_f})
        if per_scene > 1:
            out.append({"scene": i, "kind": "late", "frame": start + min(late_f, length - 2)})
    total = t["total"]
    for k in out:
        k["frame"] = max(0, min(total - 1, k["frame"]))
    return out


# ───────────────────────────────────────────── layer 2: from the real frames

def _rect(b: dict):
    return (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])


def _inter(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def _ancestors(box: dict, by_id: dict) -> set:
    out, cur, guard = set(), box.get("parent", -1), 0
    while cur is not None and cur >= 0 and guard < 50:
        out.add(cur)
        cur = (by_id.get(cur) or {}).get("parent", -1)
        guard += 1
    return out


def sample_background(image, box: dict, scale: float, text_rgb) -> tuple | None:
    """The dominant colour behind the text: the pixels inside the text box that are far from the text's own colour, in buckets of 16; the fullest bucket."""
    try:
        W, H = image.size
        x0, y0 = max(0, int((box["x"] + box["w"] * 0.06) * scale)), max(0, int((box["y"] + box["h"] * 0.12) * scale))
        x1, y1 = min(W, int((box["x"] + box["w"] * 0.94) * scale)), min(H, int((box["y"] + box["h"] * 0.88) * scale))
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
        crop = image.crop((x0, y0, x1, y1)).convert("RGB")
        crop.thumbnail((64, 64))
        px = list(crop.getdata())
    except Exception:  # noqa: BLE001
        return None
    far = [p for p in px if (p[0] - text_rgb[0]) ** 2 + (p[1] - text_rgb[1]) ** 2 + (p[2] - text_rgb[2]) ** 2 > 60 ** 2]
    if len(far) < max(6, len(px) * 0.06):
        # almost every pixel is near the text colour: the text hides in a uniform background (contrast ~1) - or its glyphs fill the whole box (never uniform)
        near: dict = {}
        for p in px:
            near.setdefault((p[0] // 16, p[1] // 16, p[2] // 16), []).append(p)
        top = max(near.values(), key=len)
        if len(top) >= len(px) * 0.85:
            return tuple(sum(c[k] for c in top) // len(top) for k in range(3))
        return None
    buckets: dict = {}
    for p in far:
        buckets.setdefault((p[0] // 16, p[1] // 16, p[2] // 16), []).append(p)
    best = max(buckets.values(), key=len)
    return tuple(sum(c[k] for c in best) // len(best) for k in range(3))


def geometry_findings(spec: dict, shots: list, kit: dict | None = None) -> list:
    out: list = []
    seen: set = set()
    kit = kit or timeline.kit_of(spec)
    for shot in shots:
        W, H = shot["W"], shot["H"]
        boxes = shot.get("boxes") or []
        by_id = {b["id"]: b for b in boxes}
        safe = shot.get("safe") or {}
        sc_i = shot["scene"]
        n = sc_i + 1
        texts = [b for b in boxes if b.get("kind") == "text" and b.get("scene") == sc_i and b.get("opacity", 1) >= 0.5 and b["w"] > 3 and b["h"] > 3]
        scene = spec["scenes"][sc_i] if sc_i < len(spec["scenes"]) else {}
        cur_fs = float(((scene.get("tokens") or {}).get("font_scale")) or 1.0)

        def add(f):
            key = (f["code"], f["scene"], f.get("key", ""))
            if key not in seen:
                seen.add(key)
                f["shot"] = {"kind": shot["kind"], "frame": shot["frame"]}
                out.append(f)

        shrink = {"op": "set", "path": f"scenes/{sc_i}/tokens/font_scale", "value": round(max(0.6, cur_fs * 0.85), 2)}
        can_shrink = cur_fs > 0.62
        for b in texts:
            label = (b.get("text") or "")[:24]
            off = b["x"] < -4 or b["y"] < -4 or b["x"] + b["w"] > W + 4 or b["y"] + b["h"] > H + 4
            if b.get("overflow") or b.get("clipped") or off:
                ops = [shrink] if can_shrink else ([{"op": "split_scene", "index": sc_i}] if _can_split(scene) else [])
                add(_finding("overflow", "error", sc_i, (f"صحنهٔ {fa(n)}: متن «{label}» از قاب یا کادرش بیرون زده است.", f"Scene {n}: the text “{label}” spills out of the frame or its box."),
                             ops, key=label, box=_slim(b)))
            size_frac = b.get("size", 0) / H if b.get("size") else 1
            if b.get("size") and size_frac < motionlib.MIN_FONT_FRAC and b.get("role") != "caption":
                # the auto-fit already shrank this text to make it fit: only fewer items per scene helps, and only when it is really too small to read
                sev = "error" if size_frac < motionlib.MIN_FONT_ERROR else "warn" if size_frac < motionlib.MIN_FONT_WARN else "info"
                ops = [{"op": "split_scene", "index": sc_i}] if (sev == "error" and _can_split(scene) and _items_count(scene) >= 3) else (
                    [{"op": "set", "path": f"scenes/{sc_i}/tokens/font_scale", "value": round(min(1.6, cur_fs * 1.15), 2)}] if (sev == "error" and cur_fs < 1.3) else [])
                add(_finding("small_text", sev, sc_i, (
                    f"صحنهٔ {fa(n)}: متن «{label}» فقط {fa(round(size_frac * 100, 1))}٪ ارتفاع قاب است (حداقل {fa(round(motionlib.MIN_FONT_FRAC * 100, 1))}٪).",
                    f"Scene {n}: the text “{label}” is only {size_frac * 100:.1f} % of the frame height (at least {motionlib.MIN_FONT_FRAC * 100:.1f} %)."),
                    ops, key=label, box=_slim(b)))
            if any(safe.get(k, 0) > 0 for k in ("top", "right", "bottom", "left")):
                tol = 6
                bad = []
                if safe.get("left", 0) and b["x"] < safe["left"] - tol:
                    bad.append("left")
                if safe.get("right", 0) and b["x"] + b["w"] > W - safe["right"] + tol:
                    bad.append("right")
                if safe.get("top", 0) and b["y"] < safe["top"] - tol:
                    bad.append("top")
                if safe.get("bottom", 0) and b["y"] + b["h"] > H - safe["bottom"] + tol:
                    bad.append("bottom")
                if bad:
                    ov_i = _overlay_index(scene, b.get("overlay"))
                    if ov_i is not None:
                        dy = -0.15 if "bottom" in bad else 0.15 if "top" in bad else 0.0
                        ops = [{"op": "set", "path": f"scenes/{sc_i}/overlays/{ov_i}/dy", "value": max(-0.5, min(0.5, float((scene["overlays"][ov_i]).get("dy") or 0) + dy))}] if dy else \
                              [{"op": "set", "path": f"scenes/{sc_i}/overlays/{ov_i}/anchor", "value": "center"}]
                    else:
                        ops = [shrink] if can_shrink else []
                    add(_finding("safe_zone", "warn", sc_i, (
                        f"صحنهٔ {fa(n)}: متن «{label}» در ناحیهٔ {'، '.join(SIDES[s] for s in bad)} از ناحیهٔ امن پلتفرم بیرون است.",
                        f"Scene {n}: the text “{label}” leaves the platform's safe area on the {', '.join(bad)}."), ops, key=label + "".join(bad), box=_slim(b)))
        # overlap
        for ai in range(len(texts)):
            for bi in range(ai + 1, len(texts)):
                a, b = texts[ai], texts[bi]
                if a["id"] in _ancestors(b, by_id) or b["id"] in _ancestors(a, by_id):
                    continue
                if a.get("excl") and a.get("excl") == b.get("excl"):
                    continue                                    # stacked on purpose (before/after wipe)
                inter = _inter(_rect(a), _rect(b))
                small = min(a["w"] * a["h"], b["w"] * b["h"])
                if small > 0 and inter / small >= 0.18:
                    ov = a.get("overlay") or b.get("overlay")
                    ov_i = _overlay_index(scene, ov)
                    if ov_i is not None:
                        cur_anchor = (scene["overlays"][ov_i].get("anchor") or "lower")
                        alt = {"lower": "top", "bottom": "top", "top": "bottom", "upper": "bottom", "center": "bottom"}.get(cur_anchor, "bottom")
                        ops = [{"op": "set", "path": f"scenes/{sc_i}/overlays/{ov_i}/anchor", "value": alt}]
                    else:
                        ops = [shrink] if can_shrink else ([{"op": "split_scene", "index": sc_i}] if _can_split(scene) else [])
                    ta, tb = (a.get("text") or "")[:18], (b.get("text") or "")[:18]
                    add(_finding("overlap", "error" if inter / small >= 0.4 else "warn", sc_i, (f"صحنهٔ {fa(n)}: «{ta}» و «{tb}» روی هم افتاده‌اند.", f"Scene {n}: “{ta}” and “{tb}” overlap."),
                                 ops, key=f"{a['id']}-{b['id']}", box=_slim(a)))
        # contrast from the pixels
        img = shot.get("_image")
        if img is not None:
            scale = shot.get("scale", 1.0)
            for b in texts:
                col = parse_color(b.get("color", ""))
                if not col or col[3] < 0.5 or b.get("opacity", 1) < 0.85 or b["w"] < 24 or b["h"] < 14:
                    continue
                bg = sample_background(img, b, scale, col[:3])
                if bg is None:
                    continue
                ratio = contrast(col[:3], bg)
                big = (b.get("size", 0) / H) >= 0.03
                need = motionlib.MIN_CONTRAST if big else motionlib.MIN_CONTRAST_SMALL * 0.8
                if ratio < need:
                    hx, best = best_text_color(bg, ("#ffffff", "#111111"))
                    # a coloured accent word is fixed in the accent colour, ordinary text in the text colour
                    accents = [parse_color(c) for c in _accent_colours(kit, scene)]
                    is_accent = any(c and sum((c[k] - col[k]) ** 2 for k in range(3)) < 28 ** 2 for c in accents)
                    key = "accent" if is_accent else "text"
                    if is_accent:           # keep the hue of the style: the same colour made much darker / lighter, else white / near-black
                        tries = [hexof(colors.mix(col[:3], (0, 0, 0), 0.55)), hexof(colors.mix(col[:3], (255, 255, 255), 0.6)), hx]
                        good = [c for c in tries if contrast(parse_color(c), bg) >= need]
                        hx = good[0] if good else hx
                        best = contrast(parse_color(hx), bg)
                    ops = [{"op": "set", "path": f"scenes/{sc_i}/tokens/{key}", "value": hx}] if best > ratio + 0.6 else []
                    t20 = (b.get("text") or "")[:20]
                    add(_finding("low_contrast", "error" if ratio < 2.0 else "warn", sc_i, (
                        f"صحنهٔ {fa(n)}: متن «{t20}» کنتراست {fa(round(ratio, 1))} دارد (حداقل {fa(round(need, 1))}).",
                        f"Scene {n}: the text “{t20}” has contrast {ratio:.1f} (at least {need:.1f})."), ops, key=t20, ratio=round(ratio, 2), box=_slim(b)))
    return out


def _accent_colours(kit: dict, scene: dict) -> list:
    pal = colors.palette_from_kit(kit)
    out = [pal.get(k) for k in ("accent", "accent2", "accent3")]
    out.append((scene.get("tokens") or {}).get("accent"))
    return [c for c in out if c]


def _overlay_index(scene: dict, kind) -> int | None:
    if not kind:
        return None
    for i, ov in enumerate(scene.get("overlays") or []):
        if ov.get("type") == kind:
            return i
    return None


def _slim(b: dict) -> dict:
    return {k: (round(v, 1) if isinstance(v, float) else v) for k, v in b.items() if k in ("x", "y", "w", "h", "size", "role", "text", "overlay")}


# ───────────────────────────────────────────── the loop: measure => fix => measure again

GROUP = {"duration": "duration", "font_scale": "font", "tokens/text": "color", "tokens/accent": "color", "overlays": "overlay", "split_scene": "struct", "remove_scene": "struct"}


def _group(op: dict) -> str:
    path = str(op.get("path", ""))
    if op.get("op") in ("split_scene", "remove_scene"):
        return "struct"
    for k, g in GROUP.items():
        if k in path:
            return g
    return path or "other"


def _slim_finding(f: dict) -> dict:
    return {k: v for k, v in f.items() if k not in ("_image",)}


def _order(findings: list) -> list:
    return sorted(findings, key=lambda f: (PRIORITY.index(f["code"]) if f["code"] in PRIORITY else 99, SEVERITY_ORDER.get(f["severity"], 3)))


def apply_fixes(spec: dict, findings: list, *, max_total: float = specs.MAX_TOTAL_S, allowed_sources=None, kit: dict | None = None) -> tuple:
    """=> (new spec, applied[], unresolved[]). One fix per (scene, group of change) per round; structural ones from the bottom up so the numbers do not jump."""
    cur = spec
    applied, unresolved = [], []
    touched: set = set()
    work = [f for f in _order(findings) if f["severity"] in ("error", "warn") and f.get("ops") and f.get("auto", True)]
    struct = [f for f in work if any(_group(o) == "struct" for o in f["ops"])]
    plain = [f for f in work if f not in struct]
    for f in plain:
        groups = {(f["scene"], _group(o)) for o in f["ops"]}
        if groups & touched or (f["scene"], "struct") in touched:
            continue
        try:
            cur = patch_mod.apply_patch(cur, f["ops"], max_total=max_total, allowed_sources=allowed_sources, kit=kit)
        except patch_mod.PatchError as exc:
            unresolved.append({**_slim_finding(f), "why": str(exc), "why_en": exc.en})
            continue
        touched |= groups
        applied.append({"code": f["code"], "scene": f["scene"], "message": f["message"], "message_en": f.get("message_en", ""), "ops": f["ops"]})
    for f in sorted(struct, key=lambda x: -(x["scene"] if x["scene"] is not None else 0)):
        if (f["scene"], "struct") in touched:
            continue
        try:
            cur = patch_mod.apply_patch(cur, f["ops"], max_total=max_total, allowed_sources=allowed_sources, kit=kit)
        except patch_mod.PatchError as exc:
            unresolved.append({**_slim_finding(f), "why": str(exc), "why_en": exc.en})
            continue
        touched.add((f["scene"], "struct"))
        applied.append({"code": f["code"], "scene": f["scene"], "message": f["message"], "message_en": f.get("message_en", ""), "ops": f["ops"]})
    return cur, applied, unresolved


def run_loop(spec: dict, *, measure=None, rounds: int = 3, max_total: float = specs.MAX_TOTAL_S, on_round=None, allowed_sources=None, kit: dict | None = None) -> dict:
    """measure(spec) => shots (or None). => {spec, rounds[], fixed, remaining[], geometry: bool, geometry_error?}"""
    cur = spec
    kit = kit or timeline.kit_of(spec)
    report: dict = {"rounds": [], "fixed": 0, "remaining": [], "geometry": measure is not None}
    last: list = []
    for n in range(1, rounds + 1):
        shots = None
        geo: list = []
        if measure is not None:
            try:
                shots = measure(cur)
                geo = geometry_findings(cur, shots, kit)
            except Exception as exc:  # noqa: BLE001 - the browser / render was not available: the other rules go on
                report["geometry_error"] = str(exc)[:300]
                report["geometry"] = False
                measure = None
        findings = _order(static_findings(cur, kit) + geo)
        rec = {"n": n, "findings": [_slim_finding(f) for f in findings], "applied": [], "shots": [_shot_meta(s) for s in (shots or [])]}
        last = findings
        fixable = [f for f in findings if f["severity"] in ("error", "warn") and f.get("ops") and f.get("auto", True)]
        if not fixable:
            report["rounds"].append(rec)
            if on_round:
                on_round(rec)
            break
        new, applied, unresolved = apply_fixes(cur, findings, max_total=max_total, allowed_sources=allowed_sources, kit=kit)
        rec["applied"], rec["unresolved"] = applied, unresolved
        report["rounds"].append(rec)
        if on_round:
            on_round(rec)
        if not applied:
            break
        report["fixed"] += len(applied)
        cur = new
    if report["rounds"]:
        # the last round applied fixes but did not measure again => one final measurement
        if report["rounds"][-1].get("applied"):
            final = static_findings(cur, kit)
            if measure is not None:
                try:
                    final += geometry_findings(cur, measure(cur), kit)
                except Exception as exc:  # noqa: BLE001
                    report["geometry_error"] = str(exc)[:300]
            last = _order(final)
            report["final_check"] = [_slim_finding(f) for f in last]
    report["remaining"] = [_slim_finding(f) for f in last if f["severity"] in ("error", "warn")]
    report["info"] = [_slim_finding(f) for f in last if f["severity"] == "info"]
    report["spec"] = cur
    report["ok"] = not report["remaining"]
    return report


def _shot_meta(s: dict) -> dict:
    return {k: s.get(k) for k in ("scene", "kind", "frame", "image_rel", "W", "H") if k in s}


def summary(report: dict, lang: str = "fa") -> str:
    fixed, rem = report.get("fixed", 0), len(report.get("remaining") or [])
    if lang == "en":
        geo = "" if report.get("geometry") else " (the geometry check of the frame was not done: the renderer was not available)"
        if not fixed and not rem:
            return "Quality check: nothing found." + geo
        return f"Quality check: {fixed} problem(s) fixed automatically" + (f"; {rem} still remain" if rem else "; all resolved") + "." + geo
    geo = "" if report.get("geometry") else " (بررسی هندسی کادر انجام نشد: ابزار رندر در دسترس نبود)"
    if not fixed and not rem:
        return "کنترل کیفیت: مشکلی پیدا نشد." + geo
    return f"کنترل کیفیت: {fa(fixed)} مشکل خودکار اصلاح شد" + (f"؛ {fa(rem)} مورد هنوز مانده" if rem else "؛ همه رفع شد") + "." + geo


def open_image(path):
    from PIL import Image

    im = Image.open(Path(path))
    im.load()
    return im
