"""SQLite's "database is locked" is not a real failure: it only means another writer has not finished THIS moment.

InstAI keeps one SQLite file (WAL) that the server (8 threads), the worker (lanes + heartbeat threads), the model discovery and the
paired PCs' API calls all write to. Three layers keep a lock from ever failing or half-finishing a job:
  1. settings: `busy_timeout` 30 s, WAL, and `BEGIN IMMEDIATE` (the write lock is taken at the start of a transaction and waited for,
     instead of failing in the middle of a read-then-write);
  2. this module: the short queue writes are repeated with a growing, jittered pause when the lock error does come;
  3. the worker API answers 503 + Retry-After (not 500), which the PC B agent treats as "try again".
Never retry inside `transaction.atomic()` (the transaction is broken then): the error goes to the outermost layer, which retries.
Idea adapted from NMarketing's apps/compute/dbretry.py (own project, same owner).
"""
from __future__ import annotations

import functools
import logging
import random
import time

from django.db import OperationalError, connection

log = logging.getLogger("instai.db")

_MARKS = ("database is locked", "database table is locked", "database schema is locked", "database is busy", "sqlite_busy")
TRIES = 6
BASE_DELAY = 0.25
MAX_DELAY = 4.0


def is_lock_error(exc: BaseException) -> bool:
    """A SQLite lock error (not every OperationalError: "no such table" must still fail at once)."""
    return isinstance(exc, OperationalError) and any(m in str(exc).lower() for m in _MARKS)


def call_with_retry(fn, *args, _tries: int | None = None, _what: str = "", **kwargs):
    tries = _tries or TRIES
    delay = BASE_DELAY
    for attempt in range(1, tries + 1):
        try:
            return fn(*args, **kwargs)
        except OperationalError as exc:
            if not is_lock_error(exc):
                raise
            if connection.in_atomic_block or attempt >= tries:
                if attempt >= tries:
                    log.warning("database stayed locked after %d tries (%s)", attempt, _what or getattr(fn, "__name__", "?"))
                raise
            log.info("database is locked (%s); retry %d/%d", _what or getattr(fn, "__name__", "?"), attempt, tries)
            time.sleep(delay * (0.6 + random.random() * 0.8))
            delay = min(MAX_DELAY, delay * 2)
    raise AssertionError("unreachable")  # pragma: no cover


def retry_on_lock(fn=None, *, tries: int | None = None):
    """Decorator for a short, repeatable write (one UPDATE, or a few writes that can safely run twice)."""
    def deco(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            return call_with_retry(f, *args, _tries=tries, _what=f.__name__, **kwargs)
        return wrapper
    return deco(fn) if fn else deco
