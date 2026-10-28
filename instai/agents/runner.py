"""The one place that talks to a text provider and returns *validated* JSON.

call_json: ask -> extract JSON -> repair (types, unknown fields) -> validate against the schema -> run semantic checks ->
on problems send the list back to the model and retry (max_attempts) -> AgentError. Every agent boundary goes through this.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from instai.providers.base import LLMResult, ProviderError, TextProvider
from instai.providers.registry import get_text_provider

from .jsonschema_lite import repair, validate

log = logging.getLogger("instai.agents")

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


class AgentError(Exception):
    def __init__(self, message: str, *, code: str = "llm_invalid_output", errors: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.errors = errors or []


@dataclass
class AgentResult:
    data: dict
    attempts: int = 1
    provider: str = ""
    model: str = ""
    seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    notes: list[str] = field(default_factory=list)  # e.g. "repaired: ..." for the job log

    def meta(self) -> dict:
        return {"attempts": self.attempts, "provider": self.provider, "model": self.model, "seconds": round(self.seconds, 2),
                "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of a model answer (handles ```json fences and chatter around it)."""
    text = (text or "").strip()
    m = _FENCE.search(text)
    candidates = [m.group(1).strip()] if m else []
    candidates.append(text)
    for cand in candidates:
        try:
            return json.loads(cand)
        except ValueError:
            pass
        start = min([i for i in (cand.find("{"), cand.find("[")) if i >= 0], default=-1)
        if start < 0:
            continue
        opener = cand[start]
        closer = "}" if opener == "{" else "]"
        depth, in_str, esc = 0, False, False
        for i in range(start, len(cand)):
            ch = cand[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cand[start: i + 1])
                    except ValueError:
                        break
    raise ValueError("no JSON found in the model answer")


def call_json(task: str, schema: dict, *, system: str, user: str, meta: dict | None = None, provider: TextProvider | None = None,
              max_attempts: int = 3, temperature: float = 0.4, max_tokens: int = 4096,
              semantic: Callable[[dict], list[str]] | None = None, transform: Callable[[dict], dict] | None = None) -> AgentResult:
    provider = provider or get_text_provider()
    system_full = (system.rstrip() + "\n\nReply with ONLY one JSON object that follows this JSON schema. "
                   "No markdown, no commentary.\nSCHEMA:\n" + json.dumps(schema, ensure_ascii=False, separators=(",", ":")))
    messages = [{"role": "system", "content": system_full}, {"role": "user", "content": user}]
    out = AgentResult(data={}, provider=provider.name, model=provider.model)
    last_errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        try:
            res: LLMResult = provider.generate(messages, schema=schema, temperature=temperature if attempt == 1 else max(0.1, temperature - 0.2),
                                               max_tokens=max_tokens, task=task, meta=meta)
        except ProviderError:
            raise
        out.attempts = attempt
        out.provider, out.model = res.provider, res.model or out.model
        out.seconds += res.seconds
        out.prompt_tokens += res.prompt_tokens or 0
        out.completion_tokens += res.completion_tokens or 0
        try:
            data = extract_json(res.text)
        except ValueError as e:
            last_errors = [str(e)]
            _retry_messages(messages, res.text, last_errors)
            log.info("agent %s attempt %d: not JSON", task, attempt)
            continue
        if not isinstance(data, dict):
            data = {"items": data} if isinstance(data, list) else {}
        data = repair(data, schema)
        if transform:
            data = transform(data)
        errs = validate(data, schema)
        if not errs and semantic:
            errs = semantic(data)
        if not errs:
            if attempt > 1:
                out.notes.append(f"valid after {attempt} attempts")
            out.data = data
            return out
        last_errors = errs[:12]
        log.info("agent %s attempt %d: %d problems", task, attempt, len(errs))
        _retry_messages(messages, res.text, last_errors)
    raise AgentError(f"{task}: the model did not return valid output after {max_attempts} attempts", errors=last_errors)


def _retry_messages(messages: list[dict], bad_text: str, errors: list[str]) -> None:
    messages.append({"role": "assistant", "content": (bad_text or "")[:6000]})
    messages.append({"role": "user", "content": "Your previous answer had these problems:\n- " + "\n- ".join(errors) +
                     "\nReturn ONLY the corrected JSON object."})
