"""Delivery loudness (0.16): the file is measured with the platforms' meter after the render and brought to the page's target (-14 LUFS for new pages, -16 for old ones),
true peak held under -1 dBTP; the picture is never touched. Real ffmpeg on tiny synthetic mixes (docs/BENCHMARKS.md has the measured numbers)."""
from __future__ import annotations

import hashlib

import pytest

np = pytest.importorskip("numpy")

from instai.pages import profiles  # noqa: E402
from instai.render import audiofixtures as fx  # noqa: E402
from instai.render import ffmpeg, loudness  # noqa: E402

pytestmark = pytest.mark.slow
SR = fx.SR


def ff():
    return ffmpeg.binaries()[0]


def speech_mp4(tmp_path, name, x, *, one_pass: float | None, seconds=None, gain_db=0.0):
    wav = fx.write_wav(tmp_path / f"{name}.wav", x)
    return fx.synthetic_video(tmp_path / f"{name}.mp4", wav, ffmpeg_exe=ff(), seconds=seconds or round(len(x) / SR, 2), loudnorm_to=one_pass, gain_db=gain_db)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def varying_pauses():
    """Five sentences at -18 / -30 / -24 / -14 / -27 dBFS with 2.5 and 3 s silences between some of them: the case where ONE pass of loudnorm misses its target."""
    parts = []
    for i, (db, pause) in enumerate([(-18, 0.2), (-30, 2.5), (-24, 0.2), (-14, 3.0), (-27, 0.2)]):
        parts += [fx.speechlike(2.2, seed=10 + i, level_db=db, pause_every=0), np.zeros(int(pause * SR), dtype=np.float32)]
    return np.concatenate(parts)


# ------------------------------------------------------------------------------------------------------------------------------ profiles and defaults

def test_a_new_page_starts_at_minus_14_and_an_old_value_is_kept():
    assert profiles.default_data("audio")["target_lufs"] == -14 and profiles.default_data("audio")["loudness_settle"] is True
    assert profiles.normalize("audio", {})["target_lufs"] == -14
    assert profiles.normalize("audio", {"target_lufs": -16})["target_lufs"] == -16      # a page saved with the old default keeps it
    assert profiles.normalize("audio", {"target_lufs": -99})["target_lufs"] == -30       # the range is still enforced
    assert profiles.normalize("audio", {"loudness_settle": False})["loudness_settle"] is False


def test_profiles_name_the_three_targets_and_everything_else_is_custom():
    assert [(p["key"], p["lufs"]) for p in loudness.catalogue()] == [("social", -14.0), ("messenger", -16.0), ("broadcast", -23.0)]
    assert [loudness.profile_for(v) for v in (-14, -16.0, -23, -18, None)] == ["social", "messenger", "broadcast", "custom", "custom"]
    assert all(p["fa"] and p["en"] for p in loudness.catalogue())


# ------------------------------------------------------------------------------------------------------------------------------ settle

def test_a_quiet_file_is_brought_to_minus_14_within_0_8_and_under_the_true_peak_ceiling(tmp_path, ffmpeg_available):
    mp4 = speech_mp4(tmp_path, "quiet", fx.speechlike(5.0, seed=3), one_pass=-19.0)
    info_before = ffmpeg.probe(mp4)
    before = loudness.measure(mp4)
    assert before["lufs"] < -18
    rep = loudness.settle(mp4, target=-14.0)
    after = loudness.measure(mp4)
    assert rep["adjusted"] and rep["rounds"] >= 1 and rep["before"] == before["lufs"] and rep["target"] == -14.0 and rep["ok"] is True
    assert abs(after["lufs"] + 14.0) <= 0.8 and after["tp"] <= -0.95
    assert rep["lufs"] == after["lufs"] == rep["after"] and rep["tp"] == after["tp"]
    info_after = ffmpeg.probe(mp4)
    assert (info_after["width"], info_after["height"], info_after["vcodec"]) == (info_before["width"], info_before["height"], info_before["vcodec"])
    assert abs(info_after["duration"] - info_before["duration"]) < 0.15 and info_after["has_audio"]
    assert not list(tmp_path.glob("*.loud*")), "no half-written candidate is left behind"


def test_a_file_that_is_already_on_target_is_not_touched(tmp_path, ffmpeg_available):
    mp4 = speech_mp4(tmp_path, "ok", fx.speechlike(5.0, seed=4), one_pass=-14.0)
    h = sha(mp4)
    rep = loudness.settle(mp4, target=-14.0)
    assert rep and rep["adjusted"] is False and rep["rounds"] == 0 and rep["ok"] is True and sha(mp4) == h


def test_one_pass_loudnorm_misses_on_speech_with_long_pauses_and_settle_fixes_it(tmp_path, ffmpeg_available):
    """The reason the pass exists (docs/BENCHMARKS.md): on this mix the render's own one-pass filter lands more than 0.8 LU from -14."""
    mp4 = speech_mp4(tmp_path, "pauses", varying_pauses(), one_pass=-14.0)
    before = loudness.measure(mp4)
    assert abs(before["lufs"] + 14.0) > 0.8, before
    rep = loudness.settle(mp4, target=-14.0)
    after = loudness.measure(mp4)
    assert rep["adjusted"] and abs(after["lufs"] + 14.0) <= 0.8 and after["tp"] <= -0.95


@pytest.mark.parametrize("target", [-14.0, -16.0, -23.0])
def test_every_profile_target_is_reached(tmp_path, ffmpeg_available, target):
    mp4 = speech_mp4(tmp_path, f"t{int(-target)}", fx.speechlike(4.0, seed=8), one_pass=-27.0)         # far from all of them
    rep = loudness.settle(mp4, target=target)
    after = loudness.measure(mp4)
    assert abs(after["lufs"] - target) <= 0.8 and after["tp"] <= -0.95 and rep["ok"], (target, rep)


def test_a_hot_file_is_pulled_under_the_true_peak_ceiling(tmp_path, ffmpeg_available):
    x = fx.speechlike(4.0, seed=5, level_db=-14.0)
    mp4 = speech_mp4(tmp_path, "hot", x, one_pass=None, gain_db=6.0)       # no loudnorm and +6 dB: true peak about +3 dBTP, loudness about -10
    assert loudness.measure(mp4)["tp"] > 1.0
    loudness.settle(mp4, target=-14.0)
    after = loudness.measure(mp4)
    assert after["tp"] <= -0.95 and abs(after["lufs"] + 14.0) <= 0.8


def test_peaks_only_mode_leaves_loudness_alone_and_only_a_clipping_file_is_touched(tmp_path, ffmpeg_available):
    calm = speech_mp4(tmp_path, "calm", fx.speechlike(3.0, seed=6, level_db=-30.0), one_pass=None)
    h = sha(calm)
    rep = loudness.settle(calm, target=None)
    assert rep["target"] is None and rep["adjusted"] is False and sha(calm) == h
    hot = speech_mp4(tmp_path, "hot2", fx.speechlike(3.0, seed=6, level_db=-14.0), one_pass=None, gain_db=6.0)
    peak = loudness.measure(hot)["tp"]
    assert peak > -0.1
    loudness.settle(hot, target=None)
    assert loudness.measure(hot)["tp"] < peak


def test_a_file_without_sound_or_a_broken_file_is_not_an_error(tmp_path, ffmpeg_available):
    import subprocess

    silent = tmp_path / "silent.mp4"
    subprocess.run([ff(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(silent)], check=True)
    assert loudness.settle(silent, target=-14.0) == {}
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video at all")
    assert loudness.settle(junk, target=-14.0) == {} and junk.read_bytes() == b"not a video at all"
    assert loudness.measure(tmp_path / "missing.mp4") is None
    assert not list(tmp_path.glob("*.loud*"))
