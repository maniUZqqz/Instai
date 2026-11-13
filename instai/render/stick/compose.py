"""Compose stick-figure pictures and clips: a scene (background + characters in named poses and expressions + speech bubbles + caption)
becomes a PNG (an Instagram post, a keyframe, a storyboard frame) or a silent H.264 clip through the existing puppet renderer.

The characters come from `spec.py` dictionaries, so the SAME dictionary gives the SAME character on every page, in every pose and in
every video clip. `model_sheet` draws the reference sheet the owner approves once.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from instai.render import fa_text
from instai.render.puppet import renderer as puppet_renderer

from . import parts, poses, scenes
from . import spec as S

DEFAULT_SIZE = (1080, 1350)               # Instagram 4:5 portrait
SIZES = {"4:5": (1080, 1350), "9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
HEAD_FACTOR = {"stand": 1.0, "crouch": 0.6, "hide": 0.58, "sit": 0.62, "lying": 0.22, "sneak": 0.82, "cheer": 1.0}
INK = (31, 36, 48, 255)


def size_for(aspect: str) -> tuple[int, int]:
    return SIZES.get(aspect, DEFAULT_SIZE)


def _rig_for(spec: dict, expression: str, work: Path) -> dict:
    """The rig spec of (character, expression); the part pictures are drawn once into work/stick/<hash>/ and reused."""
    s = S.normalize(spec)
    key = hashlib.sha256((S.spec_hash(s) + "|" + expression + "|v1").encode()).hexdigest()[:14]
    folder = work / "stick" / key
    marker = folder / "rig.json"
    if marker.exists():
        return json.loads(marker.read_text(encoding="utf-8"))
    rig = parts.make_rig_spec(s, folder, work, expression)
    marker.write_text(json.dumps(rig, ensure_ascii=False), encoding="utf-8")
    return rig


def _background(bg, w: int, h: int, work: Path) -> Image.Image:
    if isinstance(bg, dict) and bg.get("color"):
        return Image.new("RGB", (w, h), tuple(int(bg["color"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)))
    key = bg if isinstance(bg, str) else "plain"
    return scenes.draw(key, w, h)


def _actor_spec(a: dict, work: Path, w: int, h: int) -> dict:
    expression = a.get("expression") if a.get("expression") in parts._EXPR else "neutral"
    pose = a.get("pose") if a.get("pose") in poses.POSES else "stand"
    shape = parts.expression_parts(expression)[3] if a.get("talk") is not True else "C"
    return {"rig": _rig_for(a["spec"], expression, work), "x": float(a.get("x", 0.5)), "y": float(a.get("y", 0.93)), "height": float(a.get("height", 0.55)),
            "flip": bool(a.get("flip")), "seed": 1, "blink": False, "shadow": a.get("shadow", True),
            "timeline": [{"layer": "base", "clips": [{"motion": f"pose_{pose}", "start": 0.0, "end": 1.0, "blend": 0.0}]}],
            "mouth": [[0.0, 1.0, shape]]}


def head_xy(a: dict, w: int, h: int, rig_size: tuple[int, int] = parts.DESIGN) -> tuple[float, float, float]:
    """(x, y, radius) of the actor's head on the canvas, for placing bubbles."""
    px = float(a.get("height", 0.55)) * h / rig_size[1]
    feet_x, feet_y = float(a.get("x", 0.5)) * w, float(a.get("y", 0.93)) * h
    f = HEAD_FACTOR.get(a.get("pose", "stand"), 0.9)
    head_up = (parts.ANCHOR[1] - 224) * px * f
    return feet_x, feet_y - head_up, 78 * px


# ------------------------------------------------------------------ text overlays

def _bubble(draw: ImageDraw.ImageDraw, canvas_size: tuple[int, int], head: tuple[float, float, float], text: str, kind: str = "say", *, side: str = "auto",
            font_px: int = 46) -> None:
    w, h = canvas_size
    fnt = fa_text.font(font_px, bold=True)
    max_w = int(w * 0.62)
    lines = fa_text.wrap(text, fnt, max_w - 48)[:5]
    lh = fa_text.line_height(fnt, 1.3)
    tw = max(fa_text.text_width(ln, fnt) for ln in lines) if lines else 80
    bw, bh = tw + 56, lh * len(lines) + 40
    hx, hy, hr = head
    bx = min(max(hx - bw * (0.32 if hx > w / 2 else 0.68), 24), w - bw - 24)
    gap = {"shout": 120, "think": 96}.get(kind, 64)
    by = max(24, hy - hr - bh - gap)
    box = [bx, by, bx + bw, by + bh]
    fill, line = (255, 255, 255, 255), INK
    if kind == "shout":
        n, cx, cy = 14, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        rx, ry = bw / 2 + 24, bh / 2 + 24
        import math

        pts = []
        for i in range(n * 2):
            r = 1.0 if i % 2 == 0 else 0.84
            ang = math.pi * i / n
            pts.append((cx + math.cos(ang) * rx * r, cy + math.sin(ang) * ry * r))
        draw.polygon(pts, fill=(255, 236, 140, 255), outline=line)
        draw.line(pts + [pts[0]], fill=line, width=5, joint="curve")
    else:
        draw.rounded_rectangle(box, radius=34, fill=fill, outline=line, width=5)
        tail_x = min(max(hx, box[0] + 50), box[2] - 50)
        if kind == "think":
            span = max(20.0, hy - hr - 8 - box[3])
            for dx, rr in ((0.18, 15), (0.5, 11), (0.80, 7)):
                cxx, cyy = tail_x + (hx - tail_x) * dx, box[3] + span * dx
                draw.ellipse([cxx - rr, cyy - rr, cxx + rr, cyy + rr], fill=fill, outline=line, width=4)
        else:
            tip = (hx, min(hy - hr - 6, box[3] + 90))
            draw.polygon([(tail_x - 24, box[3] - 3), (tail_x + 24, box[3] - 3), tip], fill=fill)
            draw.line([(tail_x - 24, box[3] - 2), tip, (tail_x + 24, box[3] - 2)], fill=line, width=5, joint="curve")
            draw.line([(tail_x - 21, box[3] - 3), (tail_x + 21, box[3] - 3)], fill=fill, width=8)
    y = by + 20
    for ln in lines:
        right = fa_text.has_rtl(ln)
        if right:
            fa_text.draw_text(draw, (bx + bw - 28, y), ln, fnt, INK, anchor="ra")
        else:
            fa_text.draw_text(draw, (bx + 28, y), ln, fnt, INK, anchor="la")
        y += lh


def _caption(draw: ImageDraw.ImageDraw, canvas_size: tuple[int, int], text: str, position: str = "top", *, font_px: int = 52) -> None:
    w, h = canvas_size
    fnt = fa_text.font(font_px, bold=True)
    margin = 54
    lines = fa_text.wrap(text, fnt, w - 2 * margin - 40)[:6]
    lh = fa_text.line_height(fnt, 1.32)
    bh = lh * len(lines) + 44
    y0 = 0 if position == "top" else h - bh
    draw.rectangle([0, y0, w, y0 + bh], fill=(20, 24, 34, 232))
    y = y0 + 22
    for ln in lines:
        if fa_text.has_rtl(ln):
            fa_text.draw_text(draw, (w - margin, y), ln, fnt, (255, 255, 255, 255), anchor="ra")
        else:
            fa_text.draw_text(draw, (margin, y), ln, fnt, (255, 255, 255, 255), anchor="la")
        y += lh


def _sfx(draw: ImageDraw.ImageDraw, canvas_size: tuple[int, int], item: dict) -> None:
    w, h = canvas_size
    fnt = fa_text.font(int(item.get("size", 120)), bold=True)
    x, y = float(item.get("x", 0.5)) * w, float(item.get("y", 0.3)) * h
    fa_text.draw_text(draw, (x, y), str(item.get("text", "")), fnt, tuple(item.get("fill", (240, 70, 60))) + (255,), anchor="mm", stroke_width=9, stroke_fill=INK)


# ------------------------------------------------------------------ stills

def compose_still(scene: dict, out_path: Path, work: Path) -> Path:
    """Render one picture. scene = {width, height | aspect, background, actors[{spec, x, y, height, flip, pose, expression, talk}], bubbles[{actor, text, kind}],
    caption{text, position}, sfx[{text, x, y}], night: 0..1}. Returns `out_path`."""
    w, h = (int(scene["width"]), int(scene["height"])) if scene.get("width") else size_for(scene.get("aspect", "4:5"))
    work.mkdir(parents=True, exist_ok=True)
    canvas = _background(scene.get("background", "plain"), w, h, work).convert("RGBA")
    if scene.get("night"):
        ov = Image.new("RGBA", (w, h), (10, 16, 48, int(255 * max(0.0, min(0.8, float(scene["night"]))))))
        canvas.alpha_composite(ov)
    actors = list(scene.get("actors") or [])
    for a in sorted(actors, key=lambda a: float(a.get("y", 0.93))):
        spec = _actor_spec(a, work, w, h)
        actor = puppet_renderer._Actor(spec, 1.0, w, h, 1.0, work)
        actor.draw(canvas, 0.0, (0.0, 0.0, 1.0))
    draw = ImageDraw.Draw(canvas)
    for b in scene.get("bubbles") or []:
        idx = int(b.get("actor", 0))
        if 0 <= idx < len(actors) and str(b.get("text", "")).strip():
            _bubble(draw, (w, h), head_xy(actors[idx], w, h), str(b["text"]), str(b.get("kind", "say")), font_px=int(b.get("font", 46)))
    for item in scene.get("sfx") or []:
        _sfx(draw, (w, h), item)
    cap = scene.get("caption")
    if cap and str(cap.get("text", "")).strip():
        _caption(draw, (w, h), str(cap["text"]), str(cap.get("position", "top")), font_px=int(cap.get("font", 52)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


# ------------------------------------------------------------------ clips (silent; narration and subtitles are added at assembly)

def clip_scene(scene: dict, work: Path, duration: float, fps: int = 15) -> dict:
    """The puppet-renderer scene description of a stick scene (actors play named motions; see poses.EXTRA_MOTIONS and puppet motions)."""
    w, h = (int(scene["width"]), int(scene["height"])) if scene.get("width") else size_for(scene.get("aspect", "9:16"))
    work.mkdir(parents=True, exist_ok=True)
    bg = _background(scene.get("background", "plain"), w, h, work)
    bg_path = work / f"bgclip_{hashlib.sha256(json.dumps(scene.get('background'), sort_keys=True).encode()).hexdigest()[:10]}_{w}x{h}.png"
    if not bg_path.exists():
        bg.save(bg_path)
    actors = []
    for a in scene.get("actors") or []:
        expression = a.get("expression") if a.get("expression") in parts._EXPR else "neutral"
        motion_list = a.get("motions") or [{"motion": "idle", "start": 0.0, "end": duration}]
        actors.append({"rig": _rig_for(a["spec"], expression, work), "x": float(a.get("x", 0.5)), "y": float(a.get("y", 0.93)), "height": float(a.get("height", 0.55)),
                       "flip": bool(a.get("flip")), "seed": int(a.get("seed", 1)), "blink": True, "shadow": True,
                       "timeline": [{"layer": "base", "clips": [m for m in motion_list if m["motion"] in puppet_renderer.motions.MOTIONS]}],
                       "mouth": a.get("mouth") or []})
    return {"width": w, "height": h, "fps": fps, "duration": duration, "color": "#202028", "background": {"layers": [{"image": str(bg_path), "parallax": 0.0, "fit": "stretch"}]},
            "actors": actors, "camera": scene.get("camera") or []}


def render_clip(scene: dict, out_path: Path, work: Path, duration: float, *, fps: int = 15, ctx=None) -> dict:
    return puppet_renderer.PuppetRenderer(clip_scene(scene, work, duration, fps), work).render(out_path, ctx=ctx)


# ------------------------------------------------------------------ the model sheet

def _cell(spec: dict, work: Path, size: tuple[int, int], *, expression: str = "neutral", pose: str = "stand", flip: bool = False, zoom_head: bool = False) -> Image.Image:
    w, h = size
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if zoom_head:
        px = (w * 0.62) / 156
        a = {"spec": spec, "expression": expression, "pose": pose, "flip": flip, "x": 0.5, "shadow": False,
             "height": 900 * px / h, "y": (h * 0.46 + (parts.ANCHOR[1] - 224) * px) / h}
    else:
        a = {"spec": spec, "expression": expression, "pose": pose, "flip": flip, "x": 0.5, "y": 0.96, "height": 0.9, "shadow": False}
    actor = puppet_renderer._Actor(_actor_spec(a, work, w, h), 1.0, w, h, 1.0, work)
    actor.draw(canvas, 0.0, (0.0, 0.0, 1.0))
    return canvas


def model_sheet(spec: dict, out_path: Path, work: Path, *, title: str = "", language: str = "fa") -> Path:
    """The reference sheet: name, front and mirrored view, 8 expressions, 8 poses, colour key and identity note, on paper.
    This is the picture the owner approves; every later page and video is made from the same spec."""
    s = S.normalize(spec)
    W, H = 2000, 1540
    sheet = Image.new("RGB", (W, H), (244, 241, 234))
    d = ImageDraw.Draw(sheet)
    fa = language == "fa"
    name = title or s["name"] or "?"
    d.rectangle([0, 0, W, 110], fill=(31, 36, 48))
    fa_text.draw_text(d, (W - 60 if fa else 60, 30), name, fa_text.font(58, True), (255, 255, 255), anchor="ra" if fa else "la")
    fa_text.draw_text(d, (60 if fa else W - 60, 40), "MODEL SHEET" if not fa else "برگهٔ مدل (MODEL SHEET)", fa_text.font(36), (200, 206, 220), anchor="la" if fa else "ra")
    def label(x, y, text, size=30, anchor="mt"):
        fa_text.draw_text(d, (x, y), text, fa_text.font(size, True), (60, 64, 76), anchor=anchor)

    # row 1: turnaround (front + mirrored) and the colour key
    sheet.paste(Image.new("RGB", (380, 560), (255, 255, 255)), (60, 150))
    sheet.paste(Image.new("RGB", (380, 560), (255, 255, 255)), (470, 150))
    for i, flip in enumerate((False, True)):
        cell = _cell(s, work, (380, 560), flip=flip)
        sheet.paste(cell, (60 + i * 410, 150), cell)
    label(250, 718, "نمای اصلی" if fa else "Front view")
    label(660, 718, "نمای آینه‌ای" if fa else "Mirrored view")
    kx = 900
    label(kx + 420, 150, "کلید رنگ" if fa else "Colour key", 34)
    pal = S.palette(s)
    for i, c in enumerate(pal):
        col, row = i % 2, i // 2
        x0, y0 = kx + col * 520, 210 + row * 118
        d.rounded_rectangle([x0, y0, x0 + 96, y0 + 96], radius=18, fill=tuple(int(c["hex"][j:j + 2], 16) for j in (1, 3, 5)), outline=(31, 36, 48), width=4)
        fa_text.draw_text(d, (x0 + 116, y0 + 8), c["hex"].upper(), fa_text.font(32, True), (31, 36, 48), anchor="la")
        fa_text.draw_text(d, (x0 + 116, y0 + 52), f"{c['role']} · {c['name']}", fa_text.font(26), (90, 94, 106), anchor="la")
    anchor_y = 210 + ((len(pal) + 1) // 2) * 118 + 20
    label(kx + 520, anchor_y, "قاعدهٔ هویت" if fa else "Identity rule", 32)
    fa_text.draw_paragraph(d, (kx, anchor_y + 54, W - 60, anchor_y + 270), S.anchor_text(s), fa_text.font(28), (60, 64, 76), align="left", spacing=1.3)
    # row 2: expressions
    label(W // 2, 768, "حالت‌های چهره" if fa else "Expressions", 34)
    ew = (W - 120) // 8
    for i, ex in enumerate(parts._EXPR):
        cell = _cell(s, work, (ew - 10, 240), expression=ex, zoom_head=True)
        x = 60 + i * ew
        sheet.paste(Image.new("RGB", (ew - 10, 240), (255, 255, 255)), (x, 818))
        sheet.paste(cell, (x, 818), cell)
        label(x + (ew - 10) // 2, 1066, ex, 26)
    # row 3: poses
    label(W // 2, 1108, "ژست‌ها" if fa else "Poses", 34)
    pw = (W - 120) // len(poses.SHEET_POSES)
    for i, pz in enumerate(poses.SHEET_POSES):
        cell = _cell(s, work, (pw - 10, 340), pose=pz)
        x = 60 + i * pw
        sheet.paste(Image.new("RGB", (pw - 10, 340), (255, 255, 255)), (x, 1156))
        sheet.paste(cell, (x, 1156), cell)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, "PNG", optimize=True)
    return out_path
