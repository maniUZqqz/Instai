"""The automatic self-test of THIS PC: does the program really work here, with the GPU and the tools it needs? (0.14.0)

The owner asked that nothing be left for him to do once the GPU PC is on: every feature must start working AND be tested by itself. The studio pipeline already
tests itself (`instai/studio/selftest.py`); this is the same idea for the machine under it. Each check is one small REAL action (an ffmpeg encode, a Persian line drawn
with the real font, one still rendered through Remotion, a few tokens from the real Ollama model, ComfyUI started and asked about its card ...), judged on its own:

  ok       it worked                                  warn   it works but something should be looked at       fail   it does not work (with the reason and the fix)
  skip     does not apply to this PC (not Windows)    pending  it WAITS for something (the GPU PC is off, Ollama is not running, Remotion is still installing) and runs by itself the moment it can

* The cheap checks (database, disk, ffmpeg, Persian text, the update channel, autostart) run once for every new version and again every day.
* The tool checks (Remotion) and the GPU checks (the card, NVENC, the Ollama model on the GPU, ComfyUI on the GPU) run as soon as THEIR OWN requirement is there (the ones that
  load a model or an encoder also wait until nobody works hard on the card: under 40 % utilization); a check that waited is not repeated more often than every 15 minutes, a
  check that ran is not repeated by itself for a week (the cheap ones: a day).
* The report is `data/selftest/pc.json` and is shown on the System screen; a failing check is a result, never a crashed job. It writes nothing to the owner's database and
  publishes nothing. Off with `INSTAI_PC_SELFTEST_AUTO=0` or the setting `pc_selftest_auto`.

The update channel check is the one that tells the owner (and anybody who reads the report) whether this folder can bring itself up to date: a folder that came from an old
"Download ZIP" has a START.bat without the updater, and the check says so with the one thing to do (the NMarketing node does it by itself when it is on).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from instai.jobs import describe
from instai.jobs.registry import handler

log = logging.getLogger("instai.pcselftest")

describe.KIND_TEXT.update({"system.selftest": ("آزمون خودکار این رایانه", "Automatic self-test of this PC")})

ROOT = Path(__file__).resolve().parents[2]
AUTO_EVERY_S = 300
RETRY_WAITING_S = 15 * 60               # a check that waited although its own requirement was there is not hammered
RETRY_PROBLEM_S = 60 * 60               # a warning / failure is looked at again after an hour (the owner may have fixed it)
REFRESH_BASE_S = 24 * 3600              # the cheap checks, once a day
REFRESH_HEAVY_S = 7 * 24 * 3600         # tool and GPU checks, once a week
VERSION_RETRY_S = 6 * 3600              # a result of an older version is made again by itself, but several updates in one day do not repeat the heavy checks
CONCLUSIVE = ("ok", "warn", "fail", "skip")       # the check really ran (or does not apply); "pending" means it still has to
_LAST_AUTO = [0.0]
_CTX = [None]                       # the job context of the self-test run that is going on (the GPU checks that need `compute.run_task` read it)
_FA_DIGITS = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")
GITHUB_REPO = "maniUZqqz/Instai"


def _fd(v) -> str:
    """A number inside a Persian sentence is written with Persian digits."""
    return str(v).translate(_FA_DIGITS)


def _r(verdict: str, fa: str, en: str, **metrics) -> dict:
    return {"verdict": verdict, "reason_fa": fa, "reason_en": en, "metrics": metrics}


def report_path() -> Path:
    return Path(settings.DATA_DIR) / "selftest" / "pc.json"


def load_report() -> dict | None:
    try:
        return json.loads(report_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_report(rep: dict) -> None:
    p = report_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def stamp() -> str:
    """Changes with the version of the program, so a new version is tested again by itself."""
    from instai.version import read_version

    return read_version()


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ------------------------------------------------------------------------------------------------------------------------------ cheap checks

def check_database(work: Path) -> dict:
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from instai.jobs.models import Job

    with connection.cursor() as c:
        c.execute("PRAGMA journal_mode")
        mode = str(c.fetchone()[0]).lower()
    ex = MigrationExecutor(connection)
    pending = ex.migration_plan(ex.loader.graph.leaf_nodes())
    jobs = Job.objects.count()
    if pending:
        return _r("fail", f"پایگاه‌داده کامل به‌روز نشده ({_fd(len(pending))} مهاجرت مانده)؛ START.bat را یک بار دیگر اجرا کنید.",
                  f"The database is not fully migrated ({len(pending)} migrations pending); run START.bat once more.", pending=len(pending), journal=mode)
    return _r("ok", f"پایگاه‌داده سالم و به‌روز است (حالت {mode.upper()}؛ {_fd(jobs)} کار در صف و تاریخچه).",
              f"The database is sound and migrated ({mode.upper()} mode; {jobs} jobs in the queue and history).", journal=mode, jobs=jobs)


def check_disk(work: Path) -> dict:
    from instai.core import hardware, runtime

    rows = {}
    for name, p in (("data", Path(settings.DATA_DIR)), ("models", runtime.models_root())):
        try:
            rows[name] = hardware.disk_info(p)
        except Exception:  # noqa: BLE001
            continue
    if not rows:
        return _r("skip", "اندازهٔ فضای دیسک خوانده نشد.", "The free disk space could not be read.")
    low = min(rows.values(), key=lambda d: d["free_gb"])
    gb = low["free_gb"]
    free = {k: v["free_gb"] for k, v in rows.items()}
    if gb < 3:
        return _r("fail", f"فضای دیسک تقریباً پر است ({_fd(gb)} گیگابایت آزاد). ساخت ویدئو و دانلود مدل متوقف می‌شود؛ جا باز کنید.",
                  f"The disk is almost full ({gb} GB free). Video rendering and model downloads stop; free some space.", free_gb=free)
    if gb < 20:
        return _r("warn", f"فضای آزاد کم است ({_fd(gb)} گیگابایت). یک مدل تصویر یا ویدئو چند گیگابایت است؛ بهتر است دست‌کم ۲۰ گیگابایت جا داشته باشید.",
                  f"Free space is low ({gb} GB). A single image or video model is several GB; keep at least 20 GB free.", free_gb=free)
    return _r("ok", f"فضای دیسک کافی است ({_fd(gb)} گیگابایت آزاد).", f"There is enough disk space ({gb} GB free).", free_gb=free)


def _ffmpeg_encode(ff: str, out: Path, codec: str, timeout: float = 90) -> tuple[bool, str, float]:
    cmd = [ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
           "-c:v", codec, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_flags(), stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")      # never a decode error from a Windows console code page
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {e}", time.time() - t0
    ok = r.returncode == 0 and out.is_file() and out.stat().st_size > 1500
    return ok, (r.stderr or "").strip()[-300:], time.time() - t0


def check_ffmpeg_encode(work: Path) -> dict:
    from instai.core import runtime

    info = runtime.ffmpeg_info()
    if not info["ffmpeg"]:
        return _r("fail", "ffmpeg پیدا نشد؛ START.bat آن را خودکار در پوشهٔ tools می‌گذارد.", "ffmpeg was not found; START.bat puts it in the tools folder by itself.")
    feats = info.get("features") or {}
    missing = [k for k in ("libx264", "ass", "zoompan", "xfade") if not feats.get(k)]
    out = work / "enc.mp4"
    ok, err, secs = _ffmpeg_encode(info["ffmpeg"], out, "libx264")
    if not ok:
        return _r("fail", "ffmpeg یک کلیپ یک‌ثانیه‌ای را رمزگذاری نکرد: " + (err[-160:] or "بی‌پیام"), "ffmpeg could not encode a one-second clip: " + (err[-160:] or "no message"),
                  version=info["version"], path=info["ffmpeg"])
    size = out.stat().st_size
    if missing:
        return _r("warn", f"ffmpeg کلیپ را ساخت ولی این امکانات را ندارد: {'، '.join(missing)}. مونتاژ کامل به این نسخه نیاز دارد؛ START.bat نسخهٔ درست را می‌گذارد.",
                  f"ffmpeg encoded the clip but lacks: {', '.join(missing)}. The full assembly needs those; START.bat installs a build that has them.", version=info["version"], missing=missing)
    return _r("ok", f"ffmpeg {info['version']} یک کلیپ یک‌ثانیه‌ای را در {_fd(round(secs, 2))} ثانیه رمزگذاری کرد.", f"ffmpeg {info['version']} encoded a one-second clip in {secs:.2f} s.",
              version=info["version"], bytes=size, seconds=round(secs, 2))


def check_persian_text(work: Path) -> dict:
    """A Persian line is drawn with the program's own font and the picture must really contain ink (the font file is there, the shaping did not fail)."""
    from PIL import Image, ImageDraw

    from instai.render import fa_text

    img = Image.new("L", (900, 140), 0)
    fnt = fa_text.font(56, True)
    fa_text.draw_text(ImageDraw.Draw(img), (870, 70), "سلام؛ این یک آزمون فارسی است ۱۲۳", fnt, 255, anchor="rm")
    bbox = img.getbbox()
    ink = img.point(lambda v: 255 if v > 128 else 0).histogram()[255]
    engine = "raqm" if fa_text._use_raqm(fnt) else "built-in"
    if "vazirmatn" not in str(getattr(fnt, "path", "")).lower():              # Pillow's own fallback font is not the program's font (and has no Persian letters)
        return _r("fail", "فونت فارسی برنامه (Vazirmatn) بارگذاری نشد؛ متن فارسی روی تصویرها و ویدئوها درست دیده نمی‌شود. پوشهٔ فونت را بررسی کنید.",
                  "The program's Persian font (Vazirmatn) did not load; Persian text on pictures and videos will not show properly. Check the font folder.")
    if not bbox or ink < 400:
        return _r("fail", "متن فارسی روی تصویر کشیده نشد (تصویر خالی ماند).", "The Persian text was not drawn (the picture stayed empty).", ink=ink)
    if engine == "built-in" and not fa_text.RAQM_OK:
        return _r("ok", "متن فارسی با فونت برنامه کشیده شد (حرف‌چینی داخلیِ برنامه؛ موتور raqm در این رایانه نیست و لازم هم نیست).",
                  "Persian text was drawn with the program's font (its own letter shaping; the raqm engine is not on this PC and is not needed).", engine=engine, ink=ink)
    return _r("ok", "متن فارسی با فونت برنامه و حرف‌چینی درست کشیده شد.", "Persian text was drawn with the program's font and proper shaping.", engine=engine, ink=ink)


def _delivery_tools(work: Path):
    """(numpy-based fixtures, ffmpeg path) or a ready result row: both are needed by the two delivery checks."""
    from instai.core import runtime
    from instai.render import audioqc

    if not audioqc.available():
        return None, None, _r("warn", "بستهٔ numpy روی این رایانه نیست؛ بررسی صدا (اکو، بلندی) کار نمی‌کند. START.bat آن را از requirements.txt نصب می‌کند.",
                              "numpy is not installed on this PC, so the sound checks (echo, loudness) cannot run. START.bat installs it from requirements.txt.")
    ff = runtime.ffmpeg_info()["ffmpeg"]
    if not ff:
        return None, None, _r("fail", "ffmpeg پیدا نشد؛ START.bat آن را خودکار در پوشهٔ tools می‌گذارد.", "ffmpeg was not found; START.bat puts it in the tools folder by itself.")
    from instai.render import audiofixtures

    return audiofixtures, ff, None


def check_delivery_loudness(work: Path) -> dict:
    """The delivery loudness: a 3 s synthetic video with speech-like sound is made 4 LU too quiet (-18), then settled to -14 LUFS like a final render, and measured again
    with the platforms' meter: within +-0.8 LU of the target and under -1 dBTP (render/loudness.py, docs/DELIVERY.md)."""
    from instai.render import loudness

    fx, ff, row = _delivery_tools(work)
    if row:
        return row
    wav = fx.write_wav(work / "speech.wav", fx.speechlike(3.0, seed=7))
    mp4 = fx.synthetic_video(work / "speech.mp4", wav, ffmpeg_exe=ff, seconds=3.0, loudnorm_to=-18.0)
    rep = loudness.settle(mp4, target=-14.0)
    after = loudness.measure(mp4) or {}
    if not rep or after.get("lufs") is None:
        return _r("fail", "بلندی صدای فایل آزمایشی اندازه‌گیری نشد (ffmpeg فیلتر ebur128 را ندارد؟).", "The loudness of the test file could not be measured (does ffmpeg lack the ebur128 filter?).")
    off, tp = abs(after["lufs"] + 14.0), after.get("tp")
    m = dict(before=rep.get("before"), after=after["lufs"], tp=tp, rounds=rep.get("rounds"), gain_db=rep.get("gain_db"))
    if off <= 0.8 and tp is not None and tp <= -0.95:
        return _r("ok", f"بلندی صدا از {_fd(rep['before'])} به {_fd(after['lufs'])} LUFS رسید (هدف ‎-۱۴؛ اوج {_fd(tp)} dBTP، {_fd(rep.get('rounds', 0))} دور).",
                  f"Loudness went from {rep['before']} to {after['lufs']} LUFS (target -14; true peak {tp} dBTP, {rep.get('rounds', 0)} round(s)).", **m)
    return _r("fail", f"پس از اصلاح، بلندی {_fd(after['lufs'])} LUFS و اوج {_fd(tp)} dBTP ماند (باید در ±۰٫۸ از ‎-۱۴ و زیر ‎-۱ باشد).",
              f"After the correction the loudness is {after['lufs']} LUFS and the peak {tp} dBTP (it must be within 0.8 of -14 and under -1).", **m)


def check_delivery_echo(work: Path) -> dict:
    """The sound check on two real files: a mix whose narration plays twice 150 ms apart must report the echo, a clean mix of the same length must report nothing."""
    from instai.render import audioqc

    fx, ff, row = _delivery_tools(work)
    if row:
        return row
    clean = fx.speechlike(3.5, seed=11)
    doubled = fx.delayed_copy(clean, 0.15, 0.9)
    reps = {}
    for name, x in (("clean", clean), ("doubled", doubled)):
        wav = fx.write_wav(work / f"{name}.wav", x)
        reps[name] = audioqc.analyze_file(fx.synthetic_video(work / f"{name}.mp4", wav, ffmpeg_exe=ff, seconds=3.5))
    c, d = reps["clean"].get("echo") or {}, reps["doubled"].get("echo") or {}
    m = dict(clean_strength=c.get("strength"), doubled_strength=d.get("strength"), doubled_lag=d.get("lag_s"))
    if d.get("doubled") and abs((d.get("lag_s") or 0) - 0.15) <= 0.03 and not c.get("doubled"):
        return _r("ok", f"گفتارِ دوبار پخش‌شده پیدا شد (فاصلهٔ {_fd(int(round(d['lag_s'] * 1000)))} میلی‌ثانیه) و مخلوط سالم چیزی گزارش نکرد.",
                  f"The doubled narration was found ({int(round(d['lag_s'] * 1000))} ms apart) and the clean mix reported nothing.", **m)
    if c.get("doubled"):
        return _r("fail", "مخلوط سالم هم اکو گزارش کرد (هشدار کاذب).", "The clean mix reported an echo too (a false alarm).", **m)
    return _r("fail", "گفتارِ عمداً دوبار پخش‌شده پیدا نشد.", "The deliberately doubled narration was not found.", **m)


def check_captions(work: Path) -> dict:
    """Word-by-word captions: each of the seven presets renders one second of a dark clip through the real ffmpeg + libass, in a vertical and a landscape frame; the frame must
    hold caption ink inside the platform's safe zone, the ASS script must have no unescaped brace and the colours must pass the contrast rule. Skipped (not failed) when this
    ffmpeg has no `ass` filter: the ffmpeg row already says so."""
    from instai.core import runtime
    from instai.render import captions_check, ffmpeg

    info = runtime.ffmpeg_info()
    if not info["ffmpeg"] or not (info.get("features") or {}).get("ass"):
        return _r("skip", "ffmpeg این رایانه فیلتر زیرنویس (ass) ندارد؛ ردیف «رمزگذاری ویدئو» دلیل و راه‌حل را می‌گوید.",
                  "This PC's ffmpeg has no subtitle (ass) filter; the video-encoding row gives the reason and the fix.")
    t0 = time.time()
    try:
        rows = captions_check.run(work, shapes=("vertical", "landscape"))
    except ffmpeg.FFmpegError as e:
        return _r("fail", "ffmpeg یکی از قالب‌های زیرنویس را نکشید: " + str(e)[-160:], "ffmpeg could not draw one of the caption presets: " + str(e)[-160:])
    bad = [r for r in rows if not r["ok"]]
    injection = captions_check.injection_ok()
    secs = round(time.time() - t0, 2)
    if bad:
        first = bad[0]
        return _r("fail", f"قالب «{first['preset']}» ({first['shape']}) درست کشیده نشد: {first['reason'] or 'نامعلوم'}",
                  f"The preset «{first['preset']}» ({first['shape']}) was not drawn properly: {first['reason'] or 'unknown'}", bad=[f"{r['preset']}/{r['shape']}" for r in bad])
    if not injection:
        return _r("fail", "متن کاربر می‌تواند در اسکریپت زیرنویس تگ بسازد (آکولادها درست محافظت نشده‌اند).", "A typed text can inject tags into the caption script (braces are not escaped properly).")
    return _r("ok", f"{_fd(len(rows))} نمونه (هفت قالب در دو شکل قاب) با libass کشیده شد؛ زیرنویس همه داخل حاشیهٔ امن بود ({_fd(secs)} ثانیه).",
              f"{len(rows)} samples (seven presets in two frame shapes) were drawn with libass; every caption was inside the safe zone ({secs} s).", samples=len(rows), seconds=secs)


def _read_start_bat() -> str:
    try:
        return (ROOT / "START.bat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _update_log_tail() -> tuple[str, float | None]:
    """(last line, its age in seconds) of data/logs/update.log written by scripts/self_update.py."""
    p = ROOT / "data" / "logs" / "update.log"
    try:
        lines = [x for x in p.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
        if not lines:
            return "", None
        line = lines[-1]
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) ", line)
        age = (datetime.now() - datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")).total_seconds() if m else None
        return line[:200], age
    except (OSError, ValueError):
        return "", None


def _remote_version(timeout: float = 8.0) -> str:
    """VERSION of GitHub's main ('' when it cannot be read: offline, blocked, rate limit). INSTAI_UPDATE_RAW points tests at a local server."""
    repo = os.environ.get("INSTAI_UPDATE_REPO") or GITHUB_REPO
    branch = os.environ.get("INSTAI_UPDATE_BRANCH") or "main"
    base = (os.environ.get("INSTAI_UPDATE_RAW") or "https://raw.githubusercontent.com").rstrip("/")
    try:
        req = urllib.request.Request(f"{base}/{repo}/{branch}/VERSION", headers={"User-Agent": "InstAI-selftest/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            v = r.read(200).decode("ascii", "ignore").strip().splitlines()[0].strip()
        return v if re.match(r"^\d+\.\d+\.\d+$", v) else ""
    except Exception:  # noqa: BLE001
        return ""


def check_update_channel(work: Path) -> dict:
    from instai.version import read_version, tuple_of

    local = read_version()
    bat = _read_start_bat()
    has_updater = "self_update.py" in bat
    script = (ROOT / "scripts" / "self_update.py").is_file()
    mode = "git" if (ROOT / ".git").exists() else "zip"
    last, age = _update_log_tail()
    metrics = {"local": local, "mode": mode, "start_bat_has_updater": has_updater, "updater_script": script, "last_update_line": last}
    if not bat:
        return _r("warn", "فایل START.bat در این پوشه نیست؛ به‌روزرسانی خودکار هنگام راه‌اندازی کار نمی‌کند. ZIP تازهٔ برنامه را از GitHub بگیرید و روی این پوشه کپی کنید.",
                  "START.bat is not in this folder, so the automatic update at start-up cannot run. Download the fresh ZIP from GitHub and copy it over this folder.", **metrics)
    if not has_updater or not script:
        return _r("warn", "START.bat این پوشه قدیمی است و خودش را به‌روز نمی‌کند (این پوشه از یک «Download ZIP» قدیمی مانده). یک بار ZIP تازهٔ برنامه را از GitHub روی این پوشه کپی کنید "
                          "(پوشه‌های data و models و فایل .env دست‌نخورده می‌مانند)؛ از آن به بعد همه‌چیز خودکار است. اگر پردازشگر NMarketing روی همین رایانه روشن باشد، همین کار را خودش می‌کند.",
                  "This folder's START.bat is old and cannot update itself (the folder is from an old Download-ZIP). Copy the fresh ZIP from GitHub over this folder once "
                  "(data, models and .env stay untouched); everything is automatic after that. When the NMarketing processing node is on this PC it does that by itself.", **metrics)
    remote = _remote_version()
    metrics["github"] = remote
    if not remote:
        return _r("warn", f"روی این رایانه به‌روزرسانی خودکار نصب است ({'git' if mode == 'git' else 'ZIP'})؛ ولی همین حالا GitHub در دسترس نبود تا نسخهٔ تازه سنجیده شود. دوباره سنجیده می‌شود.",
                  f"The automatic updater is installed here ({mode}), but GitHub could not be reached just now to compare versions. It is checked again later.", **metrics)
    lv, rv = tuple_of(local), tuple_of(remote)
    if rv > lv:
        return _r("warn", f"نسخهٔ تازه‌تر روی GitHub هست (v{remote}؛ این پوشه v{local}). با STOP.bat و سپس START.bat نصب می‌شود (و بعد از هر ورود به ویندوز هم خودکار).",
                  f"GitHub has a newer version (v{remote}; this folder is v{local}). It installs with STOP.bat then START.bat (and by itself at every Windows logon).", **metrics)
    if rv < lv:
        return _r("warn", f"این پوشه (v{local}) از GitHub (v{remote}) جلوتر است: بهبودهای تازه هنوز روی GitHub نرفته‌اند، پس رایانه‌ای که از GitHub به‌روز می‌شود آن‌ها را نمی‌گیرد.",
                  f"This folder (v{local}) is ahead of GitHub (v{remote}): the latest improvements are not pushed yet, so a PC that updates from GitHub does not get them.", **metrics)
    return _r("ok", f"نسخه v{local} با GitHub یکی است و به‌روزرسانی خودکار نصب است" + (f" (آخرین بررسی: {last[:19]})." if last else "."),
              f"v{local} is the same as GitHub's and the automatic updater is installed" + (f" (last check: {last[:19]})." if last else "."), **metrics)


def check_autostart(work: Path) -> dict:
    sys_path = str(ROOT / "scripts")
    import importlib.util

    spec = importlib.util.spec_from_file_location("instai_autostart", Path(sys_path) / "autostart.py")
    mod = importlib.util.module_from_spec(spec)           # type: ignore[arg-type]
    spec.loader.exec_module(mod)                          # type: ignore[union-attr]
    st = mod.status(str(ROOT))
    if not st.get("supported"):
        return _r("skip", "راه‌اندازی خودکار با ورود به ویندوز فقط روی ویندوز معنا دارد.", "Starting at logon only applies to Windows.", **{k: st.get(k) for k in ("folder",)})
    if st.get("disabled"):
        return _r("skip", f"راه‌اندازی خودکار با انتخاب خودتان خاموش است ({st['disabled']}).", f"Starting at logon is switched off on purpose ({st['disabled']}).", disabled=st["disabled"])
    if not st.get("registered"):
        return _r("warn", "برنامه هنگام ورود به ویندوز خودش بالا نمی‌آید. START.bat را یک بار اجرا کنید تا میان‌بُرش در پوشهٔ Startup ساخته شود.",
                  "InstAI does not start by itself at Windows logon. Run START.bat once; it adds the shortcut to the Startup folder.", folder=st.get("folder"))
    return _r("ok", "برنامه با هر ورود به ویندوز خودش بالا می‌آید (میان‌بُر در پوشهٔ Startup هست).", "InstAI starts by itself at every Windows logon (the shortcut is in the Startup folder).", path=st.get("path"))


# ------------------------------------------------------------------------------------------------------------------------------ Remotion

def check_remotion_toolchain(work: Path) -> dict:
    from instai.remotion import toolchain

    toolchain.clear_cache()
    st = toolchain.status()
    parts = {"node": bool(st["node"]), "packages": bool(st["packages"]), "browser": bool(st["browser"])}
    if st["ready"]:
        return _r("ok", f"ابزار «ویدئو با کد» آماده است (Node.js {st['node']['version']}، بسته‌ها و مرورگر).", f"The code-to-video toolchain is ready (Node.js {st['node']['version']}, packages and browser).",
                  node_version=st["node"]["version"], **parts)
    if st["state"] == "error":
        return _r("fail", "نصب ابزار «ویدئو با کد» کامل نشد: " + (st.get("error_fa") or st["message_fa"] or "بی‌پیام")[:200] + " — در صفحهٔ Remotion دکمهٔ «نصب دوباره» هست.",
                  "The code-to-video toolchain did not install: " + (st["error"] or st["message_en"] or "no message")[:200] + " - the Remotion page has a re-install button.", **parts)
    from instai.jobs.handlers.remotion import kick_setup

    if st["auto"] and st["state"] != "running":
        kick_setup()                                           # idempotent: the setup takes a lock, so a second call does not run twice
    wait = st["message_fa"] or "نصب خودکار در پس‌زمینه انجام می‌شود (Node.js، بسته‌ها، مرورگر)."
    return _r("pending", "ابزار «ویدئو با کد» هنوز نصب نشده؛ خودش نصب می‌شود و بعد دوباره آزمایش می‌شود. " + wait, "The code-to-video toolchain is not installed yet; it installs by itself and is tested again after that. "
              + (st["message_en"] or ""), **parts, phase=st.get("phase"))


def check_remotion_render(work: Path) -> dict:
    """One still of one composition through the real toolchain: Node + the bundled project + the browser + the Persian font, about 10-60 s."""
    from instai.jobs.handlers.remotion import EVENT, node_env
    from instai.remotion import kit as kitmod
    from instai.remotion import toolchain

    st = toolchain.status()
    if not st["ready"]:
        return _r("pending", "ساخت آزمایشی Remotion منتظر پایان نصب ابزار است.", "The Remotion trial render waits for the toolchain to finish installing.")
    node, browser = st["node"], st["browser"]
    out = work / "still.png"
    kit = kitmod.style_kit(None, None)
    spec = {"composition": "TitleCard", "props": {"title": "آزمون خودکار", "subtitle": "InstAI", "kit": kit, "size": "square"}, "out": str(out), "still": 30,
            "browser": browser["path"], "chrome_mode": browser["mode"], "crf": 28, "hw_accel": False, "bundle_dir": str(toolchain.work_dir() / "bundles")}
    spec_path = work / "job.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    t0 = time.time()
    try:
        r = subprocess.run([node["path"], str(toolchain.PROJECT / "render.mjs"), str(spec_path)], cwd=str(toolchain.PROJECT), capture_output=True, text=True, timeout=420,
                           env=node_env(node["path"]), creationflags=_flags(), stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        return _r("fail", f"Remotion اجرا نشد: {type(e).__name__}", f"Remotion could not be started: {type(e).__name__}: {e}")
    events = []
    for line in (r.stdout or "").splitlines():
        if line.startswith(EVENT):
            try:
                events.append(json.loads(line[len(EVENT):]))
            except ValueError:
                pass
    comp = next((e for e in events if e.get("event") == "composition"), {})
    err = next((e for e in events if e.get("event") == "error"), None)
    size = out.stat().st_size if out.is_file() else 0
    secs = round(time.time() - t0, 1)
    if r.returncode != 0 or err or size < 4000:
        from instai.jobs.handlers.remotion import explain

        msg = (err or {}).get("message") or (r.stderr or r.stdout or "")[-300:] or "the renderer stopped without a message"
        return _r("fail", "یک قاب آزمایشی با Remotion ساخته نشد. " + (explain(msg) or "جزئیات فنی در گزارش این آزمون هست."), "A trial frame could not be rendered with Remotion: " + msg[:240],
                  seconds=secs, bytes=size)
    return _r("ok", f"یک قاب آزمایشی با Remotion ساخته شد ({_fd(comp.get('width', '?'))}×{_fd(comp.get('height', '?'))}، {_fd(secs)} ثانیه).",
              f"A trial frame was rendered with Remotion ({comp.get('width', '?')}x{comp.get('height', '?')}, {secs} s).", seconds=secs, bytes=size, width=comp.get("width"), height=comp.get("height"))


# ------------------------------------------------------------------------------------------------------------------------------ motion graphics (the scene-plan engine)

def check_motion_library(work: Path) -> dict:
    """The component library without a browser: every one of the 19 components has a valid sample in both languages, the deterministic plan of a narration is valid and as long as the
    shot, the rule checks run on it. About a second; it never waits for anything."""
    from instai.motion_plan import components, fallback, qa, specs
    from instai.remotion import kit as kitmod

    try:
        for cid in components.COMPONENTS:
            for lang in ("fa", "en"):
                specs.normalize_scene(components.sample(cid, lang), 0)
        kit = kitmod.style_kit(None, None)
        plan = fallback.make_plan("آب روی زمین ۷۱ درصد سطح را پوشانده است. ابتدا بخار می‌شود، سپس ابر می‌سازد و در نهایت باران می‌شود.", 12.0, kit=kit, style=kit["key"])
        found = qa.static_findings(plan, kit)
    except Exception as e:  # noqa: BLE001 - a broken library is a failed check
        return _r("fail", f"کتابخانهٔ قطعه‌های گرافیک متحرک خراب است: {type(e).__name__}", f"The motion-graphics component library is broken: {type(e).__name__}: {e}"[:300])
    n = len(components.COMPONENTS)
    return _r("ok", f"کتابخانهٔ گرافیک متحرک سالم است ({_fd(n)} قطعه، فارسی و انگلیسی؛ طرح خودکار از گفتار {_fd(len(plan['scenes']))} صحنه).",
              f"The motion-graphics library is healthy ({n} components in Persian and English; the automatic plan of a narration has {len(plan['scenes'])} scenes).",
              components=n, scenes=len(plan["scenes"]), findings=len(found))


def check_motion_frames(work: Path) -> dict:
    """One frame of every component in landscape, vertical and square through the REAL toolchain, then the rule checks over what the page reported (overflow, overlap, safe area,
    size, contrast). About 1-3 minutes."""
    from instai.motion_plan import selftest
    from instai.remotion import toolchain

    st = toolchain.status()
    if not st["ready"]:
        return _r("pending", "بازبینی قطعه‌های گرافیک متحرک منتظر پایان نصب ابزار «ویدئو با کد» است.", "The check of the motion-graphics components waits for the code-to-video toolchain to finish installing.")
    t0 = time.time()
    try:
        rep = selftest.run_every_component(work, lang="fa", status=st)
    except Exception as e:  # noqa: BLE001
        return _r("fail", "ساخت قاب‌های آزمایشی قطعه‌های گرافیک متحرک انجام نشد: " + str(e)[:160], "The trial frames of the motion-graphics components could not be made: " + str(e)[:240])
    secs = round(time.time() - t0, 1)
    errors = [f for f in rep["findings"] if f["severity"] == "error"]
    warns = [f for f in rep["findings"] if f["severity"] == "warn"]
    total = len(rep["components"]) * len(rep["sizes"])
    m = dict(rendered=rep["rendered"], total=total, errors=len(errors), warnings=len(warns), seconds=secs)
    if rep["render_errors"] or rep["rendered"] < total:
        return _r("fail", f"فقط {_fd(rep['rendered'])} از {_fd(total)} قاب ساخته شد: " + "؛ ".join(rep["render_errors"])[:200], f"Only {rep['rendered']} of {total} frames were made: " + "; ".join(rep["render_errors"])[:240], **m)
    if errors:
        f = errors[0]
        return _r("fail", f"در {_fd(len(errors))} قاب مشکل چیدمان دیده شد (مثلاً {f['component']} در حالت {f['size']}): " + f["message"][:160],
                  f"{len(errors)} frame(s) have a layout problem (e.g. {f['component']} in {f['size']}): " + f["message_en"][:200], **m)
    if warns:
        return _r("warn", f"همهٔ {_fd(total)} قاب ساخته شد؛ {_fd(len(warns))} هشدار چیدمان (مثلاً متن نزدیک لبه).", f"All {total} frames were made; {len(warns)} layout warning(s) (e.g. text near an edge).", **m)
    return _r("ok", f"{_fd(total)} قاب (هر قطعه در سه اندازه) ساخته و سنجیده شد؛ مشکل چیدمان نیست ({_fd(secs)} ثانیه).",
              f"{total} frames (every component in three sizes) were made and measured; no layout problem ({secs} s).", **m)


def check_motion_critique(work: Path) -> dict:
    """One frame of a two-scene plan is shown to the owner's vision model through InstAI's own Ollama: the answer must be the JSON verdict the critique loop reads."""
    from instai.motion_plan import components, critique, qa, qa_browser, selftest, specs
    from instai.providers.base import ProviderError
    from instai.remotion import kit as kitmod
    from instai.remotion import toolchain

    st = toolchain.status()
    if not st["ready"]:
        return _r("pending", "نقد تصویری منتظر ابزار «ویدئو با کد» است.", "The visual critique waits for the code-to-video toolchain.")
    t0 = time.time()
    try:
        prov = critique.vision_provider()
    except ProviderError as e:
        if e.code == "no_vision_model":
            return _r("skip", "مدل بینایی (مثلاً qwen3-vl) در Ollama نصب نیست؛ نقد تصویری اجرا نمی‌شود و قاعده‌ها کار خود را می‌کنند.", "No vision model (e.g. qwen3-vl) is installed in Ollama; the visual critique does not run and the rule checks do their job.")
        return _r("pending", "Ollama روشن نیست؛ آزمون نقد تصویری بعداً خودکار اجرا می‌شود.", "Ollama is not running; the visual critique test runs by itself later.")
    kit = kitmod.style_kit(None, None)
    spec = specs.normalize_spec({"style": kit["key"], "size": "vertical", "lang": "fa", "scenes": [components.sample("kinetic_title", "fa") | {"duration": 4}, components.sample("list", "fa")]}, max_total=300)
    try:
        measure = qa_browser.make_measure(SimpleNamespaceCtx(), st, kit=kit, size="vertical", work=work, frames_fn=lambda s: critique.pick_frames(s, kit=kit))
        shots = measure(spec)
        res = critique.ask(prov, spec, shots)
    except Exception as e:  # noqa: BLE001
        return _r("fail", "نقد تصویری با مدل بینایی جواب قابل‌خواندن نداد: " + str(e)[:160], "The vision model gave no readable answer: " + str(e)[:240])
    secs = round(time.time() - t0, 1)
    return _r("ok", f"مدل بینایی ({prov.model}) فریم‌ها را دید و نظر داد: {'مشکلی نبود' if res['verdict'] == 'ok' else _fd(len(res['ops'])) + ' اصلاح پیشنهاد شد'} ({_fd(secs)} ثانیه).",
              f"The vision model ({prov.model}) looked at the frames and answered: {'no problem' if res['verdict'] == 'ok' else str(len(res['ops'])) + ' fix(es) suggested'} ({secs} s).",
              model=prov.model, answer=res["verdict"], issues=len(res["issues"]), seconds=secs)


class SimpleNamespaceCtx:
    """The minimum of a job context that the renderer helper needs when a check calls it without a job: logging and progress go nowhere, the command runs in this process."""

    def check(self):
        return None

    def log(self, *a, **k):
        return None

    def progress(self, *a, **k):
        return None

    def live(self, *a, **k):
        return None

    def run_cmd(self, cmd, cwd=None, on_line=None, timeout=900, env=None):
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env, creationflags=_flags(), stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        for line in (r.stdout or "").splitlines():
            if on_line:
                on_line(line)
        return r.returncode, (r.stdout or "") + (r.stderr or "")


def _vision_ready() -> bool:
    if not _ollama_ready():
        return False
    try:
        from instai.core import settings_store
        from instai.motion_plan import critique

        return bool(critique.vision_model(str(settings_store.effective("ollama_url"))))
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------------------------------------------------------------------ GPU checks

def check_gpu_card(work: Path) -> dict:
    from instai.core import hardware

    g = hardware.gpu_status()
    if not g:
        return _r("pending", "کارت گرافیک NVIDIA (یا درایورش) روی این رایانه دیده نشد. بررسی‌های GPU وقتی رایانهٔ GPUدار روشن شود خودکار اجرا می‌شوند.",
                  "No NVIDIA graphics card (or driver) was found on this PC. The GPU checks run by themselves once the GPU PC is on.")
    gb = round((g["total_mb"] or 0) / 1024, 1)
    m = dict(name=g["name"], vram_gb=gb, driver=g["driver"], used_mb=g["used_mb"])
    if gb < 11:
        return _r("warn", f"کارت {g['name']} با {_fd(gb)} گیگابایت حافظه دیده شد؛ ویدئوهای سنگین (Wan) روی آن کند یا ناموفق‌اند.", f"{g['name']} with {gb} GB was found; heavy video models (Wan) are slow or fail on it.", **m)
    return _r("ok", f"کارت {g['name']} با {_fd(gb)} گیگابایت حافظه و درایور {g['driver']} دیده شد.", f"{g['name']} with {gb} GB and driver {g['driver']} was found.", **m)


def _nvenc_listed(ff: str) -> bool:
    try:
        out = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15, creationflags=_flags(), encoding="utf-8", errors="replace").stdout
        return "h264_nvenc" in out
    except (OSError, subprocess.SubprocessError):
        return False


def check_nvenc(work: Path) -> dict:
    from instai.core import hardware, runtime

    if hardware.gpu_status() is None:
        return _r("pending", "بدون کارت NVIDIA رمزگذاری سخت‌افزاری ممکن نیست؛ با رسیدن رایانهٔ GPUدار خودکار آزمایش می‌شود.", "No NVIDIA card, no hardware encoding; it is tested by itself when the GPU PC is on.")
    ff = runtime.ffmpeg_info()["ffmpeg"]
    if not ff:
        return _r("pending", "ffmpeg هنوز نیست.", "ffmpeg is not there yet.")
    if not _nvenc_listed(ff):
        return _r("warn", "ffmpegِ این رایانه رمزگذار کارت گرافیک (NVENC) ندارد؛ مونتاژ ویدئو با CPU انجام می‌شود (کندتر ولی درست).",
                  "This PC's ffmpeg has no graphics-card encoder (NVENC); video assembly runs on the CPU (slower but correct).")
    ok, err, secs = _ffmpeg_encode(ff, work / "nv.mp4", "h264_nvenc")
    if not ok:
        return _r("warn", "ffmpeg رمزگذار NVENC را دارد ولی کارت آن را نپذیرفت (درایور قدیمی یا کارت پر)؛ مونتاژ با CPU انجام می‌شود. " + err[-120:],
                  "ffmpeg has the NVENC encoder but the card refused it (old driver or a full card); assembly runs on the CPU. " + err[-120:])
    return _r("ok", f"رمزگذاری با کارت گرافیک (NVENC) کار کرد ({_fd(round(secs, 2))} ثانیه برای یک کلیپ یک‌ثانیه‌ای).", f"Encoding on the graphics card (NVENC) worked ({secs:.2f} s for a one-second clip).", seconds=round(secs, 2))


def check_ollama_run(work: Path) -> dict:
    """A few tokens from the real Ollama model, and WHERE it ran (Ollama's own /api/ps): the proof that the owner's model works on the GPU."""
    from instai.core import gpu_diag

    c = gpu_diag.probe_ollama()
    if c is None:
        return _r("pending", "Ollama روشن نیست یا مدلی ندارد؛ وقتی روشن و آماده شد خودکار آزمایش می‌شود (برنامه مدل‌های شما را عوض نمی‌کند).",
                  "Ollama is not running or has no model; it is tested by itself once it is ready (the program never changes your models).")
    level = c.get("level")
    verdict = {"ok": "ok", "warn": "warn", "bad": "fail"}.get(level, "warn")
    fa = (c.get("title_fa") or "") + ((" — " + c["detail_fa"]) if c.get("detail_fa") else "") + ((" " + c["fix_fa"]) if c.get("fix_fa") else "")
    en = (c.get("title_en") or "") + ((" - " + c["detail_en"]) if c.get("detail_en") else "") + ((" " + c["fix_en"]) if c.get("fix_en") else "")
    return _r(verdict, fa, en, level=level)


def check_comfyui(work: Path) -> dict:
    """ComfyUI is started the way a real job starts it, then asked about its card and its workflows."""
    from instai.core import hardware, runtime
    from instai.providers.base import ProviderError
    from instai.providers.comfy import launcher

    if hardware.gpu_status() is None:
        return _r("pending", "بدون کارت NVIDIA ComfyUI (تصویر و ویدئو) آزمایش نمی‌شود؛ با رسیدن رایانهٔ GPUدار خودکار آزمایش می‌شود.", "ComfyUI is not tested without an NVIDIA card; it is tested by itself when the GPU PC is on.")
    url = runtime.comfyui_url()
    try:
        launcher.ensure_running(timeout=300)
    except ProviderError as e:
        if getattr(e, "code", "") == "comfy_on_cpu":
            return _r("fail", e.fa or "ComfyUI روی CPU کار می‌کند.", str(e))
        return _r("pending", (e.fa or "ComfyUI روشن نشد.") + " دوباره امتحان می‌شود.", "ComfyUI is not up yet: " + str(e)[:200])
    info = launcher.device_info(url) or {}
    item = hardware.check_comfyui(url)
    d = item.get("data") or {}
    wf = d.get("workflows") or []
    ready = sum(1 for w in wf if w.get("available"))
    dev = info.get("name") or info.get("type") or "?"
    m = dict(device=dev, nodes=d.get("node_count"), workflows_ready=ready, workflows=len(wf), version=info.get("version"))
    if ready == 0:
        return _r("warn", f"ComfyUI روی کارت گرافیک کار می‌کند ({dev}) ولی هیچ‌کدام از گردش‌کارها آماده نیست؛ مدل‌ها را از صفحهٔ «مدل‌ها» یا «دانلودها» بگیرید.",
                  f"ComfyUI runs on the graphics card ({dev}) but none of the workflows is ready; get the models on the Models or Downloads page.", **m)
    return _r("ok", f"ComfyUI روی کارت گرافیک کار می‌کند ({dev})؛ {_fd(ready)} از {_fd(len(wf))} گردش‌کار آماده است.", f"ComfyUI runs on the graphics card ({dev}); {ready} of {len(wf)} workflows are ready.", **m)


# ------------------------------------------------------------------------------------------------------------------------------ readiness (when may a waiting check run?)

QUIET_UTIL = 40                         # % GPU utilization under which the card counts as quiet


def _gpu_present() -> bool:
    from instai.core import hardware

    return hardware.gpu_status() is not None


def _gpu_quiet() -> bool:
    """A card with a GPU, and one nobody is working hard on right now (the NMarketing agent's job, a render): the automatic checks that load a model or an encoder wait for a quiet
    moment instead of pushing another model in front of somebody's work. (The button «Run now» ignores this: the owner decided.)"""
    from instai.core import hardware

    g = hardware.gpu_status()
    return g is not None and (g.get("utilization") or 0) < QUIET_UTIL


def _ollama_ready() -> bool:
    from instai.core import runtime
    from instai.providers import ollama_fit

    return bool(_gpu_quiet() and ollama_fit.loaded(runtime.ollama_url(), 1.5) is not None)


def _comfy_ready() -> bool:
    from instai.core import runtime
    from instai.providers.comfy import launcher

    return bool(_gpu_quiet() and (launcher._up(runtime.comfyui_url()) or launcher.selected()))


def _nvenc_ready() -> bool:
    from instai.core import runtime

    ff = runtime.ffmpeg_info()["ffmpeg"]
    return bool(_gpu_quiet() and ff)


def _remotion_ready() -> bool:
    from instai.remotion import toolchain

    return bool(toolchain.status()["ready"])


def check_covers(work: Path) -> dict:
    from instai.covers import selftest

    return selftest.check_covers(work)


def check_covers_bg(work: Path) -> dict:
    from instai.covers import selftest

    return selftest.check_covers_bg(work)


CHECKS = [
    {"key": "database", "group": "pc", "fa": "پایگاه‌داده", "en": "Database", "fn": check_database},
    {"key": "disk", "group": "pc", "fa": "فضای دیسک", "en": "Disk space", "fn": check_disk},
    {"key": "ffmpeg", "group": "pc", "fa": "رمزگذاری ویدئو (ffmpeg)", "en": "Video encoding (ffmpeg)", "fn": check_ffmpeg_encode},
    {"key": "persian_text", "group": "pc", "fa": "متن فارسی روی تصویر", "en": "Persian text on a picture", "fn": check_persian_text},
    {"key": "delivery_loudness", "group": "pc", "fa": "بلندی صدای تحویل (‎-۱۴ LUFS)", "en": "Delivery loudness (-14 LUFS)", "fn": check_delivery_loudness},
    {"key": "delivery_echo", "group": "pc", "fa": "تشخیص گفتارِ دوبار پخش‌شده (اکو)", "en": "Doubled narration (echo) detection", "fn": check_delivery_echo},
    {"key": "captions", "group": "pc", "fa": "زیرنویس کلمه‌به‌کلمه (هفت قالب)", "en": "Word-by-word captions (seven presets)", "fn": check_captions},
    {"key": "update_channel", "group": "pc", "fa": "به‌روزرسانی خودکار", "en": "Automatic update", "fn": check_update_channel},
    {"key": "autostart", "group": "pc", "fa": "راه‌اندازی خودکار با ویندوز", "en": "Start with Windows", "fn": check_autostart},
    {"key": "remotion_toolchain", "group": "tools", "fa": "ابزار «ویدئو با کد» (Remotion)", "en": "Code-to-video toolchain (Remotion)", "fn": check_remotion_toolchain},
    {"key": "remotion_render", "group": "tools", "fa": "ساخت یک قاب با Remotion", "en": "Rendering a frame with Remotion", "fn": check_remotion_render, "ready": _remotion_ready},
    {"key": "covers", "group": "tools", "fa": "سازندهٔ کاور (همهٔ طرح‌ها و اندازه‌ها)", "en": "Cover maker (every layout and size)", "fn": check_covers},
    {"key": "motion_library", "group": "tools", "fa": "کتابخانهٔ قطعه‌های گرافیک متحرک", "en": "Motion-graphics component library", "fn": check_motion_library},
    {"key": "motion_frames", "group": "tools", "fa": "قاب هر قطعهٔ گرافیک متحرک در سه اندازه", "en": "A frame of every motion-graphics component in three sizes", "fn": check_motion_frames, "ready": _remotion_ready},
    {"key": "gpu_card", "group": "gpu", "fa": "کارت گرافیک", "en": "Graphics card", "fn": check_gpu_card, "ready": _gpu_present},
    {"key": "nvenc", "group": "gpu", "fa": "رمزگذاری با کارت گرافیک (NVENC)", "en": "Encoding on the graphics card (NVENC)", "fn": check_nvenc, "ready": _nvenc_ready},
    {"key": "ollama_run", "group": "gpu", "fa": "مدل زبانی Ollama روی GPU", "en": "Ollama language model on the GPU", "fn": check_ollama_run, "ready": _ollama_ready},
    {"key": "comfyui", "group": "gpu", "fa": "ComfyUI (تصویر و ویدئو) روی GPU", "en": "ComfyUI (image and video) on the GPU", "fn": check_comfyui, "ready": _comfy_ready},
    {"key": "covers_bg", "group": "gpu", "fa": "پس‌زمینهٔ هوش مصنوعیِ کاور روی GPU", "en": "AI background of a cover on the GPU", "fn": check_covers_bg, "ready": _comfy_ready},
    {"key": "motion_critique", "group": "gpu", "fa": "نقد تصویری گرافیک متحرک با مدل بینایی", "en": "Visual critique of motion graphics by the vision model", "fn": check_motion_critique, "ready": _vision_ready},
]
BY_KEY = {c["key"]: c for c in CHECKS}


def ready_keys() -> list[str]:
    """The checks that have what they need right now, each judged by its OWN requirement. A look at a service never disturbs the caller."""
    out = []
    for c in CHECKS:
        fn = c.get("ready")
        try:
            if fn is None or fn():
                out.append(c["key"])
        except Exception:  # noqa: BLE001
            pass
    return out


def run(ctx=None, *, gpu: bool = True, only: list[str] | None = None) -> dict:
    """Run the checks and keep the report. A check that raises is a failed check, never a crashed run. `gpu=False` leaves the GPU-group rows as they were."""
    from instai.providers.base import ProviderError
    from instai.version import read_version

    old = load_report() or {}
    _CTX[0] = ctx
    work_root = Path(tempfile.mkdtemp(prefix="pcselftest-"))
    rows: list[dict] = []
    started = datetime.now(timezone.utc)
    cur = stamp()
    ready_now = set(ready_keys())
    try:
        todo = [c for c in CHECKS if (not only or c["key"] in only)]
        for k, c in enumerate(todo):
            if c["group"] == "gpu" and not gpu:
                prev = next((r for r in old.get("checks", []) if r["key"] == c["key"]), None)
                rows.append(prev or {"key": c["key"], "group": "gpu", "fa": c["fa"], "en": c["en"], **_r("pending", "وقتی رایانهٔ GPU روشن و آماده باشد خودکار آزمایش می‌شود.", "Tested by itself once the GPU PC is on and ready."), "seconds": 0, "at": None})
                continue
            if ctx is not None:
                ctx.check()
                ctx.progress(k / max(1, len(todo)), c["key"])
            work = work_root / c["key"]
            work.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            try:
                res = c["fn"](work)
            except ProviderError as e:
                res = _r("pending", getattr(e, "fa", "") or "سرویس در دسترس نبود؛ بعداً دوباره آزمایش می‌شود.", f"The service was not reachable: {e}")
            except Exception as e:  # noqa: BLE001 - a broken check is a result
                log.exception("PC self-test %s failed", c["key"])
                res = _r("fail", f"آزمون با خطا تمام شد: {type(e).__name__}: {str(e)[:160]}", f"The check ended with an error: {type(e).__name__}: {str(e)[:160]}")
            rows.append({"key": c["key"], "group": c["group"], "fa": c["fa"], "en": c["en"], **res, "seconds": round(time.time() - t0, 1),
                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stamp": cur, "ready": c["key"] in ready_now})
        if only:                                           # keep the rows of the checks that were not asked for
            rows += [r for r in old.get("checks", []) if r["key"] not in {x["key"] for x in rows}]
        order = {c["key"]: i for i, c in enumerate(CHECKS)}
        rows.sort(key=lambda r: order.get(r["key"], 99))
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
    rep = {"stamp": cur, "version": read_version(), "started_at": started.isoformat(timespec="seconds"), "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "machine": _machine(), "checks": rows, "summary": summarize(rows), "ok": not any(r["verdict"] == "fail" for r in rows)}
    save_report(rep)
    return rep


def summarize(rows: list[dict]) -> dict:
    s = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("ok", "warn", "fail", "skip", "pending")}
    s["state"] = "problems" if s["fail"] else ("waiting" if s["pending"] else ("attention" if s["warn"] else "sound"))
    return s


def _machine() -> dict:
    import platform

    try:
        from instai.core import hardware

        g = hardware.gpu_status()
    except Exception:  # noqa: BLE001
        g = None
    return {"os": platform.platform(), "python": platform.python_version(), "gpu": (g or {}).get("name") or ""}


@handler("system.selftest", resource=lambda payload: "gpu" if payload.get("gpu") else "cpu", timeout=3 * 3600)
def selftest_job(ctx):
    rep = run(ctx, gpu=bool(ctx.payload.get("gpu", True)), only=[str(k) for k in (ctx.payload.get("only") or [])] or None)
    return {"summary": rep["summary"], "ok": rep["ok"], "stamp": rep["stamp"]}


# ------------------------------------------------------------------------------------------------------------------------------ automatic start

def _age_s(at: str | None, now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(at)).total_seconds() if at else 10 ** 9
    except (TypeError, ValueError):
        return 10 ** 9


def due(rep: dict, cur: str, ready: list[str]) -> list[str]:
    """Which checks should run now, from the kept report (judged one by one, so one check that cannot run never holds back or repeats the others):
    * never ran, or still waiting: as soon as its own requirement is there - at once when it was NOT ready at its last attempt (the situation changed), otherwise not more
      often than every RETRY_WAITING_S;
    * has a result of an older version: the cheap checks at once, the tool / GPU checks after VERSION_RETRY_S;
    * a warning or a failure: again after RETRY_PROBLEM_S (the owner may have fixed it);
    * a good result of this version: again after a day (cheap) or a week (tool / GPU)."""
    rows = {r["key"]: r for r in rep.get("checks", [])}
    now = datetime.now(timezone.utc)
    out: list[str] = []
    for c in CHECKS:
        if c["key"] not in ready:
            continue
        r = rows.get(c["key"]) or {}
        age = _age_s(r.get("at"), now)
        heavy = c["group"] != "pc"
        if r.get("verdict", "pending") not in CONCLUSIVE:
            go = (not r.get("ready")) or age > RETRY_WAITING_S
        elif r.get("stamp") != cur:
            go = age > (VERSION_RETRY_S if heavy else 0)
        elif r.get("verdict") in ("warn", "fail"):
            go = age > RETRY_PROBLEM_S
        else:
            go = age > (REFRESH_HEAVY_S if heavy else REFRESH_BASE_S)
        if go:
            out.append(c["key"])
    return out


def auto_queue(force: bool = False):
    """Queue the self-test by itself (called from the automation tick). Returns the job or None."""
    from instai.core import settings_store
    from instai.jobs import queue
    from instai.jobs.models import Job

    if not force and time.time() - _LAST_AUTO[0] < AUTO_EVERY_S:
        return None
    _LAST_AUTO[0] = time.time()
    if os.environ.get("INSTAI_TESTING") == "1" and not force:        # the test suite never gets surprise jobs; the self-test's own tests pass force=True
        return None
    if os.environ.get("INSTAI_PC_SELFTEST_AUTO", "1") == "0" or settings_store.get_setting("pc_selftest_auto", True) in (False, 0, "0"):
        return None
    if Job.objects.filter(kind="system.selftest", status__in=[Job.QUEUED, Job.RUNNING]).exists():
        return None
    keys = due(load_report() or {}, stamp(), ready_keys())
    if not keys:
        return None
    gpu = any(BY_KEY[k]["group"] == "gpu" for k in keys)
    return queue.enqueue("system.selftest", {"gpu": gpu, "only": keys, "auto": True}, title="آزمون خودکار این رایانه" + (" (با GPU)" if gpu else ""), priority=-10)
