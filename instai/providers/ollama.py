"""Ollama adapter (local models, uses the GPU). Structured output: the JSON schema goes in `format`."""
from __future__ import annotations

import re
import time

import requests

from .base import LLMResult, ProviderError, TextProvider

_THINK = re.compile(r"<think>.*?</think>", re.S)


class OllamaProvider(TextProvider):
    name = "ollama"
    resource = "gpu"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "", keep_alive: str = "10m", num_ctx: int = 8192):
        self.base_url = base_url.rstrip("/")
        self._model = model
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx  # Ollama's default context is small; prompts carry story memory and the full script

    @property
    def model(self) -> str:
        return self._model

    def health(self) -> dict:
        try:
            r = requests.get(self.base_url + "/api/tags", timeout=1.5)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "detail": f"{len(names)} models", "models": names}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "detail": f"{type(e).__name__}", "models": []}

    def _pick_model(self, model: str | None) -> str:
        m = model or self._model
        if m:
            return m
        names = self.health().get("models", [])
        if not names:
            raise ProviderError("Ollama has no models installed", retryable=False)
        # prefer a mid-size instruct model that fits 12 GB; the owner picks the real one in Settings
        for pref in ("qwen3:8b", "qwen3.5:9b", "gemma3:12b", "qwen3:14b", "qwen3.5:4b"):
            if pref in names:
                return pref
        return names[0]

    def generate(self, messages, *, schema=None, temperature=0.4, max_tokens=4096, task=None, meta=None,
                 model=None, timeout=600) -> LLMResult:
        mdl = self._pick_model(model)
        body: dict = {"model": mdl, "messages": messages, "stream": False, "keep_alive": self.keep_alive,
                      "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": self.num_ctx}}
        if schema:
            body["format"] = schema
        if mdl.lower().startswith("qwen3"):
            body["think"] = False  # thinking mode wastes minutes on a 3060 and can break structured output
        t0 = time.time()
        try:
            r = requests.post(self.base_url + "/api/chat", json=body, timeout=timeout)
            if r.status_code == 400 and "think" in r.text.lower() and "think" in body:
                body.pop("think")
                r = requests.post(self.base_url + "/api/chat", json=body, timeout=timeout)
            if r.status_code == 404:
                raise ProviderError(f"Ollama model not found: {mdl}", retryable=False)
            r.raise_for_status()
        except ProviderError:
            raise
        except requests.RequestException as e:
            raise ProviderError(f"Ollama request failed: {type(e).__name__}: {e}") from e
        data = r.json()
        text = _THINK.sub("", (data.get("message") or {}).get("content") or "").strip()
        dt = time.time() - t0
        ev, ed = data.get("eval_count"), data.get("eval_duration")
        tps = round(ev / (ed / 1e9), 1) if ev and ed else None
        return LLMResult(text=text, provider=self.name, model=mdl, seconds=dt, prompt_tokens=data.get("prompt_eval_count"),
                         completion_tokens=ev, tokens_per_second=tps, raw={"done_reason": data.get("done_reason")})

    def loaded_models(self) -> list[str]:
        try:
            r = requests.get(self.base_url + "/api/ps", timeout=3)
            return [m.get("name", "") for m in r.json().get("models", [])]
        except Exception:  # noqa: BLE001
            return []

    def unload(self) -> None:
        """keep_alive 0 for every loaded model (frees VRAM for ComfyUI / voice models)."""
        for name in self.loaded_models():
            try:
                requests.post(self.base_url + "/api/generate", json={"model": name, "keep_alive": 0}, timeout=30)
            except requests.RequestException:
                pass
