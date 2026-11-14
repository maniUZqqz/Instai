"""The delivery table (0.15): nine networks with their size, frame rate, quality, length limit, safe-zone key and loudness target; the per-network plan (never a crop); and the
file made for a network (size, loudness, GPU encoder with a CPU fallback). Real ffmpeg on tiny clips."""
from __future__ import annotations

import subprocess

import pytest

np = pytest.importorskip("numpy")

from instai.render import audiofixtures as fx  # noqa: E402
from instai.render import delivery, ffmpeg, loudness  # noqa: E402

SR = fx.SR
NINE = ["ig_reel", "ig_story", "ig_post", "ig_square", "yt_wide", "yt_shorts", "tiktok", "telegram", "aparat"]


def ff():
    return ffmpeg.binaries()[0]


def vertical(**kw):
    return {"width": 1080, "height": 1920, "fps": 30.0, "duration": 45.0, "vcodec": "h264", **kw}


def episode_mp4(tmp_path, name="ep", *, size="270x480", seconds=3.0, fps=30, lufs=-14.0):
    wav = fx.write_wav(tmp_path / f"{name}.wav", fx.speechlike(seconds, seed=12))
    return fx.synthetic_video(tmp_path / f"{name}.mp4", wav, ffmpeg_exe=ff(), seconds=seconds, size=size, fps=fps, loudnorm_to=lufs)


# ------------------------------------------------------------------------------------------------------------------------------ the table

def test_the_table_has_the_nine_networks_with_everything_a_network_wants():
    assert list(delivery.NETWORKS) == NINE and list(delivery.KEYS) == NINE
    for row in delivery.catalogue():
        assert row["fa"] and row["en"] and row["approximate"] is True
        assert row["width"] % 2 == 0 and row["height"] % 2 == 0 and row["width"] > 0 and row["fps"] in (25, 30)
        assert row["crf"] in (18, 22, 27) and row["audio_kbps"] >= 96 and row["safe_zone"] in ("reels", "story", "tiktok", "shorts", "feed")
        assert set(row["safe_margins"]) == {"top", "bottom", "left", "right"}
        assert row["lufs"] in (-14.0, -16.0) and row["loudness_profile"] in ("social", "messenger")


def test_sizes_loudness_and_limits_follow_the_networks():
    c = {r["key"]: r for r in delivery.catalogue()}
    assert (c["ig_reel"]["width"], c["ig_reel"]["height"]) == (1080, 1920) and c["ig_reel"]["max_seconds"] == 90
    assert (c["ig_post"]["width"], c["ig_post"]["height"]) == (1080, 1350)
    assert (c["ig_square"]["width"], c["ig_square"]["height"]) == (1080, 1080)
    assert (c["yt_wide"]["width"], c["yt_wide"]["height"]) == (1920, 1080) and c["yt_wide"]["max_seconds"] is None
    assert (c["yt_shorts"]["width"], c["yt_shorts"]["height"], c["yt_shorts"]["max_seconds"]) == (1080, 1920, 180)
    assert (c["telegram"]["width"], c["telegram"]["height"], c["telegram"]["quality"]) == (1280, 720, "small")
    assert (c["aparat"]["fps"], c["aparat"]["lufs"]) == (25, -16.0)
    assert {k for k, r in c.items() if r["lufs"] == -14.0} == {"ig_reel", "ig_story", "ig_post", "ig_square", "yt_wide", "yt_shorts", "tiktok"}
    assert {k for k, r in c.items() if r["lufs"] == -16.0} == {"telegram", "aparat"}
    assert c["tiktok"]["safe_zone"] == "tiktok" and c["yt_shorts"]["safe_zone"] == "shorts" and c["ig_story"]["safe_zone"] == "story"


def test_a_target_platform_means_one_network():
    assert delivery.network_for("ig_reel") == "ig_reel" and delivery.network_for("Telegram") == "telegram"
    assert delivery.network_for("instagram") == "ig_reel"                       # what every page said before the nine keys existed
    assert delivery.network_for("youtube", "9:16") == "yt_shorts" and delivery.network_for("youtube", "16:9") == "yt_wide" and delivery.network_for("youtube") == "yt_wide"
    assert delivery.network_for("facebook") is None and delivery.network_for("") is None
    assert delivery.group_of("ig_story") == "instagram" and delivery.group_of("instagram") == "instagram" and delivery.group_of("telegram") == "messenger"
    assert delivery.aspect_of(1080, 1920) == "9:16" and delivery.aspect_of(1920, 1080) == "16:9" and delivery.aspect_of(1080, 1350) == "4:5" and delivery.aspect_of(1000, 700) is None


# ------------------------------------------------------------------------------------------------------------------------------ the plan: never a crop

def test_a_vertical_episode_fits_the_vertical_networks_and_a_messenger():
    plans = {p["key"]: p for p in delivery.plan(vertical(), NINE)}
    for k in ("ig_reel", "ig_story", "yt_shorts", "tiktok", "telegram"):
        assert plans[k]["status"] == "ready" and plans[k]["mode"] == "native" and plans[k]["offers"] == [], k
    assert (plans["ig_reel"]["width"], plans["ig_reel"]["height"]) == (1080, 1920)
    assert (plans["telegram"]["width"], plans["telegram"]["height"]) == (720, 1280)         # a messenger plays any shape: the 9:16 stays 9:16, at its small size


def test_another_shape_is_said_in_both_languages_and_never_cropped():
    plans = {p["key"]: p for p in delivery.plan(vertical(), NINE)}
    for k, want in (("yt_wide", "16:9"), ("aparat", "16:9"), ("ig_post", "4:5"), ("ig_square", "1:1")):
        p = plans[k]
        assert p["status"] == "needs_aspect" and p["mode"] == "" and p["width"] is None and p["want_aspect"] == want and p["have_aspect"] == "9:16", k
        assert "9:16" in p["notes"][0]["fa"] and want in p["notes"][0]["fa"] and "برش" in p["notes"][0]["fa"]
        assert "crop" in p["notes"][0]["en"] and want in p["notes"][0]["en"]
        assert p["offers"] == ["fit_blur"], "the assembly renders 9:16 only today: no re-render offer for other shapes"


def test_the_rerender_offer_exists_only_for_a_shape_the_assembly_can_render():
    wide = {"width": 1920, "height": 1080, "fps": 30.0, "duration": 30.0, "vcodec": "h264"}
    p = delivery.plan_network("ig_reel", wide)
    assert p["status"] == "needs_aspect" and p["offers"] == ["rerender", "fit_blur"]         # 9:16 is a shape the assembly can render
    assert delivery.plan_network("ig_post", wide)["offers"] == ["fit_blur"]                  # 4:5 is not (yet)
    assert delivery.RERENDER_ASPECTS == ("9:16",)


def test_the_whole_frame_option_keeps_everything_and_sizes_the_canvas_like_the_network():
    p = delivery.plan_network("yt_wide", vertical(), fit="blur")
    assert p["status"] == "fit" and p["mode"] == "fit" and (p["width"], p["height"]) == (1920, 1080) and "blurred" in p["notes"][0]["en"] and "محو" in p["notes"][0]["fa"]
    small = delivery.plan_network("yt_wide", {"width": 360, "height": 640, "fps": 15.0, "duration": 10, "vcodec": "h264"}, fit="blur")
    assert (small["width"], small["height"]) == (1138, 640), "a small source is not enlarged: the 16:9 canvas shrinks to fit it"
    assert small["width"] / small["height"] == pytest.approx(16 / 9, abs=0.03)


def test_a_file_is_never_larger_than_its_source():
    assert delivery.output_size("ig_reel", {"width": 360, "height": 640}, "native") == (360, 640)
    assert delivery.output_size("telegram", {"width": 1080, "height": 1920}, "native") == (720, 1280)
    assert delivery.output_size("ig_reel", {"width": 1080, "height": 1920}, "native") == (1080, 1920)


def test_length_limits_and_a_preview_source_are_warnings_never_blockers():
    p = delivery.plan_network("ig_reel", vertical(duration=120.0))
    assert p["status"] == "ready" and "تقریبی" in p["warnings"][0]["fa"] and "approximate" in p["warnings"][0]["en"]
    assert delivery.plan_network("yt_wide", {"width": 1920, "height": 1080, "duration": 4000, "vcodec": "h264"})["warnings"] == []          # no limit
    low = delivery.plan_network("ig_reel", {"width": 360, "height": 640, "fps": 15.0, "duration": 20.0, "vcodec": "h264"})
    assert low["status"] == "ready" and any("پیش‌نمایش" in w["fa"] for w in low["warnings"])
    assert delivery.plan_network("ig_reel", {})["status"] == "needs_aspect"                    # nothing known about the file: nothing is promised


# ------------------------------------------------------------------------------------------------------------------------------ encoder choice

def test_encoder_arguments_follow_the_networks_quality_and_the_gpu_flag():
    cpu = delivery.video_args("ig_reel")
    assert cpu[:2] == ["-c:v", "libx264"] and cpu[cpu.index("-crf") + 1] == "18" and "yuv420p" in cpu
    assert delivery.video_args("telegram")[delivery.video_args("telegram").index("-crf") + 1] == "27"
    gpu = delivery.video_args("ig_reel", gpu=True)
    assert gpu[:2] == ["-c:v", "h264_nvenc"] and gpu[gpu.index("-cq") + 1] == "19" and "-crf" not in gpu          # cq runs one step above x264's crf


def test_the_gpu_encoder_is_used_when_it_works_and_the_cpu_one_when_it_does_not(tmp_path, ffmpeg_available, monkeypatch):
    src = episode_mp4(tmp_path)
    info = ffmpeg.probe(src)
    real_run = ffmpeg.run
    calls = []

    def fake_run(args, **kw):
        calls.append("nvenc" if "h264_nvenc" in args else "x264")
        if "h264_nvenc" in args:
            raise ffmpeg.FFmpegError("no NVENC capable device found")
        return real_run(args, **kw)

    monkeypatch.setattr(ffmpeg, "run", fake_run)
    r = delivery.render_network(src, tmp_path / "t" / "telegram.mp4", "telegram", info, gpu=True)
    assert r["encoder"] == "libx264" and calls == ["nvenc", "x264"] and (tmp_path / "t" / "telegram.mp4").is_file()
    calls.clear()
    r = delivery.render_network(src, tmp_path / "t" / "telegram2.mp4", "telegram", info, gpu=False)
    assert r["encoder"] == "libx264" and calls == ["x264"]
    monkeypatch.setattr(ffmpeg, "run", lambda args, **kw: (_ for _ in ()).throw(ffmpeg.FFmpegError("broken encoder")))
    with pytest.raises(ffmpeg.FFmpegError):
        delivery.render_network(src, tmp_path / "t" / "telegram3.mp4", "telegram", info, gpu=False)
    assert not (tmp_path / "t" / "telegram3.mp4").exists()


# ------------------------------------------------------------------------------------------------------------------------------ the file of a network

def test_a_network_file_has_the_networks_size_frame_rate_and_loudness(tmp_path, ffmpeg_available):
    src = episode_mp4(tmp_path, size="270x480", fps=15, lufs=-14.0)
    info = ffmpeg.probe(src)
    r = delivery.render_network(src, tmp_path / "o" / "ig.mp4", "ig_reel", info, gpu=False)
    got = ffmpeg.probe(r["path"])
    assert (got["width"], got["height"]) == (270, 480) and round(got["fps"]) == 30 and r["encoder"] == "libx264" and got["has_audio"] and got["vcodec"] == "h264"
    m = loudness.measure(r["path"])
    assert abs(m["lufs"] + 14.0) <= 0.8 and m["tp"] <= -0.95
    t = delivery.render_network(src, tmp_path / "o" / "tg.mp4", "telegram", info, gpu=False)
    assert abs(loudness.measure(t["path"])["lufs"] + 16.0) <= 0.8 and t["loudness"]["target"] == -16.0
    assert (t["width"], t["height"]) == (270, 480)                                          # small source: not enlarged to 720x1280


def test_a_file_that_already_has_the_shape_and_rate_is_copied_not_re_encoded(tmp_path, ffmpeg_available):
    src = episode_mp4(tmp_path, size="270x480", fps=30, lufs=-14.0)
    # a 270x480 source is "smaller than the network", so output_size keeps it and the shape + rate already match
    r = delivery.render_network(src, tmp_path / "o" / "ig.mp4", "ig_reel", ffmpeg.probe(src), gpu=False)
    assert r["encoder"] == "copy" and abs(loudness.measure(r["path"])["lufs"] + 14.0) <= 0.8


def test_the_whole_frame_option_makes_a_16_9_file_with_nothing_cut_away(tmp_path, ffmpeg_available):
    src = episode_mp4(tmp_path, size="270x480", fps=15)
    info = ffmpeg.probe(src)
    plan = delivery.plan_network("yt_wide", info, fit="blur")
    assert plan["mode"] == "fit"
    r = delivery.render_network(src, tmp_path / "o" / "yt.mp4", "yt_wide", info, mode="fit", gpu=False)
    got = ffmpeg.probe(r["path"])
    assert got["width"] / got["height"] == pytest.approx(16 / 9, abs=0.02) and (got["width"], got["height"]) == (r["width"], r["height"]) == (plan["width"], plan["height"])
    # the centre column of the frame carries the picture and the far-left column carries its blurred copy: both exist and they differ
    from PIL import Image

    png = tmp_path / "f.png"
    subprocess.run([ff(), "-y", "-v", "error", "-ss", "1", "-i", r["path"], "-frames:v", "1", str(png)], check=True)
    im = Image.open(png).convert("RGB")
    w, h = im.size
    left = np.asarray(im.crop((0, 0, w // 10, h)), dtype=float)
    centre = np.asarray(im.crop((w * 45 // 100, 0, w * 55 // 100, h)), dtype=float)
    assert left.std() > 3 and centre.std() > 20 and abs(left.mean() - centre.mean()) + abs(left.std() - centre.std()) > 1


def test_no_file_is_left_half_written_when_the_source_is_broken(tmp_path, ffmpeg_available):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"nope")
    with pytest.raises(ffmpeg.FFmpegError):
        delivery.render_network(bad, tmp_path / "o" / "x.mp4", "ig_story", {"width": 1080, "height": 1920, "fps": 15.0, "vcodec": "h264", "duration": 1}, gpu=False)
    assert not (tmp_path / "o" / "x.mp4").exists()
