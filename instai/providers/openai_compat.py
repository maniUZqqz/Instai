"""OpenAI-compatible chat API (e.g. MetisAI). Base URL, model and mode come from Settings; the key only from .env."""
from __future__ import annotations

import os
import time

import requests

from .base import LLMResult, ProviderError, TextProvider


def normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url


class OpenAICompatProvider(TextProvider):
    name = "openai"
    resource = "net"

    def __init__(self, base_url: str, model: str, json_mode: str = "json_object", api_key: str | None = None):
        self.base_url = normalize_base_url(base_url)
        self._model = model
        self.json_mode = json_mode if json_mode in ("json_schema", "json_object", "none") else "json_object"
        self._api_key = api_key

    @property
    def api_key(self) -> str:
        return self._api_key if self._api_key is not None else os.environ.get("INSTAI_OPENAI_API_KEY", "")

    @property
    def model(self) -> str:
        return self._model

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def health(self) -> dict:
        if not self.base_url:
            return {"ok": False, "detail": "base URL not set", "models": []}
        if not self.api_key:
            return {"ok": False, "detail": "API key not set", "models": []}
        try:
            r = requests.get(self.base_url + "/models", headers=self._headers(), timeout=8)
            if r.status_code in (401, 403):
                return {"ok": False, "detail": "key rejected", "models": []}
            r.raise_for_status()
            ids = sorted(m.get("id", "") for m in (r.json().get("data") or []) if isinstance(m, dict))
            return {"ok": True, "detail": f"{len(ids)} models", "models": ids}
        except Exception as e:  # noqa: BLE001
            # many compatible gateways have no /models; a reachable host with a key is "maybe ok"
            return {"ok": False, "detail": type(e).__name__, "models": []}

    def generate(self, messages, *, schema=None, temperature=0.4, max_tokens=4096, task=None, meta=None,
                 model=None, timeout=600) -> LLMResult:
        mdl = model or self._model
        if not self.base_url or not mdl:
            raise ProviderError("OpenAI-compatible provider needs a base URL and a model", retryable=False)
        if not self.api_key:
            raise ProviderError("OpenAI-compatible provider needs an API key in .env", retryable=False)
        body: dict = {"model": mdl, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if schema and self.json_mode == "json_schema":
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": (task or "output").replace(".", "_"), "schema": schema, "strict": False}}
        elif schema and self.json_mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        t0 = time.time()
        last: Exception | None = None
        for attempt in range(3):
            try:
                r = requests.post(self.base_url + "/chat/completions", json=body, headers=self._headers(), timeout=timeout)
                if r.status_code in (401, 403):
                    raise ProviderError("API key rejected", retryable=False)
                if r.status_code == 400 and "response_format" in body:
                    body.pop("response_format")  # gateway does not know JSON mode: the validator will repair
                    continue
                if r.status_code in (429, 500, 502, 503, 504):
                    last = ProviderError(f"HTTP {r.status_code}")
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                data = r.json()
                text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                usage = data.get("usage") or {}
                return LLMResult(text=text.strip(), provider=self.name, model=data.get("model") or mdl, seconds=time.time() - t0,
                                 prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"))
            except ProviderError:
                raise
            except requests.RequestException as e:
                last = e
                time.sleep(2 ** attempt)
        raise ProviderError(f"API request failed: {type(last).__name__ if last else 'unknown'}") from last
