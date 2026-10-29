"""Pytest bootstrap: an isolated data dir per test run and no real services. Loaded before Django settings."""
import atexit
import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="instai-test-")
os.environ["INSTAI_TESTING"] = "1"
os.environ["INSTAI_DATA_DIR"] = os.path.join(_TMP, "data")
os.environ["INSTAI_SECRET_KEY"] = "test-secret-key-not-for-production-0123456789"
os.environ["INSTAI_LLM_PROVIDER"] = "fake"
os.environ["INSTAI_TTS_ENGINE"] = "fake"
os.environ["INSTAI_SFX_ENGINE"] = "fake"
os.environ["INSTAI_MUSIC_ENGINE"] = "fake"
os.environ["INSTAI_IMAGE_ENGINE"] = "placeholder"
os.environ["INSTAI_RESEARCH_FETCH"] = "fake"
os.environ["INSTAI_MODELS_DIR"] = os.path.join(_TMP, "models")   # hermetic: tools/models of the dev checkout (Piper, Rhubarb ...) must not leak into tests
os.environ["INSTAI_TOOLS_DIR"] = os.path.join(_TMP, "tools")
os.environ["INSTAI_OLLAMA_URL"] = "http://127.0.0.1:9"       # nothing listens here: detection must degrade to "missing"
os.environ["INSTAI_COMFYUI_URL"] = "http://127.0.0.1:9"
os.environ["INSTAI_SCAN_DEFAULTS"] = "0"      # model discovery reads only the folders a test gives it, never this PC's disk
os.environ.pop("INSTAI_SCAN_ROOTS", None)
for _v in ("COMFYUI_DIR", "NM_HOME", "NM_DATA_DIR", "OLLAMA_MODELS"):
    os.environ.pop(_v, None)
os.environ.pop("INSTAI_OPENAI_API_KEY", None)
atexit.register(lambda: shutil.rmtree(_TMP, ignore_errors=True))
