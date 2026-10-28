"""Post-production: time-range video retakes (exact A/V sync, audio keep/mute/replace/cut, seams, revert), music / ambience / SFX mix with
ducking, and a draft rig made from a character sheet."""
from __future__ import annotations

import re
import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from tests import fakes
from tests.conftest import finish
from tests.test_hero import VideoComfy, comfy_local, prepared_episode, run_final  # noqa: F401  (fixtures)

pytestmark = pytest.mark.django_db(transaction=True)
FPS, W, H, SECONDS = 15, 120, 216, 6


def ff():
    from instai.core import runtime

    return runtime.ffmpeg_info()["ffmpeg"]


def make_source(path: Path, seconds=SECONDS, tone=600, amp=0.4) -> Path:
    subprocess.run([ff(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r={FPS}", "-f", "lavfi", "-i", f"sine=f={tone}:r=48000",
                    "-af", f"volume={amp}", "-t", str(seconds), "-ac", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(path)], check=True)
    return path


def frame_at(video: Path, t: float) -> Image.Image:
    out = video.parent / f"f_{video.stem}_{int(t * 100)}.png"
    subprocess.run([ff(), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return Image.open(out).convert("RGB")


def diff(a: Image.Image, b: Image.Image) -> float:
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def audio_rms_db(path: Path, t0: float, t1: float, pre: str = "") -> float:
    p = subprocess.run([ff(), "-hide_banner", "-nostats", "-ss", f"{t0}", "-t", f"{t1 - t0}", "-i", str(path), "-vn", "-af", (pre + "," if pre else "") + "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", p.stderr)
    return float(m.group(1)) if m else -99.0


def stream_durations(path: Path) -> tuple[float, float]:
    """(video seconds = decoded frames / fps, audio seconds = decoded samples) - measured by decoding, not by trusting the container."""
    p = subprocess.run([ff(), "-hide_banner", "-nostats", "-i", str(path), "-map", "0:v", "-f", "null", "-"], capture_output=True, text=True)
    frames = int(re.findall(r"frame=\s*(\d+)", p.stderr)[-1]) if re.findall(r"frame=\s*(\d+)", p.stderr) else 0
    p2 = subprocess.run([ff(), "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a", "-f", "null", "-"], capture_output=True, text=True)
    a = re.findall(r"time=(\d+):(\d+):([\d.]+)", p2.stderr)
    return frames / FPS, int(a[-1][0]) * 3600 + int(a[-1][1]) * 60 + float(a[-1][2])


# ------------------------------------------------------------------ retake: planning and video maths

def test_plan_range_is_exact_on_the_frame_grid_and_validates(tmp_path, ffmpeg_available):
    from instai.render import ffmpeg
    from instai.render import retake as rk

    src = make_source(tmp_path / "src.mp4")
    info = ffmpeg.probe(src)
    p = rk.plan_range(info, 2.0, 3.0)
    assert (p.fps, p.total_frames, p.start, p.end, p.n, p.before, p.after) == (15.0, 90, 30, 45, 15, 29, 45)
    assert p.t_start == 2.0 and p.t_end == 3.0
    with pytest.raises(rk.RetakeError, match="after"):
        rk.plan_range(info, 3.0, 2.0)
    with pytest.raises(rk.RetakeError, match="at least"):
        rk.plan_range(info, 2.0, 2.2)
    rk.MAX_SECONDS, saved = 3.0, rk.MAX_SECONDS
    try:
        with pytest.raises(rk.RetakeError, match="at most"):
            rk.plan_range(info, 0.5, 5.0)
    finally:
        rk.MAX_SECONDS = saved
    with pytest.raises(rk.RetakeError, match="outside"):
        rk.plan_range(info, 7.0, 8.0)
    assert rk.plan_range(info, 1.0, 5.5, cut=True).n == 67                      # a cut may be longer than a generated piece


def run_stitch(tmp_path, mode, audio_file=None, hue=90):
    """Fake piece (testsrc with shifted hue) + stitch + verify, no database."""
    from instai.render import colormatch, ffmpeg
    from instai.render import retake as rk

    src = make_source(tmp_path / "src.mp4")
    info = ffmpeg.probe(src)
    plan = rk.plan_range(info, 2.0, 3.0, cut=mode == "cut")
    piece = None
    if mode != "cut":
        raw = tmp_path / "raw.mp4"
        raw.write_bytes(fakes.make_test_video(96, 160, 25, 16, color_shift=hue))       # what a Wan 'first/last frame' call returns (16 fps, other size)
        piece = rk.fit_piece(raw, plan, src, tmp_path / "fitted.mp4", edge=1)
    out = tmp_path / "out.mp4"
    rk.stitch(src, piece, plan, out, audio_mode=mode, audio_file=audio_file)
    return src, out, plan, info, rk.verify(info, out, plan, mode)


def test_stitch_keep_replaces_only_the_range_and_keeps_sync(tmp_path, ffmpeg_available):
    src, out, plan, info, ver = run_stitch(tmp_path, "keep")
    assert ver["ok"] and ver["duration_error"] == pytest.approx(0, abs=0.07) and ver["frames"] == ver["expected_frames"] == 90 and ver["size"] == f"{W}x{H}"
    for t in (0.5, 1.5, 4.0, 5.5):                                   # outside the range: the same picture (one re-encode: tiny difference)
        assert diff(frame_at(src, t), frame_at(out, t)) < 4, t
    assert diff(frame_at(src, 2.5), frame_at(out, 2.5)) > 12         # inside: new footage
    vd, ad = stream_durations(out)
    assert abs(vd - ad) < 0.08 and abs(vd - 6.0) < 0.08              # A/V lengths match the source
    assert audio_rms_db(out, 2.0, 3.0) == pytest.approx(audio_rms_db(src, 2.0, 3.0), abs=0.6)     # audio untouched


def test_stitch_mute_and_replace_and_cut(tmp_path, ffmpeg_available):
    src, out, plan, info, ver = run_stitch(tmp_path, "mute")
    assert ver["ok"] and audio_rms_db(out, 2.1, 2.9) < -50 and audio_rms_db(out, 0.5, 1.5) > -40 and audio_rms_db(out, 4.0, 5.0) > -40
    loud = tmp_path / "new.wav"
    subprocess.run([ff(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=330:r=48000", "-af", "volume=4.0", "-t", "2", str(loud)], check=True)
    sub = tmp_path / "rep"
    sub.mkdir()
    src2, out2, _, _, ver2 = run_stitch(sub, "replace", audio_file=loud)
    assert ver2["ok"] and audio_rms_db(out2, 2.1, 2.9) > audio_rms_db(src2, 2.1, 2.9) + 6      # the replacement is louder than the muted original
    assert audio_rms_db(out2, 0.5, 1.5) == pytest.approx(audio_rms_db(src2, 0.5, 1.5), abs=1.5)
    sub2 = tmp_path / "cut"
    sub2.mkdir()
    src3, out3, plan3, info3, ver3 = run_stitch(sub2, "cut")
    assert ver3["ok"] and ver3["duration"] == pytest.approx(5.0, abs=0.08) and ver3["frames"] == 75
    vd, ad = stream_durations(out3)
    assert abs(vd - ad) < 0.08                                       # a cut removes the same time from video and audio
    assert diff(frame_at(src3, 4.0), frame_at(out3, 3.0)) < 4        # what followed the cut now starts where the range was


def test_seam_ratio_flags_a_pop_and_accepts_smooth_motion(tmp_path, ffmpeg_available):
    from instai.render import retake as rk

    smooth = tmp_path / "smooth.mp4"
    subprocess.run([ff(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r={FPS}", "-t", "4", "-pix_fmt", "yuv420p", str(smooth)], check=True)
    pop = tmp_path / "pop.mp4"       # a hard cut to a different picture at 2.0 s
    subprocess.run([ff(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r={FPS}", "-f", "lavfi", "-i", f"color=c=red:s={W}x{H}:r={FPS}",
                    "-filter_complex", "[0:v]trim=0:2,setpts=PTS-STARTPTS[a];[1:v]trim=0:2,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(pop)], check=True)
    assert rk.seam_ratio(smooth, 30) < 3 and rk.seam_ratio(pop, 30) > 5


def test_filter_graph_of_the_mix_tracks():
    from instai.render import assemble as asm

    tracks = [{"file": "m.wav", "kind": "music", "start": 0.0, "end": 12.0, "gain_db": -22, "duck": True, "fade_in": 1.0, "fade_out": 2.0, "loop": True},
              {"file": "s.wav", "kind": "sfx", "start": 3.5, "end": 5.0, "gain_db": -10, "duck": False, "fade_in": 0.02, "fade_out": 0.1, "loop": False}]
    chains, duck, plain = asm.track_filters(tracks, 7, 12.0)
    assert duck == ["[tr0]"] and plain == ["[tr1]"]
    assert "[7:a]" in chains[0] and "aloop" in chains[0] and "afade=t=in" in chains[0] and "volume=-22.0dB" in chains[0] and "adelay=0|0" in chains[0]
    assert "[8:a]" in chains[1] and "aloop" not in chains[1] and "adelay=3500|3500" in chains[1] and "atrim=0:1.500" in chains[1]
    parts: list[str] = []
    label = asm.mix_with_tracks(parts, "[nar]", duck, plain)
    g = ";".join(parts)
    assert "sidechaincompress" in g and "asplit=2[vkey][vmix]" in g and label == "[mixed2]" and "[vmix][ducked][tr1]amix=inputs=3" in g
    only_plain = []
    assert asm.mix_with_tracks(only_plain, "[nar]", [], []) == "[nar]" and only_plain == []


def test_ducking_lowers_the_bed_under_dialogue(tmp_path, ffmpeg_available):
    """A constant 'music' tone next to a 2-second dialogue burst: through the real graph the tone is much quieter while someone speaks."""
    from instai.render import assemble as asm

    chains, duck, plain = asm.track_filters([{"file": "x", "start": 0.0, "end": 5.0, "gain_db": -6, "duck": True, "fade_in": 0, "fade_out": 0, "loop": False}], 1, 5.0)
    parts = ["[0:a]aformat=channel_layouts=stereo[nar]"] + chains
    mixed = asm.mix_with_tracks(parts, "[nar]", duck, plain)
    graph = ";".join(parts)
    voice = tmp_path / "voice.wav"          # speech-like loud burst 0.5-2.5 s, silence otherwise
    subprocess.run([ff(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=2500:r=48000:d=5", "-af", "volume='if(between(t,0.5,2.5),3.0,0.0)':eval=frame", str(voice)], check=True)
    bed = tmp_path / "bed.wav"
    subprocess.run([ff(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=220:r=48000:d=5", "-af", "volume=0.5", str(bed)], check=True)
    out = tmp_path / "ducked.wav"
    subprocess.run([ff(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(voice), "-i", str(bed), "-filter_complex", graph, "-map", mixed, str(out)], check=True)
    band = "lowpass=f=300,lowpass=f=300,lowpass=f=300"             # only the 220 Hz bed, not the 2.5 kHz dialogue
    during, after = audio_rms_db(out, 1.0, 2.2, band), audio_rms_db(out, 3.5, 4.8, band)
    assert after - during > 6, (during, after)


# ------------------------------------------------------------------ retake through the API on a real episode

def test_retake_api_end_to_end_with_revert(api, worker, ffmpeg_available, comfy_local):  # noqa: F811
    from instai.assets.models import Asset
    from instai.production.models import Retake
    from instai.render import ffmpeg
    from instai.assets.storage import storage

    page, ep_id, shots, _ = prepared_episode(api, worker, ["still_kenburns"] * 3, with_sheet=False)
    ep = run_final(api, worker, ep_id)
    final = Asset.objects.get(episode_id=ep_id, role="final", is_current=True)
    dur = final.duration_sec
    assert dur > 4
    assert api.post(f"/api/episodes/{ep_id}/video-retakes", {"start_sec": 0.0, "end_sec": 1.0}, format="json").status_code == 400          # may not touch the first frame
    assert api.post(f"/api/episodes/{ep_id}/video-retakes", {"start_sec": 1.0, "end_sec": 1.1}, format="json").status_code == 400
    assert api.post(f"/api/episodes/{ep_id}/video-retakes", {"start_sec": 1.0, "end_sec": 2.0, "audio_mode": "replace"}, format="json").status_code == 400   # needs an audio file
    r = api.post(f"/api/episodes/{ep_id}/video-retakes", {"start_sec": 1.2, "end_sec": 2.6, "prompt": "she looks up and smiles", "audio_mode": "mute"}, format="json")
    assert r.status_code == 202, r.content
    j = finish(api, worker, r)
    rt = Retake.objects.get(pk=r.json()["retake"]["id"])
    assert rt.status == "done" and rt.result_asset_id and rt.seam["verify"]["ok"] and "start" in rt.seam["seam"] and "end" in rt.seam["seam"]
    new = Asset.objects.get(pk=rt.result_asset_id)
    assert new.is_current and new.role == "final" and new.provenance["retake"] == rt.pk and new.provenance["audio_mode"] == "mute"
    assert not Asset.objects.get(pk=final.pk).is_current                                           # the old video stays as history
    info = ffmpeg.probe(storage.path_for(new.path))
    assert abs(info["duration"] - dur) < 0.12 and (info["width"], info["height"]) == (final.width, final.height) and info["has_audio"]
    # the FIRST/LAST frame graph of Wan was used with the boundary frames of the range
    flf = [g for g in comfy_local.prompts if any(n["class_type"] == "WanFirstLastFrameToVideo" for n in g.values())]
    assert flf and flf[-1]["12"]["inputs"]["end_image"] == ["18", 0]
    assert api.get(f"/api/episodes/{ep_id}").json()["qc"]["retake"] == rt.pk                       # technical QC re-ran on the new video
    assert api.post(f"/api/video-retakes/{rt.pk}/revert", {}, format="json").json()["status"] == "done"
    assert Asset.objects.get(pk=final.pk).is_current and not Asset.objects.get(pk=new.pk).is_current
    # a cut needs no GPU at all and shortens the video exactly
    cut = api.post(f"/api/episodes/{ep_id}/video-retakes", {"start_sec": 1.0, "end_sec": 2.0, "audio_mode": "cut"}, format="json")
    finish(api, worker, cut)
    c = Retake.objects.get(pk=cut.json()["retake"]["id"])
    assert c.seam["verify"]["ok"] and abs(c.seam["verify"]["duration"] - (dur - 1.0)) < 0.12 and not c.seam.get("device")


# ------------------------------------------------------------------ mix: plan, generate (fake engines), assemble

def test_mix_plan_generate_and_assemble_with_ducking_and_hash(api, worker, ffmpeg_available):
    from instai.assets.models import Asset
    from instai.production import pipeline
    from instai.production.models import MixTrack
    from tests.test_pipeline_e2e import build_episode, produce

    page, sid, ep_id = build_episode(api, worker)
    api.put(f"/api/pages/{page['id']}/profiles/audio", {"music_enabled": True, "sfx_enabled": True, "music_mood": "epic", "music_volume_db": -20}, format="json")
    ep = api.get(f"/api/episodes/{ep_id}").json()
    first = ep["scenes"][0]["shots"][0]
    api.patch(f"/api/shots/{first['id']}", {"sfx": "heavy door slam"}, format="json")
    plan = api.post(f"/api/episodes/{ep_id}/mix/plan", {}, format="json").json()["tracks"]
    kinds = [t["kind"] for t in plan]
    assert "music" in kinds and "sfx" in kinds and all(t["status"] == "planned" for t in plan)
    music = next(t for t in plan if t["kind"] == "music")
    assert "epic" in music["prompt"] and music["duck"] is True and music["gain_db"] == -20
    sfx = next(t for t in plan if t["kind"] == "sfx")
    assert sfx["prompt"] == "heavy door slam" and sfx["duck"] is False and sfx["shot"] == first["id"]
    assert api.post(f"/api/episodes/{ep_id}/mix/plan", {}, format="json").json()["tracks"] == plan or len(api.get(f"/api/episodes/{ep_id}/mix").json()["tracks"]) == len(plan)   # never duplicated
    finish(api, worker, api.post(f"/api/episodes/{ep_id}/mix/generate", {}, format="json"))
    tracks = api.get(f"/api/episodes/{ep_id}/mix").json()["tracks"]
    assert all(t["status"] == "ready" and t["asset"]["duration_sec"] > 0.5 for t in tracks)
    assert Asset.objects.filter(episode_id=ep_id, role="music").exists() and Asset.objects.filter(episode_id=ep_id, role="sfx").exists()
    assert api.post(f"/api/episodes/{ep_id}/mix/generate", {}, format="json").status_code == 409          # everything is ready
    ep = produce(api, worker, ep_id, "preview")
    assert ep["state"] == "ready_for_approval", ep["qc"]
    video = next(v for v in ep["videos"] if v["role"] == "preview")
    from instai.assets.storage import storage
    from instai.render import ffmpeg

    info = ffmpeg.probe(storage.path_for(Asset.objects.get(pk=video["id"]).path))
    assert info["has_audio"] and abs(info["duration"] - video["duration_sec"]) < 0.2 and abs(video["loudness_lufs"] + 16) <= 4
    # editing a track's gain re-assembles (the mix is part of the timeline hash); a new prompt needs new audio
    h1 = pipeline.timeline_hash(__import__("instai.story.models", fromlist=["Episode"]).Episode.objects.get(pk=ep_id), "preview")
    t = MixTrack.objects.get(pk=music["id"])
    assert api.patch(f"/api/mix-tracks/{t.pk}", {"gain_db": -30}, format="json").json()["gain_db"] == -30
    h2 = pipeline.timeline_hash(__import__("instai.story.models", fromlist=["Episode"]).Episode.objects.get(pk=ep_id), "preview")
    assert h1 != h2
    p = api.patch(f"/api/mix-tracks/{t.pk}", {"prompt": "something else"}, format="json").json()
    assert p["status"] == "planned" and p["asset"] is None
    assert api.delete(f"/api/mix-tracks/{t.pk}").status_code == 204


def test_dialogue_uses_one_voice_per_character(api, worker, ffmpeg_available):
    """Two characters speak in different shots: each shot's narration asset records the voice (engine/voice) of ITS speaker."""
    from instai.assets.models import Asset
    from instai.pages.models import Character
    from tests.test_pipeline_e2e import build_episode, produce

    page, sid, ep_id = build_episode(api, worker)
    a = Character.objects.create(page_id=page["id"], name="الف")
    b = Character.objects.create(page_id=page["id"], name="ب")
    api.put(f"/api/characters/{a.pk}/voices/fa", {"engine": "fake", "voice_id": "voice-alef"}, format="json")
    api.put(f"/api/characters/{b.pk}/voices/fa", {"engine": "fake", "voice_id": "voice-be"}, format="json")
    ep = api.get(f"/api/episodes/{ep_id}").json()
    shots = [sh for sc in ep["scenes"] for sh in sc["shots"]]
    for sh, who in zip(shots[:2], ("الف", "ب")):
        api.patch(f"/api/shots/{sh['id']}", {"speaker": who, "narration": "این یک جملهٔ آزمایشی برای شنیدن صدای شخصیت است"}, format="json")
    produce(api, worker, ep_id, "preview")
    voices = {Asset.objects.get(shot_id=sh["id"], role="narration", is_current=True).provenance["voice"] for sh in shots[:2]}
    assert voices == {"voice-alef", "voice-be"}
    assert Asset.objects.get(shot_id=shots[0]["id"], role="narration", is_current=True).provenance["speaker"] == "الف"


# ------------------------------------------------------------------ rig from a character sheet

def test_rig_from_sheet_job_builds_a_complete_draft_rig(api, worker, ffmpeg_available, comfy_local):  # noqa: F811
    from instai.assets import storage as asset_storage
    from instai.pages.models import Character, CharacterReference
    from instai.production.models import CharacterRig
    from instai.render.puppet.rig import Rig

    page = api.post("/api/pages", {"name": "ص", "format": "recurring_character", "languages": ["fa"], "idea": "x"}, format="json").json()
    ch = Character.objects.create(page_id=page["id"], name="سارا")
    r = api.post(f"/api/characters/{ch.pk}/rigs", {"source": "sheet"}, format="json")
    finish(api, worker, r, expect="failed")                                                         # no approved sheet yet: a clear refusal
    tmp = Path(asset_storage.storage.root) / "_t" / "sheet.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (300, 400), (200, 60, 60)).save(tmp)
    CharacterReference.objects.create(character=ch, kind="sheet", approved=True, asset=asset_storage.register(tmp, f"characters/{ch.pk}/sheet.png", kind="image", role="reference"))
    j = finish(api, worker, api.post(f"/api/characters/{ch.pk}/rigs", {"source": "sheet", "name": "from sheet"}, format="json"))
    rig = CharacterRig.objects.get(pk=j["result"]["rig_id"])
    assert rig.source == "flux_cutout" and rig.sheet_asset_id and not rig.approved and "draft" in rig.notes
    assert j["result"]["parts"] == 18 and j["result"]["workflow"] == "qwen_image_edit_ref" and j["result"]["cutout"] == "flood-fill"
    loaded = Rig.from_spec(rig.spec, Path(asset_storage.storage.root))
    assert loaded.mouth_shapes() == sorted("ABCDEFGHX") and {"body", "head", "arm_l", "arm_r", "leg_l", "leg_r", "eyes_open", "eyes_closed"} <= set(loaded.parts)
    assert loaded.parts["head"].parent == "body" and loaded.parts["mouth_C"].parent == "head" and loaded.parts["leg_l"].parent is None
    prompts = [n["inputs"]["prompt"] for g in comfy_local.prompts for n in g.values() if n["class_type"] == "TextEncodeQwenImageEditPlus" and n["inputs"]["prompt"]]
    assert any("only the torso" in p for p in prompts) and sum("mouth" in p for p in prompts) >= 9 and all("plain pure white background" in p for p in prompts)
    d = api.get(f"/api/characters/{ch.pk}/rigs").json()[0]
    assert d["completeness"]["ok"] and not d["completeness"]["missing_mouth_shapes"]
