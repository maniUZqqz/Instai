"""The character picture of a cover: a transparent (cut-out) image of a series character.

Where it comes from, in this order (the first that exists):

1. **a stick character** (``CharacterLock.source == "stick"``): drawn by code with ``instai.render.stick`` - transparent already, the same character as in every episode;
2. **an approved reference picture** of the character (``CharacterReference`` of kind ``image``), or a **locked keyframe** of an episode shot the character is in;
3. **the design / model sheet** of the character (used as a plain photo: the sheet holds several views, so it is not cut out);
4. nothing: the layouts keep their own replacement shape (an abstract scene, or the channel logo).

A picture without a transparent background is cut out with ``instai.render.puppet.cutout`` (BiRefNet-lite when it is installed, otherwise the flood fill of the border colour); when
that finds no clear outline the picture is used as a photo. NMarketing's matting jobs and photo library are NOT used here.
"""
from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from PIL import Image

from instai.assets import storage as asset_storage
from instai.assets.models import Asset

from .engine import primitives as P

log = logging.getLogger("instai.covers")
MAX_SIDE = 1100


def _lock(character):
    try:
        return character.lock
    except Exception:  # noqa: BLE001 - a character without a lock row
        return None


def _approved_image_ref(character) -> Asset | None:
    ref = character.references.filter(kind="image", approved=True).exclude(asset=None).select_related("asset").order_by("-id").first()
    return ref.asset if ref and asset_storage.storage.exists(ref.asset.path) else None


def _keyframe(character, episode=None) -> Asset | None:
    from instai.story.models import Shot

    shots = Shot.objects.filter(scene__characters=character)
    if episode is not None:
        shots = shots.filter(scene__episode=episode)
    for sh in shots.order_by("-id")[:12]:
        a = Asset.objects.filter(shot=sh, role="keyframe", is_current=True).order_by("-id").first()
        if a and asset_storage.storage.exists(a.path):
            return a
    return None


def _sheet(character) -> Asset | None:
    ref = character.references.filter(kind="sheet").exclude(asset=None).select_related("asset").order_by("-approved", "-id").first()
    return ref.asset if ref and asset_storage.storage.exists(ref.asset.path) else None


def source_of(character, episode=None) -> tuple[str, Asset | None]:
    """-> (source, asset): "stick" | "image" | "keyframe" | "sheet" | "none"."""
    lock = _lock(character)
    if lock is not None and lock.source == "stick" and lock.stick:
        return "stick", None
    for name, fn in (("image", lambda: _approved_image_ref(character)), ("keyframe", lambda: _keyframe(character, episode)), ("sheet", lambda: _sheet(character))):
        a = fn()
        if a is not None:
            return name, a
    return "none", None


def list_subjects(page, episode=None) -> list[dict]:
    """The characters of a page with where their cover picture would come from (for the picker of the UI)."""
    out = []
    for c in page.characters.all().order_by("-approved", "id"):
        src, a = source_of(c, episode)
        out.append({"id": c.pk, "name": c.name, "role": c.role, "source": src, "asset_id": a.pk if a else None, "url": a.url if a else None,
                    "locked": bool(getattr(_lock(c), "status", "") == "locked")})
    return out


def _work_dir() -> Path:
    p = Path(settings.DATA_DIR) / "cache" / "covers-stick"
    p.mkdir(parents=True, exist_ok=True)
    return p


def stick_bust(character, expression: str = "") -> Image.Image | None:
    """The head and shoulders of a locked stick character, transparent."""
    from instai.render.stick import compose, parts, spec as stick_spec

    lock = _lock(character)
    if lock is None or not lock.stick:
        return None
    expr = expression if expression in getattr(parts, "_EXPR", {}) else "happy"
    sp = stick_spec.normalize(lock.stick, name=character.name)
    return compose._cell(sp, _work_dir(), (900, 1100), expression=expr, pose="stand", zoom_head=True)


def cut_out(img: Image.Image) -> tuple[Image.Image, bool]:
    """-> (picture, is_cutout). A picture that is already transparent stays; otherwise the background is cut away when that gives a clear outline."""
    from instai.render.puppet import cutout

    im = img.convert("RGBA")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    if P.has_cutout(im):
        return P.crop_to_alpha(im, pad=2), True
    try:
        cut = cutout.cut_part(im)
    except Exception:  # noqa: BLE001 - a picture that cannot be cut is used as a photo
        log.info("covers: the background could not be cut away", exc_info=True)
        return im.convert("RGB"), False
    if P.has_cutout(cut):
        return cut, True
    return im.convert("RGB"), False


def open_asset(asset_id: int) -> Image.Image | None:
    a = Asset.objects.filter(pk=asset_id).first()
    if a is None or not asset_storage.storage.exists(a.path):
        return None
    with Image.open(asset_storage.storage.path_for(a.path)) as im:
        return im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")


def load(page, *, character_id=None, asset_id=None, expression: str = "", episode=None) -> tuple[Image.Image | None, bool, dict]:
    """-> (picture or None, is_cutout, info{source, asset}). An explicit asset wins over the character."""
    if asset_id:
        im = open_asset(int(asset_id))
        if im is not None:
            pic, cut = cut_out(im)
            return pic, cut, {"source": "asset", "asset": int(asset_id)}
    if character_id:
        c = page.characters.filter(pk=character_id).first()
        if c is not None:
            src, a = source_of(c, episode)
            if src == "stick":
                im = stick_bust(c, expression)
                if im is not None:
                    return P.crop_to_alpha(im, pad=2), True, {"source": "stick", "character": c.pk}
            elif a is not None:
                im = open_asset(a.pk)
                if im is not None:
                    if src == "sheet":
                        im.thumbnail((MAX_SIDE, MAX_SIDE))
                        return im.convert("RGB"), False, {"source": src, "asset": a.pk, "character": c.pk}
                    pic, cut = cut_out(im)
                    return pic, cut, {"source": src, "asset": a.pk, "character": c.pk}
    return None, False, {"source": "none"}
