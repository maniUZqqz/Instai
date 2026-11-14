"""The delivery package of a publication: one file per network the page posts to, the caption after its check, the hashtags, the subtitles and the cover when they exist.

What goes in (docs/DELIVERY.md):
* the finished episode (`episode-NN.mp4`, as before) - always;
* for every network the page targets (`PublishTarget.platform`, enabled): `<network>/episode-NN-<network>.mp4` at that network's size, frame rate, quality and loudness
  (`render/delivery.py`) - ONLY the networks the page targets, and only when the episode's shape fits (no cropping: otherwise the README says why there is no file);
* `caption.txt` (the caption as written + the hashtags, repaired where glued) after `caption_lint` has read it - the caption itself is never rewritten;
* `hashtags.txt`, `README.txt` (Persian and English: what is where, what was measured, what to look at), `delivery.json` (the same, for programs);
* `episode-NN.srt` and one cover per network when the captions / cover work has produced them (found by their assets; absent = left out, nothing breaks).

Nothing here posts anything. The soft inputs are looked up, never required."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.jobs.context import JobCancelled, JobDeferred
from instai.render import delivery, ffmpeg

from . import caption_lint, hashtags

log = logging.getLogger("instai.delivery_package")


def info_from_asset(video: Asset) -> dict:
    """The facts `render/delivery.plan_network` needs, from the asset row (no probing)."""
    return {"width": video.width, "height": video.height, "fps": video.fps, "duration": video.duration_sec or 0.0, "vcodec": video.codec or ""}


def page_networks(page, aspect: str | None = None) -> tuple[list[dict], list[dict]]:
    """`(networks, ignored)`: the distinct networks the page's ENABLED publishing targets mean, in the table's order, each `{key, targets: [ids], fit}`; `ignored` =
    targets whose platform is not one of the nine (named, never silently dropped)."""
    found: dict[str, dict] = {}
    ignored: list[dict] = []
    for t in page.targets.all():
        if not t.enabled:
            continue
        key = delivery.network_for(t.platform, aspect)
        if key is None:
            ignored.append({"target": t.pk, "platform": t.platform})
            continue
        slot = found.setdefault(key, {"key": key, "targets": [], "fit": ""})
        slot["targets"].append(t.pk)
        if (t.config or {}).get("fit") == "blur":
            slot["fit"] = "blur"
    return [found[k] for k in delivery.KEYS if k in found], ignored


def tags_for(pub, page, series=None, episode=None) -> tuple[list[str], list[str]]:
    """`(given, repaired)`: the stored hashtags and the same list with glued ones split, each as a plain word without `#`."""
    given = [str(h) for h in (pub.hashtags or []) if str(h).strip()]
    vocab = hashtags.page_vocabulary(page, series, episode)
    return given, [hashtags.clean(hashtags.repair(h, vocab)) for h in given]


def tags_text(tags: list[str]) -> str:
    return " ".join("#" + t for t in tags if t)


def lint_for(pub, caption: str | None = None, tags: list | None = None, networks: list[str] | None = None) -> list[dict]:
    ep = pub.episode
    page = ep.series.page
    page_nets, _ = page_networks(page)
    return caption_lint.check(pub.caption if caption is None else caption, pub.hashtags if tags is None else tags, networks=networks if networks is not None else [n["key"] for n in page_nets],
                              title=ep.title, extra_words=hashtags.page_vocabulary(page, ep.series, ep))


def find_srt(ep) -> Asset | None:
    """The newest current subtitle file in SubRip form (the captions work registers it); None when there is none."""
    for a in Asset.objects.filter(episode=ep, kind="subtitle", is_current=True).order_by("-id"):
        if str(a.path).lower().endswith(".srt"):
            return a
    return None


def cover_for(ep, key: str, pub=None) -> Asset | None:
    """The cover for one network: a cover made for exactly that network when the cover work produced one (its provenance or its path names the network key), else the
    publication's own cover, else the newest current cover of the episode."""
    covers = list(Asset.objects.filter(episode=ep, role="cover", is_current=True).order_by("-id"))
    for a in covers:
        prov = a.provenance or {}
        if key in (prov.get("network"), prov.get("format"), prov.get("fmt")) or f"-{key}." in str(a.path) or f"_{key}." in str(a.path):
            return a
    if pub is not None and getattr(pub, "cover_id", None):
        return pub.cover
    generic = [a for a in covers if not any((a.provenance or {}).get(k) for k in ("network", "format", "fmt"))]          # a cover made for another network is not "the" cover
    return (generic or covers or [None])[0]


def plan_for(pub, video: Asset | None = None, info: dict | None = None) -> dict:
    """What the package will contain, from the facts: `{source, networks[...], ignored, lint, hashtags, no_targets}`. Cheap: no probing, no encoding."""
    from .services import best_video

    ep = pub.episode
    page = ep.series.page
    video = video or best_video(ep)
    info = info or (info_from_asset(video) if video else {})
    aspect = delivery.aspect_of(info.get("width"), info.get("height"))
    nets, ignored = page_networks(page, aspect)
    plans = []
    for n in nets:
        item = delivery.plan_network(n["key"], info, fit=n["fit"], duration=info.get("duration"))
        item["targets"] = n["targets"]
        item["fit"] = n["fit"]
        plans.append(item)
    given, repaired = tags_for(pub, page, ep.series, ep)
    return {"source": {"asset": video.pk if video else None, "role": video.role if video else None, "width": info.get("width"), "height": info.get("height"), "aspect": aspect,
                       "duration": info.get("duration"), "loudness_lufs": video.loudness_lufs if video else None,
                       "loudness": (video.provenance or {}).get("loudness") if video else None, "preview": bool(video and video.role == "preview")},
            "networks": plans, "ignored": ignored, "no_targets": not nets and not ignored,
            "lint": lint_for(pub, networks=[p["key"] for p in plans]), "hashtags": {"given": given, "repaired": repaired,
                                                                                       "changed": [g for g, r in zip(given, repaired) if hashtags.clean(g) != r]},
            "page_lufs": float(page.profile("audio")["target_lufs"]), "rerender_aspects": list(delivery.RERENDER_ASPECTS)}


# ---------------------------------------------------------------------------------------------------------------------------- building

def _readme(pub, plan: dict, results: dict[str, dict]) -> str:
    ep = pub.episode
    page = ep.series.page
    schedule = pub.scheduled_at.strftime("%Y-%m-%d %H:%M UTC") if pub.scheduled_at else "not scheduled"
    lines = [
        "InstAI upload package / بستهٔ انتشار InstAI",
        f"Page / صفحه: {page.name}",
        f"Episode / قسمت {ep.number}: {ep.title}",
        f"Schedule / زمان‌بندی: {schedule}",
        f"AI label / برچسب هوش مصنوعی: {'yes - mark the post as AI-generated where the platform requires it / بله؛ در جاهایی که پلتفرم می‌خواهد پست را «ساخته‌شده با هوش مصنوعی» علامت بزنید' if pub.ai_label else 'no'}",
        "Upload manually from the phone or the platform's own tools. Nothing was posted. / آپلود دستی است؛ هیچ چیزی خودکار منتشر نشده است.",
        "",
    ]
    if plan["networks"]:
        lines += ["== Networks / شبکه‌ها (all numbers are approximate / همهٔ عددها تقریبی است) =="]
        for p in plan["networks"]:
            r = results.get(p["key"], {})
            head = f"- {p['key']}: {p['en']} / {p['fa']}"
            if r.get("status") == "made":
                lo = r.get("loudness") or {}
                lines.append(f"{head}\n    file: {r['arc']}   {r['width']}x{r['height']}, {r['fps']} fps, encoder {r['encoder']}"
                             + (f", loudness {lo.get('lufs')} LUFS (target {lo.get('target')}), true peak {lo.get('tp')} dBTP" if lo else ""))
            elif r.get("status") == "failed":
                lines.append(f"{head}\n    NOT MADE (an error while encoding) / ساخته نشد (خطا در رمزگذاری): {r.get('error', '')[:200]}")
            else:
                lines.append(f"{head}\n    NOT MADE / ساخته نشد")
            for n in p["notes"] + p["warnings"]:
                lines.append(f"    {n['en']}\n    {n['fa']}")
        lines.append("")
    for ig in plan.get("ignored", []):
        lines.append(f"- target #{ig['target']} ({ig['platform']}) is not a network this package knows; nothing was made for it / مقصدی ناشناخته؛ برایش فایلی ساخته نشد")
    if plan["lint"]:
        lines += ["== Checks / بررسی‌ها (warnings only; the text was NOT changed / فقط هشدار است؛ متن تغییر نکرده) =="]
        for w in plan["lint"]:
            lines.append(f"- [{w['level']}] {w['message_en']}\n    {w['message']}")
        lines.append("")
    if plan["hashtags"]["changed"]:
        lines.append("Hashtags repaired in hashtags.txt / هشتگ‌های اصلاح‌شده در hashtags.txt: " + ", ".join(plan["hashtags"]["changed"]))
    return "\n".join(lines).rstrip() + "\n"


def build(pub, video: Asset, tmp: Path, ctx=None) -> tuple[list[tuple[str, Path | bytes]], dict]:
    """Make the files of the package inside `tmp`. Returns `(entries, manifest)`: `entries` = [(name in the zip, path or text bytes)]; `manifest` = what `delivery.json`
    holds. A network whose encode fails is reported and skipped, never fatal; the master file, the caption and the README are always there."""
    ep = pub.episode
    src = asset_storage.storage.path_for(video.path)
    try:
        info = ffmpeg.probe(src)
    except Exception:  # noqa: BLE001 - the asset row is a fair fallback
        info = info_from_asset(video)
    plan = plan_for(pub, video, info)
    given, repaired = plan["hashtags"]["given"], plan["hashtags"]["repaired"]
    caption = (pub.caption or ep.title) + ("\n\n" + tags_text(repaired) if repaired else "")
    entries: list[tuple[str, Path | bytes]] = [(f"episode-{ep.number:02d}.mp4", src)]
    results: dict[str, dict] = {}
    todo = [p for p in plan["networks"] if p["status"] in ("ready", "fit")]
    for i, p in enumerate(plan["networks"]):
        key = p["key"]
        if p["status"] not in ("ready", "fit"):
            results[key] = {"status": "skipped", "reason": p["status"]}
            continue
        if ctx is not None:
            ctx.check()
            ctx.progress(0.1 + 0.8 * todo.index(p) / max(1, len(todo)), key)
        arc = f"{key}/episode-{ep.number:02d}-{key}.mp4"
        out = tmp / key / f"episode-{ep.number:02d}-{key}.mp4"
        try:
            r = delivery.render_network(src, out, key, info, mode=p["mode"], ctx=ctx)
            results[key] = {"status": "made", "arc": arc, **{k: r[k] for k in ("width", "height", "fps", "encoder", "mode", "bytes", "loudness")}}
            entries.append((arc, out))
            cover = cover_for(ep, key, pub)
            if cover:
                ext = Path(str(cover.path)).suffix or ".png"
                entries.append((f"{key}/cover{ext}", asset_storage.storage.path_for(cover.path)))
        except Exception as exc:  # noqa: BLE001 - one network failing must not lose the others
            if isinstance(exc, (JobCancelled, JobDeferred)):
                raise
            log.warning("delivery encode failed for %s: %s", key, exc)
            results[key] = {"status": "failed", "error": str(exc)[:300]}
            out.unlink(missing_ok=True)
    cover = cover_for(ep, "", pub)                                      # the one cover the package always had
    if cover:
        entries.append(("cover.png", asset_storage.storage.path_for(cover.path)))
    srt = find_srt(ep)
    if srt:
        entries.append((f"episode-{ep.number:02d}.srt", asset_storage.storage.path_for(srt.path)))
    entries.append(("caption.txt", caption.encode("utf-8")))
    entries.append(("hashtags.txt", tags_text(repaired).encode("utf-8")))
    manifest = {"version": 1, "publication": pub.pk, "episode": ep.pk, "source": plan["source"], "networks": [{**p, "result": results.get(p["key"], {})} for p in plan["networks"]],
                "ignored": plan["ignored"], "lint": plan["lint"], "hashtags": plan["hashtags"], "srt": bool(srt), "approximate_numbers": True}
    entries.append(("README.txt", _readme(pub, plan, results).encode("utf-8")))
    entries.append(("delivery.json", json.dumps(manifest, ensure_ascii=False, indent=1, default=str).encode("utf-8")))
    return entries, manifest


def write_zip(entries: list[tuple[str, Path | bytes]], zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            if isinstance(data, (bytes, bytearray)):
                z.writestr(name, bytes(data))
            else:
                z.write(data, name, compress_type=zipfile.ZIP_STORED if name.lower().endswith((".mp4", ".png", ".jpg", ".jpeg")) else zipfile.ZIP_DEFLATED)


def make_workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="exp-", dir=settings.MEDIA_ROOT))


def cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
