"""Deterministic outputs of the pipeline tasks for the fake text provider (tests, demo mode, the GPU-less dev PC). Schema-valid and clearly a demo."""
from __future__ import annotations

from instai.providers import fake

TAG_FA, TAG_EN = fake.DEMO_TAG_FA, fake.DEMO_TAG_EN


def _fa(meta: dict) -> bool:
    return (meta.get("language") or "fa").startswith("fa")


def _tag(meta: dict) -> str:
    return TAG_FA if _fa(meta) else TAG_EN


def _title(meta: dict) -> str:
    return str(meta.get("series_title") or meta.get("title") or meta.get("page_name") or ("داستان" if _fa(meta) else "the story"))


def identity_anchor(meta: dict) -> dict:
    ch = meta.get("character") or {}
    app = str(ch.get("appearance") or "").strip()
    name = ch.get("name") or "hero"
    anchor = f"{name}: a distinctive original character, {app}" if app and app.isascii() else f"{name}: a distinctive original character with a simple clear silhouette, flat colours, thick outlines"
    return {"anchor": anchor[:600], "avoid": "different outfit, different colours, realistic shading", "visual_hooks": ["clear silhouette", "signature colour"],
            "palette": [{"role": "outfit", "hex": "#2f7fd1"}, {"role": "accent", "hex": "#d94a3d"}]}


def logline(meta: dict) -> dict:
    fa = _fa(meta)
    t = _title(meta)
    ins = str(meta.get("instruction") or "")
    base = (f"{_tag(meta)} وقتی قهرمانِ «{t}» در دامی گیر می‌افتد، باید پیش از طلوع راه فرار پیدا کند وگرنه همه‌چیز را از دست می‌دهد."
            if fa else f"{_tag(meta)} When the hero of '{t}' is trapped, they must find a way out before dawn or lose everything.")
    return {"logline": base + (f" ({ins})" if ins else ""), "hook": "فقط یک راه بیرون هست." if fa else "There is only one way out.",
            "stakes": "آزادیِ قهرمان" if fa else "the hero's freedom",
            "alternatives": [("نسخهٔ دیگر: " if fa else "Alternative: ") + t]}


def treatment(meta: dict) -> dict:
    fa = _fa(meta)
    t = _title(meta)
    paras = [f"{_tag(meta)} {t}: " + ("قهرمان در یک موقعیت بسته گیر می‌افتد." if fa else "the hero is stuck in a closed situation."),
             "هر قدم او را به خطر بزرگ‌تری نزدیک می‌کند." if fa else "Every step brings a bigger danger.",
             "در نقطهٔ میانی همه‌چیز برمی‌گردد." if fa else "At the midpoint everything turns.",
             "فصل با یک سؤال بی‌پاسخ تمام می‌شود." if fa else "The season ends on an unanswered question."]
    acts = [{"name": ("پرده ۱" if fa else "Act 1"), "summary": paras[0]}, {"name": ("پرده ۲" if fa else "Act 2"), "summary": paras[1] + " " + paras[2]},
            {"name": ("پرده ۳" if fa else "Act 3"), "summary": paras[3]}]
    return {"synopsis": paras, "acts": acts, "tone": "سریع و سرگرم‌کننده" if fa else "fast and entertaining", "themes": ["freedom", "choices"]}


def beat_sheet(meta: dict) -> dict:
    fa = _fa(meta)
    secs = float(meta.get("duration_sec") or 45)
    names = (["قلاب", "مقدمه", "مشکل", "تشدید", "نقطهٔ چرخش", "بحران", "پایان باز"] if fa else
             ["Hook", "Setup", "Problem", "Escalation", "Turn", "Crisis", "Cliffhanger"])
    each = round(secs / len(names), 1)
    return {"beats": [{"name": n, "summary": f"{_tag(meta)} {n}: {_title(meta)}", "seconds": each, "purpose": "کنجکاوی" if fa else "curiosity"} for n in names]}


def dialogue(meta: dict) -> dict:
    sc = meta.get("script") or {}
    blocks = sc.get("blocks") or []
    lines = [{"speaker": str(b.get("speaker") or ("راوی" if _fa(meta) else "Narrator")), "text": str(b.get("text") or ""), "emotion": str(b.get("emotion") or "neutral"),
              "subtext": "", "pause_after": 0.3} for b in blocks if str(b.get("text") or "").strip()]
    if len(lines) < 2:
        lines = [{"speaker": "راوی" if _fa(meta) else "Narrator", "text": f"{_tag(meta)} {_title(meta)}", "emotion": "neutral", "subtext": "", "pause_after": 0.3},
                 {"speaker": "راوی" if _fa(meta) else "Narrator", "text": "ادامه دارد…" if _fa(meta) else "To be continued…", "emotion": "tense", "subtext": "", "pause_after": 0.5}]
    return {"lines": lines}


_SIZES = ["WS", "MS", "CU", "MCU", "CU"]


def shot_list(meta: dict) -> dict:
    d = meta.get("dialogue") or {}
    lines = d.get("lines") or (meta.get("script") or {}).get("blocks") or []
    total = float(meta.get("duration_sec") or 30)
    n = max(3, min(12, len(lines) or 4))
    names = sorted({str(x.get("speaker") or "") for x in lines if str(x.get("speaker") or "")})[:3]
    shots = []
    for i in range(n):
        ln = lines[i % len(lines)] if lines else {}
        shots.append({"scene": 1 + i // 4, "size": _SIZES[i % len(_SIZES)], "angle": "eye-level", "movement": "static" if i % 2 else "push-in", "characters": names,
                      "action": f"{_tag(meta)} " + (str(ln.get("text") or "")[:120] or f"shot {i + 1}"), "seconds": round(total / n, 1), "transition": "cut", "notes": ""})
    return {"shots": shots}


def layout(meta: dict) -> dict:
    shots = meta.get("shots") or []
    out = []
    for i, s in enumerate(shots or [{}], 1):
        out.append({"shot": i, "background": str(s.get("location") or s.get("description") or "plain background")[:120], "staging": "characters in the lower third, camera-facing",
                    "camera": "locked off", "lighting": "soft key light", "props": []})
    return {"layouts": out}


def sound_design(meta: dict) -> dict:
    total = float(meta.get("duration_sec") or 30)
    fa = _fa(meta)
    return {"cues": [{"kind": "ambience", "shot": 0, "start_sec": 0, "end_sec": total, "description": "فضای محیط" if fa else "room tone", "prompt": "quiet ambience, low rumble",
                      "gain_db": -28, "duck": True},
                     {"kind": "sfx", "shot": 1, "start_sec": 0, "end_sec": 1.0, "description": "ضربهٔ شروع" if fa else "opening hit", "prompt": "short impact stinger", "gain_db": -10, "duck": False},
                     {"kind": "music", "shot": 0, "start_sec": 1.0, "end_sec": total, "description": "موسیقی پرتنش" if fa else "tense music bed", "prompt": "tense minimal underscore, 100 bpm",
                      "gain_db": -22, "duck": True},
                     {"kind": "silence", "shot": 0, "start_sec": max(0.0, total - 2.0), "end_sec": max(0.5, total - 1.0), "description": "سکوت پیش از افشا" if fa else "silence before the reveal",
                      "prompt": "", "gain_db": -60, "duck": False}],
            "mix_notes": "دیالوگ همیشه بالای موسیقی بماند." if fa else "Dialogue stays above the music.", "loudness_target": -16}


def grade(meta: dict) -> dict:
    scenes = meta.get("scenes") or [{"index": 1}]
    presets = ["neutral", "cold_night", "tension", "warm_dusk"]
    return {"scenes": [{"scene": int(s.get("index") or i + 1), "preset": presets[i % len(presets)], "mood": "calm", "palette": ["#1f2430", "#2f7fd1", "#e8a22b"], "notes": ""}
                       for i, s in enumerate(scenes)], "global_notes": "رنگ شخصیت‌ها هرگز عوض نمی‌شود." if _fa(meta) else "Character colours never change."}


def choice_plan(meta: dict) -> dict:
    from instai.choice import graph

    return graph.skeleton_plan(int(meta.get("post_count") or 14), fa=_fa(meta), title=str(meta.get("title") or ""), tag=_tag(meta))


def choice_posts(meta: dict) -> dict:
    fa = _fa(meta)
    out = []
    for p in meta.get("posts") or []:
        ch = p.get("choices") or []
        if ch:
            tail = " ".join(f"{'اگر' if fa else 'If'} «{c.get('label', '')}» → {'پست' if fa else 'post'} {{go:{c.get('to', '')}}}" for c in ch)
        else:
            tail = "پایان." if fa else "The end."
        out.append({"id": str(p["id"]), "caption": f"{p.get('text', '')}\n\n{tail}".strip(), "hashtags": ["#داستان_تعاملی"] if fa and not out else [], "alt": str(p.get("title", ""))})
    return {"posts": out}


def season_plan(meta: dict) -> dict:
    from instai.channel import planner

    return planner.skeleton_season(int(meta.get("episodes_count") or 8), int(meta.get("runtime_sec") or 30), fa=_fa(meta), characters=[str(c) for c in (meta.get("characters") or [])],
                                   title=str(meta.get("title") or ""), tag=_tag(meta))


TASKS = {"identity_anchor": identity_anchor, "logline": logline, "treatment": treatment, "beat_sheet": beat_sheet, "dialogue": dialogue, "shot_list": shot_list,
         "layout": layout, "sound_design": sound_design, "grade": grade, "choice_plan": choice_plan, "choice_posts": choice_posts, "season_plan": season_plan}
fake._TASKS.update(TASKS)
