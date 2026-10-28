"""Thin ComfyUI HTTP client (queue a prompt, wait for the result, download outputs, free VRAM, interrupt).

Polling only (no websocket dependency). Adapted from the call pattern of Qasem processing-server/upmarket_comfyui_flask/app.py.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from instai.providers.base import ProviderError


@dataclass
class OutputFile:
    filename: str
    subfolder: str
    type: str
    node_id: str
    kind: str  # images | gifs | video | audio


class ComfyCancelled(Exception):
    pass


class ComfyClient:
    def __init__(self, base_url: str, client_id: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id or f"instai-{uuid.uuid4().hex[:8]}"

    # ---- small helpers
    def _get(self, path: str, timeout: float = 10, **kw):
        try:
            r = requests.get(self.base_url + path, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            raise ProviderError(f"ComfyUI GET {path} failed: {type(e).__name__}") from e

    def _post(self, path: str, timeout: float = 30, **kw):
        try:
            return requests.post(self.base_url + path, timeout=timeout, **kw)
        except requests.RequestException as e:
            raise ProviderError(f"ComfyUI POST {path} failed: {type(e).__name__}") from e

    def is_up(self) -> bool:
        try:
            requests.get(self.base_url + "/system_stats", timeout=2).raise_for_status()
            return True
        except requests.RequestException:
            return False

    def object_info(self) -> dict:
        return self._get("/object_info", timeout=30).json()

    def system_stats(self) -> dict:
        return self._get("/system_stats", timeout=5).json()

    # ---- running graphs
    def queue_prompt(self, graph: dict) -> str:
        r = self._post("/prompt", json={"prompt": graph, "client_id": self.client_id})
        if r.status_code != 200:
            detail = ""
            try:
                j = r.json()
                detail = (j.get("error") or {}).get("message", "") or str(j)[:300]
                ne = j.get("node_errors") or {}
                if ne:
                    detail += " | node errors: " + "; ".join(f"{k}: {v.get('class_type')}" for k, v in ne.items())
            except ValueError:
                detail = r.text[:300]
            # 400 = the graph itself is wrong or a model file is missing: trying again cannot help
            raise ProviderError(f"ComfyUI rejected the workflow (HTTP {r.status_code}): {detail}", retryable=r.status_code >= 500)
        return r.json()["prompt_id"]

    def history(self, prompt_id: str) -> dict | None:
        j = self._get(f"/history/{prompt_id}", timeout=10).json()
        return j.get(prompt_id)

    def interrupt(self, prompt_id: str | None = None) -> None:
        try:
            if prompt_id:
                self._post("/queue", json={"delete": [prompt_id]}, timeout=5)
            self._post("/interrupt", timeout=5)
        except ProviderError:
            pass

    def free(self) -> None:
        """Unload models and free VRAM (what the GPU arbiter calls before an LLM or voice job)."""
        self._post("/free", json={"unload_models": True, "free_memory": True}, timeout=30)

    def upload_image(self, path: Path, name: str | None = None) -> str:
        with open(path, "rb") as f:
            r = self._post("/upload/image", files={"image": (name or path.name, f, "image/png")}, data={"overwrite": "true"}, timeout=60)
        if r.status_code != 200:
            raise ProviderError(f"ComfyUI image upload failed (HTTP {r.status_code})", retryable=r.status_code >= 500)
        j = r.json()
        return (j.get("subfolder") + "/" if j.get("subfolder") else "") + j["name"]

    def wait(self, prompt_id: str, *, timeout: float = 3600, poll: float = 1.0,
             on_tick: Callable[[float], None] | None = None, cancel: Callable[[], bool] | None = None) -> list[OutputFile]:
        t0 = time.time()
        while True:
            if cancel and cancel():
                self.interrupt(prompt_id)
                raise ComfyCancelled()
            h = self.history(prompt_id)
            if h:
                st = (h.get("status") or {})
                if st.get("status_str") == "error":
                    msgs = [m for m in st.get("messages", []) if m and m[0] == "execution_error"]
                    detail = (msgs[-1][1].get("exception_message") if msgs else "") or "unknown error"
                    raise ProviderError(f"ComfyUI execution error: {detail}", retryable=False)
                if h.get("outputs") is not None and (st.get("completed") or st.get("status_str") == "success" or h["outputs"]):
                    return self._collect(h["outputs"])
            if time.time() - t0 > timeout:
                self.interrupt(prompt_id)
                raise ProviderError("ComfyUI job timed out", retryable=True)
            if on_tick:
                on_tick(time.time() - t0)
            time.sleep(poll)

    @staticmethod
    def _collect(outputs: dict) -> list[OutputFile]:
        files: list[OutputFile] = []
        for node_id, out in outputs.items():
            for kind in ("images", "gifs", "video", "audio"):
                for f in out.get(kind, []) or []:
                    if isinstance(f, dict) and f.get("filename") and f.get("type", "output") == "output":
                        files.append(OutputFile(f["filename"], f.get("subfolder", ""), "output", node_id, kind))
        return files

    def download(self, f: OutputFile, dest: Path) -> Path:
        r = self._get("/view", timeout=120, params={"filename": f.filename, "subfolder": f.subfolder, "type": f.type}, stream=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.replace(dest)
        return dest

    def run(self, graph: dict, *, timeout: float = 3600, on_tick=None, cancel=None) -> tuple[str, list[OutputFile]]:
        pid = self.queue_prompt(graph)
        return pid, self.wait(pid, timeout=timeout, on_tick=on_tick, cancel=cancel)
