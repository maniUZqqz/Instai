"""Captions of an episode: what the page and the episode choose, the series look they take their colours from, the render options and the soft .srt file.

The engine itself (presets, word times, ASS, SRT, contrast, safe zones) is `instai/render/captions.py` and has no Django in it; this module is the glue between that
engine and the page / episode / series records (the way `mixing.py` is the glue of the audio mix).

  page      `visual.caption_style`  {preset, mode, zone}   - "classic" + "burned" = the plain subtitle InstAI always had (nothing changes for a page that never picks)
  episode   `Episode.caption_style` {preset?, mode?, zone?} - an override, key by key, on top of the page's
  look      the series look (style + colour theme) -> its palette and typography -> the colours of the captions, contrast checked (`render/captions.resolve_style`)
"""
from __future__ import annotations

from instai.assets.models import Asset
from instai.render import captions
from instai.story.models import Episode


def page_config(page) -> dict:
    return captions.normalize_config(page.profile("visual").get("caption_style"))


def config_for(ep: Episode) -> dict:
    """The caption setting in force for an episode: the page's, with the episode's own keys on top."""
    return captions.merge_config(page_config(ep.series.page), ep.caption_style if isinstance(ep.caption_style, dict) else {})


def look_for(ep: Episode) -> dict:
    """{palette, typography} of the look in force for this episode (the series' pick over the page's), from the style library."""
    from instai.remotion import kit
    from instai.styles import library

    lk = library.look_of(ep.series.page, ep.series)
    k = kit.style_kit(lk.get("style_key") or None, lk.get("theme_key") or None)
    return {"palette": k["palette"], "typography": k["typography"], "style_key": k["key"], "theme_key": k["theme_key"]}


def position_of(page) -> str:
    pos = str((page.profile("visual").get("subtitle") or {}).get("position") or "bottom")
    return pos if pos in ("top", "middle", "bottom") else "bottom"


def platform_of(page) -> str:
    return str(page.profile("publishing").get("platform") or "instagram")


def apply_to_options(opts, ep: Episode) -> None:
    """Put the captions of an episode into the render options."""
    page = ep.series.page
    opts.captions = config_for(ep)
    opts.caption_look = look_for(ep)
    opts.language = page.language
    opts.platform = platform_of(page)


def hash_part(ep: Episode) -> str:
    """Changes whenever anything that changes the captions of this episode changes (so a render made with other captions counts as stale)."""
    page = ep.series.page
    return captions.config_hash(config_for(ep), look_for(ep), page.language, platform_of(page), position_of(page))


def srt_asset(ep: Episode, video: Asset | None = None) -> Asset | None:
    """The soft caption file of the episode's render (of this video when given): the newest .srt registered as role 'subtitles'."""
    qs = Asset.objects.filter(episode=ep, role="subtitles", path__endswith=".srt").order_by("-id")
    if video is not None:
        qs = [a for a in qs[:20] if (a.provenance or {}).get("from") == video.pk]
        return qs[0] if qs else None
    return qs.first()


def summary(ep: Episode) -> dict:
    """What the screens show for an episode: the page's choice, the episode's own override, the effective setting and the soft file."""
    page = ep.series.page
    srt = srt_asset(ep)
    cur = ep.caption_style if isinstance(ep.caption_style, dict) else {}
    return {"page": page_config(page), "override": {k: v for k, v in cur.items() if k in captions.DEFAULT_CONFIG and v},
            "effective": config_for(ep), "language": page.language, "platform": platform_of(page),
            "srt_url": srt.url if srt else None, "info": (srt.provenance or {}).get("captions") if srt else None}


def set_override(ep: Episode, data: dict | None) -> dict:
    """Save an episode's caption override ({} / None clears it). Unknown values are dropped; a key equal to the page's still counts as the episode's choice."""
    data = data if isinstance(data, dict) else {}
    clean = {}
    for k in captions.DEFAULT_CONFIG:
        v = data.get(k)
        if v in (None, ""):
            continue
        one = captions.normalize_config({k: v})
        if str(v) == one[k]:
            clean[k] = one[k]
    ep.caption_style = clean
    ep.save(update_fields=["caption_style", "updated_at"])
    return summary(ep)
