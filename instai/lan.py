"""LAN access for worker PCs - and nothing else.

Security choice (docs/DECISIONS.md): the normal server stays bound to 127.0.0.1 with localhost-only host names. When the owner turns
"worker PCs" on, a SECOND small listener starts on 0.0.0.0:<port> (default 8766). It serves the same Django app through `WorkerGate`,
which answers 404 to everything except `/api/worker/*`; those endpoints need a token (or a one-time pairing code). The UI, the
management API (`/api/workers/...`), media, settings and all other API paths are therefore never reachable from the LAN.
The listener is off by default, starts only on the owner's click (or at start-up when it was enabled), and can be stopped again.
"""
from __future__ import annotations

import logging
import socket
import threading

log = logging.getLogger("instai.lan")
DEFAULT_PORT = 8766
ALLOWED_PREFIX = "/api/worker/"


class WorkerGate:
    """WSGI wrapper: only the worker API passes; the Host header is normalised so Django's localhost-only host check still applies
    to every other entrance."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if not path.startswith(ALLOWED_PREFIX):
            body = b"not found"
            start_response("404 Not Found", [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))])
            return [body]
        environ["HTTP_HOST"] = "127.0.0.1"
        return self.app(environ, start_response)


def lan_addresses() -> list[str]:
    """IPv4 addresses of this PC that another PC on the network could use (no loopback / link-local)."""
    found: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:      # no packet is sent: this only picks the outgoing interface
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    out: list[str] = []
    for ip in found:
        if ip and not ip.startswith(("127.", "169.254.", "0.")) and ip not in out:
            out.append(ip)
    return out


class LanServer:
    def __init__(self):
        self.server = None
        self.thread: threading.Thread | None = None
        self.host = "0.0.0.0"
        self.port = 0
        self.error = ""

    @property
    def running(self) -> bool:
        return self.server is not None and self.thread is not None and self.thread.is_alive()

    def start(self, port: int = DEFAULT_PORT, host: str = "0.0.0.0") -> bool:
        if self.running:
            return True
        from waitress.server import create_server

        from instai.wsgi import application

        try:
            self.server = create_server(WorkerGate(application), host=host, port=port, threads=6, ident="instai-worker-gate")
        except OSError as e:
            self.server, self.error = None, f"port {port} is not available: {e}"
            return False
        self.host, self.port, self.error = host, self.server.effective_port if hasattr(self.server, "effective_port") else port, ""
        self.thread = threading.Thread(target=self.server.run, name="instai-lan", daemon=True)
        self.thread.start()
        log.info("worker listener started on %s:%s", host, self.port)
        return True

    def stop(self) -> None:
        if self.server is not None:
            try:
                self.server.close()
            except Exception:  # noqa: BLE001
                pass
        self.server, self.thread = None, None
        log.info("worker listener stopped")

    def status(self) -> dict:
        return {"running": self.running, "port": self.port if self.running else DEFAULT_PORT, "addresses": lan_addresses(), "error": self.error}


LAN = LanServer()


def apply_saved_setting() -> None:
    """At server start-up: open the worker listener again if the owner had enabled it."""
    from instai.core import settings_store

    if settings_store.get_setting("lan_worker_enabled"):
        LAN.start(int(settings_store.get_setting("lan_worker_port") or DEFAULT_PORT))
