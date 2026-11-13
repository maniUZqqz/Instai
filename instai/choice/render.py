"""Pictures of a choice story: the base scene (a stick-figure scene drawn by code, or an AI picture made with the locked identities), then the overlay that
carries what must be readable in any language - the post number, the story text, the choices and the number each choice points to."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw

from instai.assets import storage as asset_storage
from instai.render import fa_text
from instai.render.stick import compose, poses, scenes
from instai.render.stick import spec as stick_spec

from . import graph as G

BUTTON = [(47, 127, 209), (217, 74, 61), (46, 158, 91), (139, 79, 209)]
ENDING_STYLE = {"good": ((46, 158, 91), "پایان خوب", "Good ending"), "bad": ((217, 74, 61), "پایان بد", "Bad ending"),
                "secret": ((139, 79, 209), "پایان مخفی", "Secret ending"), "neutral": ((107, 114, 128), "پایان", "The end")}
INK = (20, 24, 34)


def story_size(story) -> tuple[int, int]:
    return compose.size_for(story.aspect)


def _fa(story) -> bool:
    return story.language == "fa"


def spec_for(story, name: str) -> dict:
    """The stick spec of a character: its locked identity when there is one, else a stable look derived from the name (so it still renders)."""
    from instai.identity.models import CharacterLock

    lock = CharacterLock.objects.filter(character__page=story.page, character__name=name).first()
    if lock is not None and lock.stick:
        return lock.stick
    return stick_spec.normalize({}, name=name)


def node_hash(story, node: dict, graph: dict) -> str:
    from instai.identity.models import CharacterLock

    names = node.get("scene", {}).get("characters") or []
    locks = sorted((l.character.name, l.version, l.status) for l in CharacterLock.objects.filter(character__page=story.page, character__name__in=names).select_related("character"))
    lines = G.choice_lines(node, graph, fa=_fa(story))
    payload = [story.renderer, story.aspect, story.language, node.get("number"), node.get("text"), node.get("kind"), node.get("ending"), node.get("scene"), lines, locks,
               node.get("title"), "v3"]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def stale_nodes(story) -> list[str]:
    return [n["id"] for n in G.nodes_of(story.graph) if n.get("image_hash") != node_hash(story, n, story.graph) or not n.get("asset_id")]


# ------------------------------------------------------------------ base scene

def base_scene(story, node: dict, size: tuple[int, int]) -> dict:
    from instai.identity import stickshots

    sc = node.get("scene") or {}
    names = [n for n in (sc.get("characters") or []) if n][:2]
    text = f"{sc.get('location', '')} {node.get('text', '')}"
    bg = sc.get("background") or (sc.get("location") if sc.get("location") in scenes.BACKGROUNDS else scenes.pick(text, default="plain"))
    ending = node.get("ending")
    pose = sc.get("pose") if sc.get("pose") in poses.POSES else stickshots.guess_pose(node.get("text", ""))
    expr = sc.get("expression") if sc.get("expression") else stickshots.guess_expression(node.get("text", ""))
    xs = {0: [], 1: [0.5], 2: [0.30, 0.72]}[len(names)]
    actors = []
    for k, name in enumerate(names):
        actors.append({"spec": spec_for(story, name), "x": xs[k], "y": 0.77, "height": 0.40 if len(names) == 1 else 0.36, "flip": k == 1,
                       "pose": pose if k == 0 else "stand", "expression": expr if k == 0 else "neutral"})
    scene = {"width": size[0], "height": size[1], "background": bg, "actors": actors}
    if ending == "bad":
        scene["night"] = 0.18
    return scene


def ai_base(ctx, story, node: dict, size: tuple[int, int], out: Path) -> dict:
    """The picture from the image model with the locked identities (placeholder in demo mode). Returns the provenance dict."""
    from instai.core import settings_store
    from instai.identity import service as identity
    from instai.production import hero, pipeline
    from instai.render.placeholders import make_placeholder

    engine = str(settings_store.effective("image_engine") or "auto")
    if engine == "placeholder":
        make_placeholder(out, size[0], size[1], f"post {node.get('number')}", seed=f"{story.pk}-{node['id']}")
        return {"engine": "placeholder", "note": "demo mode: placeholder, not an AI image"}
    from instai.gpu import compute
    from instai.providers.comfy.workflows import get_workflow
    from instai.providers.base import ProviderError

    sc = node.get("scene") or {}
    chars = [c for c in story.page.characters.all() if c.name in (sc.get("characters") or [])]
    from instai.styles import library

    look = library.compose_for_series(story.series) if story.series_id else library.compose_for_page(story.page)
    prompt = ", ".join(x for x in (f"{sc.get('location', '')} {sc.get('pose', '')} {sc.get('expression', '')}".strip(), node.get("text", "")[:160], look.get("positive", "")) if x)
    seed = int(hashlib.sha256(f"{story.pk}-{node['id']}".encode()).hexdigest()[:8], 16) % (2 ** 31)
    base = {"prompt": prompt, "negative_prompt": look.get("negative", ""), "width": size[0] // 2 * 2, "height": size[1] // 2 * 2, "seed": seed, "steps": 24}
    plan = identity.plan_for_characters(chars, base, hero.reference_workflow)
    wid, inputs, files, note = (plan.workflow, plan.inputs, plan.files, plan.note) if plan else ("", base, {}, "")
    wid = wid or str(settings_store.effective("image_workflow"))
    if not compute.workflow_available(wid):
        raise ProviderError("ComfyUI در دسترس نیست (یا گردش‌کار تصویر آماده نیست).", retryable=False, code="not_ready")
    spec = get_workflow(wid)
    res = compute.run_task(ctx, "comfy.graph", {"graph": spec.build(inputs), "workflow": wid, "timeout": 1800, "expected": spec.expected_seconds}, inputs=files)
    try:
        pics = res.of_kind(*hero.IMAGE_SUFFIX)
        if not pics:
            raise ProviderError("ComfyUI returned no image", retryable=True)
        import shutil

        shutil.move(str(pics[0]), out)
    finally:
        res.cleanup()
    return {**spec.provenance(inputs), "engine": "comfyui", "device": res.device, "note": note}


# ------------------------------------------------------------------ overlay

def overlay(img: Image.Image, story, node: dict, graph: dict) -> Image.Image:
    fa = _fa(story)
    canvas = img.convert("RGBA")
    w, h = canvas.size
    f = w / 1080.0
    d = ImageDraw.Draw(canvas, "RGBA")
    margin, pad = int(50 * f), int(26 * f)
    # top: number badge + story text
    fnt = fa_text.font(int(46 * f), True)
    badge_d = int(112 * f)
    x_l, x_r = margin + (badge_d + int(24 * f) if fa else 0), w - margin - (0 if fa else badge_d + int(24 * f))
    lines = fa_text.wrap(node.get("text", ""), fnt, x_r - x_l)[:5]
    lh = fa_text.line_height(fnt, 1.3)
    band = max(int(150 * f), lh * len(lines) + 2 * pad)
    d.rectangle([0, 0, w, band], fill=INK + (236,))
    bx = margin if fa else w - margin - badge_d
    by = (band - badge_d) // 2
    d.ellipse([bx, by, bx + badge_d, by + badge_d], fill=(232, 162, 43, 255), outline=(255, 255, 255, 255), width=int(5 * f))
    num = fa_text.digits_fa(node.get("number", "")) if fa else str(node.get("number", ""))
    fa_text.draw_text(d, (bx + badge_d / 2, by + badge_d / 2), num, fa_text.font(int((58 if len(str(num)) < 3 else 44) * f), True), INK, anchor="mm")
    y = (band - lh * len(lines)) // 2
    for ln in lines:
        if fa_text.has_rtl(ln):
            fa_text.draw_text(d, (x_r, y), ln, fnt, (255, 255, 255, 255), anchor="ra")
        else:
            fa_text.draw_text(d, (x_l, y), ln, fnt, (255, 255, 255, 255), anchor="la")
        y += lh
    # bottom: choices or the ending banner
    lines_c = G.choice_lines(node, graph, fa=fa)
    bf = fa_text.font(int(44 * f), True)
    sm = fa_text.font(int(34 * f), True)
    if node.get("kind") == "ending":
        col, tfa, ten = ENDING_STYLE.get(node.get("ending") or "neutral", ENDING_STYLE["neutral"])
        bh = int(250 * f)
        d.rectangle([0, h - bh, w, h], fill=col + (238,))
        fa_text.draw_text(d, (w / 2, h - bh + int(72 * f)), tfa if fa else ten, fa_text.font(int(78 * f), True), (255, 255, 255, 255), anchor="mm")
        first = next((n for n in G.nodes_of(graph) if n.get("kind") == "start"), None)
        again = (f"برای امتحان مسیر دیگر به پست {fa_text.digits_fa(first['number'])} برگرد" if fa else f"Go back to post {first['number']} and try another way") if first else ""
        fa_text.draw_text(d, (w / 2, h - bh + int(172 * f)), again, sm, (255, 255, 255, 235), anchor="mm")
    else:
        bh_each, gap = int(120 * f), int(22 * f)
        total = len(lines_c) * bh_each + (len(lines_c) + 1) * gap
        d.rectangle([0, h - total, w, h], fill=INK + (205,))
        for k, c in enumerate(lines_c):
            y0 = h - total + gap + k * (bh_each + gap)
            col = BUTTON[k % 4]
            d.rounded_rectangle([margin, y0, w - margin, y0 + bh_each], radius=int(30 * f), fill=col + (250,), outline=(255, 255, 255, 255), width=int(4 * f))
            letter_x = (w - margin - int(56 * f)) if fa else (margin + int(56 * f))
            d.ellipse([letter_x - int(38 * f), y0 + bh_each / 2 - int(38 * f), letter_x + int(38 * f), y0 + bh_each / 2 + int(38 * f)], fill=(255, 255, 255, 255))
            fa_text.draw_text(d, (letter_x, y0 + bh_each / 2), c["letter"], fa_text.font(int(40 * f), True), col + (255,), anchor="mm")
            pill_w = int(260 * f)
            px0 = (margin + int(22 * f)) if fa else (w - margin - int(22 * f) - pill_w)
            d.rounded_rectangle([px0, y0 + int(22 * f), px0 + pill_w, y0 + bh_each - int(22 * f)], radius=int(22 * f), fill=(255, 255, 255, 255))
            to = (f"← پست {fa_text.digits_fa(c['number'])}" if fa else f"→ post {c['number']}") if c["number"] else "?"
            fa_text.draw_text(d, (px0 + pill_w / 2, y0 + bh_each / 2), to, sm, INK + (255,), anchor="mm")
            lab_right = (letter_x - int(52 * f)) if fa else (letter_x + int(52 * f))
            if fa:
                fa_text.draw_text(d, (lab_right, y0 + bh_each / 2), c["label"], bf, (255, 255, 255, 255), anchor="rm")
            else:
                fa_text.draw_text(d, (lab_right, y0 + bh_each / 2), c["label"], bf, (255, 255, 255, 255), anchor="lm")
    return canvas.convert("RGB")


def render_post(story, node: dict, out: Path, work: Path, *, ctx=None, size: tuple[int, int] | None = None) -> dict:
    """Render the finished picture of one post to `out` (PNG). Returns {engine, ...} provenance."""
    size = size or story_size(story)
    work.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="cp-", dir=work)) / "base.png"
    if story.renderer == "image":
        prov = ai_base(ctx, story, node, size, tmp)
    else:
        compose.compose_still(base_scene(story, node, size), tmp, work / "stick")
        prov = {"engine": "stick", "note": "drawn by code from the locked stick identities"}
    with Image.open(tmp) as base:
        final = overlay(base, story, node, story.graph)
    out.parent.mkdir(parents=True, exist_ok=True)
    final.save(out, "PNG", optimize=True)
    import shutil

    shutil.rmtree(tmp.parent, ignore_errors=True)
    return prov


def register_post(story, node: dict, ctx=None) -> dict:
    """Render a post and register it as an Asset; returns {asset_id, hash}."""
    h = node_hash(story, node, story.graph)
    tmp = Path(tempfile.mkdtemp(prefix="cpost-", dir=settings.MEDIA_ROOT)) / "post.png"
    prov = render_post(story, node, tmp, Path(settings.MEDIA_ROOT) / "stickwork" / f"choice{story.pk}", ctx=ctx)
    rel = f"choice/{story.pk}/post-{node['number']:03d}-{node['id']}-{h[:8]}.png"
    asset = asset_storage.register(tmp, rel, kind="image", role="other", page=story.page, input_hash=h,
                                   provenance={**prov, "purpose": "choice_post", "story": story.pk, "node": node["id"], "number": node["number"]})
    import shutil

    shutil.rmtree(tmp.parent, ignore_errors=True)
    return {"asset_id": asset.pk, "hash": h, "url": asset.url}
