"""Phase 3 jobs: anime model comparison, character LoRA training, video retakes, audio (music / SFX) generation, rig from a character sheet.
Handlers are thin; the work lives in instai.production / instai.render."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings

from instai.jobs.registry import handler


@handler("compare.run", resource="gpu", timeout=6 * 3600)
def compare_run(ctx):
    from instai.production import anime
    from instai.production.models import AnimeComparison

    return anime.run(ctx, AnimeComparison.objects.get(pk=ctx.payload["comparison_id"]))


@handler("lora.train", resource="gpu", timeout=6 * 3600)
def lora_train(ctx):
    from instai.production import lora
    from instai.production.models import CharacterLora

    return lora.train(ctx, CharacterLora.objects.select_related("character__page").get(pk=ctx.payload["lora_id"]))


def _retake_resource(payload: dict) -> str:
    return "cpu" if payload.get("audio_mode") == "cut" else "gpu"


@handler("retake.run", resource=_retake_resource, timeout=4 * 3600)
def retake_run(ctx):
    from instai.production import retakes
    from instai.production.models import Retake

    return retakes.run(ctx, Retake.objects.select_related("episode__series__page", "source_asset").get(pk=ctx.payload["retake_id"]))


@handler("audio.generate", resource="gpu", timeout=3600)
def audio_generate(ctx):
    """Generate one or all planned tracks of an episode's mix."""
    from instai.production import mixing
    from instai.production.models import MixTrack

    ids = ctx.payload.get("track_ids") or []
    tracks = list(MixTrack.objects.select_related("episode__series__page", "shot").filter(pk__in=ids))
    out = []
    for i, t in enumerate(tracks):
        ctx.check()
        ctx.progress(i / max(1, len(tracks)), f"{t.kind}: {t.label[:40]}")
        out.append(mixing.generate(ctx, t))
    return {"generated": len(out), "tracks": out}


@handler("rig.from_sheet", resource="gpu", timeout=3 * 3600)
def rig_from_sheet(ctx):
    from instai.assets import storage as asset_storage
    from instai.pages.models import Character, CharacterReference
    from instai.production import rigbuild
    from instai.production.api_rigs import _next_version
    from instai.production.models import CharacterRig
    from instai.providers.base import ProviderError

    ch = Character.objects.select_related("page").get(pk=ctx.payload["character_id"])
    asset = None
    if ctx.payload.get("sheet_asset"):
        from instai.assets.models import Asset

        asset = Asset.objects.filter(pk=ctx.payload["sheet_asset"]).first()
    if asset is None:
        ref = CharacterReference.objects.filter(character=ch, approved=True, kind="sheet").exclude(asset=None).select_related("asset").first()
        asset = ref.asset if ref else None
    if asset is None or not asset_storage.storage.exists(asset.path):
        raise ProviderError("this character has no approved character sheet (approve a sheet first, or upload PNG layers)", retryable=False, code="not_ready")
    version = _next_version(ch)
    root = Path(settings.MEDIA_ROOT)
    folder = root / "characters" / str(ch.pk) / f"rig{version}"
    spec, report = rigbuild.from_sheet(ctx, ch, asset_storage.storage.path_for(asset.path), folder, root)
    rig = CharacterRig.objects.create(character=ch, version=version, name=ctx.payload.get("name") or f"{ch.name} v{version} (from sheet)", source="flux_cutout", spec=spec,
                                      sheet_asset=asset, notes="; ".join(report["notes"]))
    return {"rig_id": rig.pk, "version": version, **report}
