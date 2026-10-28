"""Phase 3 jobs: anime model comparison, character LoRA training, retakes, audio (music / SFX) generation, rig from a character sheet.
Handlers are thin; the work lives in instai.production / instai.render."""
from __future__ import annotations

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
