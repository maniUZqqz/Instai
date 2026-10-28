"""2D puppet engine: maths, rig, motion library, lip-sync (amplitude + Rhubarb wrapper), cut-out, rig builder, renderer, API and a
puppet shot rendered through the real episode pipeline."""
from __future__ import annotations

import base64
import io
import json
import math
import os
import stat
import struct
import sys
import wave
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from instai.render.puppet import builder, cutout, demo, geometry as g, lipsync, motions, renderer
from instai.render.puppet.rig import MOUTH_FALLBACK, Rig, RigError

from tests.conftest import finish


# ------------------------------------------------------------------ geometry / easing

def test_matrix_maths_roundtrip():
    m = g.mul(g.translate(10, 20), g.mul(g.rotate(30), g.scale(2, 3)))
    x, y = g.apply(m, 5, 7)
    ix, iy = g.apply(g.invert(m), x, y)
    assert (round(ix, 6), round(iy, 6)) == (5, 7)
    # clockwise on screen: a vector pointing down swings to the LEFT for a positive angle
    x, y = g.apply(g.rotate(90), 0, 1)
    assert round(x, 6) == -1 and round(y, 6) == 0
    # PIL wants the inverse mapping (output -> input)
    a, b, c, d, e, f = g.pil_inverse(g.translate(5, 0))
    assert (a, b, c, d, e, f) == (1, 0, -5, 0, 1, 0)


def test_track_value_easing_and_clamping():
    keys = [(0, 0), (1, 10, "linear"), (2, 10, "linear"), (3, 0, "inout")]
    assert g.track_value(keys, -1) == 0 and g.track_value(keys, 9) == 0
    assert g.track_value(keys, 0.5) == pytest.approx(5)
    assert g.track_value(keys, 1.5) == pytest.approx(10)
    assert 0 < g.track_value(keys, 2.5) < 10
    assert g.track_value([(0, 0), (1, 100, "hold")], 0.99) == 0          # hold keeps the previous value until the key
    assert g.ease("back", 0.8) > 1.0                                      # overshoot


# ------------------------------------------------------------------ rig

@pytest.fixture(scope="module")
def media(tmp_path_factory):
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="module")
def demo_spec(media):
    return demo.make_rig_spec("Sara", media / "rig", media)


def test_demo_rig_is_a_valid_complete_rig(demo_spec, media):
    rig = Rig.from_spec(demo_spec, media)
    assert rig.mouth_shapes() == sorted("ABCDEFGHX")
    info = builder.completeness(demo_spec)
    assert info["has_arms"] and info["has_legs"] and info["has_blink"] and not info["missing_mouth_shapes"]
    names = [p.name for p in rig.visible_parts("D", "closed")]
    assert "mouth_D" in names and "eyes_closed" in names and "eyes_open" not in names and "mouth_A" not in names
    assert [p.z for p in rig.visible_parts("X")] == sorted(p.z for p in rig.visible_parts("X"))


def test_rig_validation_and_mouth_fallback(media):
    with pytest.raises(RigError):
        Rig.from_spec({"parts": {}}, media)
    with pytest.raises(RigError, match="unknown parent"):
        Rig.from_spec({"parts": {"a": {"image": "", "parent": "zzz"}}}, media, load_sizes=False)
    with pytest.raises(RigError, match="loop"):
        Rig.from_spec({"parts": {"a": {"image": "", "parent": "b"}, "b": {"image": "", "parent": "a"}}}, media, load_sizes=False)
    with pytest.raises(RigError, match="not readable"):
        Rig.from_spec({"parts": {"a": {"image": "missing.png"}}}, media)
    # a rig that only draws A, C and X still has an answer for every Rhubarb shape
    spec = {"size": [100, 100], "parts": {f"mouth_{s}": {"image": "", "group": "mouth", "state": s, "parent": None} for s in "ACX"}}
    rig = Rig.from_spec(spec, media, load_sizes=False)
    assert {s: rig.choose_state("mouth", s) for s in "ABCDEFGHX"} == {"A": "A", "B": "A", "C": "C", "D": "C", "E": "C", "F": "C", "G": "A", "H": "C", "X": "X"}
    assert all(k in "ABCDEFGHX" for k in MOUTH_FALLBACK)


def test_world_matrix_follows_parent_and_pivot(demo_spec, media):
    rig = Rig.from_spec(demo_spec, media)
    base = g.translate(0, 0)
    rest = rig.world_matrices(base, {})
    posed = rig.world_matrices(base, {"body": (0, 0, 0, 1, 1), "arm_r": (0, 0, -90, 1, 1)})
    hand_rest = g.apply(rest["arm_r"], 30, 215)       # a point near the hand, in the arm image
    hand_up = g.apply(posed["arm_r"], 30, 215)
    shoulder_rest, shoulder_up = g.apply(rest["arm_r"], 30, 24), g.apply(posed["arm_r"], 30, 24)
    assert shoulder_rest == pytest.approx(shoulder_up)                      # the joint stays put
    assert hand_up[0] > hand_rest[0] + 100                                  # the hand swings outward to the viewer's right
    moved = rig.world_matrices(base, {"body": (0, -50, 0, 1, 1)})
    assert g.apply(moved["head"], 0, 0)[1] == pytest.approx(g.apply(rest["head"], 0, 0)[1] - 50)   # the head follows the body


# ------------------------------------------------------------------ motions

def test_motion_library_is_complete_and_loops():
    for name in ("idle", "talk", "walk", "wave", "point", "react", "jump", "sit", "nod", "shake"):
        assert name in motions.MOTIONS
    a, b = motions.evaluate("walk", 0.0), motions.evaluate("walk", 0.8)
    assert a["leg_l"]["rot"] == pytest.approx(b["leg_l"]["rot"])           # a walk cycle closes on itself
    mid = motions.evaluate("walk", 0.4)
    assert mid["leg_l"]["rot"] == pytest.approx(-a["leg_l"]["rot"]) and mid["leg_r"]["rot"] == pytest.approx(-a["leg_r"]["rot"])
    top = motions.evaluate("jump", 0.4)["body"]["dy"]
    assert top < -100 and motions.evaluate("jump", 0.9)["body"]["dy"] == pytest.approx(0)
    assert motions.evaluate("wave", 0.7)["arm_r"]["rot"] < -140


def test_timeline_layers_add_and_blend():
    tl = motions.Timeline.from_spec(4.0, motions.talk_timeline(4.0, [(0.5, 3.0)], base="walk", gestures=[("wave", 0.2)]))
    solo = motions.Timeline.from_spec(4.0, [{"layer": "base", "clips": [{"motion": "walk", "start": 0, "end": 4, "blend": 0}]}])
    t = 1.3
    assert tl.pose(t)["arm_r"][2] != solo.pose(t)["arm_r"][2]             # the overlay changes the arm
    assert tl.pose(t)["leg_l"][2] == pytest.approx(solo.pose(t)["leg_l"][2])  # but not the legs
    assert tl.root_x(2.0) == pytest.approx(2.0 * 190.0) and tl.root_x(9) == pytest.approx(4.0 * 190.0)
    empty = motions.Timeline.from_spec(2.0, None)
    assert empty.layers["base"][0].motion == "idle"                        # nothing planned -> alive
    assert motions.Timeline.from_spec(2.0, [{"layer": "base", "clips": [{"motion": "no_such", "start": 0, "end": 1}]}]).layers["base"][0].motion == "idle"
    clip = motions.Clip("wave", 1.0, 2.0, blend=0.4)
    assert clip.weight(0.9) == 0 and clip.weight(1.0) == 0 and clip.weight(1.5) == 1 and 0 < clip.weight(1.1) < 1


def test_blinks_are_deterministic_and_short():
    a, b = motions.blink_times(20, 3), motions.blink_times(20, 3)
    assert a == b and a != motions.blink_times(20, 4) and len(a) >= 3
    assert motions.is_blinking(a, a[0] + 0.05) and not motions.is_blinking(a, a[0] + 0.5)


# ------------------------------------------------------------------ lip-sync

def speech_like_wav(path, pattern=((0.0, 0.5, 0.0), (0.5, 1.5, 0.5), (1.5, 2.0, 0.0), (2.0, 3.0, 0.9)), rate=16000):
    """Silence, a quiet vowel, silence, a loud vowel."""
    total = max(e for _, e, _ in pattern)
    frames = bytearray()
    for i in range(int(total * rate)):
        t = i / rate
        amp = next((a for s, e, a in pattern if s <= t < e), 0.0)
        frames += struct.pack("<h", int(amp * 30000 * math.sin(2 * math.pi * 180 * t) * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * t))))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


def test_amplitude_mouth_follows_loudness(tmp_path):
    wav = speech_like_wav(tmp_path / "s.wav")
    cues = lipsync.amplitude_cues(wav)
    assert abs(cues[-1][1] - 3.0) < 0.05
    assert lipsync.shape_at(cues, 0.2) == "X" and lipsync.shape_at(cues, 1.75) == "X"          # silence = closed mouth at rest
    assert lipsync.shape_at(cues, 2.5) in ("D", "E", "C")                                       # loud = wide
    wide = sum(e - s for s, e, v in cues if v == "D" and s >= 2.0)
    quiet = sum(e - s for s, e, v in cues if v == "D" and s < 1.5)
    assert wide > quiet                                                                         # the loud part opens wider than the quiet part
    assert all(v in lipsync.SHAPES for _, _, v in cues)
    assert all(cues[i][1] <= cues[i + 1][0] + 1e-6 for i in range(len(cues) - 1))              # cues do not overlap
    assert lipsync.shape_at(cues, 99) == "X" and lipsync.shape_at([], 1) == "X"


def fake_rhubarb(tmp_path: Path, cues: list, fail: bool = False) -> str:
    """A stand-in `rhubarb` executable that follows its command line: -o <json file>, last argument = audio."""
    script = tmp_path / "fake_rhubarb.py"
    script.write_text(
        "import sys, json\n"
        "a = sys.argv[1:]\n"
        f"if {fail!r}:\n    sys.stderr.write('boom'); sys.exit(3)\n"
        "out = a[a.index('-o') + 1]\n"
        "rec = a[a.index('-r') + 1]\n"
        f"json.dump({{'metadata': {{'recogniser': rec}}, 'mouthCues': {json.dumps(cues)}}}, open(out, 'w'))\n"
        "open(out + '.args', 'w').write(' '.join(a))\n", encoding="utf-8")
    if os.name == "nt":
        exe = tmp_path / "rhubarb.cmd"
        exe.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        exe = tmp_path / "rhubarb"
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(exe)


def test_rhubarb_wrapper_languages_and_fallback(tmp_path, monkeypatch):
    wav = speech_like_wav(tmp_path / "s.wav")
    cues = [{"start": 0.0, "end": 0.4, "value": "X"}, {"start": 0.4, "end": 0.7, "value": "D"}, {"start": 0.7, "end": 1.0, "value": "B"}]
    monkeypatch.setenv("INSTAI_RHUBARB_EXE", fake_rhubarb(tmp_path, cues))
    fa = lipsync.visemes(wav, language="fa", text="سلام")
    assert fa["engine"] == "rhubarb" and fa["note"] == "recogniser=phonetic" and fa["cues"][1] == (0.4, 0.7, "D")
    en = lipsync.visemes(wav, language="en", text="hello world")
    assert en["note"] == "recogniser=pocketSphinx"
    # Rhubarb breaks -> the amplitude mouth takes over, with a note
    monkeypatch.setenv("INSTAI_RHUBARB_EXE", fake_rhubarb(tmp_path, [], fail=True))
    r = lipsync.visemes(wav, language="fa")
    assert r["engine"] == "amplitude" and "Rhubarb failed" in r["note"]
    with pytest.raises(RuntimeError):
        lipsync.visemes(wav, engine="rhubarb")
    monkeypatch.setenv("INSTAI_RHUBARB_EXE", str(tmp_path / "nothing-here.exe"))
    monkeypatch.setattr("instai.core.runtime.find_tool", lambda name: None)
    assert lipsync.visemes(wav)["engine"] == "amplitude"


# ------------------------------------------------------------------ cut-out and rig builder

def part_on_white(size=(160, 120), box=(30, 20, 130, 100), color=(200, 60, 60)):
    im = Image.new("RGB", size, (255, 255, 255))
    ImageDraw.Draw(im).ellipse(box, fill=color)
    return im


def test_cutout_removes_background_and_trims():
    part = cutout.cut_part(part_on_white(), method="flood")
    assert part.mode == "RGBA" and part.size[0] < 160 and part.size[1] < 120
    assert part.getpixel((part.width // 2, part.height // 2))[3] == 255          # inside stays opaque
    assert part.getpixel((0, 0))[3] == 0                                         # the white corner is gone


def test_birefnet_wrapper_uses_the_model_mask():
    np = pytest.importorskip("numpy")

    class FakeSession:
        def get_inputs(self):
            return [type("I", (), {"name": "x"})()]

        def run(self, _out, feed):
            assert feed["x"].shape == (1, 3, 1024, 1024) and feed["x"].dtype == np.float32
            m = np.full((1, 1, 1024, 1024), -9.0, dtype=np.float32)
            m[:, :, 256:768, 256:768] = 9.0
            return [m]

    out = cutout.birefnet_alpha(Image.new("RGB", (200, 100), (10, 200, 10)), FakeSession())
    assert out.size == (200, 100) and out.getpixel((100, 50))[3] > 250 and out.getpixel((2, 2))[3] < 5


def full_canvas_layers():
    W, H = 400, 600
    layers = {}

    def layer(name, box, color):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle(box, fill=color)
        layers[name] = im
    layer("Body", (150, 250, 250, 450), (60, 120, 200, 255))
    layer("Head", (160, 120, 240, 240), (240, 200, 160, 255))
    layer("arm_L", (110, 260, 145, 400), (60, 120, 200, 255))
    layer("arm_R", (255, 260, 290, 400), (60, 120, 200, 255))
    layer("Leg L", (155, 450, 195, 580), (50, 50, 90, 255))
    layer("Leg R", (205, 450, 245, 580), (50, 50, 90, 255))
    layer("Eyes Open", (170, 160, 230, 175), (20, 20, 20, 255))
    layer("Eyes Closed", (170, 165, 230, 168), (20, 20, 20, 255))
    for s in "ACX":
        layer(f"Mouth {s}", (185, 205, 215, 205 + {"A": 3, "C": 14, "X": 5}[s]), (140, 30, 40, 255))
    return layers


def test_builder_reads_positions_from_a_full_canvas_export(tmp_path):
    media = tmp_path
    spec = builder.rig_from_layers(full_canvas_layers(), media / "rig", media)
    parts = spec["parts"]
    assert set(parts) >= {"body", "head", "arm_l", "arm_r", "leg_l", "leg_r", "eyes_open", "eyes_closed", "mouth_A", "mouth_C", "mouth_X"}
    assert parts["head"]["parent"] == "body" and parts["mouth_C"]["parent"] == "head" and parts["leg_l"]["parent"] is None
    assert parts["mouth_C"]["group"] == "mouth" and parts["eyes_closed"]["state"] == "closed"
    # the head joint (its bottom centre) lands where it was in the canvas: 200, ~240 -> relative to the body's top-left (150, 250)
    head_joint_canvas = (160 - 2 + parts["head"]["pivot"][0], 120 - 2 + parts["head"]["pivot"][1])
    body_tl = (150 - 2, 250 - 2)
    assert parts["head"]["pos"] == [round(head_joint_canvas[0] - body_tl[0], 1), round(head_joint_canvas[1] - body_tl[1], 1)]
    rig = Rig.from_spec(spec, media)
    # at rest the rebuilt character looks like the exported layout: render and compare a pixel inside the head
    scene = {"width": 200, "height": 300, "fps": 5, "duration": 0.4, "color": "#ffffff", "actors": [
        {"rig": json.loads(json.dumps(spec)), "x": 0.5, "y": 0.97, "height": 0.97, "blink": False, "shadow": False,
         "timeline": [{"layer": "base", "clips": [{"motion": "sit", "start": 5, "end": 6}]}]}]}
    for p in scene["actors"][0]["rig"]["parts"].values():
        p["image"] = str(media / p["image"])
    px = renderer.PuppetRenderer(scene, media).frame(0.0).convert("RGB")
    assert rig.anchor[1] > 500
    body_px = px.getpixel((100, 175))
    assert body_px[2] > body_px[0] + 60                    # blue torso in the middle of the canvas


def test_builder_zip_psd_and_errors(tmp_path):
    layers = full_canvas_layers()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, im in layers.items():
            b = io.BytesIO()
            im.save(b, "PNG")
            z.writestr(f"layers/{name}.png", b.getvalue())
        z.writestr("__MACOSX/._junk.png", b"x")
    got, extra = builder.layers_from_zip(buf.getvalue())
    assert "Body" in got and extra == {}
    with pytest.raises(RigError):
        builder.layers_from_zip(b"not a zip")
    # differently sized layers need positions
    odd = {"body": Image.new("RGBA", (50, 80), (1, 2, 3, 255)), "head": Image.new("RGBA", (40, 40), (9, 9, 9, 255))}
    with pytest.raises(RigError, match="rig.json"):
        builder.rig_from_layers(odd, tmp_path / "r", tmp_path)
    spec = builder.rig_from_layers(odd, tmp_path / "r2", tmp_path, extra={"size": [200, 300], "parts": {"body": {"pos": [100, 250]}, "head": {"pos": [25, 5]}}})
    assert spec["parts"]["head"]["pos"] == [25, 5] and spec["parts"]["body"]["pos"] == [100, 250]
    try:
        import psd_tools  # noqa: F401
    except ImportError:
        with pytest.raises(RigError, match="psd-tools"):
            builder.layers_from_psd(b"8BPS")
    assert builder.classify("Mouth A") == ("mouth_A", "mouth", "A") and builder.classify("eyes-blink")[2] == "closed"
    assert builder.classify("Arm Left")[0] == "arm_l"


# ------------------------------------------------------------------ renderer

def scene_for(demo_spec, media, **kw):
    spec = json.loads(json.dumps(demo_spec))
    for p in spec["parts"].values():
        p["image"] = str(media / p["image"])
    layers = demo.make_background(media / "bg", 360, 640)
    base = {"width": 180, "height": 320, "fps": 10, "duration": 1.0, "background": {"layers": layers}, "camera": [],
            "actors": [{"rig": spec, "x": 0.5, "y": 0.94, "height": 0.6, "seed": 1, "blink": False,
                        "timeline": [{"layer": "base", "clips": [{"motion": "idle", "start": 0, "end": 1}]}], "mouth": []}]}
    base.update(kw)
    return base


def test_frames_are_deterministic_and_react_to_mouth_and_camera(demo_spec, media):
    a = renderer.PuppetRenderer(scene_for(demo_spec, media), media).frame(0.3)
    b = renderer.PuppetRenderer(scene_for(demo_spec, media), media).frame(0.3)
    assert a.tobytes() == b.tobytes()
    assert a.size == (180, 320)
    talking = scene_for(demo_spec, media)
    talking["actors"][0]["mouth"] = [[0.0, 1.0, "D"]]
    assert renderer.PuppetRenderer(talking, media).frame(0.3).tobytes() != a.tobytes()
    # parallax: the camera pans, the sky barely moves, the hills move more, the foreground most
    cam = renderer.camera_from_move("pan_right", 1.0, 1.0)
    panned = renderer.PuppetRenderer(scene_for(demo_spec, media, camera=cam), media)
    r0, r1 = panned.frame(0.0).convert("RGB"), panned.frame(1.0).convert("RGB")

    def band_shift(y0, y1):
        import itertools

        best = (1e18, 0)
        for dx in range(-30, 31):
            err = 0
            for y, x in itertools.product(range(y0, y1, 4), range(40, 140, 4)):
                p, q = r0.getpixel((x, y)), r1.getpixel((x + dx, y))
                err += sum(abs(p[i] - q[i]) for i in range(3))
            best = min(best, (err, dx))
        return abs(best[1])
    assert band_shift(285, 315) >= band_shift(30, 60), "the foreground band moves at least as much as the sky"


def test_render_to_video_frame_count_and_cancel(demo_spec, media, ffmpeg_available):
    from instai.render import ffmpeg

    out = media / "out" / "clip.mp4"
    sc = scene_for(demo_spec, media, duration=1.2)
    sc["actors"][0]["mouth"] = [[0.1, 0.5, "C"], [0.5, 1.0, "D"]]
    info = renderer.PuppetRenderer(sc, media).render(out, crf=30, preset="ultrafast")
    p = ffmpeg.probe(out)
    assert info["frames"] == 12 and (p["width"], p["height"]) == (180, 320) and p["fps"] == 10 and p["vcodec"] == "h264" and abs(p["duration"] - 1.2) < 0.15

    class Ctx:
        n = 0

        def check(self):
            self.n += 1
            if self.n > 1:
                raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        renderer.PuppetRenderer(scene_for(demo_spec, media, duration=3.0), media).render(media / "out" / "x.mp4", ctx=Ctx())


def test_a_rig_without_legs_or_extra_mouths_still_renders(demo_spec, media):
    spec = json.loads(json.dumps(demo_spec))
    for n in ("leg_l", "leg_r", "mouth_E", "mouth_F", "mouth_G", "mouth_H", "arm_l"):
        spec["parts"].pop(n)
    sc = scene_for(spec, media)
    sc["actors"][0]["rig"] = {**spec, "parts": {n: {**p, "image": str(media / p["image"]) if not os.path.isabs(p["image"]) else p["image"]} for n, p in spec["parts"].items()}}
    sc["actors"][0]["timeline"] = motions.talk_timeline(1.0, [(0.1, 0.9)], base="walk", gestures=[("wave", 0.1)])     # motions name parts it lacks
    sc["actors"][0]["mouth"] = [[0.0, 1.0, "E"]]
    assert renderer.PuppetRenderer(sc, media).frame(0.5).size == (180, 320)


# ------------------------------------------------------------------ API + pipeline

pytestmark_db = pytest.mark.django_db(transaction=True)


@pytestmark_db
def test_rig_api_demo_zip_edit_approve_preview(api, worker, ffmpeg_available):
    from tests.test_voices import mk_character

    page, ch = mk_character(api)
    r = api.post(f"/api/characters/{ch['id']}/rigs", {"source": "demo"}, format="json")
    assert r.status_code == 201, r.content
    rig = r.json()
    assert rig["version"] == 1 and rig["completeness"]["ok"] and rig["parts"]["head"]["url"].startswith("/media/characters/")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, im in full_canvas_layers().items():
            b = io.BytesIO()
            im.save(b, "PNG")
            z.writestr(f"{name}.png", b.getvalue())
    r2 = api.post(f"/api/characters/{ch['id']}/rigs", {"source": "upload", "zip_base64": base64.b64encode(buf.getvalue()).decode(), "name": "from zip"}, format="json")
    assert r2.status_code == 201 and r2.json()["version"] == 2 and r2.json()["source"] == "upload"
    assert api.post(f"/api/characters/{ch['id']}/rigs", {"source": "upload", "zip_base64": base64.b64encode(b"x" * 500).decode()}, format="json").status_code == 400
    assert api.post(f"/api/characters/{ch['id']}/rigs", {"source": "nope"}, format="json").status_code == 400
    # edit a pivot, approve (only one approved rig per character)
    ed = api.patch(f"/api/rigs/{rig['id']}", {"parts": {"arm_r": {"pivot": [31, 25], "z": 31}}, "approved": True}, format="json").json()
    assert ed["parts"]["arm_r"]["pivot"] == [31.0, 25.0] and ed["parts"]["arm_r"]["z"] == 31 and ed["approved"]
    api.patch(f"/api/rigs/{r2.json()['id']}", {"approved": True}, format="json")
    assert [x["approved"] for x in api.get(f"/api/characters/{ch['id']}/rigs").json()] == [True, False]
    assert api.patch(f"/api/rigs/{rig['id']}", {"parts": {"arm_r": {"parent": "ghost"}}}, format="json").status_code == 400
    j = finish(api, worker, api.post(f"/api/rigs/{rig['id']}/preview", {"motion": "wave"}, format="json"))
    from instai.assets.models import Asset
    from instai.assets.storage import storage
    from instai.render import ffmpeg

    a = Asset.objects.get(pk=j["result"]["asset_id"])
    info = ffmpeg.probe(storage.path_for(a.path))
    assert (info["width"], info["height"]) == (270, 480) and info["duration"] > 3
    assert any(m["name"] == "walk" for m in api.get("/api/puppet/motions").json())


@pytestmark_db
@pytest.mark.slow
def test_puppet_shots_render_through_the_episode_pipeline(api, worker, ffmpeg_available):
    from instai.assets.models import Asset
    from instai.production.models import ShotRender
    from tests.test_pipeline_e2e import build_episode, produce
    from tests.test_voices import wav_bytes  # noqa: F401

    page, sid, ep_id = build_episode(api, worker, fmt="recurring_character")
    ch = api.post(f"/api/pages/{page['id']}/characters", {"name": "نیما", "role": "main"}, format="json").json()
    rig = api.post(f"/api/characters/{ch['id']}/rigs", {"source": "demo"}, format="json").json()
    ep = api.get(f"/api/episodes/{ep_id}").json()
    shots = [sh for sc in ep["scenes"] for sh in sc["shots"]]
    assert len(shots) >= 3
    for sh in shots[:2]:
        assert api.patch(f"/api/shots/{sh['id']}", {"technique": "puppet_2d", "speaker": "نیما", "description": "he waves hello"}, format="json").status_code == 200
    # no approved rig yet: the draft rig is used and QC/job notes say so
    ep = produce(api, worker, ep_id, "preview")
    assert ep["state"] == "ready_for_approval", ep["qc"]
    renders = list(ShotRender.objects.filter(shot__scene__episode_id=ep_id, technique="puppet_2d"))
    n_puppet = len([sh for sc in api.get(f"/api/episodes/{ep_id}").json()["scenes"] for sh in sc["shots"] if sh["technique"] == "puppet_2d"])
    assert n_puppet >= 2 and len(renders) == n_puppet and all(r.status == "done" and r.seconds is not None and r.params["lipsync"] == "amplitude" for r in renders)
    video = next(v for v in ep["videos"] if v["role"] == "preview")
    assert video["duration_sec"] > 3
    notes = Asset.objects.get(pk=video["id"]).provenance["notes"]
    assert any("not approved" in n for n in notes)
    # a puppet shot has a background plate keyframe (no characters) and a cached clip that the next render reuses
    kf = Asset.objects.filter(shot_id=shots[0]["id"], role="keyframe", is_current=True).get()
    assert kf.provenance["engine"] == "placeholder"
    api.patch(f"/api/rigs/{rig['id']}", {"approved": True}, format="json")
    before = Asset.objects.filter(role="render_clip", episode_id=ep_id).count()
    api.post(f"/api/episodes/{ep_id}/produce", {"mode": "preview"}, format="json")
    ep2 = produce(api, worker, ep_id, "preview")
    assert Asset.objects.filter(role="render_clip", episode_id=ep_id).count() == before, "same rig, same audio: clips are reused"
    assert ep2["state"] == "ready_for_approval"
