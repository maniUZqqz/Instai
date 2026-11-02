"""A tiny WebSocket reader (standard library only) for ComfyUI's /ws: the sampler's "step 8 of 20" and which node is running.

ComfyUI reports sampler progress only on its websocket (the HTTP /history call says nothing until the job is finished). The watcher runs in a
background thread, never raises, and simply stays silent when the socket cannot be opened (old ComfyUI, proxy ...): the caller then shows
elapsed time only. It must be started BEFORE the prompt is queued (same client id), or the first messages are missed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time
from urllib.parse import quote, urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class ProgressWatcher(threading.Thread):
    def __init__(self, base_url: str, client_id: str, connect_timeout: float = 3.0):
        super().__init__(daemon=True, name="comfy-ws")
        self.base_url, self.client_id, self.connect_timeout = base_url, client_id, connect_timeout
        self._state: dict = {"connected": False, "prompt_id": None, "step": None, "steps": None, "node": None, "executing": None, "updated": 0.0, "events": 0}
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._sock: socket.socket | None = None

    # ---- public
    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def stop(self) -> None:
        self._stop_evt.set()
        s = self._sock
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass

    # ---- thread
    def run(self) -> None:
        try:
            self._loop()
        except Exception:  # noqa: BLE001 - progress is a nicety
            pass
        finally:
            self.stop()

    def _loop(self) -> None:
        u = urlsplit(self.base_url)
        if u.scheme not in ("http", ""):
            return                                                  # https/wss is not needed for a local ComfyUI
        host, port = u.hostname or "127.0.0.1", u.port or 80
        sock = self._sock = socket.create_connection((host, port), timeout=self.connect_timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {(u.path.rstrip('/') or '')}/ws?clientId={quote(self.client_id)} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        sock.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.recv(1024)
            if not chunk:
                return
            head += chunk
            if len(head) > 16384:
                return
        header, _, rest = head.partition(b"\r\n\r\n")
        if b" 101 " not in header.split(b"\r\n", 1)[0] + b" ":
            return
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode().lower()
        if b"sec-websocket-accept" in header.lower() and accept.encode() not in header.lower():
            return
        sock.settimeout(1.0)
        buf = bytearray(rest)
        with self._lock:
            self._state["connected"] = True
        text_parts: list[bytes] = []
        while not self._stop_evt.is_set():
            frame = self._read_frame(sock, buf)
            if frame is None:
                continue
            fin, opcode, payload = frame
            if opcode == 0x8:
                return
            if opcode == 0x9:                                       # ping -> masked pong
                self._send(sock, 0xA, payload)
                continue
            if opcode == 0x1:
                text_parts = [payload]
            elif opcode == 0x0 and text_parts:
                text_parts.append(payload)
            else:
                continue                                            # binary frames are previews; ignore
            if fin:
                data, text_parts = b"".join(text_parts), []
                self._handle(data)

    @staticmethod
    def _send(sock: socket.socket, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        head = bytes([0x80 | opcode, 0x80 | len(payload)]) if len(payload) < 126 else bytes([0x80 | opcode, 0x80 | 126]) + struct.pack(">H", len(payload))
        sock.sendall(head + mask + masked)

    def _need(self, sock: socket.socket, buf: bytearray, n: int) -> bool:
        """Fill buf to at least n bytes; False when stopped. A socket timeout just retries (so stop() is noticed within a second)."""
        while len(buf) < n:
            if self._stop_evt.is_set():
                return False
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                self._stop_evt.set()
                return False
            buf.extend(chunk)
        return True

    def _read_frame(self, sock: socket.socket, buf: bytearray):
        if not self._need(sock, buf, 2):
            return None
        b1, b2 = buf[0], buf[1]
        fin, opcode, masked, ln, off = bool(b1 & 0x80), b1 & 0x0F, bool(b2 & 0x80), b2 & 0x7F, 2
        if ln == 126:
            if not self._need(sock, buf, 4):
                return None
            ln, off = struct.unpack(">H", bytes(buf[2:4]))[0], 4
        elif ln == 127:
            if not self._need(sock, buf, 10):
                return None
            ln, off = struct.unpack(">Q", bytes(buf[2:10]))[0], 10
        if masked:
            off += 4
        if ln > 64 * 1024 * 1024 or not self._need(sock, buf, off + ln):
            if ln > 64 * 1024 * 1024:
                self._stop_evt.set()
            return None
        payload = bytes(buf[off:off + ln])
        if masked:
            mk = bytes(buf[off - 4:off])
            payload = bytes(b ^ mk[i % 4] for i, b in enumerate(payload))
        del buf[:off + ln]
        return fin, opcode, payload

    def _handle(self, data: bytes) -> None:
        try:
            msg = json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            return
        typ, d = msg.get("type"), msg.get("data") or {}
        now = time.time()
        with self._lock:
            s = self._state
            s["events"] += 1
            if d.get("prompt_id"):
                if typ in ("execution_start", "executing") and d["prompt_id"] != s["prompt_id"]:
                    s.update(step=None, steps=None, node=None)
                s["prompt_id"] = d["prompt_id"]
            if typ == "progress" and d.get("max"):
                s.update(step=int(d.get("value") or 0), steps=int(d["max"]), node=d.get("node"), updated=now)
            elif typ == "executing":
                s["executing"] = d.get("node")
                if d.get("node") is None:
                    s.update(step=None, steps=None, updated=now)
            elif typ == "execution_start":
                s.update(step=None, steps=None, executing=None, updated=now)
