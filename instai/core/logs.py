"""Structured (JSON) logs with secret redaction."""
from __future__ import annotations

import json
import logging
import os
import re
import time

_SECRET_ENV = ("INSTAI_OPENAI_API_KEY", "INSTAI_SECRET_KEY")
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.I)
_SK = re.compile(r"\b(sk|mk|key)[-_][A-Za-z0-9]{12,}\b", re.I)


def redact(text: str) -> str:
    if not text:
        return text
    for name in _SECRET_ENV:
        val = os.environ.get(name, "")
        if len(val) >= 8:
            text = text.replace(val, "***")
    text = _BEARER.sub(r"\1***", text)
    return _SK.sub("***", text)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # never break logging
            pass
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for k in ("job_id", "episode_id", "page_id", "kind"):
            if hasattr(record, k):
                data[k] = getattr(record, k)
        if record.exc_info:
            data["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False)
