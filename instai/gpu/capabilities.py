"""What THIS PC can do for the GPU tasks (used for routing and reported by worker PCs).

Capability names: `gpu`; `comfy:<workflow id>` (the ComfyUI on this PC has the nodes and model files); `voice:moss`, `voice:sfx`,
`voice:music`, `voice:piper`, `voice:pocket`. Detected at call time, never hard-coded.
"""
from __future__ import annotations

TASK_NEEDS = {"voice.tts": lambda p: [f"voice:{p.get('engine')}"] if p.get("engine") in ("moss", "piper", "pocket") else [],
              "voice.sfx": lambda p: ["voice:sfx"], "voice.music": lambda p: ["voice:music"],
              "comfy.graph": lambda p: [f"comfy:{p['workflow']}"] if p.get("workflow") else [], "bench.node": lambda p: []}
# free VRAM a task needs before it may start on a PC (MB); 0 = no GPU needed
VRAM_NEED = {"comfy": 10500, "moss": 9500, "sfx": 8000, "music": 7000, "piper": 0, "pocket": 0}


def local_capabilities(refresh: bool = False) -> dict:
    from instai.core import hardware, runtime
    from instai.providers.audio import services
    from instai.providers.tts import MossTTS, PiperTTS, PocketTTS

    caps: list[str] = []
    gpu = hardware.gpu_status()
    if gpu:
        caps.append("gpu")
    info = hardware.comfy_object_info(runtime.comfyui_url(), force=refresh)
    workflows: dict = {}
    startable = False
    if info is not None:
        from instai.providers.comfy.workflows import workflow_availability

        for w in workflow_availability(info):
            workflows[w["id"]] = {"available": w["available"], "missing": (w["missing_models"] + w["missing_nodes"])[:4]}
            if w["available"]:
                caps.append(f"comfy:{w['id']}")
    else:
        # ComfyUI is not running but model discovery found it with a launcher: what its files allow counts, and the task starts it
        try:
            from instai.core import model_status

            workflows = model_status.workflows_ready_on_disk()
        except Exception:  # noqa: BLE001 - detection must never break routing
            workflows = {}
        startable = bool(workflows)
        caps += [f"comfy:{wid}" for wid, w in workflows.items() if w["available"]]
    voices: dict = {}
    for key, ok in (("moss", MossTTS().available()[0]), ("piper", PiperTTS().available()[0]), ("pocket", PocketTTS().available()[0]),
                    ("sfx", services.installed("sfx") or services.health("sfx", 0.5)["status"] == "ready"),
                    ("music", services.installed("music") or services.health("music", 0.5)["status"] == "ready")):
        voices[key] = bool(ok)
        if ok:
            caps.append(f"voice:{key}")
    return {"caps": sorted(set(caps)), "gpu_name": (gpu or {}).get("name") or "", "vram_total_mb": int((gpu or {}).get("total_mb") or 0),
            "vram_free_mb": int(((gpu or {}).get("total_mb") or 0) - ((gpu or {}).get("used_mb") or 0)) if gpu else 0,
            "models": {"comfyui": info is not None, "comfyui_startable": startable, "workflows": workflows, "voices": voices}}


def needs_for(kind: str, payload: dict) -> list[str]:
    fn = TASK_NEEDS.get(kind)
    return fn(payload) if fn else []


def vram_for(kind: str, payload: dict) -> int:
    if kind == "comfy.graph" or kind == "bench.node":
        return VRAM_NEED["comfy"]
    if kind == "voice.tts":
        return VRAM_NEED.get(str(payload.get("engine") or "moss"), VRAM_NEED["moss"])
    if kind == "voice.sfx":
        return VRAM_NEED["sfx"]
    if kind == "voice.music":
        return VRAM_NEED["music"]
    return 0
