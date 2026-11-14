"""The sound checks on a rendered mix (0.15): a doubled narration reports the echo, a clean mix reports nothing, music as loud as the voice is named by shot and track, an
out-of-phase mix is found. Calibrated on InstAI's own mixes: narration + side-chain-ducked music/ambience + effects (production/mixing.py, render/assemble.py);
the numbers are in docs/BENCHMARKS.md. numpy is the one requirement; without it the checks say so and the render goes on."""
from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from instai.render import assemble as asm  # noqa: E402
from instai.render import audiofixtures as fx  # noqa: E402
from instai.render import audioqc, ffmpeg  # noqa: E402

SR = fx.SR


def ff():
    return ffmpeg.binaries()[0]


# ------------------------------------------------------------------------------------------------------------------------------ echo

@pytest.mark.parametrize("seed", [1, 2, 5, 9, 14])
def test_clean_speech_never_reports_an_echo(seed):
    r = audioqc.echo_report(fx.speechlike(10.0, seed=seed))
    assert r["doubled"] is False and r["strength"] < audioqc.ECHO_R * 0.6, r        # measured about 0.06 against the 0.16 line


@pytest.mark.parametrize("delay,gain", [(0.15, 1.0), (0.15, 0.5), (0.30, 0.5), (0.50, 0.3)])
def test_the_same_speech_twice_is_found_with_its_offset(delay, gain):
    x = fx.delayed_copy(fx.speechlike(10.0, seed=3), delay, gain)
    r = audioqc.echo_report(x)
    assert r["doubled"] is True and abs(r["lag_s"] - delay) <= 0.012 and r["share"] >= audioqc.ECHO_SHARE and r["spans"], r


def test_a_copy_that_is_not_close_is_another_sentence_not_an_echo():
    r = audioqc.echo_report(fx.delayed_copy(fx.speechlike(10.0, seed=3), 2.5, 1.0))        # 2.5 s apart: beyond MAX_LAG
    assert r["doubled"] is False


def test_a_synthetic_tone_is_not_a_voice_and_is_never_called_an_echo():
    """The fake narration engine makes sine bursts: strictly periodic, they correlate with themselves at many lags. Calling that «the same speech twice» would put
    a false warning on every fake render, so a crowd of equal peaks is «tonal», not «doubled»."""
    import tempfile
    from pathlib import Path

    from instai.providers.tts import FakeTTS

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "fake.wav"
        FakeTTS().synthesize("این یک جمله آزمایشی برای بررسی صدا است و باید چند کلمه داشته باشد تا طولانی شود " * 3, out)
        x = audioqc.decode_mono(out)
    r = audioqc.echo_report(x)
    assert len(x) > 10 * SR and r["doubled"] is False and r["tonal"] == r["windows"] > 0, r


def test_silence_and_short_signals_are_not_judged():
    assert audioqc.echo_report(np.zeros(10 * SR, dtype=np.float32))["doubled"] is False
    assert audioqc.echo_report(fx.speechlike(1.0, seed=1))["windows"] == 0


# ------------------------------------------------------------------------------------------------------------------------------ phase and levels

def test_out_of_phase_channels_are_found_and_normal_stereo_is_not():
    x = fx.speechlike(4.0, seed=2)
    assert audioqc.channel_report(x, -x)["out_of_phase"] is True
    assert audioqc.channel_report(x, x)["out_of_phase"] is False
    assert audioqc.channel_report(x, np.roll(x, 40) * 0.8)["out_of_phase"] is False
    assert audioqc.channel_report(x, np.zeros_like(x))["corr"] is None                    # one silent channel: nothing to compare


def test_level_helpers():
    t = np.full(SR, 0.1, dtype=np.float32)
    assert audioqc.level_db(t) == -20.0 and audioqc.peak_db(t) == -20.0 and audioqc.level_db(np.zeros(0, dtype=np.float32)) == -120.0


# ------------------------------------------------------------------------------------------------------------------------------ music over the voice

def test_the_voice_must_stand_above_the_bed_while_it_speaks():
    voice = fx.speechlike(6.0, seed=4, level_db=-22.0)
    windows = [{"shot": 1, "from": 0.0, "to": 3.0}, {"shot": 2, "from": 3.0, "to": 6.0}]
    loud = fx.pulse_music(6.0, level_db=-24.0)                                            # 2 dB under the voice
    quiet = fx.pulse_music(6.0, level_db=-44.0)                                           # 22 dB under
    rows = audioqc.masking_by_window(voice, loud, windows)
    assert rows and all(r["masked"] for r in rows) and all(r["margin_db"] < audioqc.MASK_MARGIN_DB for r in rows)
    ok = audioqc.masking_by_window(voice, quiet, windows)
    assert ok and not any(r["masked"] for r in ok) and all(r["margin_db"] > 15 for r in ok)
    assert audioqc.masking_by_window(voice, np.zeros_like(voice), windows)[0]["masked"] is False          # no bed: nothing to mask with
    assert audioqc.masking_report(voice, loud)["masked"] is True and audioqc.masking_report(voice, quiet)["masked"] is False


def test_pauses_inside_a_narration_do_not_count_as_a_quiet_voice():
    voice = fx.speechlike(8.0, seed=4, level_db=-22.0, pause_every=2, pause_s=1.2)       # a lot of silence in the window
    bed = fx.pulse_music(8.0, level_db=-40.0)
    row = audioqc.masking_by_window(voice, bed, [{"shot": 1, "from": 0.0, "to": 8.0}])[0]
    assert 12 < row["margin_db"] < 24 and row["masked"] is False                           # speech frames only: 18 dB, not diluted by the pauses


# ------------------------------------------------------------------------------------------------------------------------------ an episode: shots, tracks, stems

def episode_parts(tmp_path, *, music_db=-22.0, sfx_db=-12.0, sfx_duck=False, speech_in_track=False, doubled_narration=False, seconds_per_shot=4.0):
    """Three shots with their own narration files and three mix tracks (a ducked music bed, a ducked ambience, one effect in shot 2), the way `step_assemble` hands
    them over, plus the final file as the mix the platforms would play (the same sum, in numpy)."""
    shots, narr = [], []
    for i in range(3):
        x = fx.speechlike(seconds_per_shot - 0.6, seed=20 + i, level_db=-22.0)
        if doubled_narration and i == 1:
            x = fx.delayed_copy(x, 0.15, 1.0)
        wav = fx.write_wav(tmp_path / f"n{i}.wav", x)
        narr.append(x)
        shots.append(asm.ShotSpec(key=str(i + 1), duration=seconds_per_shot, audio=str(wav), audio_duration=len(x) / SR, transition="cut"))
    timeline = asm.plan_timeline(shots)
    total = timeline[-1]["end"]
    music = fx.write_wav(tmp_path / "music.wav", fx.pulse_music(total, level_db=-24.0))
    amb = fx.write_wav(tmp_path / "amb.wav", fx.pulse_music(total, level_db=-30.0, freq=130.0))
    sfx_x = fx.speechlike(1.2, seed=77, level_db=-18.0, pause_every=0) if speech_in_track else fx.pulse_music(1.2, level_db=-22.0, freq=600.0)
    sfx = fx.write_wav(tmp_path / "sfx.wav", sfx_x)
    tracks = [
        {"file": str(music), "kind": "music", "start": 0.0, "end": total, "gain_db": music_db, "duck": True, "fade_in": 1.0, "fade_out": 2.0, "loop": True, "id": 1, "label": "موسیقی زمینه"},
        {"file": str(amb), "kind": "ambience", "start": 0.0, "end": total, "gain_db": -26.0, "duck": True, "fade_in": 0.8, "fade_out": 0.8, "loop": True, "id": 2, "label": "فضای شب"},
        {"file": str(sfx), "kind": "sfx", "start": timeline[1]["start"] + 0.4, "end": timeline[1]["start"] + 1.6, "gain_db": sfx_db, "duck": sfx_duck, "fade_in": 0.02, "fade_out": 0.15,
         "loop": False, "id": 3, "label": "door slam"},
    ]
    return shots, timeline, tracks, narr, total


def final_mix(tmp_path, shots, timeline, tracks, narr, total, name="final"):
    """A stereo mp4 of the episode's mix: narration where the shots put it, the tracks at their gains (ducking is modelled by the real stems in the checks, so the
    file here only needs to carry the same material)."""
    n = int(total * SR) + SR
    mix = np.zeros(n, dtype=np.float32)
    for x, t in zip(narr, timeline):
        a = int(t["audio_start"] * SR)
        mix[a:a + len(x)] += x
    for tr in tracks:
        y = audioqc.decode_mono(tr["file"], max_seconds=60)
        y = y * np.float32(10 ** (tr["gain_db"] / 20)) * (0.3 if tr["duck"] else 1.0)
        a = int(tr["start"] * SR)
        mix[a:a + len(y)] += y[: max(0, n - a)]
    wav = fx.write_wav(tmp_path / f"{name}.wav", mix)
    return fx.synthetic_video(tmp_path / f"{name}.mp4", wav, ffmpeg_exe=ff(), seconds=round(total, 2))


def test_a_clean_episode_mix_reports_nothing(tmp_path, ffmpeg_available):
    shots, timeline, tracks, narr, total = episode_parts(tmp_path)
    mp4 = final_mix(tmp_path, shots, timeline, tracks, narr, total)
    rep = audioqc.analyze_episode(mp4, shots, timeline, tracks, tmp_path / "w")
    assert rep["ok"] and rep["problems"] == [] and rep["clean"] is True, rep
    assert rep["echo"]["doubled"] is False and rep["channels"]["out_of_phase"] is False
    assert rep["masking"]["applicable"] and rep["masking"]["masked"] == [] and rep["masking"]["margin_db"] > audioqc.MASK_MARGIN_DB + 3
    rows = audioqc.qc_rows(rep)
    assert [r["name"] for r in rows] == ["audio_echo", "audio_masking", "audio_phase"] and {r["level"] for r in rows} == {"ok"}
    assert all(r["message"] and r["message_en"] for r in rows)


def test_a_loud_effect_over_the_voice_names_the_shot_and_the_track(tmp_path, ffmpeg_available):
    shots, timeline, tracks, narr, total = episode_parts(tmp_path, sfx_db=-1.0, sfx_duck=False)       # «door slam» in shot 2 at nearly full level, not ducked
    mp4 = final_mix(tmp_path, shots, timeline, tracks, narr, total)
    rep = audioqc.analyze_episode(mp4, shots, timeline, tracks, tmp_path / "w")
    assert "masking" in rep["problems"] and rep["clean"] is False
    m = rep["masking"]["masked"]
    assert m and {r["shot"] for r in m} == {2} and m[0]["group"] == "plain" and m[0]["track"]["label"] == "door slam"
    row = next(r for r in audioqc.qc_rows(rep) if r["name"] == "audio_masking")
    assert row["level"] == "warn" and "شات ۲" in row["message"] and "door slam" in row["message"] and "shot 2" in row["message_en"] and "door slam" in row["message_en"]
    assert row["value"]["shot"] == 2 and row["value"]["track"]["kind"] == "sfx"


def test_a_music_bed_that_is_too_loud_even_after_ducking_is_named(tmp_path, ffmpeg_available):
    shots, timeline, tracks, narr, total = episode_parts(tmp_path, music_db=12.0)       # the bed is far too loud: ducking cannot save the words
    rep = audioqc.analyze_episode(final_mix(tmp_path, shots, timeline, tracks, narr, total), shots, timeline, tracks, tmp_path / "w")
    assert rep["masking"]["masked"], rep["masking"]
    w = min(rep["masking"]["masked"], key=lambda r: r["margin_db"])
    assert w["group"] == "ducked" and w["track"]["kind"] == "music"
    row = next(r for r in audioqc.qc_rows(rep) if r["name"] == "audio_masking")
    assert "موسیقی «موسیقی زمینه»" in row["message"] and "music" in row["message_en"]


def test_a_doubled_narration_is_found_and_the_shot_is_named(tmp_path, ffmpeg_available):
    shots, timeline, tracks, narr, total = episode_parts(tmp_path, doubled_narration=True, seconds_per_shot=7.0)
    mp4 = final_mix(tmp_path, shots, timeline, tracks, narr, total)
    rep = audioqc.analyze_episode(mp4, shots, timeline, tracks, tmp_path / "w")
    e = rep["echo"]
    assert e["doubled"] is True and abs(e["lag_s"] - 0.15) <= 0.02 and e["narration"] is True and 2 in e["shots"], e
    row = next(r for r in audioqc.qc_rows(rep) if r["name"] == "audio_echo")
    assert row["level"] == "warn" and "شات" in row["message"] and "راوی" in row["message"] and "150" in row["message"].translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    assert "narration itself plays twice" in row["message_en"] and "ms apart" in row["message_en"]


def test_a_track_that_carries_speech_is_named_when_the_narration_alone_is_fine(tmp_path, ffmpeg_available):
    """An effect file that contains a voice: the narration (its own stem) is clean, the mix is not."""
    shots, timeline, tracks, narr, total = episode_parts(tmp_path, seconds_per_shot=7.0)
    # the 'effect' is a copy of the narration of shot 2, 150 ms late, at the same level
    copy = fx.write_wav(tmp_path / "copy.wav", np.concatenate([np.zeros(int(0.15 * SR), dtype=np.float32), narr[1]]))
    tracks[2] = {**tracks[2], "file": str(copy), "kind": "sfx", "start": timeline[1]["audio_start"], "end": timeline[1]["audio_start"] + len(narr[1]) / SR + 0.15, "gain_db": 0.0, "duck": False,
                 "label": "voice in the effect"}
    mp4 = final_mix(tmp_path, shots, timeline, tracks, narr, total)
    rep = audioqc.analyze_episode(mp4, shots, timeline, tracks, tmp_path / "w")
    e = rep["echo"]
    assert e["doubled"] is True and e["narration"] is False and any(t["label"] == "voice in the effect" for t in e["tracks"]), e
    row = next(r for r in audioqc.qc_rows(rep) if r["name"] == "audio_echo")
    assert "voice in the effect" in row["message"] and "voice in the effect" in row["message_en"]


def test_an_episode_without_tracks_has_nothing_to_mask_and_a_doubled_narration_is_the_narration(tmp_path, ffmpeg_available):
    shots, timeline, tracks, narr, total = episode_parts(tmp_path, doubled_narration=True, seconds_per_shot=7.0)
    mp4 = final_mix(tmp_path, shots, timeline, [], narr, total)
    rep = audioqc.analyze_episode(mp4, shots, timeline, [], tmp_path / "w")
    assert rep["masking"]["applicable"] is False and rep["echo"]["doubled"] and rep["echo"]["narration"] is True
    rows = {r["name"]: r for r in audioqc.qc_rows(rep)}
    assert rows["audio_masking"]["level"] == "ok" and "موسیقی یا جلوه‌ای" in rows["audio_masking"]["message"]


def test_a_phase_inverted_file_is_found_by_the_file_check(tmp_path, ffmpeg_available):
    import subprocess

    wav = fx.write_wav(tmp_path / "s.wav", fx.speechlike(3.0, seed=2))
    mp4 = tmp_path / "phase.mp4"
    subprocess.run([ff(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=3", "-i", str(wav), "-af", "pan=stereo|c0=c0|c1=-1*c0", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", "3", str(mp4)], check=True)
    rep = audioqc.analyze_file(mp4)
    assert rep["channels"]["out_of_phase"] and rep["problems"] == ["phase"]
    row = next(r for r in audioqc.qc_rows(rep) if r["name"] == "audio_phase")
    assert row["level"] == "warn" and row["message"] and row["message_en"]


# ------------------------------------------------------------------------------------------------------------------------------ degrade

def test_without_numpy_the_checks_say_so_and_nothing_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(audioqc, "np", None)
    assert audioqc.available() is False
    rep = audioqc.analyze_file(tmp_path / "x.mp4")
    assert rep == {"ok": False, "reason": "numpy_missing"}
    rows = audioqc.qc_rows(rep)
    assert len(rows) == 1 and rows[0]["level"] == "info" and "numpy" in rows[0]["message"] and "numpy" in rows[0]["message_en"]


def test_a_file_without_sound_or_a_missing_file_never_raises(tmp_path, ffmpeg_available):
    import subprocess

    silent = tmp_path / "silent.mp4"
    subprocess.run([ff(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(silent)], check=True)
    assert audioqc.analyze_file(silent)["reason"] == "no_audio"
    assert audioqc.analyze_file(tmp_path / "nope.mp4")["ok"] is False
    assert audioqc.qc_rows({"ok": False, "reason": "no_audio"})[0]["level"] == "info"
