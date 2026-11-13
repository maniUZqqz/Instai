"""START.bat self-check and self-repair. Runs with the project's venv Python. English / ASCII console text only.

Steps: packages (pinned, mirror fallback) -> .env -> ffmpeg -> UI build (only if Node exists and sources changed) ->
database migration -> hardware/model checklist.   Exit code: 0 fine, 2 cannot continue.
With --bench-needed: exit 0 when this looks like a first run on a GPU machine (no benchmark yet), else 1.
"""
import hashlib
import os
import re
import socket
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
PY = sys.executable
MIRRORS = ["https://mirror-pypi.runflare.com/simple", "https://mirrors.aliyun.com/pypi/simple"]


def say(tag: str, msg: str) -> None:
    print(f"  [{tag}] {msg}", flush=True)


def run(cmd, **kw) -> int:
    return subprocess.call(cmd, cwd=ROOT, **kw)


def install_requirements() -> bool:
    req = os.path.join(ROOT, "requirements.txt")
    stamp = os.path.join(ROOT, ".venv", ".requirements.sha256")
    want = hashlib.sha256(open(req, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
    try:
        have = open(stamp).read().strip()
    except OSError:
        have = ""
    if want == have:
        say("OK", "Python packages are installed")
        return True
    say("..", "Installing Python packages (first run: a minute or two) ...")
    base = [PY, "-m", "pip", "install", "--disable-pip-version-check", "--default-timeout", "60", "--retries", "5", "-q", "-r", req]
    ok = run(base) == 0
    for m in MIRRORS:
        if ok:
            break
        say("..", "PyPI failed; trying a mirror: " + m.split("//")[1].split("/")[0])
        ok = run(base + ["-i", m]) == 0
    if not ok:
        say("!!", "Could not install the packages. Check the internet connection and run START.bat again.")
        return False
    with open(stamp, "w") as f:
        f.write(want)
    say("OK", "Python packages installed")
    return True


def ensure_env() -> None:
    env, example = os.path.join(ROOT, ".env"), os.path.join(ROOT, ".env.example")
    if not os.path.exists(env) and os.path.exists(example):
        with open(example, "rb") as s, open(env, "wb") as d:
            d.write(s.read())
        say("OK", "Created .env from .env.example (settings and the API key are kept there; it is never committed)")


def _env_value(path: str, key: str) -> str | None:
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                m = re.match(r"^\s*%s\s*=\s*(.*?)\s*$" % re.escape(key), line)
                if m:
                    return m.group(1).strip("\"'")
    except OSError:
        pass
    return None


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def _is_instai(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with urllib.request.urlopen("http://%s:%d/api/health" % (host, port), timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def ensure_port() -> int:
    """InstAI shares this PC with other programs (NMarketing's agent, ComfyUI, Ollama ...). When the port InstAI would use (INSTAI_PORT, default
    8765) is held by another program, the next free port is chosen and saved in .env (once), so START.bat never fails on a port clash."""
    envfile = os.path.join(ROOT, ".env")
    chosen = os.environ.get("INSTAI_PORT") or _env_value(envfile, "INSTAI_PORT")
    port = int(chosen) if chosen and chosen.isdigit() else 8765
    if _port_free(port) or _is_instai(port):
        return port
    if chosen:
        say("!!", "Port %d (INSTAI_PORT) is used by another program. Change INSTAI_PORT in .env or close that program." % port)
        return port
    for cand in range(port + 1, port + 40):
        if _port_free(cand):
            with open(envfile, "a", encoding="utf-8", newline="") as f:
                lead = "\n" if os.path.exists(envfile) and os.path.getsize(envfile) else ""
                f.write(lead + "INSTAI_PORT=%d\n" % cand)
            say("OK", "Port %d is used by another program; InstAI will use port %d (saved in .env)" % (port, cand))
            return cand
    say("!!", "No free port found near %d; set INSTAI_PORT in .env" % port)
    return port


def ensure_ffmpeg() -> None:
    probe = ("import sys; sys.path.insert(0, %r); import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','instai.settings'); "
             "import django; django.setup(); from instai.core import runtime; i = runtime.ffmpeg_info(); "
             "sys.exit(0 if i['ffmpeg'] else 1)" % ROOT)
    if run([PY, "-c", probe]) == 0:
        say("OK", "ffmpeg found")
        return
    say("..", "ffmpeg not found; downloading the pinned build (about 30 MB, once) ...")
    rc = run([PY, os.path.join("scripts", "download_models.py"), "--only", "ffmpeg", "--yes"])
    say("OK" if rc == 0 else "!!", "ffmpeg ready" if rc == 0 else "ffmpeg download failed (videos cannot be assembled until it is fixed)")


def main() -> int:
    if "--bench-needed" in sys.argv:
        return run([PY, "-m", "instai.core.checklist", "--bench-needed"])
    if not install_requirements():
        return 2
    ensure_env()
    if "--worker" not in sys.argv:
        ensure_port()
    if "--worker" in sys.argv:        # PC B: no UI, no database; only ffmpeg and the capability checklist
        os.environ["INSTAI_WORKER_MODE"] = "1"
        ensure_ffmpeg()
        run([PY, "-m", "instai.core.checklist"])
        return 0
    run([PY, os.path.join("scripts", "build_ui.py")])
    if run([PY, "manage.py", "migrate", "-v0"]) != 0:
        say("!!", "Database migration failed (see above)")
        return 2
    say("OK", "Database is ready")
    ensure_ffmpeg()
    run([PY, "-m", "instai.core.checklist"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
