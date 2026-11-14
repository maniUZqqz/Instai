"""Silent downgrades made visible (audit 2026-11-14, batch ia_core).

A shot whose planned technique cannot be rendered is made as a still picture with a camera move instead (Ken Burns). That is fine as a
fallback, but the owner must be told: before it happens (the shot list), when he starts production (pre-flight) and in the quality check
afterwards. This module is the ONE place that decides which shots are downgraded and why; the shot list, the pre-flight, the job log, the
video's provenance and the quality check all read it, so they can never disagree.

Every entry carries Persian and English text (`fa` / `en`); the owner reads Persian only, and never a development phase number.
"""
from __future__ import annotations

from instai.story import costs

LAB_RIGS_PATH = "/lab/rigs"          # «آزمایشگاه تولید ← شخصیت‌های پاپت» (frontend/src/lab/registry.ts, key "rigs")

TECH_FA = {
    "still_kenburns": "تصویر ثابت با حرکت دوربین", "parallax_25d": "پارالاکس ۲٫۵بعدی", "puppet_2d": "عروسکی دوبعدی", "motion_graphics": "گرافیک متحرک",
    "wan_i2v": "ویدئوی Wan", "wan_flf": "Wan اول/آخر فریم", "talking_video": "ویدئوی گویا", "three_d": "سه‌بعدی",
}
TECH_EN = {
    "still_kenburns": "still + camera move", "parallax_25d": "2.5D parallax", "puppet_2d": "2D puppet", "motion_graphics": "motion graphics",
    "wan_i2v": "Wan video", "wan_flf": "Wan first/last frame", "talking_video": "talking video", "three_d": "3D",
}
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fd(n) -> str:
    """A number in a Persian sentence, in Persian digits."""
    return str(n).translate(_FA_DIGITS)


def shot_label(shot) -> tuple[str, str]:
    """('شات ۱٫۲', 'shot 1.2'): scene and shot number as the owner sees them in the shot list."""
    return f"شاتِ {fd(shot.scene.index)}٫{fd(shot.index)}", f"shot {shot.scene.index}.{shot.index}"


def _character_name(shot, ep) -> str:
    """The character a puppet shot needs a rig for: its speaker when that is a character of the page, else the page's first character."""
    chars = list(ep.series.page.characters.all())
    speaker = next((c for c in chars if shot.speaker and c.name == shot.speaker), None)
    return (speaker or (chars[0] if chars else None)).name if (speaker or chars) else ""


def _entry(shot, code: str, fa: str, en: str, **extra) -> dict:
    return {"shot": shot.pk, "scene": shot.scene.index, "index": shot.index, "technique": shot.technique, "code": code, "fa": fa, "en": en, **extra}


def shot_fallback(shot, ep, mode: str = "preview", *, have_clip: bool | None = None) -> dict | None:
    """Why this shot will NOT be made with its planned technique, or None when it is made as planned. `have_clip` (assembly time only)
    says whether a Wan clip exists for a Wan shot in FINAL mode."""
    t = shot.technique
    sl_fa, sl_en = shot_label(shot)
    still_fa, still_en = "تصویر ثابت با حرکت دوربین می‌آید.", "a still picture with a camera move is used."
    if t == "puppet_2d":
        from . import puppet

        rig, _draft = puppet.rig_for_shot(shot, ep)
        if rig is None:
            name = _character_name(shot, ep)
            who_fa = f"شخصیتِ «{name}» هنوز عروسک ندارد" if name else "این صفحه هنوز شخصیتی با عروسک ندارد"
            who_en = f"the character \"{name}\" has no puppet yet" if name else "this page has no character with a puppet yet"
            return _entry(shot, "no_rig", f"{sl_fa}: {who_fa}؛ به‌جای عروسکِ متحرک {still_fa}", f"{sl_en}: {who_en}; {still_en}",
                          character=name)
        return None
    if t == "parallax_25d":
        return _entry(shot, "no_layers", f"{sl_fa}: لایه‌های جداشده برای پارالاکس ساخته نمی‌شود؛ {still_fa}",
                      f"{sl_en}: no separated layers are made for parallax; {still_en}")
    if t == "motion_graphics" and have_clip is False:
        return _entry(shot, "no_motion_clip", f"{sl_fa}: کلیپ گرافیک متحرک ساخته نشد؛ {still_fa}", f"{sl_en}: the motion-graphics clip could not be made; {still_en}")
    if t not in costs.IMPLEMENTED:
        return _entry(shot, "not_implemented", f"{sl_fa}: روشِ «{TECH_FA.get(t, t)}» هنوز ساخته نمی‌شود؛ {still_fa}",
                      f"{sl_en}: the technique \"{TECH_EN.get(t, t)}\" is not made yet; {still_en}")
    if t == "wan_i2v" and mode == "final" and have_clip is False:
        return _entry(shot, "no_clip", f"{sl_fa}: کلیپِ ویدئویی (Wan) آماده نشد؛ {still_fa}",
                      f"{sl_en}: the Wan video clip could not be made; {still_en}")
    return None


def episode_fallbacks(ep, mode: str = "preview", shots=None) -> list[dict]:
    """Every downgraded shot of the episode, in shot order (no clip-availability check: that is only known at assembly)."""
    from instai.story import services

    out = []
    for s in (shots if shots is not None else services.all_shots(ep)):
        fb = shot_fallback(s, ep, mode)
        if fb:
            out.append(fb)
    return out


def needs_rig(ep, shots=None) -> list[dict]:
    """The characters whose puppet shots lack a rig: [{character: id|None, name, shots: n}]. One click («ساخت عروسکِ چوبیِ خودکار»)
    makes them (`ensure_stick_rigs`)."""
    from instai.story import services

    found: dict[str, dict] = {}
    chars = {c.name: c for c in ep.series.page.characters.all()}
    for fb in episode_fallbacks(ep, "preview", shots if shots is not None else services.all_shots(ep)):
        if fb["code"] != "no_rig":
            continue
        name = fb.get("character") or ""
        row = found.setdefault(name, {"character": chars[name].pk if name in chars else None, "name": name, "shots": 0})
        row["shots"] += 1
    return list(found.values())


def ensure_stick_rigs(ep) -> list[dict]:
    """Give every character that needs one a stick-figure puppet (instead of falling back to a still). A character whose identity is not
    locked gets the whole stick identity (rig + model sheet + words, the same as the «شخصیت‌ها» page button); one whose identity is locked
    from pictures gets only the rig, so the locked look is never rewritten. Returns what was made: [{character, name, rig}]."""
    from instai.identity import service as identity
    from instai.pages.models import Character
    from instai.production.models import CharacterRig

    made = []
    for row in needs_rig(ep):
        ch = Character.objects.filter(pk=row["character"]).first() if row["character"] else None
        if ch is None:
            ch = Character.objects.filter(page=ep.series.page).order_by("id").first()
        if ch is None:                                   # a page with no character at all: make the narrator-like host one
            ch = Character.objects.create(page=ep.series.page, name="مجری" if ep.series.page.language.startswith("fa") else "Host", role="host")
        if CharacterRig.objects.filter(character=ch).exists():
            continue
        lock = identity.get_lock(ch)
        if lock is not None and lock.status == "locked":
            _rig_only(ch)
        else:
            identity.build_stick(ch)
        rig = CharacterRig.objects.filter(character=ch).order_by("-version").first()
        made.append({"character": ch.pk, "name": ch.name, "rig": rig.pk if rig else None})
    return made


def _rig_only(ch) -> None:
    from pathlib import Path

    from django.conf import settings

    from instai.production.models import CharacterRig
    from instai.render.stick import parts, spec as stick_spec

    root = Path(settings.MEDIA_ROOT)
    last = CharacterRig.objects.filter(character=ch).order_by("-version").first()
    version = (last.version + 1) if last else 1
    spec = stick_spec.normalize({}, name=ch.name)
    rig_spec = parts.make_rig_spec(spec, root / "characters" / str(ch.pk) / f"stick{version}", root)
    CharacterRig.objects.create(character=ch, version=version, name=f"{ch.name} (stick)", source="stick", spec=rig_spec, approved=False)


def qc_check(fallbacks: list[dict]) -> dict:
    """The quality-check row (same shape as the other rows of `pipeline.run_qc`): a warning that names the count and the shots."""
    if not fallbacks:
        return {"name": "fallbacks", "level": "ok", "value": [], "message": "همهٔ شات‌ها با همان روشی که در استوری‌بورد انتخاب شده ساخته شدند"}
    n = len(fallbacks)
    by_code: dict[str, list[dict]] = {}
    for f in fallbacks:
        by_code.setdefault(f["code"], []).append(f)
    parts = []
    if "no_rig" in by_code:
        names = sorted({f.get("character") or "" for f in by_code["no_rig"]} - {""})
        parts.append(f"{fd(len(by_code['no_rig']))} شاتِ عروسکی بدون عروسک" + (f" (شخصیتِ «{'»، «'.join(names)}»)" if names else "")
                     + "؛ عروسک را از «آزمایشگاه تولید ← شخصیت‌های پاپت» بسازید")
    if "no_layers" in by_code:
        parts.append(f"{fd(len(by_code['no_layers']))} شاتِ پارالاکس بدون لایه")
    if "not_implemented" in by_code:
        parts.append(f"{fd(len(by_code['not_implemented']))} شاتِ با روشِ ساخته‌نشده")
    if "no_clip" in by_code:
        parts.append(f"{fd(len(by_code['no_clip']))} شاتِ ویدئویی بدون کلیپ")
    if "no_motion_clip" in by_code:
        parts.append(f"{fd(len(by_code['no_motion_clip']))} شاتِ گرافیک متحرک بدون کلیپ")
    where = "، ".join(f"{fd(f['scene'])}٫{fd(f['index'])}" for f in sorted(fallbacks, key=lambda f: (f["scene"], f["index"])))
    return {"name": "fallbacks", "level": "warn", "value": fallbacks,
            "message": f"{fd(n)} شات همان‌طور که در استوری‌بورد بود ساخته نشد و تصویرِ ثابت با حرکتِ دوربین شد (شاتِ {where}): " + "؛ ".join(parts)}
