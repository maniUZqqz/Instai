"""The stick-figure kit and the Persian text drawing: identical characters in every pose and scene, drawn by code; Persian shaping that does not depend on libraqm."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from instai.render import fa_text
from instai.render.puppet import motions
from instai.render.puppet.rig import Rig
from instai.render.stick import compose, parts, poses, scenes
from instai.render.stick import spec as S


# ------------------------------------------------------------------ Persian text

def test_shaper_joins_letters_and_orders_them_visually():
    shaped = fa_text.shape("سلام")
    assert all(0xFB50 <= ord(c) <= 0xFEFF for c in shaped), "every Persian letter becomes a presentation form"
    assert len(shaped) == 3                       # lam + alef make one ligature glyph
    assert shaped[0] == "ﻡ"                  # the visual left end is the isolated meem (the word ends there)
    assert fa_text.shape("abc 123") == "abc 123"  # Latin is untouched
    mixed = fa_text.shape("پست 12 را ببین")
    assert "12" in mixed                          # a number keeps its own left-to-right order inside right-to-left text


def test_basic_and_raqm_layouts_draw_nearly_the_same_picture():
    text = "اگر الف را انتخاب کنی برو به پست ۷"

    def draw(force_basic: bool) -> Image.Image:
        im = Image.new("L", (1100, 90), 255)
        fnt = fa_text.font(44, force_basic=force_basic)
        fa_text.draw_text(ImageDraw.Draw(im), (1080, 10), text, fnt, 0, anchor="ra")
        return im.point(lambda v: 255 if v < 128 else 0)

    a, b = draw(False), draw(True)
    ba, bb = a.getbbox(), b.getbbox()
    assert ba and bb
    wa, wb = ba[2] - ba[0], bb[2] - bb[0]
    assert abs(wa - wb) / wa < 0.08, (wa, wb)                                           # the same line width (the built-in shaper matches libraqm's layout)
    ink_a, ink_b = sum(1 for v in a.tobytes() if v), sum(1 for v in b.tobytes() if v)
    assert abs(ink_a - ink_b) / ink_a < 0.15, (ink_a, ink_b)                           # and about the same amount of ink (all letters joined the same way)


def test_wrap_and_paragraph_stay_inside_the_box():
    fnt = fa_text.font(40, True)
    text = "این یک جملهٔ بلند است که باید در چند خط بشکند و از کادر بیرون نزند " * 2
    lines = fa_text.wrap(text, fnt, 500)
    assert len(lines) >= 3 and all(fa_text.text_width(ln, fnt) <= 520 for ln in lines)
    im = Image.new("RGB", (600, 300), "white")
    w, h = fa_text.draw_paragraph(ImageDraw.Draw(im), (50, 20, 550, 280), text, fnt, "black")
    assert w <= 500 and h <= 260


def test_digits_fa():
    assert fa_text.digits_fa("پست 12") == "پست ۱۲"


# ------------------------------------------------------------------ the spec: identity as data

def test_spec_is_normalised_and_gives_identity_words_and_colour_key():
    s = S.normalize({"limb_colour": "#2F7FD1", "hat": "cap", "hat_colour": "#e8a22b", "neck": "scarf", "neck_colour": "#d94a3d", "bogus": 1, "line_width": 99}, name="رامین")
    assert "bogus" not in s and s["line_width"] == 26 and s["limb_colour"] == "#2f7fd1"
    pal = S.palette(s)
    assert {p["role"] for p in pal} >= {"limbs", "head", "outline", "hat", "neck"}
    anchor = S.anchor_text(s)
    assert "blue-limbed stick figure" in anchor and "amber cap" in anchor and "red scarf" in anchor
    assert S.spec_hash(s) == S.spec_hash(dict(s)) and S.spec_hash(s) != S.spec_hash({**s, "hat": "none"})
    a, b = S.normalize({}, name="رامین"), S.normalize({}, name="نگهبان")
    assert a["limb_colour"] != b["limb_colour"] or a["neck"] != b["neck"]          # two characters of one page do not come out identical
    assert S.normalize({}, name="رامین") == S.normalize({}, name="رامین")          # and the look is stable for a name


def test_rig_loads_and_every_pose_and_motion_is_registered(tmp_path):
    root = tmp_path / "media"
    spec = parts.make_rig_spec(S.normalize({}, name="x"), root / "c", root)
    rig = Rig.from_spec(spec, root)
    assert {"body", "head", "arm_l", "arm_r", "leg_l", "leg_r", "forearm_r", "shin_l"} <= set(rig.parts)
    assert rig.mouth_shapes() == sorted("ABCDEFGHX")
    for name in poses.POSES:
        assert f"pose_{name}" in motions.MOTIONS
    for extra in ("run", "sneak", "panic", "shiver", "fall_down", "punch", "cheer_jump"):
        assert extra in motions.MOTIONS
    assert len(poses.POSES) >= 20 and len(scenes.keys()) >= 12 and len(parts._EXPR) == 8
    assert json.loads(json.dumps(spec))["stick"]["limb_colour"]


# ------------------------------------------------------------------ pictures

HERO = {"name": "رامین", "limb_colour": "#2f7fd1", "neck": "scarf", "neck_colour": "#d94a3d", "hat": "cap", "hat_colour": "#e8a22b"}


def test_still_has_the_right_size_and_is_deterministic(tmp_path):
    scene = {"aspect": "4:5", "background": "cell", "actors": [{"spec": HERO, "x": 0.4, "pose": "run_a", "expression": "scared"}], "caption": {"text": "پست ۳", "position": "top"},
             "bubbles": [{"actor": 0, "text": "الان چه کار کنم؟", "kind": "think"}]}
    a = compose.compose_still(scene, tmp_path / "a.png", tmp_path / "w")
    b = compose.compose_still(scene, tmp_path / "b.png", tmp_path / "w2")
    with Image.open(a) as ia, Image.open(b) as ib:
        assert ia.size == (1080, 1350)
        assert list(ia.getdata()) == list(ib.getdata())                     # same scene, same pixels


def test_same_character_keeps_the_same_colours_in_every_pose_scene_and_expression(tmp_path):
    from instai.identity import check
    from instai.identity.models import CharacterLock

    pal = S.palette(S.normalize(HERO))
    lock = CharacterLock(palette=pal)
    seen = 0
    for i, (bg, pose, expr) in enumerate([("cell", "stand", "neutral"), ("street", "run_a", "scared"), ("forest", "hide", "angry"), ("rooftop", "sit", "happy"), ("desert", "hands_up", "surprised")]):
        p = compose.compose_still({"aspect": "1:1", "background": bg, "actors": [{"spec": HERO, "x": 0.5, "height": 0.7, "pose": pose, "expression": expr}]}, tmp_path / f"s{i}.png", tmp_path / "w")
        res = check.check_image(p, lock)
        assert res["ok"], (bg, pose, res["notes"])
        seen += 1
    assert seen == 5
    # a character of other colours is flagged
    other = compose.compose_still({"aspect": "1:1", "background": "street", "actors": [{"spec": {**HERO, "limb_colour": "#2e9e5b", "hat_colour": "#8a4fd1", "neck_colour": "#1ba0a8"}, "x": 0.5,
                                                                                     "height": 0.7}]}, tmp_path / "o.png", tmp_path / "w")
    bad = check.check_image(other, lock)
    assert not bad["ok"] and {n["code"] for n in bad["notes"]} == {"colour_missing"}


def test_backgrounds_pick_from_persian_and_english_words():
    assert scenes.pick("در حیاط زندان") == "cell" or scenes.pick("در حیاط") == "yard"
    assert scenes.pick("a long dark corridor") == "corridor"
    assert scenes.pick("on the rooftop at night") == "rooftop"
    assert scenes.pick("nothing known here") == "plain"


def test_model_sheet_is_drawn(tmp_path):
    p = compose.model_sheet(S.normalize(HERO), tmp_path / "sheet.png", tmp_path / "w", title="رامین")
    with Image.open(p) as im:
        assert im.size[0] == 2000 and im.size[1] >= 1500
        colours = im.convert("RGB").getcolors(maxcolors=200000)
    assert colours and len(colours) > 20


@pytest.mark.slow
def test_stick_clip_renders_with_the_puppet_pipeline(tmp_path, ffmpeg_available):
    scene = {"aspect": "9:16", "width": 270, "height": 480, "background": "corridor",
             "actors": [{"spec": HERO, "x": 0.3, "motions": [{"motion": "run", "start": 0.0, "end": 1.0}], "height": 0.5}]}
    out = tmp_path / "clip.mp4"
    res = compose.render_clip(scene, out, tmp_path / "w", 1.0, fps=10)
    assert out.exists() and res["frames"] == 10
