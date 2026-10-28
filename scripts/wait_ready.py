"""Used by START.bat: is the server answering? Stdlib only.

  wait_ready.py --once          exit 0 if /api/health answers now, else 1
  wait_ready.py --timeout 90    wait up to 90 s
  wait_ready.py --print-url     print the address of the app
"""
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from instai.envfile import read_env  # noqa: E402

env = {**read_env(), **{k: v for k, v in os.environ.items() if k.startswith("INSTAI_")}}
HOST = env.get("INSTAI_HOST", "127.0.0.1")
PORT = env.get("INSTAI_PORT", "8765")
SHOW = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST
URL = f"http://{SHOW}:{PORT}/"


def ready() -> bool:
    try:
        with urllib.request.urlopen(URL + "api/health", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    if "--print-url" in sys.argv:
        print(URL)
        return 0
    if "--once" in sys.argv:
        return 0 if ready() else 1
    timeout = 60
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])
    end = time.time() + timeout
    while time.time() < end:
        if ready():
            return 0
        time.sleep(1)
    return 1


if __name__ == "__main__":
    sys.exit(main())
