"""In-process fake HTTP services (Ollama, OpenAI-compatible API, ComfyUI, MOSS-TTS) so every real adapter is tested without a GPU."""
from __future__ import annotations

import io
import json
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image


def sample_from_schema(schema: dict, key: str = "") -> object:
    """Minimal valid value for a (lite) JSON schema - what a well-behaved structured-output model would return."""
    t = schema.get("type")
    t = t[0] if isinstance(t, list) else t
    if "enum" in schema:
        return schema["enum"][0]
    if t == "object":
        props = schema.get("properties", {})
        return {k: sample_from_schema(v, k) for k, v in props.items() if k in schema.get("required", [])}
    if t == "array":
        n = max(schema.get("minItems", 1), 1)
        return [sample_from_schema(schema.get("items", {"type": "string"}), key) for _ in range(n)]
    if t == "integer":
        return max(1, schema.get("minimum", 1))
    if t == "number":
        return float(max(1, schema.get("minimum", 1)))
    if t == "boolean":
        return True
    if key == "text":
        return " ".join(["word"] * 14)  # long enough to pass the script length checks
    return f"{key or 'text'} sample"


class _Server:
    def __init__(self, handler_cls):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.httpd.owner = self
        self.requests: list[dict] = []
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode() or "{}")
        except ValueError:
            return {"_raw": raw}

    def record(self, body=None):
        self.server.owner.requests.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body})


# ------------------------------------------------------------------ Ollama

class OllamaHandler(_H):
    def do_GET(self):
        self.record()
        o = self.server.owner
        if self.path == "/api/tags":
            self.send_json({"models": [{"name": n, "size": 5_000_000_000, "details": {"parameter_size": "8B", "quantization_level": "Q4_K_M"}} for n in o.models]})
        elif self.path == "/api/ps":
            self.send_json({"models": [{"name": n, "size_vram": 5_000_000_000} for n in o.loaded]})
        else:
            self.send_json({}, 404)

    def do_POST(self):
        b = self.body()
        self.record(b)
        o = self.server.owner
        if self.path == "/api/generate":  # unload
            if b.get("keep_alive") == 0 and b.get("model") in o.loaded:
                o.loaded.remove(b["model"])
            return self.send_json({"done": True})
        if self.path == "/api/chat":
            if b.get("model") not in o.models:
                return self.send_json({"error": "model not found"}, 404)
            if "think" in b and o.reject_think:
                return self.send_json({"error": "model does not support think"}, 400)
            o.loaded.add(b["model"]) if hasattr(o.loaded, "add") else o.loaded.append(b["model"])
            fmt = b.get("format")
            content = json.dumps(sample_from_schema(fmt), ensure_ascii=False) if isinstance(fmt, dict) else "ok"
            if o.thinking_prefix:
                content = "<think>hmm</think>" + content
            return self.send_json({"message": {"role": "assistant", "content": content}, "done": True, "done_reason": "stop",
                                   "eval_count": 100, "eval_duration": 2_000_000_000, "prompt_eval_count": 50})
        self.send_json({}, 404)


def ollama_server(models=("qwen3:8b", "gemma3:12b"), loaded=("qwen3:8b",), reject_think=False, thinking_prefix=False) -> _Server:
    s = _Server(OllamaHandler)
    s.models, s.loaded, s.reject_think, s.thinking_prefix = list(models), set(loaded), reject_think, thinking_prefix
    return s


# ------------------------------------------------------------------ OpenAI-compatible

class OpenAIHandler(_H):
    def _auth(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {self.server.owner.key}"

    def do_GET(self):
        self.record()
        if not self._auth():
            return self.send_json({"error": "bad key"}, 401)
        if self.path == "/v1/models":
            self.send_json({"data": [{"id": "gpt-test"}, {"id": "other"}]})
        else:
            self.send_json({}, 404)

    def do_POST(self):
        b = self.body()
        self.record(b)
        o = self.server.owner
        if not self._auth():
            return self.send_json({"error": "bad key"}, 401)
        if self.path == "/v1/chat/completions":
            if o.fail_times > 0:
                o.fail_times -= 1
                return self.send_json({"error": "overloaded"}, 503)
            if b.get("response_format", {}).get("type") == "json_schema" and o.reject_json_schema:
                return self.send_json({"error": "unsupported response_format"}, 400)
            rf = b.get("response_format") or {}
            schema = (rf.get("json_schema") or {}).get("schema")
            content = json.dumps(sample_from_schema(schema)) if schema else (o.reply or '{"ok": true}')
            return self.send_json({"model": b.get("model"), "choices": [{"message": {"role": "assistant", "content": content}}],
                                   "usage": {"prompt_tokens": 10, "completion_tokens": 20}})
        self.send_json({}, 404)


def openai_server(key="sk-test-secret-key-123456", fail_times=0, reject_json_schema=False, reply=None) -> _Server:
    s = _Server(OpenAIHandler)
    s.key, s.fail_times, s.reject_json_schema, s.reply = key, fail_times, reject_json_schema, reply
    return s


# ------------------------------------------------------------------ ComfyUI

def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (max(8, w // 16), max(8, h // 16)), (40, 90, 160)).save(buf, "PNG")
    return buf.getvalue()


class ComfyHandler(_H):
    def do_GET(self):
        o = self.server.owner
        u = urlparse(self.path)
        self.record()
        if u.path == "/object_info":
            return self.send_json(o.object_info())
        if u.path == "/system_stats":
            return self.send_json({"system": {"comfyui_version": "fake-0.3"}, "devices": []})
        if u.path.startswith("/history/"):
            pid = u.path.rsplit("/", 1)[1]
            h = o.history.get(pid)
            if h is None:
                return self.send_json({})
            if h.get("polls_left", 0) > 0:
                h["polls_left"] -= 1
                return self.send_json({})
            return self.send_json({pid: {k: v for k, v in h.items() if k != "polls_left"}})
        if u.path == "/view":
            q = parse_qs(u.query)
            data = o.files.get(q["filename"][0])
            if data is None:
                return self.send_json({}, 404)
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_json({}, 404)

    def do_POST(self):
        o = self.server.owner
        if self.path == "/upload/image":
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            self.record("<multipart>")
            o.uploads += 1
            return self.send_json({"name": "uploaded.png", "subfolder": "", "type": "input"})
        b = self.body()
        self.record(b)
        if self.path == "/prompt":
            graph = b.get("prompt", {})
            if o.reject:
                return self.send_json({"error": {"message": "Prompt outputs failed validation"}, "node_errors": {"4": {"class_type": "CLIPTextEncode"}}}, 400)
            pid = f"p{len(o.history) + 1}"
            o.prompt_times.append(time.time())
            outputs, errors = {}, None
            for nid, node in graph.items():
                if node["class_type"] == "SaveImage":
                    lat = next((n for n in graph.values() if n["class_type"] == "EmptyLatentImage"), {"inputs": {"width": 64, "height": 64}})["inputs"]
                    fn = f"img_{pid}_{nid}.png"
                    o.files[fn] = _png(lat["width"], lat["height"])
                    outputs[nid] = {"images": [{"filename": fn, "subfolder": "", "type": "output"}]}
                elif node["class_type"] == "SaveVideo":
                    fn = f"vid_{pid}_{nid}.mp4"
                    o.files[fn] = o.video_bytes(graph) if getattr(o, "video_bytes", None) else b"not-a-real-mp4"
                    outputs[nid] = {"images": [{"filename": fn, "subfolder": "", "type": "output"}], "animated": [True]}
            entry = {"outputs": outputs, "status": {"status_str": "success", "completed": True, "messages": []}, "polls_left": o.polls}
            if o.execution_error:
                entry = {"outputs": {}, "status": {"status_str": "error", "completed": False,
                                                   "messages": [["execution_error", {"exception_message": "CUDA out of memory"}]]}, "polls_left": 0}
            o.history[pid] = entry
            o.prompts.append(graph)
            return self.send_json({"prompt_id": pid, "number": len(o.history)})
        if self.path == "/free":
            o.freed += 1
            return self.send_json({})
        if self.path == "/interrupt":
            o.interrupted += 1
            return self.send_json({})
        if self.path == "/queue":
            return self.send_json({})
        self.send_json({}, 404)


def comfy_server(missing_models=(), polls=0, reject=False, execution_error=False) -> _Server:
    from instai.providers.comfy.workflows import WORKFLOWS

    s = _Server(ComfyHandler)
    s.history, s.files, s.prompts, s.prompt_times, s.video_bytes = {}, {}, [], [], None
    s.freed = s.interrupted = s.uploads = 0
    s.polls, s.reject, s.execution_error = polls, reject, execution_error

    def object_info():
        info = {}
        for w in WORKFLOWS.values():
            for n in w.required_nodes:
                info.setdefault(n, {"input": {"required": {}}})
            for node, key, fname in w.required_models:
                if fname in missing_models:
                    info[node]["input"]["required"].setdefault(key, [[]])
                    continue
                opts = info[node]["input"]["required"].setdefault(key, [[]])[0]
                if fname not in opts:
                    opts.append(fname)
        return info

    s.object_info = object_info
    return s


# ------------------------------------------------------------------ MOSS-TTS

class MossHandler(_H):
    def do_GET(self):
        self.record()
        if self.path == "/health":
            self.send_json({"engine": "moss-tts", "status": self.server.owner.status})
        else:
            self.send_json({}, 404)

    def do_POST(self):
        b = self.body()
        self.record(b)
        if self.path == "/run":
            secs = max(1.0, len(b["text"]) / 12.5)
            with wave.open(b["out"], "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(24000)
                w.writeframes(b"\x00\x01" * int(24000 * secs))
            return self.send_json({"ok": True, "seconds": secs, "sample_rate": 24000})
        self.send_json({}, 404)


def moss_server(status="ready") -> _Server:
    s = _Server(MossHandler)
    s.status = status
    return s


def wait_until(pred, timeout=5.0, step=0.02):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return False


def make_test_video(width: int, height: int, frames: int, fps: float = 16.0, color_shift: int = 0) -> bytes:
    """A real small H.264 clip (ffmpeg testsrc) - what a fake Wan returns so retake/stitch code runs on real video."""
    import subprocess
    import tempfile
    from pathlib import Path

    from instai.core import runtime

    ff = runtime.ffmpeg_info()["ffmpeg"]
    d = Path(tempfile.mkdtemp(prefix="fakevid-"))
    out = d / "v.mp4"
    vf = f"hue=h={color_shift}" if color_shift else "null"
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s={width}x{height}:r={fps}", "-vf", vf, "-frames:v", str(frames),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(out)], check=True)
    data = out.read_bytes()
    import shutil

    shutil.rmtree(d, ignore_errors=True)
    return data
