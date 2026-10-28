"""Helpers of the Studio screen tests: a browser context per language/size with problem collection, readiness waits, a tone WAV."""
from __future__ import annotations

import io
import math
import os
import re
import struct
import tempfile
import wave
from pathlib import Path

VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 390, "height": 844}}
SHOTS = Path(os.environ.get("INSTAI_UI_SHOTS", tempfile.gettempdir())) / "instai-ui-shots"
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
PERSIAN = re.compile(r"[؀-ۿ]")


def open_studio(browser, base: str, size: str, path: str, lang: str = "fa"):
    """(context, page, problems): console errors, page errors and HTTP >= 400 are collected in `problems`."""
    ctx = browser.new_context(viewport=VIEWPORTS[size], locale="fa-IR" if lang == "fa" else "en-US", has_touch=(size == "phone"))
    ctx.add_init_script(f"try {{ localStorage.setItem('instai.lang', '{lang}'); }} catch (e) {{}}")
    page = ctx.new_page()
    problems: list[str] = []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "favicon" not in r.url else None)
    page.goto(base + path, wait_until="domcontentloaded")
    page.wait_for_selector("main h1", timeout=20000)
    return ctx, page, problems


def digits(text: str) -> str:
    """Persian/Arabic-Indic digits -> ASCII, so assertions work in both languages."""
    return (text or "").translate(PERSIAN_DIGITS)


def hscroll(page) -> tuple[int, int]:
    return tuple(page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]"))


def tone_wav(seconds: float = 4.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 220 * i / rate) * (0.6 + 0.4 * math.sin(2 * math.pi * 3 * i / rate))))
                               for i in range(int(seconds * rate))))
    return buf.getvalue()
