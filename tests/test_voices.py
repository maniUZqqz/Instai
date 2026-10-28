"""Voice stack: engines with licence badges, Pocket/Edge adapters, on-demand audio servers (real server scripts in --fake mode),
SFX/music generators, voice casting per character and language, consent rules, voice licence in the QC report."""
from __future__ import annotations

import base64
import io
import json
import socket
import sys
import threading
import types
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wav_bytes(seconds=4.0, rate=24000, amp=0.3) -> bytes:
    import math
    import struct

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(amp * 32767 * math.sin(2 * math.pi * 200 * i / rate))) for i in range(int(seconds * rate))))
    return buf.getvalue()


class FakePocketGateway(ThreadingHTTPServer):
    def __init__(self):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/api/voice/engines":
                    return self._send(200, json.dumps({"gateway": True, "engines": [{"id": "pocket", "available": True}]}).encode())
                if self.path == "/api/voice/voices":
                    return self._send(200, json.dumps([{"id": "mana", "name": "Mana", "gender": "female"}]).encode())
                self._send(404, b"{}")

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode() or "{}")
                self.server.calls.append(body)
                if self.path == "/api/voice/tts":
                    return self._send(200, wav_bytes(1.5), "audio/wav")
                self._send(404, b"{}")

        super().__init__(("127.0.0.1", 0), H)
        self.calls = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


def test_every_engine_has_a_licence_badge_and_pocket_edge_warn():
    from instai.providers import tts

    pocket, edge = tts.licence_of("pocket"), tts.licence_of("edge")
    assert pocket["commercial"] == "no" and pocket["warning"] and pocket["warning_text"]["fa"] and pocket["warning_text"]["en"]
    assert edge["commercial"] == "no" and "unofficial" in edge["badge"].lower()
    assert tts.licence_of("moss")["commercial"] == "yes" and tts.licence_of("moss")["warning_text"] is None


def test_pocket_adapter_against_fake_gateway(tmp_path):
    from instai.providers.tts import PocketTTS

    gw = FakePocketGateway()
    try:
        p = PocketTTS(gw.url)
        assert p.available()[0]
        assert p.voices("fa")[0]["id"] == "mana"
        r = p.synthesize("سلام دنیا", tmp_path / "p.wav", voice="mana", seed=3)
        assert r.engine == "pocket" and r.seconds == pytest.approx(1.5, abs=0.05)
        assert r.licence["commercial"] == "no"
        assert gw.calls[0] == {"text": "سلام دنیا", "voice": "mana", "seed": "3"}
    finally:
        gw.shutdown()


def test_edge_adapter_with_fake_package(tmp_path, ffmpeg_available, monkeypatch):
    from instai.providers.tts import EdgeTTS
    from instai.render import ffmpeg

    wav = tmp_path / "src.wav"
    wav.write_bytes(wav_bytes(1.0))
    mp3 = tmp_path / "src.mp3"
    ffmpeg.run(["-i", str(wav), str(mp3)])

    class Communicate:
        def __init__(self, text, voice):
            Communicate.last = (text, voice)

        async def save(self, path):
            open(path, "wb").write(mp3.read_bytes())

    fake = types.ModuleType("edge_tts")
    fake.Communicate = Communicate
    monkeypatch.setitem(sys.modules, "edge_tts", fake)
    e = EdgeTTS()
    assert e.available()[0] and e.online
    r = e.synthesize("hello there", tmp_path / "e.wav", language="en")
    assert r.engine == "edge" and r.voice == "en-US-JennyNeural" and Communicate.last == ("hello there", "en-US-JennyNeural")
    assert r.seconds > 0.5 and r.licence["warning"] == "edge_unofficial"
    assert [v["id"] for v in e.voices("fa")] == ["fa-IR-DilaraNeural", "fa-IR-FaridNeural"]


@pytest.fixture
def fake_voice_servers(monkeypatch):
    from instai.providers.audio import services

    for k in ("MOSS", "SFX", "MUSIC"):
        monkeypatch.setenv(f"INSTAI_VOICE_PORT_{k}", str(_free_port()))
    monkeypatch.setenv("INSTAI_VOICE_FAKE", "1")
    yield services
    services.MANAGER.stop_all()


def test_managed_servers_start_on_demand_and_the_arbiter_stops_them(tmp_path, fake_voice_servers):
    services = fake_voice_servers
    from instai.gpu.arbiter import GPUArbiter
    from instai.providers.audio import AceStepMusic, MossSFX
    from instai.providers.tts import MossTTS

    assert services.health("moss")["status"] == "down"
    ref = tmp_path / "ref.wav"
    ref.write_bytes(wav_bytes(3.0))
    tts = MossTTS()
    assert tts.managed and tts.available()[0]            # installed (fake mode) -> started on demand
    r = tts.synthesize("سلام، این یک آزمون است", tmp_path / "m.wav", reference=str(ref), seed=1)
    assert r.engine == "moss" and r.seconds > 0.5 and services.health("moss")["status"] == "ready"
    sfx = MossSFX().generate("rain on a window", 3.0, tmp_path / "sfx.wav", seed=2)
    assert sfx.engine == "moss-sfx" and sfx.path.exists()
    music = AceStepMusic().generate("calm piano, instrumental", 12.0, tmp_path / "music.wav")
    assert music.engine == "acestep" and music.path.stat().st_size > 1000
    assert all(services.health(k)["status"] == "ready" for k in ("moss", "sfx", "music"))
    # switching to ComfyUI/LLM: the arbiter's "voice" unloader stops every server this process started
    GPUArbiter(probe=lambda: None).unload_others("comfy")
    assert all(services.health(k)["status"] == "down" for k in ("moss", "sfx", "music"))


def mk_character(api):
    page = api.post("/api/pages", {"name": "ص", "format": "recurring_character", "languages": ["fa"], "idea": "x"}, format="json").json()
    ch = api.post(f"/api/pages/{page['id']}/characters", {"name": "سارا", "role": "main"}, format="json").json()
    return page, ch


def test_voice_cast_per_language_consent_and_resolution(api, ffmpeg_available):
    page, ch = mk_character(api)
    eng = api.get("/api/voices/engines?language=en").json()
    by = {e["id"]: e for e in eng["engines"]}
    assert by["pocket"]["warning"] == "pocket_noncommercial" and by["edge"]["warning"] == "edge_unofficial" and by["moss"]["warning"] is None
    assert by["piper"]["default_voice"] == "en_US-lessac-medium"
    audio = base64.b64encode(wav_bytes(5.0)).decode()
    r = api.post(f"/api/characters/{ch['id']}/voice-refs", {"language": "fa", "audio_base64": audio, "consent_given": False}, format="json")
    assert r.status_code == 400
    r = api.post(f"/api/characters/{ch['id']}/voice-refs", {"language": "fa", "person_name": "علی", "purpose": "گویندگی", "audio_base64": audio,
                                                           "consent_given": True, "consent_text": "رضایت دارم"}, format="json")
    assert r.status_code == 201, r.content
    ref = r.json()
    assert ref["duration_sec"] == pytest.approx(5.0, abs=0.3)
    short = base64.b64encode(wav_bytes(1.0)).decode()
    assert api.post(f"/api/characters/{ch['id']}/voice-refs", {"audio_base64": short, "consent_given": True, "consent_text": "ok"},
                    format="json").status_code == 400
    assert api.put(f"/api/characters/{ch['id']}/voices/fa", {"engine": "piper", "reference": ref["id"]}, format="json").status_code == 200
    out = api.put(f"/api/characters/{ch['id']}/voices/en", {"engine": "edge", "voice_id": "en-US-JennyNeural"}, format="json").json()
    casts = {c["language"]: c for c in out["casts"]}
    assert casts["fa"]["engine"] == "moss" and casts["fa"]["reference"] == ref["id"]        # a reference voice always means MOSS
    assert casts["en"]["engine"] == "edge" and casts["en"]["licence"]["commercial"] == "no"
    from instai.pages.models import Character
    from instai.production import voices

    c = Character.objects.get(pk=ch["id"])
    fa, en = voices.resolve(c, "fa"), voices.resolve(c, "en")
    assert fa["engine"] == "moss" and fa["reference"].endswith(".wav") and fa["consent_ok"]
    assert en["engine"] == "edge" and en["voice"] == "en-US-JennyNeural"
    assert api.delete(f"/api/voice-refs/{ref['id']}").status_code == 204
    assert voices.resolve(c, "fa")["engine"] == "auto"
    assert api.put(f"/api/characters/{ch['id']}/voices/xx", {"engine": "piper"}, format="json").status_code == 400
    assert api.put(f"/api/characters/{ch['id']}/voices/fa", {"engine": "nonsense"}, format="json").status_code == 400


def test_voice_preview_job_carries_the_pocket_warning(api, worker, ffmpeg_available):
    gw = FakePocketGateway()
    try:
        from instai.core import settings_store

        settings_store.set_setting("pocket_url", gw.url)
        resp = api.post("/api/voices/preview", {"engine": "pocket", "voice": "mana", "language": "fa", "text": "سلام"}, format="json")
        j = finish(api, worker, resp)
        assert j["result"]["engine"] == "pocket" and j["result"]["licence"]["warning"] == "pocket_noncommercial"
    finally:
        gw.shutdown()
