"""Anime video model comparison: the same stills and the same seeds through Wan 2.2 and the optional anime fine-tunes (Index-AniSora V3.2,
AnimeGen I2V), reviewed side by side; the owner's vote sets the page's default model (used by the hero-shot step)."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.gpu import compute
from instai.providers.base import ProviderError
from instai.providers.comfy.workflows import get_workflow

from . import hero
from .models import AnimeComparison, ComparisonClip, PageProductionConfig

CANDIDATES = [
    {"id": "wan22", "label": "Wan 2.2 I2V A14B (fp8 + lightx2v) - current", "workflow": "wan22_i2v_a14b_fp8", "pack": "wan22", "licence": "Apache-2.0",
     "commercial": "yes", "note": "The model the owner already uses in NMarketing.", "needs": []},
    {"id": "anisora", "label": "Index-AniSora V3.2 (community GGUF Q4_0)", "workflow": "anisora_v32_i2v_gguf", "pack": "anisora",
     "licence": "Apache-2.0 + extra restrictions that apply when retraining / making derivatives (read before commercial use)", "commercial": "unknown",
     "note": "Bilibili's anime fine-tune of Wan 2.2. Needs the ComfyUI-GGUF custom node. ~9 GB per expert.", "needs": ["ComfyUI-GGUF"]},
    {"id": "animegen", "label": "AnimeGen I2V (AIdeaLab, community GGUF Q4_K_M)", "workflow": "animegen_i2v_gguf", "pack": "animegen",
     "licence": "Apache-2.0 (model card tag: commercial-use)", "commercial": "yes",
     "note": "Wan 2.2 I2V fine-tune for Japanese anime. Needs the ComfyUI-GGUF custom node. ~9.7 GB per expert; the card recommends an RTX 4090 for the full weights.",
     "needs": ["ComfyUI-GGUF"]},
]
LENGTH_FRAMES = 49          # 3 s: enough to judge style and motion, a third of the cost of a full shot


def describe() -> list[dict]:
    caps = compute.local_caps()
    wf = (caps.get("models") or {}).get("workflows") or {}
    out = []
    for c in CANDIDATES:
        ok = compute.workflow_available(c["workflow"])
        out.append({**c, "available": ok, "missing": (wf.get(c["workflow"]) or {}).get("missing", []), "expected_seconds": get_workflow(c["workflow"]).expected_seconds,
                    "estimate": True})
    return out


def create(page, *, name: str, prompt: str, seeds: list[int], still_assets: list[int], candidates: list[str]) -> AnimeComparison:
    ids = [c["id"] for c in CANDIDATES]
    cands = [c for c in candidates if c in ids] or ["wan22"]
    seeds = [int(s) for s in seeds][:4] or [11]
    stills = [int(a) for a in still_assets][:6]
    cmp = AnimeComparison.objects.create(page=page, name=name or "مقایسهٔ مدل‌های انیمه", prompt=prompt, seeds=seeds, stills=stills, candidates=cands)
    for si, _ in enumerate(stills):
        for seed in seeds:
            for cand in cands:
                ComparisonClip.objects.create(comparison=cmp, still_index=si, seed=seed, candidate=cand)
    return cmp


def run(ctx, cmp: AnimeComparison) -> dict:
    """Generate every missing clip. Candidates whose workflow no PC can run are 'skipped' with the reason (never a made-up result)."""
    work = {c["id"]: c for c in CANDIDATES}
    avail = {cid: compute.workflow_available(work[cid]["workflow"]) for cid in cmp.candidates}
    cmp.status = "running"
    cmp.save(update_fields=["status"])
    rows = list(ComparisonClip.objects.filter(comparison=cmp, status__in=("queued", "failed")))
    still_paths = {i: asset_storage.storage.path_for(Asset.objects.get(pk=a).path) for i, a in enumerate(cmp.stills)}
    done = {"n": 0}

    def one(row: ComparisonClip) -> int:
        c = work[row.candidate]
        if not avail.get(row.candidate):
            ComparisonClip.objects.filter(pk=row.pk).update(status="skipped", error=f"{c['workflow']} is not available on any PC (install the pack, then run again)")
            return 0
        spec = get_workflow(c["workflow"])
        inputs = {"prompt": cmp.prompt or "the character moves naturally, subtle camera motion", "negative_prompt": hero.NEG, "image": "@input:start.png",
                  "width": 480, "height": 832, "length": LENGTH_FRAMES, "seed": row.seed}
        try:
            res = compute.run_task(ctx, "comfy.graph", {"graph": spec.build(inputs), "workflow": c["workflow"], "timeout": 3600, "expected": spec.expected_seconds},
                                   inputs={"start.png": still_paths[row.still_index]})
        except ProviderError as e:
            ComparisonClip.objects.filter(pk=row.pk).update(status="failed", error=str(e)[:400])
            return 0
        try:
            vids = res.of_kind(*hero.VIDEO_SUFFIX)
            if not vids:
                ComparisonClip.objects.filter(pk=row.pk).update(status="failed", error="no video returned")
                return 0
            tmp = Path(tempfile.mkdtemp(prefix="cmp-", dir=settings.MEDIA_ROOT)) / "clip.mp4"
            shutil.move(str(vids[0]), tmp)
        finally:
            res.cleanup()
        a = asset_storage.register(tmp, f"comparisons/{cmp.pk}/still{row.still_index}-{row.candidate}-seed{row.seed}.mp4", kind="video", role="other", page=cmp.page,
                                   provenance={"purpose": "comparison", "comparison": cmp.pk, "candidate": row.candidate, "workflow": c["workflow"], "seed": row.seed,
                                               "still_asset": cmp.stills[row.still_index], "device": res.device})
        shutil.rmtree(tmp.parent, ignore_errors=True)
        ComparisonClip.objects.filter(pk=row.pk).update(status="done", asset=a, seconds=round(res.seconds, 1), device=res.device, error="")
        done["n"] += 1
        ctx.progress(done["n"] / max(1, len(rows)), f"{done['n']}/{len(rows)} clips")
        return 1
    n = sum(compute.fan_out(ctx, rows, one, kind="comfy.graph", payload={"workflow": work[cmp.candidates[0]]["workflow"]}))
    cmp.status = "done"
    cmp.save(update_fields=["status"])
    return {"generated": n, "skipped": ComparisonClip.objects.filter(comparison=cmp, status="skipped").count(),
            "failed": ComparisonClip.objects.filter(comparison=cmp, status="failed").count()}


def tally(cmp: AnimeComparison) -> dict[str, int]:
    out = {c: 0 for c in cmp.candidates}
    for v in cmp.votes.all():
        out[v.candidate] = out.get(v.candidate, 0) + 1
    return out


def vote(cmp: AnimeComparison, candidate: str, still_index: int | None = None) -> dict:
    """Record a vote; the candidate with the most votes (the newest wins a tie) becomes the page's default anime model."""
    from instai.core.errors import DomainError

    if candidate not in cmp.candidates:
        raise DomainError("validation_error", "این مدل در این مقایسه نیست.", http_status=400, details={"candidate": ["invalid"]})
    if not ComparisonClip.objects.filter(comparison=cmp, candidate=candidate, status="done").exists():
        raise DomainError("conflict", "برای این مدل هنوز ویدئویی ساخته نشده است؛ نمی‌توان به آن رأی داد.", http_status=409)
    cmp.votes.create(candidate=candidate, still_index=still_index)
    counts = tally(cmp)
    best = max(counts.values())
    leaders = [c for c, n in counts.items() if n == best]
    winner = candidate if candidate in leaders else leaders[0]
    cmp.winner = winner
    cmp.save(update_fields=["winner"])
    default = None
    if cmp.page_id:
        cfg, _ = PageProductionConfig.objects.get_or_create(page=cmp.page)
        cfg.anime_model = winner
        cfg.save(update_fields=["anime_model", "updated_at"])
        default = winner
    return {"winner": winner, "counts": counts, "page_default": default}
