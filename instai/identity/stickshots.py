"""Stick-figure keyframes made by code: when every character of a shot is a locked stick figure, the keyframe is DRAWN (no graphics card, same
character in every picture) instead of being asked from an image model. Pose, expression, background and positions are read from the shot's
words (English and Persian); the owner can still edit the shot and make the picture again."""
from __future__ import annotations

import tempfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.render.stick import compose, poses, scenes

from . import service

POSE_WORDS = [
    ("run_a", ("run", "runs", "running", "ran", "chase", "flee", "escape", "دوید", "می‌دود", "می‌دوید", "دوان", "بدو", "فرار", "تعقیب")),
    ("sneak", ("sneak", "tiptoe", "creep", "دزدکی", "آهسته")),
    ("hide", ("hide", "hiding", "behind", "پنهان", "مخفی")),
    ("crouch", ("crouch", "duck", "kneel", "خم شد", "زانو")),
    ("hands_up", ("hands up", "surrender", "freeze", "تسلیم", "دست‌ها بالا", "دستها بالا")),
    ("point_right", ("point", "points", "pointing", "اشاره")),
    ("wave", ("wave", "waves", "hello", "greet", "سلام", "دست تکان")),
    ("think", ("think", "thinking", "wonder", "ponder", "فکر", "تأمل")),
    ("push", ("push", "pull", "shove", "هل می", "هل داد")),
    ("punch", ("punch", "fight", "hit", "مشت", "دعوا", "ضربه")),
    ("kick", ("kick", "لگد")),
    ("lying", ("fall", "falls", "fell", "faint", "unconscious", "افتاد", "بیهوش", "روی زمین")),
    ("sit", ("sit", "sits", "sitting", "seated", "نشست", "نشسته")),
    ("cheer", ("cheer", "celebrate", "victory", "win", "جشن", "پیروز", "شادی")),
    ("shock", ("shock", "gasp", "startled", "جا خورد", "شوکه", "وحشت‌زده")),
    ("tired", ("tired", "exhausted", "weary", "خسته", "کوفته")),
    ("hold", ("hold", "holds", "holding", "carry", "نگه می", "نگه داشت", "حمل")),
    ("walk_a", ("walk", "walks", "walking", "راه می", "قدم")),
    ("shrug", ("shrug", "unsure", "نمی‌دانم", "نمیدانم")),
]
EXPRESSION_WORDS = [
    ("scared", ("scared", "afraid", "fear", "terrified", "panic", "ترس", "وحشت", "هراس")),
    ("angry", ("angry", "furious", "mad", "rage", "عصبانی", "خشم", "غضب")),
    ("sad", ("sad", "cry", "crying", "sorrow", "غمگین", "گریه", "ناراحت")),
    ("surprised", ("surprised", "shocked", "astonished", "شگفت", "متعجب", "تعجب")),
    ("laugh", ("laugh", "laughs", "laughing", "خنده", "می‌خندد")),
    ("happy", ("happy", "smile", "joy", "relieved", "خوشحال", "لبخند", "شاد")),
    ("smirk", ("smirk", "sly", "cunning", "پوزخند", "حیله")),
]
NIGHT_WORDS = ("night", "dark", "midnight", "شب", "تاریک", "نیمه‌شب")


def _first(words_table, text: str, default: str) -> str:
    low = text.lower()
    best, at = default, 10 ** 6
    for key, words in words_table:
        for w in words:
            i = low.find(w)
            if i != -1 and i < at:
                best, at = key, i
    return best


def guess_pose(text: str) -> str:
    return _first(POSE_WORDS, text, "stand")


def guess_expression(text: str) -> str:
    return _first(EXPRESSION_WORDS, text, "neutral")


def stick_identities(shot, ep) -> list:
    return [i for i in service.identities_for_shot(shot, ep) if i.lock.source == "stick" and i.lock.stick]


def applies(shot, ep) -> bool:
    """True when the shot's characters are all locked stick figures (at least one) and the shot is not a motion-graphics diagram."""
    if shot.technique == "motion_graphics":
        return False
    all_ids = service.identities_for_shot(shot, ep)
    return bool(all_ids) and all(i.lock.source == "stick" and i.lock.stick for i in all_ids)


def scene_for_shot(shot, ep, size: tuple[int, int], *, bubbles: bool = False) -> dict:
    ids = stick_identities(shot, ep)
    text = f"{shot.scene.location} {shot.description} {shot.image_prompt}"
    bg = scenes.pick(text, default="plain")
    pose_all, expr_all = guess_pose(f"{shot.description} {shot.image_prompt}"), guess_expression(f"{shot.description} {shot.image_prompt}")
    n = len(ids)
    xs = {1: [0.5], 2: [0.32, 0.70], 3: [0.22, 0.5, 0.78]}.get(n, [0.5])
    height = {1: 0.50, 2: 0.46, 3: 0.40}.get(n, 0.5)
    actors = []
    for k, i in enumerate(ids):
        speaker = bool(shot.speaker) and i.character.name == shot.speaker.strip()
        actors.append({"spec": i.lock.stick, "x": xs[k], "y": 0.90, "height": height, "flip": k > 0 and n > 1 and k == n - 1,
                       "pose": pose_all if (speaker or n == 1 or k == 0) else "stand", "expression": expr_all if (speaker or n == 1 or k == 0) else "neutral",
                       "talk": False})
    scene = {"width": size[0], "height": size[1], "background": bg, "actors": actors}
    if any(w in text.lower() for w in NIGHT_WORDS) and bg not in ("street", "cave", "sewer", "cell"):
        scene["night"] = 0.35
    return scene


def render_keyframe(shot, ep, out: Path, size: tuple[int, int]) -> dict:
    work = Path(settings.MEDIA_ROOT) / "stickwork" / str(ep.pk)
    scene = scene_for_shot(shot, ep, size)
    compose.compose_still(scene, out, work)
    return {"engine": "stick", "background": scene["background"], "poses": [a["pose"] for a in scene["actors"]], "expressions": [a["expression"] for a in scene["actors"]],
            "characters": [i.character.name for i in stick_identities(shot, ep)], "note": "drawn by code from the locked stick identity (no image model)"}


def make_keyframe(ctx, shot, ep, hsh: str, size: tuple[int, int]) -> None:
    """Draw and register the keyframe of one shot (called by pipeline.step_keyframes for stick shots)."""
    from instai.story.models import Shot

    rel = f"episodes/{ep.pk}/keyframes/shot{shot.pk}-{hsh[:8]}.png"
    tmp = Path(tempfile.mkdtemp(prefix="kf-", dir=settings.MEDIA_ROOT)) / "kf.png"
    info = render_keyframe(shot, ep, tmp, size)
    asset_storage.register(tmp, rel, kind="image", role="keyframe", page=ep.series.page, episode=ep, shot=shot, input_hash=hsh,
                           provenance={**info, "provider": "stick", "job_id": ctx.job.pk, "prompt": shot.image_prompt, "seed": shot.seed})
    import shutil

    shutil.rmtree(tmp.parent, ignore_errors=True)
    Shot.objects.filter(pk=shot.pk).update(status="done", last_error="")
