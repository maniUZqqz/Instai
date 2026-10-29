"""Adapted from Qasem: processing-server/audio/acestep_server.py (same /health + /run protocol as the NMarketing agent).
InstAI runs these from its own folder: `--home` is the InstAI root (models/ and vendor/ live there).

Background music: ACE-Step 1.5 (MIT; its output may be used commercially) through its own REST API.

Run by agent.py inside venvs\\acestep (Download-Models.bat makes it):

    venvs\\acestep\\Scripts\\python.exe audio\\acestep_server.py --port 5642

This only prepares ACE-Step's own API server (acestep/api_server.py, as its start_api_server.bat does) for this
node: the checkpoints downloaded into models\\acestep\\checkpoints, no 5Hz language model (instrumental beds do
not need it and it would take 4 GB more of VRAM), no flash-attention (no Windows wheel for Python 3.12), no
automatic downloads, and the models load at start-up so an open port means "ready". The agent then speaks the
documented API: POST /release_task, POST /query_result, GET /v1/audio?path=..., GET /health.
The process exits with the agent (--parent-pid), like the other GPU workers.
"""
import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parent_alive  # noqa: E402


def run_fake(port, parent_pid):
    """ACE-Step's REST protocol (release_task / query_result / v1/audio / health) answered with a test tone: tests and smoke checks."""
    import json
    import tempfile
    import uuid
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse

    from _common import fake_tone, write_wav

    tasks = {}
    tmp = tempfile.mkdtemp(prefix="acestep-fake-")

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/health":
                return self._json({"data": {"status": "ok"}, "code": 200})
            if u.path == "/v1/audio":
                path = parse_qs(u.query).get("path", [""])[0]
                if not path.startswith(tmp) or not os.path.isfile(path):
                    return self._json({"error": "not found"}, 404)
                data = open(path, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
            return self._json({"error": "unknown path"}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            u = urlparse(self.path)
            if u.path == "/release_task":
                tid = uuid.uuid4().hex
                secs = float(body.get("audio_duration") or 10)
                out = os.path.join(tmp, tid + ".wav")
                write_wav(out, fake_tone(min(secs, 20.0), 24000, 330.0), 24000)
                tasks[tid] = {"file": "/v1/audio?path=" + out, "duration": secs}
                return self._json({"data": {"task_id": tid}, "code": 200})
            if u.path == "/query_result":
                rows = []
                for tid in body.get("task_id_list", []):
                    t = tasks.get(tid)
                    rows.append({"task_id": tid, "status": 1 if t else 2,
                                 "result": json.dumps([{"file": t["file"], "metas": {"duration": t["duration"], "bpm": 100}}]) if t else "unknown task"})
                return self._json({"data": rows, "code": 200})
            return self._json({"error": "unknown path"}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", port), H)
    if parent_pid:
        def watchdog():
            while True:
                time.sleep(5)
                if not parent_alive(parent_pid):
                    os._exit(0)
        threading.Thread(target=watchdog, daemon=True).start()
    print("[acestep] fake REST server on http://127.0.0.1:%d" % port, flush=True)
    server.serve_forever()


def main():
    ap = argparse.ArgumentParser(description="InstAI: ACE-Step 1.5 API server")
    ap.add_argument("--port", type=int, default=5642)
    ap.add_argument("--home", default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    ap.add_argument("--models-dir", default="", help="folder with acestep/checkpoints (e.g. NMarketing's, found by model discovery)")
    ap.add_argument("--vendor-dir", default="", help="folder with ACE-Step-1.5/")
    ap.add_argument("--work-dir", default="", help="scratch folder for tmp/ and cache/ (InstAI's data folder; never another product's)")
    ap.add_argument("--fake", action="store_true", help="no models: speak ACE-Step's REST protocol with a test tone (tests)")
    ap.add_argument("--parent-pid", type=int, default=0)
    args = ap.parse_args()
    if args.fake:
        return run_fake(args.port, args.parent_pid)
    repo = os.path.join(args.vendor_dir or os.path.join(args.home, "vendor"), "ACE-Step-1.5")
    root = os.path.join(args.models_dir or os.path.join(args.home, "models"), "acestep")
    work = args.work_dir or root
    for p in (os.path.join(repo, "acestep", "api_server.py"), os.path.join(root, "checkpoints", "acestep-v15-turbo")):
        if not os.path.exists(p):
            print("missing %s - run Download-Models.bat" % p, flush=True)
            sys.exit(2)
    env = {
        "ACESTEP_PROJECT_ROOT": root,            # checkpoints\ lives here (only read)
        "ACESTEP_CONFIG_PATH": "acestep-v15-turbo",
        "ACESTEP_INIT_LLM": "false",
        "ACESTEP_USE_FLASH_ATTENTION": "false",
        "ACESTEP_NO_INIT": "false",              # load at start-up: an open port means ready
        "ACESTEP_DOWNLOAD_SOURCE": "huggingface",
        "ACESTEP_TMPDIR": os.path.join(work, "tmp"),
        "TRITON_CACHE_DIR": os.path.join(work, "cache", "triton"),
        "TORCHINDUCTOR_CACHE_DIR": os.path.join(work, "cache", "inductor"),
        "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1",
    }
    for k, v in env.items():
        os.environ.setdefault(k, v)
    os.makedirs(os.environ["ACESTEP_TMPDIR"], exist_ok=True)
    os.chdir(root)
    sys.path.insert(0, repo)
    if args.parent_pid:
        def watchdog():
            while True:
                time.sleep(5)
                if not parent_alive(args.parent_pid):
                    print("[acestep] the agent is gone - exiting to free the GPU", flush=True)
                    os._exit(0)
        threading.Thread(target=watchdog, daemon=True).start()
    from acestep.api_server import main as api_main

    sys.argv = ["acestep-api", "--host", "127.0.0.1", "--port", str(args.port)]
    api_main()


if __name__ == "__main__":
    main()
