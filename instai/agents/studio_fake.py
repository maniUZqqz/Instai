"""Deterministic outputs of the studio tasks for the fake text provider (tests, demo mode, the GPU-less dev PC).

Registered into the fake provider's task table without editing instai/providers/fake.py. Output is schema-valid and clearly a demo.
"""
from __future__ import annotations

from instai.providers import fake

TAG_FA, TAG_EN = fake.DEMO_TAG_FA, fake.DEMO_TAG_EN


def _fa(meta: dict) -> bool:
    return (meta.get("language") or "fa").startswith("fa")


def _tag(meta: dict) -> str:
    return TAG_FA if _fa(meta) else TAG_EN


def _name(meta: dict) -> str:
    src = meta.get("source") or {}
    return str(src.get("title") or meta.get("title") or meta.get("page_name") or ("جهان" if _fa(meta) else "the world"))


# ------------------------------------------------------------------ ideas

_DETAIL_KEYS = {
    "divergence": ["divergence_moment", "canon_outcome", "changed_outcome", "ripple_preview"],
    "series_concept": ["hook", "audience", "story_engine"],
    "scenario": ["setup", "complication", "payoff"],
    "gag_format": ["gag", "trigger", "variation"],
    "topic": ["why_it_is_hard", "hook_question", "common_misconception"],
    "analogy": ["analogy", "visual_metaphor", "where_it_breaks_down"],
    "character_concept": ["look", "flaw", "want"],
}
_LENS_FA = {"divergence": "انشعاب", "series_concept": "مجموعه", "scenario": "سناریو", "gag_format": "شوخی", "topic": "موضوع",
            "analogy": "قیاس", "character_concept": "شخصیت"}


def ideas(meta: dict) -> dict:
    lens = meta.get("lens") or "series_concept"
    n = int(meta.get("count") or 6)
    fa = _fa(meta)
    taken = {str(t).lower() for t in (meta.get("existing_ideas") or [])}
    seed = len(taken) + len(meta.get("liked_ideas") or [])
    out = []
    for i in range(n):
        k = seed + i + 1
        label = _LENS_FA.get(lens, lens) if fa else lens
        title = f"{_tag(meta)} {label} {k}: {_name(meta)}" if fa else f"{_tag(meta)} {label} idea {k}: {_name(meta)}"
        logline = (f"یک {label} شمارهٔ {k} که دربارهٔ «{_name(meta)}» داستان تازه‌ای می‌سازد." if fa
                   else f"A {label} idea #{k} that gives '{_name(meta)}' a fresh story.")
        why = "برای مخاطب روشن و قابل‌تکرار است." if fa else "It is clear for the audience and repeatable."
        details = {key: (f"{key} ({k})" if not fa else f"{key} ({k})") for key in _DETAIL_KEYS.get(lens, [])}
        out.append({"title": title, "logline": logline, "why_it_works": why, "details": details, "tags": [lens]})
    return {"ideas": out}


def idea_refine(meta: dict) -> dict:
    idea = meta.get("idea") or {}
    fa = _fa(meta)
    ins = str(meta.get("instruction") or "")
    return {"title": str(idea.get("title") or "idea"), "logline": f"{idea.get('logline', '')} " + (f"(بازنویسی: {ins})" if fa else f"(revised: {ins})"),
            "why_it_works": idea.get("why_it_works") or idea.get("why") or "", "details": idea.get("details") or {}, "tags": idea.get("tags") or []}


def idea_merge(meta: dict) -> dict:
    cards = meta.get("ideas") or []
    fa = _fa(meta)
    titles = " + ".join(str(c.get("title", "")) for c in cards[:3])
    details: dict = {}
    for c in cards:
        for k, v in (c.get("details") or {}).items():
            details.setdefault(k, v)
    return {"title": (f"ادغام: {titles}" if fa else f"Merged: {titles}")[:150], "logline": " ".join(str(c.get("logline", "")) for c in cards)[:600] or "merged",
            "why_it_works": "بهترین بخش‌های هر ایده کنار هم آمده است." if fa else "It keeps the best part of each idea.", "details": details, "tags": ["merged"]}


# ------------------------------------------------------------------ canon research

def canon(meta: dict) -> dict:
    fa = _fa(meta)
    srcs = meta.get("sources") or []
    ids = [s["id"] for s in srcs[:2]] or []
    name = _name(meta)
    return {
        "summary": (f"{_tag(meta)} خلاصهٔ پژوهش دربارهٔ «{name}» بر پایهٔ {len(srcs)} منبع." if fa else f"{_tag(meta)} Research summary about '{name}' from {len(srcs)} sources."),
        "characters": [{"name": "آرتا" if fa else "Arta", "role": "قهرمان" if fa else "protagonist", "abilities": "قدرت بدنی" if fa else "physical strength",
                        "arc": "از ناآگاهی به مسئولیت" if fa else "from naivety to responsibility", "relationships": "", "source_ids": ids},
                       {"name": "نیلا" if fa else "Nila", "role": "هم‌پیمان" if fa else "ally", "abilities": "احضار" if fa else "summoning", "arc": "", "relationships": "", "source_ids": ids[:1]}],
        "arcs": [{"title": "کمان نخست" if fa else "First arc", "summary": "آغاز ماجرا و معرفی جهان" if fa else "The story begins and the world is introduced", "source_ids": ids},
                 {"title": "کمان دوم" if fa else "Second arc", "summary": "اوج درگیری" if fa else "The conflict peaks", "source_ids": ids[:1]}],
        "key_events": [{"when": "آغاز" if fa else "Beginning", "event": "قهرمان به جهان وارد می‌شود" if fa else "The hero enters the world", "importance": "high", "source_ids": ids},
                       {"when": "میانه" if fa else "Middle", "event": "نبرد سرنوشت‌ساز" if fa else "A decisive battle", "importance": "high", "source_ids": ids[:1]},
                       {"when": "پایان" if fa else "End", "event": "پایان کمان" if fa else "The arc ends", "importance": "medium", "source_ids": []}],
        "world_rules": [{"rule": "قدرت‌ها هزینه دارند" if fa else "Powers have a cost", "source_ids": ids[:1]}],
        "themes": ["مسئولیت" if fa else "responsibility", "انتخاب" if fa else "choice"],
        "caveats": ["این خلاصه جایگزین خودِ اثر نیست." if fa else "This summary does not replace the work itself."],
    }


# ------------------------------------------------------------------ map and timeline

def consequence_map(meta: dict) -> dict:
    fa = _fa(meta)
    div = meta.get("divergence") or {}
    t0 = str(div.get("title") or ("نقطهٔ انشعاب" if fa else "Divergence point"))
    rows = [
        ("n1", t0, "divergence", "", 1), ("n2", "پیامد مستقیم: متحد در خطر می‌ماند" if fa else "Direct: the ally stays in danger", "direct", "n1", 1),
        ("n3", "پیامد مستقیم: نقشهٔ دشمن بی‌واکنش پیش می‌رود" if fa else "Direct: the enemy plan proceeds unopposed", "direct", "n1", 2),
        ("n4", "اثر زنجیره‌ای: اعتماد گروه فرو می‌ریزد" if fa else "Ripple: the group's trust breaks", "ripple", "n2", 3),
        ("n5", "اثر زنجیره‌ای: قهرمان مسیر تازه‌ای می‌گیرد" if fa else "Ripple: the hero takes a new path", "character", "n3", 3),
        ("n6", "تغییر جهان: قدرت‌ها جابه‌جا می‌شوند" if fa else "World change: power shifts", "world", "n4", 4),
    ]
    return {"nodes": [{"id": i, "title": t, "description": t, "kind": k, "parent": p, "episode_hint": e} for i, t, k, p, e in rows]}


def timeline(meta: dict) -> dict:
    fa = _fa(meta)
    return {"summary": "خط زمانی جایگزین" if fa else "Alternative timeline",
            "rows": [{"when": f"{'روز' if fa else 'Day'} {d}", "canon": "رویداد اصلی" if fa else "canon event", "alternate": f"{'رویداد تغییریافته' if fa else 'changed event'} {d}",
                      "note": ""} for d in (1, 2, 3, 4)]}


# ------------------------------------------------------------------ character bible, series bible

def character_bible(meta: dict) -> dict:
    fa = _fa(meta)
    brief = str(meta.get("brief") or "")[:80]
    return {"characters": [{"name": "میشا" if fa else "Misha", "role": "شخصیت اصلی" if fa else "main character",
                            "appearance": f"طراحی بر پایهٔ «{brief}»" if fa else f"Design based on '{brief}'", "personality": "کنجکاو و شوخ" if fa else "curious and playful",
                            "motivations": "همیشه دنبال ماجراست" if fa else "always chasing an adventure", "abilities": "", "catchphrases": ["دوباره!" if fa else "again!"],
                            "visual_hooks": ["شال قرمز" if fa else "red scarf", "گوش‌های بزرگ" if fa else "big ears"], "voice_notes": "گرم و پرانرژی" if fa else "warm and energetic",
                            "is_original": True}]}


def bible(meta: dict) -> dict:
    fa = _fa(meta)
    n = int(meta.get("episodes_count") or 5)
    name = _name(meta)
    chars = meta.get("characters") or []
    cast = [{"name": c if isinstance(c, str) else c.get("name", "؟"), "role": "نقش" if fa else "role", "appearance": "", "personality": "", "motivations": "", "abilities": "",
             "is_original": True} for c in chars[:4]] or [{"name": "آرتا" if fa else "Arta", "role": "قهرمان" if fa else "hero", "appearance": "موی مشکی" if fa else "black hair",
                                                           "personality": "شجاع" if fa else "brave", "motivations": "حفظ دوستان" if fa else "protect friends", "abilities": "",
                                                           "is_original": True}]
    out = {
        "title": str(meta.get("title") or name), "logline": f"{_tag(meta)} یک جمله دربارهٔ «{name}»." if fa else f"{_tag(meta)} One sentence about '{name}'.",
        "premise": f"فرضیهٔ مجموعه بر پایهٔ «{name}» و ایده‌های تأییدشده." if fa else f"The series premise built on '{name}' and the approved ideas.",
        "world_rules": ["قدرت‌ها هزینه دارند." if fa else "Powers have a cost."], "characters": cast, "tone": "جدی و امیدوار" if fa else "serious and hopeful",
        "themes": ["انتخاب" if fa else "choice"],
        "arcs": [{"title": f"{'بخش' if fa else 'Arc'} {i}", "summary": f"{'خلاصه' if fa else 'Summary'} {i}", "goal": "پیشبرد داستان" if fa else "advance the story",
                  "cliffhanger": "یک راز تازه" if fa else "a new secret"} for i in range(1, max(1, min(3, (n + 1) // 2)) + 1)],
        "episode_count": n, "episode_length_sec": int(meta.get("episode_length_sec") or 45), "visual_notes": "", "content_rules": ["شخصیت‌ها ثابت می‌مانند." if fa else "Characters stay consistent."],
    }
    if meta.get("divergence") or meta.get("map") or meta.get("source"):
        out["branch_point"] = str((meta.get("divergence") or {}).get("title") or ("نقطهٔ انشعاب" if fa else "Divergence point"))
        out["alternative_timeline"] = "جهانی که در آن این رویداد عوض شد." if fa else "A world where that event changed."
    return out


# ------------------------------------------------------------------ design, casting, translation

def design(meta: dict) -> dict:
    fa = _fa(meta)
    sheets = []
    for c in (meta.get("characters_detail") or [])[:4]:
        name = c.get("name", "?")
        sheets.append({"kind": "character", "subject": name, "prompt": f"character model sheet of {name}, front, three-quarter, side and back view, neutral pose, plain background",
                       "negative": "", "notes": "نمای چهارگانه" if fa else "four-view turnaround", "palette": []})
        sheets.append({"kind": "expression", "subject": name, "prompt": f"expression sheet of {name}: happy, angry, sad, surprised, plain background", "negative": "", "notes": "", "palette": []})
    for sc in (meta.get("scenes") or [])[:4]:
        loc = sc.get("location") or sc.get("title") or "location"
        sheets.append({"kind": "background", "subject": str(loc), "prompt": f"background art of {loc}, no characters", "negative": "", "notes": "", "palette": []})
        sheets.append({"kind": "colour_script", "subject": str(sc.get("title") or loc), "prompt": f"colour key for scene {sc.get('title', '')}", "negative": "",
                       "notes": "پالت و نور صحنه" if fa else "scene palette and light", "palette": ["#223344", "#CC8844", "#EEDDAA"]})
    if not sheets:
        sheets.append({"kind": "colour_script", "subject": "episode", "prompt": "colour key", "negative": "", "notes": "", "palette": ["#223344", "#CC8844"]})
    return {"sheets": sheets}


def casting(meta: dict) -> dict:
    voices = meta.get("voices") or []
    chars = meta.get("characters_detail") or []
    out = []
    for i, c in enumerate(chars):
        v = voices[i % len(voices)]["id"] if voices else "default"
        out.append({"character": c.get("name", "?"), "voice_id": v, "reason": "fake casting"})
    return {"casting": out or [{"character": "?", "voice_id": voices[0]["id"] if voices else "default", "reason": "fake casting"}]}


def translate(meta: dict) -> dict:
    target = meta.get("target_language") or "en"
    sc = meta.get("script") or {}
    mark = f"[{target}] "
    return {"title": mark + str(sc.get("title") or ""), "hook": mark + str(sc.get("hook") or ""), "cta": (mark + str(sc.get("cta"))) if sc.get("cta") else "",
            "blocks": [{"id": b.get("id", i + 1), "speaker": b.get("speaker", ""), "text": mark + str(b.get("text", "")), "emotion": b.get("emotion", "")}
                       for i, b in enumerate(sc.get("blocks") or [])]}


def translate_shots(meta: dict) -> dict:
    mark = f"[{meta.get('target_language') or 'en'}] "
    return {"lines": [{"id": str(x["id"]), "text": mark + str(x.get("text", ""))} for x in meta.get("lines") or []]}


TASKS = {"ideas": ideas, "idea_refine": idea_refine, "idea_merge": idea_merge, "canon": canon, "consequence_map": consequence_map, "timeline": timeline,
         "character_bible": character_bible, "bible": bible, "design": design, "casting": casting, "translate": translate, "translate_shots": translate_shots}
fake._TASKS.update(TASKS)
