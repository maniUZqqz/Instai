"""The processing-computers report: recording (sessions, samples, events), upkeep (thinning, deleting old rows), plain-language error
explanations and the numbers the report page and the CSV files show.

Recording is cheap and never raises: a heartbeat of a computer must not fail because the report could not be written.
  * `record_heartbeat(node, ...)` is called by this PC's worker (every few seconds, throttled) and by the worker API when PC B talks;
  * `maintain()` is called by the worker's periodic tick and does at most one small piece of work per ten minutes.
Idea adapted from NMarketing's apps/compute/report.py (sessions + samples + explain), re-done for InstAI's own tables.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import socket
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db.models import Q
from django.utils import timezone

from instai.jobs import schedule
from instai.jobs.models import Job, JobLog, RemoteTask, WorkerNode

from .models import NodeEvent, NodeSample, NodeSession

log = logging.getLogger("instai.ops")
LOCAL = "local"
GRACE_S = {LOCAL: 45}            # a heartbeat gap longer than this ends a session (this PC's worker beats every 5 s)
GRACE_DEFAULT_S = 90             # worker PCs (hello every 20 s, claim every 15 s)
TOUCH_EVERY_S = 10               # a computer's session row is written at most this often
SAMPLE_EVERY_S = 60
RAW_KEEP_H = 48                  # samples older than this are thinned to one per 15 minutes
BUCKET_S = 15 * 60
MAINTAIN_EVERY_S = 600
BATCH = 5000
SERIES_POINTS = 240

_LAST_TOUCH: dict[str, datetime] = {}
_LAST_SAMPLE: dict[str, datetime] = {}
_LAST_MAINTAIN = [0.0]


def reset_state() -> None:
    """Forget the in-process throttles (tests)."""
    _LAST_TOUCH.clear()
    _LAST_SAMPLE.clear()
    _LAST_MAINTAIN[0] = 0.0


def grace(node: str) -> int:
    return GRACE_S.get(node, GRACE_DEFAULT_S)


# ------------------------------------------------------------------ recording

def num(value, lo: float = -1e12, hi: float = 1e12):
    """A usable number in [lo, hi] or None: whatever a worker PC sends is distrusted (bool, text, NaN, infinity are not numbers)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v and lo <= v <= hi else None


def local_stats() -> dict:
    """What this PC reports about itself (GPU through nvidia-smi, RAM, the disk with the media folder)."""
    from instai.core import hardware

    return hardware.node_stats()


def _event(node: str, kind: str, level: str = "info", *, at: datetime | None = None, message: str = "", data: dict | None = None,
           job_id: int | None = None) -> None:
    try:
        NodeEvent.objects.create(node=node, at=at or timezone.now(), level=level, kind=kind, message=message[:2000], data=data or {}, job_id=job_id)
    except Exception:  # noqa: BLE001 - recording must never break the work
        log.debug("could not record an event", exc_info=True)


def record_event(node: str, kind: str, level: str = "info", message: str = "", data: dict | None = None, job_id: int | None = None) -> None:
    _event(node, kind, level, message=message, data=data, job_id=job_id)


def record_heartbeat(node: str, *, stats: dict | None = None, stats_fn=None, version: str = "", info: dict | None = None,
                     now: datetime | None = None, force: bool = False) -> bool:
    """A computer is alive. Opens / extends its session, writes a resource sample about once a minute. Returns True when this heartbeat
    started a NEW session (the computer just came online): the jobs waiting for it are woken. Never raises."""
    try:
        now = now or timezone.now()
        last = _LAST_TOUCH.get(node)
        due_touch = force or last is None or (now - last).total_seconds() >= TOUCH_EVERY_S
        new = False
        if due_touch:
            new = _touch(node, now, version, info)
            _LAST_TOUCH[node] = now
        ls = _LAST_SAMPLE.get(node)
        if (stats or stats_fn) and (force or ls is None or (now - ls).total_seconds() >= SAMPLE_EVERY_S):
            _LAST_SAMPLE[node] = now
            s = stats if stats is not None else (stats_fn() or {})
            _sample(node, now, s)
            if s.get("gpu_name"):
                _merge_info(node, {"gpu_name": str(s["gpu_name"])[:80]})
        if new and node != LOCAL:
            from instai.jobs import queue

            queue.wake_waiting()
        return new
    except Exception:  # noqa: BLE001
        log.debug("heartbeat recording failed", exc_info=True)
        return False


def _touch(node: str, now: datetime, version: str, info: dict | None) -> bool:
    gap = grace(node)
    cur = NodeSession.objects.filter(node=node, ended_at__isnull=True).order_by("-started_at").first()
    if cur is not None and (now - cur.last_seen).total_seconds() > gap:
        NodeSession.objects.filter(pk=cur.pk).update(ended_at=cur.last_seen)
        _event(node, "offline", "warning", at=cur.last_seen, data={"since": cur.last_seen.isoformat()})
        cur = None
    if cur is None:
        prev = NodeSession.objects.filter(node=node).order_by("-started_at").first()          # a claim-time heartbeat has no version: keep the known one
        NodeSession.objects.create(node=node, started_at=now, last_seen=now, version=(version or (prev.version if prev else ""))[:20],
                                   info=info or ((prev.info if prev else {}) or {}))
        _event(node, "online", at=now, data={"version": version or ""})
        return True
    upd: dict = {"last_seen": now}
    if version and version != cur.version:
        upd["version"] = version[:20]
    if info:
        upd["info"] = {**(cur.info or {}), **info}
    NodeSession.objects.filter(pk=cur.pk).update(**upd)
    return False


def _merge_info(node: str, extra: dict) -> None:
    cur = NodeSession.objects.filter(node=node, ended_at__isnull=True).order_by("-started_at").first()
    if cur is not None and any((cur.info or {}).get(k) != v for k, v in extra.items()):
        NodeSession.objects.filter(pk=cur.pk).update(info={**(cur.info or {}), **extra})


def _sample(node: str, now: datetime, s: dict) -> None:
    NodeSample.objects.create(
        node=node, at=now, gpu_util=num(s.get("gpu_util"), 0, 100), gpu_temp=num(s.get("gpu_temp"), -50, 200),
        vram_used_mb=_int(num(s.get("vram_used_mb"), 0, 1e7)), vram_total_mb=_int(num(s.get("vram_total_mb"), 0, 1e7)),
        ram_used_mb=_int(num(s.get("ram_used_mb"), 0, 1e8)), ram_total_mb=_int(num(s.get("ram_total_mb"), 0, 1e8)),
        disk_free_gb=num(s.get("disk_free_gb"), 0, 1e7), disk_total_gb=num(s.get("disk_total_gb"), 0, 1e7))


def _int(v):
    return None if v is None else int(v)


def close_stale_sessions(now: datetime | None = None) -> int:
    """Sessions whose computer stopped beating are closed at their last heartbeat (and an 'offline' event is written)."""
    now = now or timezone.now()
    n = 0
    for s in NodeSession.objects.filter(ended_at__isnull=True):
        if (now - s.last_seen).total_seconds() > grace(s.node):
            if NodeSession.objects.filter(pk=s.pk, ended_at__isnull=True).update(ended_at=s.last_seen):
                _event(s.node, "offline", "warning", at=s.last_seen, data={"since": s.last_seen.isoformat()})
                n += 1
    return n


def store_agent_log(node: str, lines: list) -> int:
    """Lines of a worker PC's own log (sent in batches by the agent): kept as events so they can be searched in the report."""
    n = 0
    now = timezone.now()
    for row in (lines or [])[:200]:
        if not isinstance(row, dict):
            continue
        msg = str(row.get("message") or "")[:1000]
        if not msg:
            continue
        level = str(row.get("level") or "info").lower()[:8]
        at = _parse_ts(row.get("at")) or now
        _event(node, "error" if level in ("error", "critical") else "log", "warning" if level == "warning" else level, at=at, message=msg)
        n += 1
    return n


def _parse_ts(v) -> datetime | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            return datetime.fromtimestamp(float(v), tz=dt_timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


# ------------------------------------------------------------------ upkeep

def maintain(now: datetime | None = None, force: bool = False) -> dict:
    """Close silent sessions, thin raw samples older than 48 h to one per 15 minutes, delete rows older than the retention (days).
    Bounded and repeatable; at most once per ten minutes unless forced."""
    if not force and time.time() - _LAST_MAINTAIN[0] < MAINTAIN_EVERY_S:
        return {}
    _LAST_MAINTAIN[0] = time.time()
    now = now or timezone.now()
    out = {"closed": close_stale_sessions(now), "thinned": 0, "deleted": 0}
    keep_days = schedule.config()["retention_days"]
    cutoff = now - timedelta(days=keep_days)
    out["deleted"] += NodeSample.objects.filter(at__lt=cutoff).delete()[0]
    out["deleted"] += NodeEvent.objects.filter(at__lt=cutoff).delete()[0]
    out["deleted"] += NodeSession.objects.filter(ended_at__isnull=False, ended_at__lt=cutoff).delete()[0]
    raw_cut = now - timedelta(hours=RAW_KEEP_H)
    rows = list(NodeSample.objects.filter(at__lt=raw_cut, at__gte=cutoff).order_by("node", "at").values_list("pk", "node", "at")[:BATCH])
    seen: set = set()
    drop = []
    for pk, node, at in rows:
        key = (node, int(at.timestamp() // BUCKET_S))
        if key in seen:
            drop.append(pk)
        else:
            seen.add(key)
    if drop:
        out["thinned"] = NodeSample.objects.filter(pk__in=drop).delete()[0]
    return out


# ------------------------------------------------------------------ plain-language error explanations

# (code, pattern on the raw error text, what happened (fa, en), what to do (fa, en))
EXPLAIN_RULES: list[tuple[str, re.Pattern, tuple[str, str], tuple[str, str]]] = [
    ("ollama_down", re.compile(r"ollama.*(not reachable|request failed|refused|connection)|ollama_down|InstAI به Ollama وصل نشد", re.I),
     ("Ollama روشن نبود یا InstAI به آن نرسید.", "Ollama was not running or InstAI could not reach it."),
     ("برنامهٔ Ollama را روشن کنید؛ کارهای منتظر خودشان ادامه می‌دهند.", "Start Ollama; the waiting jobs continue by themselves.")),
    ("comfy_down", re.compile(r"comfyui.*(not running|cannot start|did not answer|stopped while starting)|ComfyUI روشن نیست", re.I),
     ("ComfyUI روشن نبود و روشن نشد.", "ComfyUI was not running and could not be started."),
     ("ComfyUI را با run_nvidia_gpu.bat روشن کنید یا پوشهٔ آن را در صفحهٔ «مدل‌ها» بدهید؛ فایل data\\logs\\comfyui.log دلیل را می‌گوید.",
      "Start ComfyUI with run_nvidia_gpu.bat or give its folder on the Models page; data\\logs\\comfyui.log says why.")),
    ("comfy_cpu", re.compile(r"runs on the CPU|ComfyUI روی پردازنده", re.I),
     ("ComfyUI روی CPU کار می‌کرد، نه کارت گرافیک.", "ComfyUI was running on the CPU, not the graphics card."),
     ("صفحهٔ «سیستم» ← «بررسی کارت گرافیک» را بزنید؛ معمولاً PyTorch فقط‌CPU نصب است.", "Use System > GPU check; usually a CPU-only PyTorch is installed.")),
    ("out_of_memory", re.compile(r"out of memory|llm_oom|gpu_oom|could not load .*(memory|gpu)|CUDA error|OOM", re.I),
     ("حافظهٔ کارت گرافیک (VRAM) یا RAM برای این کار کم بود.", "The graphics card memory (VRAM) or RAM was not enough for this job."),
     ("مدل کوچک‌تری انتخاب کنید یا برنامه‌های دیگری که از کارت گرافیک استفاده می‌کنند را ببندید.", "Choose a smaller model or close other programs that use the graphics card.")),
    ("worker_offline", re.compile(r"worker.*(did not pick|offline|stopped sending|did not answer)|worker_offline|worker_lost|رایانهٔ .* خاموش", re.I),
     ("رایانهٔ دوم (B) خاموش بود یا ارتباطش قطع شد.", "The second PC (B) was off or lost its connection."),
     ("اگر پیام «منتظر» دیده می‌شود لازم نیست کاری بکنید؛ B را روشن کنید تا کار ادامه یابد. اگر کار شکست خورده، «دوباره امتحان» بزنید.",
      "If the job shows 'waiting' do nothing; switch B on and it continues. If it failed, press Retry.")),
    ("gpu_busy", re.compile(r"GPU busy|stayed busy|another program uses", re.I),
     ("برنامهٔ دیگری از کارت گرافیک استفاده می‌کرد.", "Another program was using the graphics card."),
     ("برنامهٔ دیگر را ببندید؛ کار خودش ادامه می‌دهد.", "Close the other program; the job continues by itself.")),
    ("timeout", re.compile(r"timeout|timed out|took longer|exceeded its timeout|llm_stalled|did not become ready", re.I),
     ("کار بیش از حد طول کشید یا مدل ساکت ماند.", "The job took too long or the model went silent."),
     ("اگر مدل بزرگ است و روی GPU کامل جا نمی‌شود، مدل کوچک‌تری انتخاب کنید؛ بعد «دوباره امتحان» بزنید.", "If the model is large and does not fit the GPU, choose a smaller one; then press Retry.")),
    ("no_model", re.compile(r"no models installed|model not found|no_model|model_missing|نصب نیست", re.I),
     ("مدل لازم نصب نیست.", "The needed model is not installed."),
     ("در صفحهٔ «مدل‌ها» مدل را نصب یا دانلود کنید.", "Install or download the model on the Models page.")),
    ("disk_full", re.compile(r"no space left|disk full|not enough (free )?space|فضای آزاد", re.I),
     ("جای خالی دیسک کم بود.", "The disk was nearly full."),
     ("فایل‌های غیرضروری را پاک کنید (InstAI خودش چیزی پاک نمی‌کند).", "Free some disk space (InstAI never deletes your files).")),
    ("network", re.compile(r"ConnectionError|Max retries exceeded|getaddrinfo|Name or service|SSL|unreachable|HTTP 5\d\d", re.I),
     ("اینترنت یا سرویس راه دور جواب نداد.", "The internet or a remote service did not answer."),
     ("اتصال اینترنت را بررسی کنید و دوباره امتحان کنید.", "Check the internet connection and retry.")),
    ("download_failed", re.compile(r"دانلود کامل نشد|download.*(failed|incomplete)|checksum|sha256", re.I),
     ("دانلود کامل نشد.", "The download did not finish."),
     ("دوباره امتحان کنید؛ دانلود از همان‌جا که مانده ادامه می‌یابد.", "Retry; the download continues where it stopped.")),
    ("api_key", re.compile(r"API key|api_key|HTTP 401|HTTP 402|HTTP 403", re.I),
     ("کلید یا اعتبار سرویس آنلاین مشکل دارد.", "The online service key or credit is the problem."),
     ("در «تنظیمات» کلید را بررسی کنید.", "Check the key in Settings.")),
    ("bad_output", re.compile(r"llm_invalid_output|invalid output|schema|not valid JSON|did not follow", re.I),
     ("مدل پاسخی نداد که قالب لازم را داشته باشد.", "The model did not answer in the required format."),
     ("دوباره امتحان کنید؛ اگر تکرار شد مدل بزرگ‌تر یا دقیق‌تری انتخاب کنید.", "Retry; if it repeats choose a larger or more careful model.")),
    ("not_ready", re.compile(r"No PC can run this task|not_ready|missing:|not installed|no handler", re.I),
     ("هیچ رایانه‌ای همهٔ ابزار لازم این کار را ندارد.", "No computer has everything this job needs."),
     ("صفحهٔ «مدل‌ها» می‌گوید چه چیزی کم است.", "The Models page says what is missing.")),
    ("consent", re.compile(r"consent", re.I),
     ("برای این صدا رضایت ثبت نشده است.", "No consent is recorded for this voice."),
     ("رضایت‌نامه را در برگهٔ صدا ثبت کنید.", "Record the consent on the voice sheet.")),
    ("lease_expired", re.compile(r"worker stopped before|lease expired|crash", re.I),
     ("برنامهٔ اجراکننده وسط کار بسته شد (چند بار پشت سر هم).", "The worker program stopped in the middle of the job (several times in a row)."),
     ("کار به اندازهٔ کافی حافظه یا زمان می‌خواهد؛ data\\logs\\instai.log را ببینید.", "The job may need more memory or time; see data\\logs\\instai.log.")),
    ("wait_limit", re.compile(r"سقفی که تعیین کرده|wait_limit", re.I),
     ("انتظار از سقفی که شما تعیین کرده بودید بیشتر شد.", "The wait went over the limit you set."),
     ("می‌توانید «دوباره امتحان» بزنید یا سقف را در صفحهٔ «دانلودها و زمان‌بندی» بردارید.", "You can Retry or remove the limit on the Downloads page.")),
]
UNKNOWN_EXPLAIN = {"code": "unknown", "known": False,
                   "what_fa": "خطای ناشناخته؛ متن فنی را زیر ببینید.", "what_en": "An unknown error; see the technical text below.",
                   "advice_fa": "«دوباره امتحان» را بزنید؛ اگر باز تکرار شد متن فنی را به پشتیبان بدهید.", "advice_en": "Press Retry; if it repeats, show the technical text to support."}


def explain(text: str, code: str = "") -> dict:
    """{"code", "known", "what_fa", "what_en", "advice_fa", "advice_en"}: a raw error (or stored error code) -> what happened, what to do."""
    raw = f"{code} {text or ''}"[:6000]
    for c, rx, what, advice in EXPLAIN_RULES:
        if rx.search(raw):
            return {"code": c, "known": True, "what_fa": what[0], "what_en": what[1], "advice_fa": advice[0], "advice_en": advice[1]}
    return dict(UNKNOWN_EXPLAIN)


EVENT_TEXT = {
    "online": ("کامپیوتر آنلاین شد{v}", "The computer came online{v}"),
    "offline": ("کامپیوتر آفلاین شد (آخرین نشانهٔ زنده بودن همین لحظه بود)", "The computer went offline (this was its last sign of life)"),
    "wait": ("کاری برای این کامپیوتر منتظر ماند: {code}", "A job is waiting for this computer: {code}"),
}


def event_text(e: NodeEvent) -> tuple[str, str]:
    """(Persian, English) text of an event. Lines of a worker PC's own log are shown as they came."""
    if e.kind in EVENT_TEXT:
        d = e.data or {}
        v_fa = f" (نسخهٔ {schedule.fa_num(d['version'])})" if d.get("version") else ""
        v_en = f" (version {d['version']})" if d.get("version") else ""
        fa, en = EVENT_TEXT[e.kind]
        code = d.get("code") or ""
        return fa.format(v=v_fa, code=code), en.format(v=v_en, code=code)
    return e.message, e.message


# ------------------------------------------------------------------ the numbers

def node_catalog() -> list[dict]:
    """This PC first, then every paired worker (also the disabled ones: their history stays)."""
    host = ""
    try:
        host = socket.gethostname()
    except OSError:
        pass
    rows = [{"key": LOCAL, "name": "کامپیوتر اصلی (A)", "name_en": "Main PC (A)", "kind": "local", "enabled": True, "worker_id": None, "host": host}]
    known = {LOCAL}
    for w in WorkerNode.objects.all():
        known.add(w.name)
        rows.append({"key": w.name, "name": f"کامپیوتر {w.name}", "name_en": f"Computer {w.name}", "kind": "worker", "enabled": w.enabled, "worker_id": w.pk,
                     "host": (w.info or {}).get("host", "")})
    for key in NodeSession.objects.exclude(node__in=known).values_list("node", flat=True).distinct():     # a removed worker keeps its history
        rows.append({"key": key, "name": f"کامپیوتر {key} (حذف‌شده)", "name_en": f"Computer {key} (removed)", "kind": "worker", "enabled": False, "worker_id": None, "host": ""})
    return rows


def parse_range(params, now: datetime | None = None) -> tuple[datetime, datetime]:
    """`from` / `to` (YYYY-MM-DD or ISO) or `days` (default 7). `to` as a date means the end of that day (local time)."""
    now = now or timezone.now()

    def one(v: str, end: bool) -> datetime | None:
        v = (v or "").strip()
        if not v:
            return None
        try:
            if len(v) <= 10:
                d = datetime.strptime(v, "%Y-%m-%d")
                loc = d.replace(tzinfo=dt_timezone(schedule.local_offset(now)))
                return (loc + timedelta(days=1) if end else loc).astimezone(dt_timezone.utc)
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=dt_timezone.utc)
        except ValueError:
            return None

    end = one(params.get("to", ""), True) or now
    start = one(params.get("from", ""), False)
    if start is None:
        try:
            days = min(365, max(1, int(params.get("days") or 7)))
        except (TypeError, ValueError):
            days = 7
        start = end - timedelta(days=days)
    if start >= end:
        start = end - timedelta(days=1)
    return start, end


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "avg": None, "median": None, "p95": None, "max": None}
    return {"n": len(values), "avg": round(sum(values) / len(values), 1), "median": round(statistics.median(values), 1),
            "p95": round(_percentile(values, 0.95), 1), "max": round(max(values), 1)}


def queue_wait(j) -> float | None:
    """Seconds the job waited in the queue before it first started (from the moment it was allowed to start)."""
    if not j.first_started_at:
        return None
    ready = j.ready_at or j.created_at
    return max(0.0, (j.first_started_at - ready).total_seconds())


def job_error(j) -> dict | None:
    if j.status != Job.FAILED and not (j.status == Job.QUEUED and j.error):
        return None
    return explain(j.error, j.error_code)


def kind_titles(kind: str) -> tuple[str, str]:
    from instai.jobs.describe import KIND_TEXT

    return KIND_TEXT.get(kind, (kind, kind))


def _node_of(j: Job) -> str:
    return j.node or LOCAL


def _session_bounds(s: NodeSession, now: datetime) -> tuple[datetime, datetime]:
    if s.ended_at:
        return s.started_at, s.ended_at
    if (now - s.last_seen).total_seconds() > grace(s.node):
        return s.started_at, s.last_seen
    return s.started_at, now


def _overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> float:
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds())


def node_report(node: dict, start: datetime, end: datetime, now: datetime, jobs: list[Job]) -> dict:
    key = node["key"]
    horizon = min(end, now)
    sessions = list(NodeSession.objects.filter(node=key, started_at__lt=horizon).filter(Q(ended_at__isnull=True) | Q(ended_at__gt=start)).order_by("started_at"))
    first = NodeSession.objects.filter(node=key).order_by("started_at").values_list("started_at", flat=True).first()
    segs, up = [], 0.0
    for s in sessions:
        a, b = _session_bounds(s, now)
        a2, b2 = max(a, start), min(b, horizon)
        if b2 > a2:
            segs.append({"start": a2.isoformat(), "end": b2.isoformat(), "minutes": round((b2 - a2).total_seconds() / 60, 1), "version": s.version})
            up += (b2 - a2).total_seconds()
    base = max(start, first) if first else None
    span = (horizon - base).total_seconds() if base and horizon > base else 0
    last = NodeSession.objects.filter(node=key).order_by("-last_seen").first()
    online = bool(last and last.ended_at is None and (now - last.last_seen).total_seconds() <= grace(key))
    samples = list(NodeSample.objects.filter(node=key, at__gte=start, at__lte=end).order_by("at"))
    mine = [j for j in jobs if _node_of(j) == key]
    by_kind: dict[str, list[Job]] = defaultdict(list)
    for j in mine:
        by_kind[j.kind].append(j)
    kinds = []
    for kind, js in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        fa, en = kind_titles(kind)
        waits = [w for w in (queue_wait(j) for j in js) if w is not None]
        durs = [j.duration_sec for j in js if j.status == Job.SUCCEEDED and j.duration_sec is not None]
        kinds.append({"kind": kind, "title_fa": fa, "title_en": en, "total": len(js), "succeeded": sum(j.status == Job.SUCCEEDED for j in js),
                      "failed": sum(j.status == Job.FAILED for j in js), "cancelled": sum(j.status == Job.CANCELLED for j in js),
                      "active": sum(j.status in (Job.QUEUED, Job.RUNNING) for j in js), "duration": _stats(durs), "wait": _stats(waits)})
    durs_all = [j.duration_sec for j in mine if j.status == Job.SUCCEEDED and j.duration_sec is not None]
    waits_all = [w for w in (queue_wait(j) for j in mine) if w is not None]
    info = (last.info if last else {}) or {}
    tasks = []
    if node["worker_id"]:
        ts = list(RemoteTask.objects.filter(worker_id=node["worker_id"], created_at__gte=start, created_at__lte=end))
        tk: dict[str, list[RemoteTask]] = defaultdict(list)
        for t in ts:
            tk[t.kind].append(t)
        for kind, xs in sorted(tk.items()):
            secs = [t.seconds for t in xs if t.status == RemoteTask.SUCCEEDED and t.seconds]
            tasks.append({"kind": kind, "total": len(xs), "succeeded": sum(t.status == "succeeded" for t in xs), "failed": sum(t.status == "failed" for t in xs),
                          "cancelled": sum(t.status == "cancelled" for t in xs), "lost": sum(t.error_code == "worker_lost" for t in xs), "duration": _stats(secs)})
    return {
        **node, "online": online, "last_seen": last.last_seen.isoformat() if last else None, "version": (last.version if last else "") or "",
        "gpu_name": info.get("gpu_name") or info.get("gpu") or "", "first_seen": first.isoformat() if first else None,
        "uptime_pct": round(100 * up / span, 1) if span > 0 else None, "online_minutes": round(up / 60, 1), "sessions": segs,
        "current": _current(samples[-1] if samples else NodeSample.objects.filter(node=key).order_by("-at").first()),
        "series": _series(samples, start, horizon),
        "jobs": {"total": len(mine), "succeeded": sum(j.status == Job.SUCCEEDED for j in mine), "failed": sum(j.status == Job.FAILED for j in mine),
                 "cancelled": sum(j.status == Job.CANCELLED for j in mine), "active": sum(j.status in (Job.QUEUED, Job.RUNNING) for j in mine),
                 "duration": _stats(durs_all), "wait": _stats(waits_all),
                 "gpu_seconds": round(sum((j.devices or {}).get(key, 0) for j in jobs), 1),
                 "deferrals": sum(j.deferrals for j in mine)},
        "by_kind": kinds, "tasks": tasks,
    }


def _current(s: NodeSample | None) -> dict | None:
    if s is None:
        return None
    return {"at": s.at.isoformat(), "gpu_util": s.gpu_util, "gpu_temp": s.gpu_temp, "vram_used_mb": s.vram_used_mb, "vram_total_mb": s.vram_total_mb,
            "ram_used_mb": s.ram_used_mb, "ram_total_mb": s.ram_total_mb, "disk_free_gb": s.disk_free_gb, "disk_total_gb": s.disk_total_gb}


def _series(samples: list[NodeSample], start: datetime, end: datetime) -> list[dict]:
    """At most SERIES_POINTS points: the samples are averaged inside equal time slices."""
    if not samples:
        return []
    span = max(1.0, (end - start).total_seconds())
    width = max(SAMPLE_EVERY_S, span / SERIES_POINTS)
    buckets: dict[int, list[NodeSample]] = defaultdict(list)
    for s in samples:
        buckets[int((s.at - start).total_seconds() // width)].append(s)

    def avg(xs, attr):
        v = [getattr(x, attr) for x in xs if getattr(x, attr) is not None]
        return round(sum(v) / len(v), 1) if v else None
    out = []
    for b in sorted(buckets):
        xs = buckets[b]
        vp = avg(xs, "vram_used_mb"), avg(xs, "vram_total_mb")
        rp = avg(xs, "ram_used_mb"), avg(xs, "ram_total_mb")
        out.append({"at": (start + timedelta(seconds=b * width)).isoformat(), "gpu_util": avg(xs, "gpu_util"), "gpu_temp": avg(xs, "gpu_temp"),
                    "vram_pct": round(100 * vp[0] / vp[1], 1) if vp[0] is not None and vp[1] else None,
                    "ram_pct": round(100 * rp[0] / rp[1], 1) if rp[0] is not None and rp[1] else None, "disk_free_gb": avg(xs, "disk_free_gb")})
    return out


def error_groups(jobs: list[Job], start: datetime, end: datetime) -> list[dict]:
    groups: dict[str, dict] = {}
    for j in jobs:
        if j.status != Job.FAILED:
            continue
        ex = explain(j.error, j.error_code)
        g = groups.setdefault(ex["code"], {**ex, "count": 0, "last_at": None, "kinds": {}, "sample": "", "job": None})
        g["count"] += 1
        g["kinds"][j.kind] = g["kinds"].get(j.kind, 0) + 1
        if g["last_at"] is None or (j.finished_at and j.finished_at.isoformat() > g["last_at"]):
            g["last_at"], g["job"] = (j.finished_at.isoformat() if j.finished_at else None), j.pk
            g["sample"] = (j.error or "")[:300]
    for t in RemoteTask.objects.filter(status=RemoteTask.FAILED, created_at__gte=start, created_at__lte=end):
        ex = explain(t.error, t.error_code)
        g = groups.setdefault(ex["code"], {**ex, "count": 0, "last_at": None, "kinds": {}, "sample": "", "job": None})
        g["count"] += 1
        k = "task:" + t.kind
        g["kinds"][k] = g["kinds"].get(k, 0) + 1
    out = sorted(groups.values(), key=lambda g: -g["count"])
    for g in out:
        g["kinds"] = [{"kind": k, "count": c} for k, c in sorted(g["kinds"].items(), key=lambda kv: -kv[1])]
    return out


def downloads_list(jobs: list[Job]) -> list[dict]:
    from .queue_view import job_state

    rows = []
    for j in jobs:
        if not j.kind.startswith("downloads."):
            continue
        st = job_state(j)
        ex = job_error(j)
        from .downloads import titles

        t_fa, t_en = titles(j)
        rows.append({"id": j.pk, "title": j.title, "title_fa": t_fa, "title_en": t_en, "status": j.status, "state": st["state"], "state_fa": st["fa"], "state_en": st["en"], "progress": j.progress,
                     "created_at": j.created_at.isoformat(), "started_at": j.started_at.isoformat() if j.started_at else None,
                     "finished_at": j.finished_at.isoformat() if j.finished_at else None, "duration_sec": j.duration_sec, "window": j.window,
                     "target": (j.payload or {}).get("target_name") or "local", "wait": queue_wait(j),
                     "error": (j.error or "")[:300], "explain": ex})
    return rows


def build_report(start: datetime, end: datetime, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    jobs = list(Job.objects.filter(created_at__gte=start, created_at__lte=end).order_by("-id"))
    nodes = [node_report(n, start, end, now, jobs) for n in node_catalog()]
    waits_all = [w for w in (queue_wait(j) for j in jobs) if w is not None]
    durs_all = [j.duration_sec for j in jobs if j.status == Job.SUCCEEDED and j.duration_sec is not None]
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat(), "days": round((end - start).total_seconds() / 86400, 1)},
        "generated_at": now.isoformat(),
        "nodes": nodes,
        "totals": {"jobs": len(jobs), "succeeded": sum(j.status == Job.SUCCEEDED for j in jobs), "failed": sum(j.status == Job.FAILED for j in jobs),
                   "cancelled": sum(j.status == Job.CANCELLED for j in jobs), "active": sum(j.status in (Job.QUEUED, Job.RUNNING) for j in jobs),
                   "waiting": Job.objects.filter(status=Job.QUEUED).exclude(wait_code="").count(), "deferrals": sum(j.deferrals for j in jobs),
                   "duration": _stats(durs_all), "wait": _stats(waits_all), "gpu_seconds": round(sum(j.gpu_seconds for j in jobs), 1)},
        "errors": error_groups(jobs, start, end),
        "downloads": downloads_list(jobs)[:100],
        "versions": {"main": _main_version(), "workers": {n["key"]: n["version"] for n in nodes if n["kind"] == "worker"}},
    }


def _main_version() -> str:
    from instai.version import read_version

    return read_version()


# ------------------------------------------------------------------ logs (search)

def search_logs(params, start: datetime, end: datetime) -> list[dict]:
    """Job log lines and computer events, newest first. params: q (text), level, node, source (jobs|events|all), limit (<= 500)."""
    q = (params.get("q") or "").strip()
    level = (params.get("level") or "").strip().lower()
    node = (params.get("node") or "").strip()
    source = params.get("source") or "all"
    try:
        limit = min(500, max(10, int(params.get("limit") or 200)))
    except (TypeError, ValueError):
        limit = 200
    rows: list[dict] = []
    if source in ("all", "jobs"):
        qs = JobLog.objects.filter(at__gte=start, at__lte=end).select_related("job").order_by("-id")
        if q:
            qs = qs.filter(Q(message__icontains=q) | Q(job__title__icontains=q) | Q(job__kind__icontains=q))
        if level:
            qs = qs.filter(level=level)
        if node:
            qs = qs.filter(job__node="") if node == LOCAL else qs.filter(job__node=node)
        for l in qs[:limit]:
            fa, en = kind_titles(l.job.kind)
            rows.append({"source": "job", "at": l.at.isoformat(), "level": l.level, "node": _node_of(l.job), "job": l.job_id, "kind": l.job.kind,
                         "title_fa": fa, "title_en": en, "message": l.message, "explain": explain(l.message) if l.level in ("error", "warning") and explain(l.message)["known"] else None})
    if source in ("all", "events"):
        qs2 = NodeEvent.objects.filter(at__gte=start, at__lte=end).order_by("-at", "-id")
        if q:
            qs2 = qs2.filter(Q(message__icontains=q) | Q(kind__icontains=q))
        if level:
            qs2 = qs2.filter(level=level)
        if node:
            qs2 = qs2.filter(node=node)
        for e in qs2[:limit]:
            fa, en = event_text(e)
            if q and e.kind in EVENT_TEXT and q.lower() not in (fa + en).lower() and q.lower() not in e.kind:
                continue
            rows.append({"source": "event", "at": e.at.isoformat(), "level": e.level, "node": e.node, "job": e.job_id, "kind": e.kind, "title_fa": "", "title_en": "",
                         "message": e.message, "text_fa": fa, "text_en": en, "explain": None})
    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows[:limit]


# ------------------------------------------------------------------ CSV (UTF-8 with BOM so Excel shows Persian correctly)

def _safe(cell):
    """Text that starts with = + - @ is run as a formula by Excel (an error text or a log line from another PC could be anything): prefix it."""
    return "'" + cell if isinstance(cell, str) and cell[:1] in ("=", "+", "-", "@", "\t", "\r") else cell


def _csv(header: list[str], rows) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    for r in rows:
        w.writerow([_safe(c) for c in r])
    return "﻿" + out.getvalue()


def csv_section(section: str, start: datetime, end: datetime, params=None, now: datetime | None = None) -> str:
    now = now or timezone.now()
    params = params or {}
    if section == "jobs":
        jobs = Job.objects.filter(created_at__gte=start, created_at__lte=end).order_by("id")
        return _csv(["id", "kind", "title", "status", "computer", "created_at", "first_started_at", "finished_at", "queue_wait_sec", "duration_sec", "gpu_seconds",
                     "attempts", "waits", "error_code", "error_explained", "error"],
                    [[j.pk, j.kind, j.title, j.status, _node_of(j), j.created_at.isoformat(), j.first_started_at.isoformat() if j.first_started_at else "",
                      j.finished_at.isoformat() if j.finished_at else "", _r(queue_wait(j)), _r(j.duration_sec), _r(j.gpu_seconds), j.attempts, j.deferrals, j.error_code,
                      (job_error(j) or {}).get("what_fa", ""), (j.error or "")[:500]] for j in jobs])
    if section == "nodes":
        rep = build_report(start, end, now)
        return _csv(["computer", "online_now", "last_seen", "version", "uptime_percent", "jobs", "succeeded", "failed", "cancelled", "avg_duration_sec", "avg_queue_wait_sec",
                     "gpu_seconds", "waits"],
                    [[n["name"], n["online"], n["last_seen"] or "", n["version"], n["uptime_pct"] if n["uptime_pct"] is not None else "", n["jobs"]["total"],
                      n["jobs"]["succeeded"], n["jobs"]["failed"], n["jobs"]["cancelled"], n["jobs"]["duration"]["avg"] or "", n["jobs"]["wait"]["avg"] or "",
                      n["jobs"]["gpu_seconds"], n["jobs"]["deferrals"]] for n in rep["nodes"]])
    if section == "samples":
        return _csv(["computer", "at", "gpu_util_percent", "gpu_temp_c", "vram_used_mb", "vram_total_mb", "ram_used_mb", "ram_total_mb", "disk_free_gb", "disk_total_gb"],
                    [[s.node, s.at.isoformat(), s.gpu_util, s.gpu_temp, s.vram_used_mb, s.vram_total_mb, s.ram_used_mb, s.ram_total_mb, s.disk_free_gb, s.disk_total_gb]
                     for s in NodeSample.objects.filter(at__gte=start, at__lte=end).order_by("node", "at")[:50000]])
    if section == "sessions":
        rows = []
        for s in NodeSession.objects.filter(started_at__lt=end).filter(Q(ended_at__isnull=True) | Q(ended_at__gt=start)).order_by("node", "started_at"):
            a, b = _session_bounds(s, now)
            rows.append([s.node, a.isoformat(), b.isoformat(), round((b - a).total_seconds() / 60, 1), s.version])
        return _csv(["computer", "online_from", "online_until", "minutes", "version"], rows)
    if section == "logs":
        rows = search_logs({**params, "limit": 500}, start, end)
        return _csv(["at", "source", "level", "computer", "job", "kind", "message"], [[r["at"], r["source"], r["level"], r["node"], r["job"] or "", r["kind"],
                                                                                      r["message"] or r.get("text_fa", "")] for r in rows])
    if section == "errors":
        rep = build_report(start, end, now)
        return _csv(["code", "what", "advice", "count", "last_at", "sample"], [[g["code"], g["what_fa"], g["advice_fa"], g["count"], g["last_at"] or "", g["sample"]] for g in rep["errors"]])
    if section == "downloads":
        rep = build_report(start, end, now)
        return _csv(["id", "title", "state", "status", "target", "window", "created_at", "started_at", "finished_at", "duration_sec", "error"],
                    [[d["id"], d["title"], d["state_fa"], d["status"], d["target"], d["window"], d["created_at"], d["started_at"] or "", d["finished_at"] or "", _r(d["duration_sec"]),
                      d["error"]] for d in rep["downloads"]])
    raise ValueError(section)


CSV_SECTIONS = ("jobs", "nodes", "samples", "sessions", "logs", "errors", "downloads")


def _r(v):
    return "" if v is None else round(float(v), 1)
