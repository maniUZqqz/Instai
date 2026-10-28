"""START.bat self-check and self-repair. Runs with the project's venv Python. English / ASCII console text only.

Steps: packages (pinned, mirror fallback) -> .env -> ffmpeg -> UI build (only if Node exists and sources changed) ->
database migration -> hardware/model checklist.   Exit code: 0 fine, 2 cannot continue.
With --bench-needed: exit 0 when this looks like a first run on a GPU machine (no benchmark yet), else 1.
"""
import hashlib
import os
import subprocess
import sys

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
