"""Console checklist printed by START.bat (English / ASCII only):  python -m instai.core.checklist [--bench-needed]"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instai.settings")


def _line(item: dict) -> str:
    d = item["data"]
    i = item["id"]
    st = {"ok": "OK", "warn": "!!", "missing": "--", "error": "!!"}[item["status"]]
    if i == "python":
        text = f"Python {d.get('version')}"
    elif i == "cpu":
        text = f"CPU {d.get('cores')} cores"
    elif i == "ram":
        text = f"RAM {d.get('total_mb', 0) / 1024:.1f} GB (detected)"
    elif i.startswith("disk_"):
        text = f"Disk {i[5:]}: {d.get('free_gb')} GB free"
    elif i == "gpu":
        text = f"GPU {d['name']} {round((d.get('total_mb') or 0) / 1024)} GB, driver {d.get('driver')}" if d else "GPU: no NVIDIA GPU found (video generation needs one)"
    elif i == "ollama":
        n = len(d.get("models", []))
        text = f"Ollama: {n} models" if n or item["status"] == "ok" else "Ollama: not running (optional: an API provider can be used instead)"
    elif i == "comfyui":
        w = d.get("workflows") or []
        text = f"ComfyUI: {d.get('node_count')} nodes, {sum(1 for x in w if x['available'])}/{len(w)} workflows ready" if d.get("node_count") else "ComfyUI: not running (needed for images and video)"
    elif i == "ffmpeg":
        text = f"ffmpeg {d.get('version')}" if d.get("ffmpeg") else "ffmpeg: missing"
    elif i.startswith("tts_"):
        text = f"Voice engine {d.get('engine')}: " + ("ready" if item["status"] == "ok" else "not ready")
    else:
        text = f"{i}: " + ("found" if item["status"] == "ok" else "not found (not needed yet)")
    return f"  [{st}] {text}"


def main() -> int:
    import django

    django.setup()
    from instai.core import hardware

    r = hardware.detect_all(refresh=True)
    by = {i["id"]: i for i in r["items"]}
    if "--bench-needed" in sys.argv:
        from django.conf import settings

        if os.path.exists(os.path.join(settings.DATA_DIR, "benchmark_prompted.txt")):
            return 1
        from instai.core.models import BenchmarkRun

        has_gpu = by["gpu"]["status"] in ("ok", "warn")
        has_service = by["comfyui"]["status"] != "missing" or by["ollama"]["status"] != "missing"
        if has_gpu and has_service and not BenchmarkRun.objects.exists():
            open(os.path.join(settings.DATA_DIR, "benchmark_prompted.txt"), "w").write("asked once\n")
            return 0
        return 1
    print("  Checklist")
    for item in r["items"]:
        print(_line(item))
    return 0


if __name__ == "__main__":
    sys.exit(main())
