"""Release 1 publishing: a ready package for MANUAL upload (video, cover, caption, hashtags, schedule reminder).
Nothing is ever posted automatically; the adapter interface is here so the official Instagram Graph API can be added later."""
from __future__ import annotations

import abc
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.core.errors import DomainError

from .models import Publication


class PublishAdapter(abc.ABC):
    """Implement for each platform. Release 1 only ships ManualExport."""

    name = "base"

    @abc.abstractmethod
    def publish(self, publication: Publication) -> dict: ...


class ManualExport(PublishAdapter):
    name = "manual"

    def publish(self, publication: Publication) -> dict:
        return export_package(publication.pk)


def best_video(ep) -> Asset | None:
    for role in ("final", "preview"):
        a = Asset.objects.filter(episode=ep, role=role, is_current=True).order_by("-id").first()
        if a:
            return a
    return None


def export_package(publication_id: int) -> dict:
    pub = Publication.objects.select_related("episode__series__page").get(pk=publication_id)
    ep = pub.episode
    video = best_video(ep)
    if not video:
        raise DomainError("not_ready", "برای این قسمت هنوز ویدئویی ساخته نشده است.")
    cover = pub.cover or Asset.objects.filter(episode=ep, role="cover", is_current=True).order_by("-id").first()
    tags = " ".join(h if h.startswith("#") else "#" + h for h in (pub.hashtags or []))
    schedule = pub.scheduled_at.strftime("%Y-%m-%d %H:%M UTC") if pub.scheduled_at else "not scheduled"
    caption = (pub.caption or ep.title) + ("\n\n" + tags if tags else "")
    reminder = (f"InstAI upload package\nPage: {ep.series.page.name}\nEpisode {ep.number}: {ep.title}\nSchedule: {schedule}\n"
                f"AI label: {'yes - mark the post as AI-generated where the platform requires it' if pub.ai_label else 'no'}\n"
                "Upload manually from the phone or the platform's own tools.\n")
    rel = f"episodes/{ep.pk}/exports/episode-{ep.number:02d}-pub{pub.pk}.zip"
    tmp = Path(tempfile.mkdtemp(prefix="exp-", dir=settings.MEDIA_ROOT)) / "pkg.zip"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(asset_storage.storage.path_for(video.path), f"episode-{ep.number:02d}.mp4")
        if cover:
            z.write(asset_storage.storage.path_for(cover.path), "cover.png")
        z.writestr("caption.txt", caption)
        z.writestr("hashtags.txt", tags)
        z.writestr("README.txt", reminder)
    pkg = asset_storage.register(tmp, rel, kind="package", role="export", page=ep.series.page, episode=ep, probe=False,
                                 provenance={"publication": pub.pk, "video_asset": video.pk})
    import shutil

    shutil.rmtree(tmp.parent, ignore_errors=True)
    pub.package = pkg
    pub.status = "exported" if pub.status in ("draft", "failed") else pub.status
    pub.save(update_fields=["package", "status", "updated_at"])
    return {"package_asset_id": pkg.pk, "url": pkg.url, "size_bytes": pkg.size_bytes}
