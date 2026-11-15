"""The automatic self-tests of the cover maker (rows of ``instai/ops/pcselftest.CHECKS``; the pass checks are in ``docs/selftests/covers.md``).

* ``covers`` (CPU, runs by itself on every new version and then weekly): a synthetic series is rendered in EVERY format at its exact size, and EVERY layout in EVERY format at a small
  scale: the picture is not blank, the title was really drawn, it stays inside the canvas, inside the safe area and out of the platform's avoid zones, and the Persian text has ink.
* ``covers.bg`` (GPU, runs by itself once ComfyUI is up): ONE 512x512 background through the real path (``compute.run_task``), judged (size, not flat) and composited under a layout. When
  ComfyUI or the image model is not there yet the check WAITS (pending) and runs by itself the moment it can.

SOURCE: adapted from NMarketing:backend/apps/thumbs/selftest.py @ v3.02 (c23f861) (a CPU check of every layout x format and a GPU check of the AI background).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PIL import Image

from instai.ops.pcselftest import _fd, _r

from .engine import fixtures
from .engine import formats as F
from .engine import render as R
from .engine.styles import STYLES

SMALL = 0.18
MIN_STD = 18.0


def _stddev(img: Image.Image) -> float:
    return float(np.asarray(img.convert("L"), dtype=np.float32).std())


def _overlap_frac(box, rect) -> float:
    ix = max(0, min(box[2], rect[2]) - max(box[0], rect[0]))
    iy = max(0, min(box[3], rect[3]) - max(box[1], rect[1]))
    return ix * iy / max(1, (box[2] - box[0]) * (box[3] - box[1]))


def sample_inputs(lang: str = "fa") -> R.Inputs:
    inp = R.Inputs(brand_colors=list(fixtures.CHAGHER_COLORS), channel_name="Chagher")
    inp.subject, inp.subject_is_cutout = fixtures.person(), True
    inp.subject2, inp.subject2_is_cutout = fixtures.person(skin="#d9a577", shirt="#dc2626", mood="sad"), True
    return inp


def judge(res: R.RenderResult, fmt: F.Format, *, size_exact: bool = False) -> list[str]:
    """The problems of one render (empty = fine): wrong size, blank, no title, text outside the canvas / safe area / in an avoid zone."""
    problems: list[str] = []
    if size_exact and res.image.size != fmt.size:
        problems.append(f"size {res.image.size} != {fmt.size}")
    if _stddev(res.image) < MIN_STD:
        problems.append("blank")
    titles = [t for t in res.texts if t["name"].startswith("title")]
    if not titles:
        problems.append("no title")
    W, H = res.size
    sx0, sy0, sx1, sy1 = F.safe_rect(fmt, res.size)
    pad = W * 0.05
    avoid = F.avoid_rects(fmt, res.size)
    for t in res.texts:
        x0, y0, x1, y1 = t["bbox"]
        if not (0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H):
            problems.append(f"{t['name']} outside the canvas")
        if t["name"].startswith("title"):
            if x0 < sx0 - pad or x1 > sx1 + pad or y0 < sy0 - pad or y1 > sy1 + pad:
                problems.append("title outside the safe area")
            if any(_overlap_frac(t["bbox"], a) >= 0.12 for a in avoid):
                problems.append("title in an avoid zone")
    return problems


def check_covers(work: Path) -> dict:
    inp = sample_inputs()
    content = fixtures.sample_content("fa")
    bad: list[str] = []
    t0 = time.time()
    n = 0
    for key, fmt in F.FORMATS.items():                       # the exact size of every format (the full-size render)
        sp = R.clean_spec({"format": key, "style": "episode_card", "lang": "fa", "content": content}, STYLES)
        res = R.render(sp, inp, scale=1.0)
        n += 1
        for p in judge(res, fmt, size_exact=True):
            bad.append(f"episode_card/{key}: {p}")
        if fmt.max_kb:
            jpg = R.to_jpeg_bytes(res.image, 90, fmt.max_kb)
            if len(jpg) > fmt.max_kb * 1024:
                bad.append(f"{key}: the JPEG is {len(jpg) // 1024} KB (over {fmt.max_kb})")
    for style in STYLES:                                     # every layout in every format, small
        for key, fmt in F.FORMATS.items():
            sp = R.clean_spec({"format": key, "style": style, "lang": "fa", "content": content}, STYLES)
            res = R.render(sp, inp, scale=SMALL)
            n += 1
            for p in judge(res, fmt):
                bad.append(f"{style}/{key}: {p}")
    secs = round(time.time() - t0, 1)
    from .engine import typo

    engine = "raqm" if typo.use_raqm() else "built-in"
    if bad:
        return _r("fail", f"سازندهٔ کاور در {_fd(len(bad))} حالت درست کار نکرد (مثلاً «{bad[0]}»). گزارش را برای پشتیبانی بفرستید.",
                  f"The cover maker failed in {len(bad)} case(s) (for example \"{bad[0]}\").", failures=bad[:12], renders=n, seconds=secs, engine=engine)
    return _r("ok", f"{_fd(len(STYLES))} طرح در {_fd(len(F.FORMATS))} اندازه ساخته شد ({_fd(n)} تصویر در {_fd(secs)} ثانیه): اندازه‌ها دقیق، تصویرها پر، متنِ فارسی (حرف‌چینی {engine}) داخلِ حاشیهٔ امن.",
              f"{len(STYLES)} layouts in {len(F.FORMATS)} sizes were made ({n} pictures in {secs} s): exact sizes, nothing blank, the Persian text ({engine} shaping) inside the safe area.",
              renders=n, seconds=secs, engine=engine, styles=len(STYLES), formats=len(F.FORMATS))


def check_covers_bg(work: Path) -> dict:
    """One real 512x512 background from ComfyUI, composited under a layout. WAITS (pending) when ComfyUI / the model is not there; runs by itself later."""
    from instai.ops import pcselftest
    from instai.providers.base import ProviderError

    from . import background

    st = background.engine_state()
    if st["demo"]:
        return _r("skip", "حالت آزمایشی روشن است و تصویر واقعی ساخته نمی‌شود؛ در «تنظیمات» موتور تصویر را روی ComfyUI بگذارید.", "Demo mode is on and no real image is made; set the image engine to ComfyUI in Settings.")
    ctx = pcselftest._CTX[0]
    if ctx is None:
        return _r("pending", "آزمونِ پس‌زمینهٔ هوش مصنوعی فقط از داخلِ «آزمون خودکار» اجرا می‌شود.", "The AI-background check only runs from the automatic self-test job.")
    try:
        out = background.probe(ctx, work)
    except ProviderError as e:
        if e.wait or e.code in ("comfy_down", "worker_offline", "worker_lost", "gpu_busy"):
            return _r("pending", "ComfyUI یا مدلِ تصویر هنوز آماده نیست؛ همین که آماده شد پس‌زمینهٔ کاور خودکار آزمایش می‌شود.", "ComfyUI or the image model is not ready yet; the cover background is tested by itself as soon as it is.")
        raise
    with Image.open(out["path"]) as im:
        pic = im.convert("RGB")
    flat = _stddev(pic)
    if pic.size != (512, 512) or flat < 6:
        return _r("fail", f"پس‌زمینهٔ ساخته‌شده درست نیست (اندازه {pic.size}، پراکندگی {_fd(round(flat, 1))}).", f"The background made is wrong (size {pic.size}, spread {flat:.1f}).", size=list(pic.size), spread=round(flat, 1))
    inp = sample_inputs()
    inp.background = pic
    sp = R.clean_spec({"format": "youtube", "style": "episode_card", "lang": "fa", "content": fixtures.sample_content("fa"), "background": {"kind": "ai"}}, STYLES)
    res = R.render(sp, inp, scale=0.4)
    probs = judge(res, F.get("youtube"))
    if probs:
        return _r("fail", "با پس‌زمینهٔ هوش مصنوعی کاور درست ساخته نشد: " + "، ".join(probs), "The cover did not come out right with the AI background: " + ", ".join(probs), problems=probs)
    keep = pcselftest.report_path().parent / "covers-bg-sample.png"
    keep.parent.mkdir(parents=True, exist_ok=True)
    res.image.save(keep)
    return _r("ok", f"یک پس‌زمینهٔ ۵۱۲×۵۱۲ با ComfyUI روی {out.get('device', '?')} ساخته شد و زیرِ طرحِ کاور درست نشست.",
              f"A 512x512 background was made by ComfyUI on {out.get('device', '?')} and sat correctly under the cover layout.", device=out.get("device"), seconds=out.get("seconds"),
              workflow=out.get("workflow"), sample="covers-bg-sample.png")
