"""SQLite concurrency: many writers at once (job creation, claim, heartbeat, progress, completion, report recording, a slow writer that holds
the write lock) must never lose or duplicate a job and never raise "database is locked" to the caller."""
from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest
from django.db import OperationalError, connection, transaction
from django.utils import timezone

from instai.core import dbretry
from instai.jobs import queue
from instai.jobs.models import Job

pytestmark = pytest.mark.django_db(transaction=True)


def test_lock_errors_are_retried_other_errors_are_not(monkeypatch):
    monkeypatch.setattr(dbretry.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OperationalError("database is locked")
        return "ok"
    assert dbretry.call_with_retry(flaky) == "ok" and calls["n"] == 3

    def broken():
        calls["n"] += 1
        raise OperationalError("no such table: nope")
    calls["n"] = 0
    with pytest.raises(OperationalError):
        dbretry.call_with_retry(broken)
    assert calls["n"] == 1, "a real database error is not repeated"

    calls["n"] = 0

    def always_locked():
        calls["n"] += 1
        raise OperationalError("database table is locked")
    with pytest.raises(OperationalError):
        dbretry.call_with_retry(always_locked, _tries=4)
    assert calls["n"] == 4

    @dbretry.retry_on_lock
    def decorated(x):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("database is locked")
        return x * 2
    calls["n"] = 0
    assert decorated(21) == 42


def test_no_retry_inside_a_transaction(monkeypatch):
    monkeypatch.setattr(dbretry.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def locked():
        calls["n"] += 1
        raise OperationalError("database is locked")
    with transaction.atomic():
        with pytest.raises(OperationalError):
            dbretry.call_with_retry(locked)
    assert calls["n"] == 1, "inside atomic() the transaction is broken: the outermost layer retries"


@pytest.mark.parametrize("busy_ms", [30000, 40])
def test_stress_many_writers_no_lost_or_duplicated_job_and_no_lock_error(busy_ms):
    """30000 = the real setting. 40 = a database that gives up after 40 ms, so "database is locked" really happens and only the retry
    layer (core/dbretry.py) stands between the callers and an error."""
    from instai.ops import report

    report.reset_state()
    PRODUCERS, PER, LANES = 6, 40, 4
    total = PRODUCERS * PER
    errors: list[BaseException] = []
    claimed: list[int] = []
    lock = threading.Lock()
    produced = threading.Event()
    stop = threading.Event()

    def guard(fn):
        def run(*a):
            try:
                with connection.cursor() as c:
                    c.execute(f"PRAGMA busy_timeout={busy_ms}")
                fn(*a)
            except BaseException as e:  # noqa: BLE001
                errors.append(e)
            finally:
                connection.close()
        return run

    def producer(i):
        for n in range(PER):
            queue.enqueue("stress.job", {"p": i, "n": n}, resource="cpu", idempotency_key=f"s{i}-{n}")

    def lane(name):
        idle = 0
        while idle < 200:
            job = queue.claim(name, ("cpu",), 30)
            if job is None:
                if produced.is_set() and not Job.objects.filter(status__in=("queued", "running")).exists():
                    return
                idle += 1
                time.sleep(0.01)
                continue
            idle = 0
            with lock:
                claimed.append(job.pk)
            queue.heartbeat(job, name, 30)
            queue.set_progress(job, 0.5, "half")
            queue.set_live(job, {"phase": "x"})
            queue.log_job(job, "working")
            queue.complete(job, {"ok": True})

    def reporter():
        i = 0
        while not stop.is_set():
            report.record_heartbeat("pcb", stats={"gpu_util": i % 100, "vram_used_mb": 1000, "vram_total_mb": 4096}, now=timezone.now() + timedelta(seconds=i * 61), force=True)
            i += 1
            time.sleep(0.005)

    def slow_writer():
        for _ in range(3):                         # another process holding the write lock for a while (a long transaction)
            with transaction.atomic():
                Job.objects.filter(pk=0).update(progress=0)         # takes the write lock (BEGIN IMMEDIATE)
                time.sleep(1.2)
            time.sleep(0.3)

    threads = ([threading.Thread(target=guard(producer), args=(i,)) for i in range(PRODUCERS)]
               + [threading.Thread(target=guard(lane), args=(f"lane{i}",)) for i in range(LANES)]
               + [threading.Thread(target=guard(reporter)), threading.Thread(target=guard(slow_writer))])
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads[:PRODUCERS]:
        t.join()
    produced.set()
    for t in threads[PRODUCERS:PRODUCERS + LANES]:
        t.join(120)
    stop.set()
    for t in threads[PRODUCERS + LANES:]:
        t.join(30)
    assert not any(t.is_alive() for t in threads), "a thread is stuck"
    assert errors == [], f"{len(errors)} errors, first: {errors[0]!r}" if errors else ""
    assert Job.objects.count() == total, "no job lost or doubled at creation"
    assert Job.objects.filter(status="succeeded").count() == total, Job.objects.values_list("status", flat=True).distinct()
    assert len(claimed) == total and len(set(claimed)) == total, "every job was claimed exactly once"
    assert Job.objects.filter(attempts__gt=1).count() == 0
    print(f"stress (busy_timeout {busy_ms} ms): {total} jobs, {LANES} lanes, a slow writer; {time.time() - t0:.1f}s, 0 errors")


def test_the_database_is_in_wal_mode_with_a_long_busy_timeout():
    with connection.cursor() as c:
        c.execute("PRAGMA journal_mode")
        assert c.fetchone()[0].lower() == "wal"
        c.execute("PRAGMA busy_timeout")
        assert c.fetchone()[0] >= 30000
    assert connection.settings_dict["OPTIONS"]["transaction_mode"] == "IMMEDIATE"
