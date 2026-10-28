"""Handler registry: job kind -> function(ctx) -> result dict. Handlers are plain functions; the worker owns scheduling."""
from __future__ import annotations

from typing import Callable

HANDLERS: dict[str, Callable] = {}
_RESOURCE: dict[str, Callable | str] = {}
_TIMEOUT: dict[str, int] = {}


def handler(kind: str, *, resource: str | Callable[[dict], str] = "cpu", timeout: int = 3600):
    """Register a handler. `resource` is "cpu" | "gpu" | "net" or a function of the payload (e.g. depends on the provider)."""
    def deco(fn: Callable) -> Callable:
        HANDLERS[kind] = fn
        _RESOURCE[kind] = resource
        _TIMEOUT[kind] = timeout
        return fn
    return deco


def default_resource(kind: str, payload: dict) -> str:
    r = _RESOURCE.get(kind, "cpu")
    return r(payload) if callable(r) else r


def default_timeout(kind: str) -> int:
    return _TIMEOUT.get(kind, 3600)


def load_handlers() -> None:
    """Import every handler module so the decorators run."""
    from . import handlers  # noqa: F401
