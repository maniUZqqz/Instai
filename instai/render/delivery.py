"""Delivery: the nine networks an episode is posted to, what each one wants, and how one finished episode becomes the file for each.

SOURCE: ported from NMarketing:backend/services/editing/social_sizes.py (SIZES) and backend/services/editing/export.py (PRESETS, QUALITY, nvenc_args) @ v3.02
(c23f861), renamed to InstAI's network keys and adapted for episode/series producers: titles in Persian AND English, the loudness target per network, and NO
subject-following reframe (NMarketing re-frames a 16:9 interview into a 9:16 reel around the speaker's face; an episode has no such subject).

InstAI renders an episode in ONE shape today (9:16, `render/assemble.py`). When a network wants another shape the plan says so (`needs_aspect`) and never crops.
Two honest ways out are offered: the day the assembly can render that shape natively (`RERENDER_ASPECTS`), a re-render in it; and, as an explicit per-network
choice, `fit = "blur"`: the WHOLE frame stays in the middle and the sides are filled with a blurred copy of the same picture (nothing is cut away).

All numbers are NMarketing's and are approximate on purpose (apps change their limits), so every screen labels them so. Nothing here posts anything.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from functools import lru_cache
from pathlib import Path

from . import ffmpeg, loudness

log = logging.getLogger("instai.delivery")

#: the shapes the assembly can render natively today (it is 9:16 only). Add a shape here the day `assemble.RenderOptions` can make it.
RERENDER_ASPECTS: tuple[str, ...] = ("9:16",)

#: x264 quality names -> (crf, preset); the network table names a quality, like NMarketing's presets do
QUALITY = {"high": (18, "medium"), "medium": (22, "medium"), "small": (27, "veryfast")}

#: key -> what the network wants. `short` = the short side in pixels (the long side follows the shape); `any_aspect`: a messenger plays any shape inline.
NETWORKS: dict[str, dict] = {
    "ig_reel": {"fa": "ریلز اینستاگرام", "en": "Instagram Reels", "group": "instagram", "aspect": "9:16", "short": 1080, "fps": 30, "quality": "high", "audio_kbps": 192,
                "max_seconds": 90, "zone": "reels", "lufs": -14.0},
    "ig_story": {"fa": "استوری اینستاگرام", "en": "Instagram Story", "group": "instagram", "aspect": "9:16", "short": 1080, "fps": 30, "quality": "high", "audio_kbps": 192,
                 "max_seconds": 60, "zone": "story", "lufs": -14.0},
    "ig_post": {"fa": "پست اینستاگرام (۴:۵)", "en": "Instagram post (4:5)", "group": "instagram", "aspect": "4:5", "short": 1080, "fps": 30, "quality": "high", "audio_kbps": 160,
                "max_seconds": 60, "zone": "feed", "lufs": -14.0},
    "ig_square": {"fa": "پست مربع", "en": "Square post", "group": "instagram", "aspect": "1:1", "short": 1080, "fps": 30, "quality": "high", "audio_kbps": 160,
                  "max_seconds": 60, "zone": "feed", "lufs": -14.0},
    "yt_wide": {"fa": "یوتیوب (افقی ۱۶:۹)", "en": "YouTube (16:9)", "group": "youtube", "aspect": "16:9", "short": 1080, "fps": 30, "quality": "high", "audio_kbps": 192,
                "max_seconds": None, "zone": "feed", "lufs": -14.0},
    "yt_shorts": {"fa": "شورتسِ یوتیوب", "en": "YouTube Shorts", "group": "youtube", "aspect": "9:16", "short": 1080, "fps": 30, "quality": "high", "audio_kbps": 192,
                  "max_seconds": 180, "zone": "shorts", "lufs": -14.0},
    "tiktok": {"fa": "تیک‌تاک", "en": "TikTok", "group": "tiktok", "aspect": "9:16", "short": 1080, "fps": 30, "quality": "high", "audio_kbps": 192,
               "max_seconds": 180, "zone": "tiktok", "lufs": -14.0},
    "telegram": {"fa": "تلگرام / ایتا (کم‌حجم)", "en": "Telegram / Eitaa (small file)", "group": "messenger", "aspect": "16:9", "any_aspect": True, "short": 720, "fps": 30,
                 "quality": "small", "audio_kbps": 128, "max_seconds": None, "zone": "feed", "lufs": -16.0},
    "aparat": {"fa": "آپارات (افقی)", "en": "Aparat (16:9)", "group": "aparat", "aspect": "16:9", "short": 1080, "fps": 25, "quality": "medium", "audio_kbps": 160,
               "max_seconds": None, "zone": "feed", "lufs": -16.0},
}
KEYS = tuple(NETWORKS)

#: a page that said only "instagram" / "youtube" in its publishing target (before the nine keys existed) means this
LEGACY_PLATFORM = {"instagram": "ig_reel", "youtube": "yt_wide"}

_ZONES_FALLBACK = {"reels": {"top": 0.13, "bottom": 0.22, "left": 0.05, "right": 0.14}, "story": {"top": 0.13, "bottom": 0.13, "left": 0.05, "right": 0.05},
                   "tiktok": {"top": 0.11, "bottom": 0.24, "left": 0.05, "right": 0.17}, "shorts": {"top": 0.10, "bottom": 0.20, "left": 0.05, "right": 0.14},
                   "feed": {"top": 0.05, "bottom": 0.05, "left": 0.05, "right": 0.05}}


def safe_zone(key: str) -> dict:
    """The fractions of the frame the network's own buttons cover (approximate). Uses the captions work's table when it is installed, else NMarketing's numbers."""
    zone = NETWORKS[key]["zone"]
    try:
        from instai.render import safezones  # ported by the captions work; optional here

        z = getattr(safezones, "ZONES", {}).get(zone)
        if z and z.get("margins"):
            return dict(z["margins"])
    except Exception:  # noqa: BLE001
        pass
    return dict(_ZONES_FALLBACK.get(zone, _ZONES_FALLBACK["feed"]))


def aspect_of(width: int | None, height: int | None) -> str | None:
    """The nearest of the shapes in use ("9:16", "16:9", "4:5", "1:1"), or None."""
    if not width or not height:
        return None
    r = width / height
    best = min(("9:16", "16:9", "4:5", "1:1"), key=lambda a: abs(r - _ratio(a)))
    return best if abs(r - _ratio(best)) <= 0.06 else None


def _ratio(a: str) -> float:
    w, h = a.split(":")
    return int(w) / int(h)


def network_for(platform: str, aspect: str | None = None) -> str | None:
    """The network key a publishing target means (`PublishTarget.platform`): one of the nine keys, or the old plain names (`instagram` = a reel; `youtube` = Shorts
    for a vertical episode, the wide player otherwise); the names `telegram`, `aparat`, `tiktok` are keys already. None = not a network this module knows."""
    p = (platform or "").strip().lower()
    if p in NETWORKS:
        return p
    if p == "youtube":
        return "yt_shorts" if aspect == "9:16" else "yt_wide"
    return LEGACY_PLATFORM.get(p)


def group_of(platform: str) -> str:
    key = network_for(platform)
    return NETWORKS[key]["group"] if key else (platform or "other")


def catalogue() -> list[dict]:
    out = []
    for k, n in NETWORKS.items():
        w, h = canvas(k)
        out.append({"key": k, "fa": n["fa"], "en": n["en"], "group": n["group"], "aspect": n["aspect"], "width": w, "height": h, "fps": n["fps"], "quality": n["quality"],
                    "crf": QUALITY[n["quality"]][0], "audio_kbps": n["audio_kbps"], "max_seconds": n["max_seconds"], "safe_zone": n["zone"], "safe_margins": safe_zone(k),
                    "lufs": n["lufs"], "loudness_profile": loudness.profile_for(n["lufs"]), "any_aspect": bool(n.get("any_aspect")), "approximate": True})
    return out


def _even(v: float) -> int:
    return max(2, int(round(v / 2.0)) * 2)


def canvas(key: str) -> tuple[int, int]:
    """The network's own frame (width, height) at its short side."""
    n = NETWORKS[key]
    r = _ratio(n["aspect"])
    if r >= 1:
        return _even(n["short"] * r), _even(n["short"])
    return _even(n["short"]), _even(n["short"] / r)


# ---------------------------------------------------------------------------------------------------------------------------- the plan

def _msg(fa: str, en: str, **extra) -> dict:
    return {"fa": fa, "en": en, **extra}


def plan_network(key: str, info: dict, *, fit: str = "", duration: float | None = None) -> dict:
    """What happens for ONE network, from the video's real facts (`info`: width, height, duration, vcodec ...). status:
    `ready` the shape matches (or the network plays any shape); `fit` another shape, the whole frame kept with blurred sides (the person chose it);
    `needs_aspect` another shape and no crop: the file for this network is NOT made. `warnings` never block the file."""
    n = NETWORKS[key]
    have = aspect_of(info.get("width"), info.get("height"))
    dur = float(duration if duration is not None else info.get("duration") or 0)
    notes: list[dict] = []
    offers: list[str] = []
    ok_shape = bool(have and (have == n["aspect"] or n.get("any_aspect")))
    if ok_shape:
        status, mode = "ready", "native"
    elif fit == "blur" and have:
        status, mode = "fit", "fit"
        notes.append(_msg(f"این قسمت {have} ساخته شده و {n['fa']} {n['aspect']} می‌خواهد؛ قابِ کامل در وسط می‌ماند و کناره‌ها با تصویرِ محوِ همان قاب پر می‌شود (چیزی بریده نمی‌شود).",
                          f"This episode is {have} and {n['en']} wants {n['aspect']}: the whole frame stays in the middle and the sides are filled with a blurred copy of the picture (nothing is cut away)."))
    else:
        status, mode = "needs_aspect", ""
        if n["aspect"] in RERENDER_ASPECTS:
            offers.append("rerender")
        if have:
            offers.append("fit_blur")
        notes.append(_msg(f"این قسمت {have or 'با نسبتی ناشناخته'} ساخته شده و {n['fa']} {n['aspect']} می‌خواهد. تصویر را برش نمی‌دهیم و برای این شبکه فایلی ساخته نشد."
                          + (" «قاب کامل با کناره‌های محو» را برای این شبکه روشن کنید یا قسمت را در همان نسبت دوباره بسازید." if "rerender" in offers else " «قاب کامل با کناره‌های محو» را برای این شبکه روشن کنید."),
                          f"This episode is {have or 'of an unknown shape'} and {n['en']} wants {n['aspect']}. We never crop, so no file was made for this network."
                          + (" Turn on 'whole frame with blurred sides' for this network, or render the episode in that shape." if "rerender" in offers else " Turn on 'whole frame with blurred sides' for this network.")))
    warnings: list[dict] = []
    if n["max_seconds"] and dur > n["max_seconds"] + 0.5:
        warnings.append(_msg(f"این شبکه تا حدود {n['max_seconds']} ثانیه می‌پذیرد (تقریبی)؛ قسمت {round(dur)} ثانیه است.",
                             f"This network takes about {n['max_seconds']} s (approximate); the episode is {round(dur)} s."))
    short_src = min(info.get("width") or 0, info.get("height") or 0)
    if short_src and short_src < min(n["short"], 720) * 0.9:
        warnings.append(_msg("ویدئوی مبدأ کم‌وضوح (پیش‌نمایش) است؛ برای انتشار نسخهٔ نهایی را بسازید.", "The source video is low resolution (a preview); render the final version before posting."))
    w, h = output_size(key, info, mode) if mode else (None, None)
    return {"key": key, "fa": n["fa"], "en": n["en"], "group": n["group"], "status": status, "mode": mode, "have_aspect": have, "want_aspect": n["aspect"],
            "width": w, "height": h, "fps": n["fps"], "quality": n["quality"], "crf": QUALITY[n["quality"]][0], "audio_kbps": n["audio_kbps"], "max_seconds": n["max_seconds"],
            "safe_zone": n["zone"], "lufs": n["lufs"], "approximate": True, "notes": notes, "warnings": warnings, "offers": offers}


def output_size(key: str, info: dict, mode: str) -> tuple[int, int]:
    """The size of the network's file. Never larger than the source (no upscaling); `fit` puts the whole frame inside the network's own shape."""
    n = NETWORKS[key]
    sw, sh = int(info.get("width") or 0), int(info.get("height") or 0)
    if mode == "fit" or not (sw and sh):
        cw, ch = canvas(key)
        if sw and sh:
            scale = min(cw / sw, ch / sh)
            if scale > 1:                                    # the picture would be enlarged: make the canvas smaller instead
                cw, ch = _even(cw / scale), _even(ch / scale)
        return cw, ch
    short = min(sw, sh)
    k = min(1.0, n["short"] / short)
    return _even(sw * k), _even(sh * k)


def plan(info: dict, networks: list[str], *, fit: dict[str, str] | None = None) -> list[dict]:
    fit = fit or {}
    return [plan_network(k, info, fit=fit.get(k, "")) for k in networks if k in NETWORKS]


# ---------------------------------------------------------------------------------------------------------------------------- encoding

#: after the graphics-card encoder refused to start, the CPU encoder is used straight away for this long (a card that is busy or absent does not get asked for every network)
GPU_RETRY_S = 600
_GPU_FAILED_AT = [0.0]


@lru_cache(maxsize=4)
def _encoder_names(ff: str) -> frozenset:
    try:
        out = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace",
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            names.add(parts[1])
    return frozenset(names)


def nvenc_listed() -> bool:
    """Does this PC's ffmpeg have the graphics card's H.264 encoder (it may still refuse to start: `render_network` then falls back to the CPU encoder)?"""
    try:
        return "h264_nvenc" in _encoder_names(ffmpeg.binaries()[0])
    except ffmpeg.FFmpegError:
        return False


def video_args(key: str, *, gpu: bool = False) -> list[str]:
    """H.264 settings of a network. `gpu` = the NVIDIA encoder (cq runs about one step above x264's crf for a similar look)."""
    n = NETWORKS[key]
    crf, preset = QUALITY[n["quality"]]
    if gpu:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", str(min(51, crf + 1)), "-b:v", "0", "-pix_fmt", "yuv420p", "-profile:v", "high",
                "-movflags", "+faststart"]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart"]


def video_filter(key: str, info: dict, mode: str) -> str:
    """The picture chain of a network's file. `native`: scale to the network's size. `fit`: the whole frame in the middle over a blurred copy of itself (the copy is
    made small, blurred and enlarged: smooth and cheap); the chain starts with `split`, so the caller prefixes the input label."""
    n = NETWORKS[key]
    w, h = output_size(key, info, mode)
    tail = f"fps={n['fps']},setsar=1,format=yuv420p"
    if mode == "fit":
        bw, bh = _even(w / 10), _even(h / 10)
        return (f"split[a][b];[a]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},boxblur=3:1,scale={w}:{h}:flags=bilinear[bg];"
                f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,{tail}")
    return f"scale={w}:{h}:flags=lanczos,{tail}"


def render_network(src, dst, key: str, info: dict, *, mode: str = "native", ctx=None, gpu: bool | None = None, settle: bool = True) -> dict:
    """Make the file for one network from the finished episode: size, frame rate, quality, AAC audio at the network's bitrate, then the loudness the network
    plays at (measured and corrected on the file). A file that already has the right shape and frame rate is copied, not re-encoded. NVIDIA's encoder is used when
    ffmpeg lists it and the card accepts it; any failure there repeats the encode on the CPU. Raises FFmpegError only when even the CPU encode fails."""
    src, dst = Path(src), Path(dst)
    n = NETWORKS[key]
    dst.parent.mkdir(parents=True, exist_ok=True)
    w, h = output_size(key, info, mode)
    same = (mode == "native" and (w, h) == (info.get("width"), info.get("height")) and abs((info.get("fps") or 0) - n["fps"]) < 0.6
            and info.get("vcodec") == "h264" and n["quality"] != "small")
    encoder = "copy"
    if same:
        shutil.copyfile(src, dst)
    else:
        if mode == "fit":
            head = ["-i", str(src), "-filter_complex", "[0:v]" + video_filter(key, info, mode) + "[v]", "-map", "[v]", "-map", "0:a?"]
        else:
            head = ["-i", str(src), "-vf", video_filter(key, info, mode), "-map", "0:v:0", "-map", "0:a?"]
        audio = ["-c:a", "aac", "-b:a", f"{n['audio_kbps']}k", "-ar", "48000"]
        use_gpu = (nvenc_listed() and time.time() - _GPU_FAILED_AT[0] > GPU_RETRY_S) if gpu is None else bool(gpu)
        err: Exception | None = None
        for g in ([True] if use_gpu else []) + [False]:
            try:
                ffmpeg.run([*head, *video_args(key, gpu=g), *audio, str(dst)], ctx=ctx)
                encoder, err = ("h264_nvenc" if g else "libx264"), None
                break
            except ffmpeg.FFmpegError as exc:
                err = exc
                if g:
                    _GPU_FAILED_AT[0] = time.time()
                dst.unlink(missing_ok=True)
                log.info("delivery encode (%s) failed for %s: %s", "gpu" if g else "cpu", key, exc)
        if err is not None:
            raise err
    rep = loudness.settle(dst, target=n["lufs"]) if settle else {}
    return {"key": key, "path": str(dst), "width": w, "height": h, "fps": n["fps"], "encoder": encoder, "mode": mode, "bytes": dst.stat().st_size, "loudness": rep}
