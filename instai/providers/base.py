"""Typed provider interfaces. Concrete adapters live next to this file."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class ProviderError(Exception):
    """A provider could not do its job. `retryable` tells the job queue whether trying again can help."""

    def __init__(self, message: str, *, retryable: bool = True, code: str = "provider_unavailable"):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    seconds: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tokens_per_second: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class TextProvider(abc.ABC):
    """Text generation. `resource` says what the call occupies: "gpu" (local model), "net" (remote API) or "cpu"."""

    name = "base"
    resource = "net"
    licence = ""

    @abc.abstractmethod
    def generate(self, messages: list[dict], *, schema: dict | None = None, temperature: float = 0.4,
                 max_tokens: int = 4096, task: str | None = None, meta: dict | None = None,
                 model: str | None = None, timeout: float = 600) -> LLMResult:
        """messages: [{"role": "system"|"user"|"assistant", "content": str}].

        `schema` is a JSON schema the answer should follow (used natively when the backend supports it).
        `task` / `meta` are only read by the fake provider; real providers ignore them.
        """

    @abc.abstractmethod
    def health(self) -> dict:
        """{"ok": bool, "detail": str, "models": [str]}  - never raises."""

    def list_models(self) -> list[str]:
        return self.health().get("models", [])

    def unload(self) -> None:
        """Free GPU memory if this provider holds any."""

    @property
    def model(self) -> str:
        return ""
