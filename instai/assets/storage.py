"""Storage abstraction over a local folder (ready for object storage later) + helpers that register files as Assets
with explicit metadata and provenance. User files are never deleted: replaced files are moved aside under media/_replaced/."""
from __future__ import annotations

import abc
import hashlib
import mimetypes
import shutil
import time
from pathlib import Path

from django.conf import settings

from .models import Asset


class Storage(abc.ABC):
    @abc.abstractmethod
    def path_for(self, rel: str) -> Path: ...

    @abc.abstractmethod
    def exists(self, rel: str) -> bool: ...

    @abc.abstractmethod
    def import_file(self, src: Path, rel: str) -> str: ...

    @abc.abstractmethod
    def url(self, rel: str) -> str: ...


class LocalStorage(Storage):
    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.MEDIA_ROOT)

    def path_for(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError("path escapes the media folder")
        return p

    def exists(self, rel: str) -> bool:
        return self.path_for(rel).is_file()

    def import_file(self, src: Path, rel: str) -> str:
        dst = self.path_for(rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            aside = self.root / "_replaced" / time.strftime("%Y%m%d-%H%M%S") / rel
            aside.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(aside))
        src = Path(src).resolve()
        if src != dst:
            if self.root.resolve() in src.parents:
                shutil.move(str(src), str(dst))   # a temp file already inside the media folder
            else:
                shutil.copyfile(src, dst)
        return rel

    def url(self, rel: str) -> str:
        return "/media/" + rel


storage = LocalStorage()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def register(src: Path, rel: str, *, kind: str, role: str = "other", page=None, episode=None, shot=None, input_hash: str = "",
             provenance: dict | None = None, probe: bool = True, approved: bool = False, loudness: bool = False) -> Asset:
    """Move/copy `src` into the media folder at `rel`, probe it, and create the Asset (older versions of the same slot stay as history)."""
    storage.import_file(Path(src), rel)
    full = storage.path_for(rel)
    meta: dict = {}
    if probe and kind in ("image", "audio", "video"):
        try:
            from instai.render import ffmpeg

            p = ffmpeg.probe(full)
            meta = {"duration_sec": p["duration"] or None, "fps": p["fps"] if kind == "video" else None, "width": p["width"],
                    "height": p["height"], "codec": p["vcodec"] or p["acodec"]}
            if loudness and p["has_audio"]:
                meta["loudness_lufs"] = ffmpeg.measure_loudness(full)
        except Exception:  # noqa: BLE001 - metadata is best effort for images (Pillow fallback below)
            meta = {}
    if kind == "image" and not meta.get("width"):
        try:
            from PIL import Image

            with Image.open(full) as im:
                meta = {"width": im.width, "height": im.height, "codec": (im.format or "").lower()}
        except Exception:  # noqa: BLE001
            pass
    qs = Asset.objects.filter(shot=shot, role=role, is_current=True) if shot else (
        Asset.objects.filter(episode=episode, shot__isnull=True, role=role, is_current=True) if episode else Asset.objects.none())
    prev = qs.order_by("-version").first()
    asset = Asset.objects.create(
        kind=kind, role=role, path=rel.replace("\\", "/"), mime=mimetypes.guess_type(rel)[0] or "", size_bytes=full.stat().st_size,
        sha256=sha256_file(full), page=page, episode=episode, shot=shot, input_hash=input_hash, provenance=provenance or {},
        version=(prev.version + 1) if prev else 1, parent=prev, approved=approved, **meta)
    if prev:
        qs.exclude(pk=asset.pk).update(is_current=False)
    return asset
