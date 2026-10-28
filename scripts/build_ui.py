"""Build the React UI into instai/static/app (committed to git, so the GPU PC needs only Python).

  python scripts/build_ui.py            build only if the sources changed since the last build (content hash, not timestamps)
  python scripts/build_ui.py --force    always build
START.bat runs this when Node.js exists; without Node it silently uses the committed build. Stdlib only.
"""
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT = os.path.join(ROOT, "frontend")
OUT = os.path.join(ROOT, "instai", "static", "app")
STAMP = os.path.join(OUT, ".build-hash")


def source_hash() -> str:
    h = hashlib.sha256()
    files = []
    for base, dirs, names in os.walk(FRONT):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", ".vite")]
        for n in names:
            if n.endswith((".ts", ".tsx", ".css", ".html", ".json", ".svg")) and n != "package-lock.json":
                files.append(os.path.join(base, n))
    for p in sorted(files):
        h.update(os.path.relpath(p, FRONT).replace("\\", "/").encode())
        with open(p, "rb") as f:
            h.update(f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def main() -> int:
    if not os.path.isfile(os.path.join(FRONT, "package.json")):
        return 0
    node, npm = shutil.which("node"), shutil.which("npm")
    want = source_hash()
    have = open(STAMP).read().strip() if os.path.isfile(STAMP) else ""
    if want == have and "--force" not in sys.argv:
        print("  [OK] UI is up to date")
        return 0
    if not node or not npm:
        print("  [--] UI sources changed but Node.js is not installed; using the committed build")
        return 0
    print("  [..] Building the UI (npm) ...")
    if not os.path.isdir(os.path.join(FRONT, "node_modules")):
        if subprocess.call([npm, "install", "--no-audit", "--no-fund", "--loglevel=error"], cwd=FRONT) != 0:
            print("  [!!] npm install failed; using the committed build")
            return 0
    if subprocess.call([npm, "run", "build"], cwd=FRONT) != 0:
        print("  [!!] UI build failed; using the committed build")
        return 0
    with open(STAMP, "w") as f:
        f.write(want)
    print("  [OK] UI built")
    return 0


if __name__ == "__main__":
    sys.exit(main())
