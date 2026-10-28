"""Optional per-character LoRA training (ComfyUI TrainLoraNode) with a MEASURED before/after.

Dataset = the character's approved reference images (sheet, poses, expressions); captions carry a trigger word. Before training the same test
prompts and seeds are generated without the LoRA, after training with it, and both sets are scored against the references with the
consistency embedding (consistency.py). The numbers are stored on the CharacterLora row; the owner decides whether to approve it.
The training graph is UNVERIFIED on real hardware (see gen_comfy_templates.py): a 12B model may not fit a 12 GB card, and then the job says so.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from django.conf import settings
from PIL import Image

from instai.assets import storage as asset_storage
from instai.gpu import compute
from instai.pages.models import CharacterReference
from instai.providers.base import ProviderError
from instai.providers.comfy.workflows import get_workflow

from . import consistency, hero
from .models import CharacterLora

DEFAULT_PROMPTS = ["{t}, portrait, smiling, soft light", "{t}, full body, walking in a park", "{t}, close-up, surprised expression"]
SEEDS = [101, 102, 103]
MIN_IMAGES = 1
OOM_HINT = ("the training ran out of GPU memory: a 12B image model does not train on a 12 GB card with these settings. Lower the rank / steps, or train on a "
            "bigger GPU; the character can still use the reference-image keyframes without a LoRA")


def trigger_word(character) -> str:
    return f"instaichar{character.pk}"


def dataset(character) -> list[tuple[Path, str]]:
    """[(image path, caption)] from the approved references that have a file."""
    rows = []
    for ref in CharacterReference.objects.filter(character=character, approved=True, kind__in=("sheet", "image", "pose", "expression")).exclude(asset=None).select_related("asset"):
        if asset_storage.storage.exists(ref.asset.path):
            cap = f"{trigger_word(character)}, {character.name}, {(character.appearance or '').strip()[:200]}".strip(", ")
            rows.append((asset_storage.storage.path_for(ref.asset.path), cap))
    return rows


def _reference_images(character) -> list[Image.Image]:
    out = []
    for path, _ in dataset(character):
        with Image.open(path) as im:
            out.append(im.convert("RGB").copy())
    return out


def score(images: list[Path], refs: list[Image.Image]) -> dict:
    """Mean over the generated images of the best similarity to any reference (palette + structure embedding)."""
    per = []
    for p in images:
        with Image.open(p) as im:
            g = im.convert("RGB").copy()
        per.append(round(max(consistency.similarity(g, r) for r in refs), 4))
    return {"similarity": round(sum(per) / len(per), 4) if per else None, "per_prompt": per, "embedder": "histogram+structure (built-in, weak)"}


def _generate(ctx, lora_name: str | None, lora_file: Path | None, prompts: list[str], width=512, height=768) -> list[Path]:
    wid = "flux_dev_fp8_t2i_lora" if lora_name else "flux_dev_fp8_t2i"
    spec = get_workflow(wid)
    paths: list[Path] = []
    work = Path(tempfile.mkdtemp(prefix="lorat-", dir=settings.MEDIA_ROOT))
    for i, prompt in enumerate(prompts):
        ctx.check()
        inputs = {"prompt": prompt, "width": width, "height": height, "steps": 20, "seed": SEEDS[i % len(SEEDS)]}
        files, payload = {}, {"workflow": wid, "timeout": 1800, "expected": spec.expected_seconds}
        if lora_name:
            inputs.update(lora_name=lora_name, lora_strength=0.9)
            files = {lora_file.name: lora_file}
            payload["install"] = [{"input": lora_file.name, "dest": "models/loras"}]
        payload["graph"] = spec.build(inputs)
        res = compute.run_task(ctx, "comfy.graph", payload, inputs=files)
        try:
            pics = res.of_kind(*hero.IMAGE_SUFFIX)
            if not pics:
                raise ProviderError("no image returned for a test prompt", retryable=True)
            dst = work / f"t{i}{pics[0].suffix}"
            shutil.move(str(pics[0]), dst)
            paths.append(dst)
        finally:
            res.cleanup()
    return paths


def train(ctx, lora: CharacterLora) -> dict:
    ch = lora.character
    rows = dataset(ch)
    if len(rows) < MIN_IMAGES:
        msg = "this character has no approved reference image to train on (approve the character sheet first)"
        CharacterLora.objects.filter(pk=lora.pk).update(status="failed", error=msg)
        raise ProviderError(msg, retryable=False, code="not_ready")
    p = lora.params or {}
    trig = trigger_word(ch)
    prompts = [t.format(t=trig) for t in (p.get("test_prompts") or DEFAULT_PROMPTS)][:4]
    refs = _reference_images(ch)
    CharacterLora.objects.filter(pk=lora.pk).update(status="training", error="")
    t0 = time.time()
    ctx.progress(0.05, "measuring before")
    try:
        before_imgs = _generate(ctx, None, None, prompts)
        before = score(before_imgs, refs)
        CharacterLora.objects.filter(pk=lora.pk).update(before=before)
        # dataset -> the ComfyUI input folder of the PC that trains
        folder = f"instai_lora_{ch.pk}"
        files: dict[str, Path] = {}
        install = []
        work = Path(tempfile.mkdtemp(prefix="lorad-", dir=settings.MEDIA_ROOT))
        for i, (path, caption) in enumerate(rows):
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((768, 768))
                img_path = work / f"img{i:03d}.png"
                im.save(img_path)
            (work / f"img{i:03d}.txt").write_text(caption, encoding="utf-8")
            for f in (img_path, work / f"img{i:03d}.txt"):
                files[f.name] = f
                install.append({"input": f.name, "dest": f"input/{folder}"})
        spec = get_workflow("train_lora_flux")
        graph = spec.build({"folder": folder, "steps": int(p.get("steps") or 300), "rank": int(p.get("rank") or 16), "seed": 7,
                            "filename_prefix": f"loras/instai_character_{ch.pk}"})
        ctx.progress(0.2, "training")
        try:
            res = compute.run_task(ctx, "comfy.graph", {"graph": graph, "workflow": "train_lora_flux", "install": install, "expect_files": False, "timeout": 4 * 3600,
                                                        "expected": spec.expected_seconds,
                                                        "collect": [f"models/loras/**/instai_character_{ch.pk}*.safetensors", f"output/**/instai_character_{ch.pk}*.safetensors"]},
                                   inputs=files, timeout=4 * 3600)
        except ProviderError as e:
            if "out of memory" in str(e).lower() or "oom" in str(e).lower():
                raise ProviderError(OOM_HINT, retryable=False, code="gpu_oom") from e
            raise
        shutil.rmtree(work, ignore_errors=True)
        try:
            loras = res.of_kind(".safetensors")
            if not loras:
                raise ProviderError("the training finished but no LoRA file was found (check COMFYUI_DIR on the PC that trained)", retryable=False, code="not_ready")
            rel = f"characters/{ch.pk}/lora/{loras[0].name}"
            tmp = Path(tempfile.mkdtemp(prefix="lorav-", dir=settings.MEDIA_ROOT)) / loras[0].name
            shutil.move(str(loras[0]), tmp)
        finally:
            res.cleanup()
        asset_storage.register(tmp, rel, kind="other", role="other", page=ch.page, probe=False, provenance={"purpose": "character_lora", "character": ch.pk,
                                                                                                           "trigger": trig, "device": res.device})
        lora_path = asset_storage.storage.path_for(rel)
        shutil.rmtree(tmp.parent, ignore_errors=True)
        ctx.progress(0.75, "measuring after")
        after_imgs = _generate(ctx, lora_path.name, lora_path, prompts)
        after = score(after_imgs, refs)
        delta = None if before["similarity"] is None or after["similarity"] is None else round(after["similarity"] - before["similarity"], 4)
        after["delta"] = delta
        after["helped"] = bool(delta is not None and delta > 0.01)
        CharacterLora.objects.filter(pk=lora.pk).update(status="trained", lora_file=lora_path.name, after=after, seconds=round(time.time() - t0, 1),
                                                        params={**p, "trigger": trig, "images": len(rows), "prompts": prompts, "device": res.device})
        for d in (before_imgs, after_imgs):
            shutil.rmtree(d[0].parent, ignore_errors=True) if d else None
        return {"lora": lora_path.name, "before": before["similarity"], "after": after["similarity"], "delta": delta, "device": res.device}
    except BaseException as e:
        CharacterLora.objects.filter(pk=lora.pk).update(status="failed", error=str(e)[:600], seconds=round(time.time() - t0, 1))
        raise
