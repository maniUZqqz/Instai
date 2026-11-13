"""Scheduled downloads: every download InstAI makes (model packages, voices, ffmpeg, the optional anime models, Ollama models) is a queue job
that can start NOW, AT a time (03:30) or INSIDE the night window (default 02:00-07:00, local time), on this PC or on a paired worker PC.

* a download waits for the clock AND for its computer: the window decides when, `defer` (jobs/queue.py) keeps it waiting while the target
  PC or Ollama is off;
* stopping is safe: the window closing (or Cancel) kills the downloader / closes the Ollama stream; the next run resumes from the partial
  files (scripts/download_models.py is resumable, Ollama keeps finished parts);
* the owner's defaults live in the setting `ops_config` (Downloads page): "now" or "night window", the window, an optional maximum wait.
"""
from __future__ import annotations

import re
from datetime import datetime

from django.utils import timezone

from instai.core.errors import DomainError
from instai.jobs import queue, schedule
from instai.jobs.models import Job, WorkerNode

OLLAMA_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,98}$")
# a few sensible suggestions for the Ollama field (the owner can type any name); sizes are rough and only a hint
OLLAMA_SUGGESTIONS = [
    {"model": "qwen3:8b", "fa": "پیشنهاد InstAI برای کارت ۱۲ گیگابایتی؛ کامل روی GPU جا می‌شود", "en": "InstAI's pick for a 12 GB card; fits the GPU completely", "gb": 5.2},
    {"model": "qwen3:14b", "fa": "کیفیت بهتر؛ برای ۱۲ گیگابایت نزدیک مرز است", "en": "Better quality; close to the limit of 12 GB", "gb": 9.3},
    {"model": "gemma3:12b", "fa": "گزینهٔ دیگر برای متن و ترجمه", "en": "Another option for text and translation", "gb": 8.1},
    {"model": "qwen3:4b", "fa": "سبک؛ برای کارت ۴ گیگابایتی (رایانهٔ B)", "en": "Light; for a 4 GB card (computer B)", "gb": 2.6},
]


def titles(job: Job) -> tuple[str, str]:
    """(Persian, English) title of a download job, built from what it fetches and where (the stored `title` is only Persian)."""
    p = job.payload or {}
    what = ", ".join(str(x) for x in (p.get("packages") or [])) or str(p.get("model") or "")
    tgt = p.get("target_name")
    to_fa = f" ← {tgt}" if tgt and tgt != "local" else ""
    to_en = f" -> {tgt}" if tgt and tgt != "local" else ""
    if job.kind == "downloads.ollama":
        return f"دانلود مدل Ollama: {what}", f"Download of the Ollama model: {what}"
    return f"دانلود: {what}{to_fa}", f"Download: {what}{to_en}"


def targets() -> list[dict]:
    """Where a download can go: this PC, or a paired worker PC."""
    from instai.gpu import compute

    out = [{"id": "local", "name": "کامپیوتر اصلی (A)", "name_en": "Main PC (A)", "online": True}]
    now = timezone.now()
    for w in WorkerNode.objects.filter(enabled=True):
        online = bool(w.last_seen and (now - w.last_seen).total_seconds() < compute.ONLINE_SECONDS)
        out.append({"id": str(w.pk), "name": f"کامپیوتر {w.name}", "name_en": f"Computer {w.name}", "online": online, "can_download": "downloads" in (w.capabilities or [])})
    return out


def resolve_target(raw) -> tuple[str, str]:
    """"local" / None -> ("local", "local");  a worker id -> (id, name). Unknown worker -> a Persian error."""
    if raw in (None, "", "local"):
        return "local", "local"
    try:
        w = WorkerNode.objects.filter(pk=int(raw), enabled=True).first()
    except (TypeError, ValueError):
        w = None
    if w is None:
        raise DomainError("validation_error", "این رایانه پیدا نشد یا غیرفعال است.", http_status=400, details={"target": ["unknown"]},
                          message_en="That computer was not found or is disabled.")
    return str(w.pk), w.name


def _schedule(when, now: datetime | None = None) -> tuple[dict, datetime | None]:
    try:
        sched = schedule.resolve(when, now=now)
    except schedule.ScheduleError as e:
        raise DomainError("validation_error", str(e), http_status=400, details={"when": ["invalid"]}, message_en=e.en) from e
    return sched, schedule.first_moment(sched["not_before"], sched["window"], now)


def start_packages(packages: list[str], title: str, *, when=None, target=None, extra: dict | None = None, key_extra: str = "") -> Job:
    """Queue a `downloads.run` job for these package / item ids."""
    tid, tname = resolve_target(target)
    sched, moment = _schedule(when)
    now = timezone.now()
    payload = {"packages": packages, "target": tid, "target_name": tname, "schedule": {"window": sched["window"], "not_before": sched["not_before"].isoformat() if sched["not_before"] else ""}, **(extra or {})}
    key = f"dl:{tid}:{','.join(sorted(packages))}{key_extra}:{int(now.timestamp() // 60)}"
    job = queue.enqueue("downloads.run", payload, title=title + (f" ← {tname}" if tid != "local" else ""), idempotency_key=key, run_after=moment, window=sched["window"])
    return job


def start_ollama(model: str, *, when=None) -> Job:
    model = (model or "").strip()
    if not OLLAMA_NAME.match(model):
        raise DomainError("validation_error", "نام مدل Ollama درست نیست؛ مثل qwen3:8b بنویسید.", http_status=400, details={"model": ["invalid"]},
                          message_en="The Ollama model name is not valid; write it like qwen3:8b.")
    sched, moment = _schedule(when)
    now = timezone.now()
    return queue.enqueue("downloads.ollama", {"model": model, "schedule": {"window": sched["window"]}}, title=f"دانلود مدل Ollama: {model}",
                         idempotency_key=f"dl-ollama:{model}:{int(now.timestamp() // 60)}", run_after=moment, window=sched["window"])


def reschedule(job: Job, when) -> Job:
    """Change the time of a download that has not started. 'now' removes the window too (one-time exception for this download)."""
    if not job.kind.startswith("downloads."):
        raise DomainError("validation_error", "فقط زمان دانلودها قابل تغییر است.", http_status=400, message_en="Only downloads can be rescheduled.")
    if job.status != Job.QUEUED:
        raise DomainError("conflict", "این دانلود شروع شده یا تمام شده است.", message_en="This download has started or finished.")
    sched, moment = _schedule(when)
    now = timezone.now()
    Job.objects.filter(pk=job.pk, status=Job.QUEUED).update(window=sched["window"], run_after=moment or now, ready_at=moment or now, wait_code="", waiting_reason="")
    queue.log_job(job, "rescheduled: " + ("now" if moment is None else moment.isoformat()) + (f" window {sched['window']}" if sched["window"] else ""))
    job.refresh_from_db()
    return job


def run_now(job: Job) -> Job:
    return reschedule(job, "now")


CURATED_GROUPS = ("image", "control", "upscale", "video", "voice")
HF_MIRROR = "https://hf-mirror.com"


def _folder_of(dest: str) -> str:
    r"""The folder a file lands in, as the owner reads it: `{COMFYUI}\models\checkpoints\x.safetensors` -> `ComfyUI\models\checkpoints`."""
    folder = dest.rsplit("\\", 1)[0] if "\\" in dest else dest
    return folder.replace("{COMFYUI}", "ComfyUI").replace("{MODELS}", "InstAI\\models").replace("{TOOLS}", "InstAI\\tools")


def curated(packages: dict | None = None, items: list | None = None, status: dict | None = None) -> list[dict]:
    """The curated model library (manifests/curated.json + the `curated` block of other packages): for each package its files with the exact
    repository / commit / path, size, sha256, destination folder, the mirror link and - from the downloader - whether each file is already
    here (`reused` = the same weights are present under another name or in another folder: de-duplication, nothing is downloaded)."""
    from instai.core import model_status

    if packages is None or items is None:
        packages, items = model_status.manifests()
    status = model_status.package_status(detail=True) if status is None else status
    out = []
    for pid, p in packages.items():
        c = p.get("curated")
        if not c:
            continue
        st = status.get(pid, {})
        det = {d["id"]: d for d in st.get("details", [])}
        files = []
        for it in (i for i in items if i.get("package") == pid and not i.get("fallback_for")):
            hf = it.get("hf") or {}
            d = det.get(it["id"], {})
            files.append({"id": it["id"], "title": it.get("title", it["id"]), "kind": it.get("kind", "file"), "size": int(it.get("size") or 0),
                          "sha256": it.get("sha256") or "", "folder": _folder_of(it.get("dest", "")), "name": str(it.get("dest", "")).rsplit("\\", 1)[-1],
                          "repo": hf.get("repo", ""), "revision": hf.get("revision", ""), "path": hf.get("path", ""), "license": hf.get("license", ""),
                          "url": (it.get("urls") or [""])[0].replace("{HF}", "https://huggingface.co"),
                          "mirror": (it.get("urls") or [""])[0].replace("{HF}", HF_MIRROR) if "{HF}" in ((it.get("urls") or [""])[0]) else "",
                          "installed": bool(d.get("installed")), "reused": bool(d.get("reused")), "where": d.get("where", "") if d.get("installed") else ""})
        commercial = c.get("commercial", "unknown")
        out.append({"id": pid, "title": p.get("title", pid), "group": c.get("group", "image"), "order": int(c.get("order") or 99), "commercial": commercial,
                    "needs_confirm": commercial != "yes", "licence": p.get("licence", ""), "licence_url": c.get("licence_url", ""), "vram": c.get("vram", ""),
                    "why": c.get("why") or {}, "note": c.get("note") or {}, "checked": c.get("checked", ""), "files": files, "needs": c.get("needs") or [],
                    "size": sum(f["size"] for f in files), "missing_size": sum(f["size"] for f in files if not f["installed"]),
                    "installed": sum(1 for f in files if f["installed"]), "reused": sum(1 for f in files if f["reused"]),
                    "complete": bool(files) and all(f["installed"] for f in files), "default": False})
    out.sort(key=lambda x: (CURATED_GROUPS.index(x["group"]) if x["group"] in CURATED_GROUPS else 99, x["order"], x["id"]))
    return out


def needs_licence_confirmation(package_ids: list[str]) -> list[str]:
    """Curated packages among `package_ids` whose licence is not plainly commercial (the UI must have shown it and the owner confirmed)."""
    from instai.core import model_status

    packages, _ = model_status.manifests()
    return [pid for pid in package_ids if ((packages.get(pid) or {}).get("curated") or {}).get("commercial", "yes") != "yes"]


def catalog() -> dict:
    """What can be downloaded (for the Downloads page): packages with sizes, Ollama suggestions, the places a download can go, the defaults."""
    from instai.core import model_status

    packages, _items = model_status.manifests()
    status = model_status.package_status(detail=True)
    items = []
    for pid, p in packages.items():
        st = status.get(pid, {})
        items.append({"id": pid, "title": p.get("title", pid), "group": p.get("group", ""), "offer": bool(p.get("offer")), "curated": bool(p.get("curated")),
                      "size": int(st.get("size") or 0),
                      "missing_size": int(st.get("missing_size") or 0), "complete": bool(st.get("complete")), "default": bool(p.get("default")),
                      "licence": p.get("licence", "")})
    return {"packages": items, "ollama": OLLAMA_SUGGESTIONS, "targets": targets(), "config": schedule.config(),
            "curated": curated(packages, _items, status)}
