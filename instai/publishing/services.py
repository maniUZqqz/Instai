"""Release 1 publishing: a ready package for MANUAL upload (video, cover, caption, hashtags, schedule reminder).
Nothing is ever posted automatically; the adapter interface is here so the official Instagram Graph API can be added later."""
from __future__ import annotations

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.core.errors import DomainError

from .models import Publication


from .adapters import ManualExport, PublishAdapter  # noqa: E402,F401  (the adapter interface lives in adapters.py)


def best_video(ep) -> Asset | None:
    for role in ("final", "preview"):
        a = Asset.objects.filter(episode=ep, role=role, is_current=True).order_by("-id").first()
        if a:
            return a
    return None


def export_package(publication_id: int, ctx=None) -> dict:
    """The package for manual upload. Always the finished episode, the caption (read by `caption_lint`, never rewritten), the hashtags and a README; plus, for every
    network the page's publishing targets name, that network's own file (`publishing/delivery_package.py`, docs/DELIVERY.md), the subtitles and the covers when they
    exist. A page with no target gets the package it always got."""
    from . import delivery_package as dp

    pub = Publication.objects.select_related("episode__series__page").get(pk=publication_id)
    ep = pub.episode
    video = best_video(ep)
    if not video:
        raise DomainError("not_ready", "برای این قسمت هنوز ویدئویی ساخته نشده است.", message_en="No video has been made for this episode yet.")
    rel = f"episodes/{ep.pk}/exports/episode-{ep.number:02d}-pub{pub.pk}.zip"
    work = dp.make_workdir()
    try:
        entries, manifest = dp.build(pub, video, work / "files", ctx)
        zip_path = work / "pkg.zip"
        dp.write_zip(entries, zip_path)
        made = [n["key"] for n in manifest["networks"] if (n.get("result") or {}).get("status") == "made"]
        pkg = asset_storage.register(zip_path, rel, kind="package", role="export", page=ep.series.page, episode=ep, probe=False,
                                     provenance={"publication": pub.pk, "video_asset": video.pk, "networks": made,
                                                 "not_made": [n["key"] for n in manifest["networks"] if n["key"] not in made], "warnings": len(manifest["lint"])})
    finally:
        dp.cleanup(work)
    pub.package = pkg
    pub.status = "exported" if pub.status in ("draft", "failed") else pub.status
    pub.save(update_fields=["package", "status", "updated_at"])
    return {"package_asset_id": pkg.pk, "url": pkg.url, "size_bytes": pkg.size_bytes, "networks": made, "warnings": len(manifest["lint"])}
