"""The two delivery rows of the PC self-test (0.15): a 3 s synthetic video with speech-like sound is settled to -14 LUFS and measured again; a doubled-narration mix must report the echo
and a clean mix nothing. They run on every PC (no GPU), by themselves, per version and daily like the other cheap checks."""
from __future__ import annotations

import shutil
from types import SimpleNamespace

import pytest

from instai.ops import pcselftest as st

pytestmark = pytest.mark.django_db(transaction=True)
KEYS = ["delivery_loudness", "delivery_echo"]


@pytest.fixture(autouse=True)
def _clean():
    shutil.rmtree(st.report_path().parent, ignore_errors=True)
    yield
    shutil.rmtree(st.report_path().parent, ignore_errors=True)


def ctx():
    return SimpleNamespace(check=lambda: None, progress=lambda *a, **k: None, live=lambda *a, **k: None)


def test_the_rows_exist_run_on_every_pc_and_are_due_by_themselves():
    keys = [c["key"] for c in st.CHECKS]
    assert all(k in keys for k in KEYS)
    for k in KEYS:
        c = st.BY_KEY[k]
        assert c["group"] == "pc" and "ready" not in c and c["fa"] and c["en"]
    assert set(KEYS) <= set(st.due({"checks": []}, st.stamp(), keys))                          # never ran: due at once, like the other cheap checks


def test_the_loudness_row_settles_a_quiet_file_to_minus_14_and_says_so(ffmpeg_available):
    pytest.importorskip("numpy")
    rep = st.run(ctx(), gpu=False, only=["delivery_loudness"])
    row = {r["key"]: r for r in rep["checks"]}["delivery_loudness"]
    assert row["verdict"] == "ok", row
    m = row["metrics"]
    assert m["before"] < -16.5 and abs(m["after"] + 14.0) <= 0.8 and m["tp"] <= -0.95 and m["rounds"] >= 1
    assert "LUFS" in row["reason_fa"] and "Loudness went from" in row["reason_en"] and "-14" in row["reason_en"]


def test_the_echo_row_finds_the_doubled_narration_and_not_the_clean_mix(ffmpeg_available):
    pytest.importorskip("numpy")
    rep = st.run(ctx(), gpu=False, only=["delivery_echo"])
    row = {r["key"]: r for r in rep["checks"]}["delivery_echo"]
    assert row["verdict"] == "ok", row
    m = row["metrics"]
    assert abs(m["doubled_lag"] - 0.15) <= 0.03 and m["doubled_strength"] > 0.3 and m["clean_strength"] < 0.16
    assert "میلی‌ثانیه" in row["reason_fa"] and "doubled narration was found" in row["reason_en"]


def test_both_rows_fail_the_right_way(ffmpeg_available, monkeypatch):
    """A check that cannot judge says so (warn: numpy missing) and one that judges wrongly fails: a doubled mix that is not found, a clean one that is."""
    pytest.importorskip("numpy")
    from instai.render import audioqc, loudness

    monkeypatch.setattr(audioqc, "echo_report", lambda x, *a, **k: {"doubled": False, "lag_s": None, "strength": 0.0, "share": 0.0, "windows": 1, "tonal": 0, "spans": []})
    row = {r["key"]: r for r in st.run(None, gpu=False, only=["delivery_echo"])["checks"]}["delivery_echo"]
    assert row["verdict"] == "fail" and "پیدا نشد" in row["reason_fa"]
    monkeypatch.setattr(audioqc, "echo_report", lambda x, *a, **k: {"doubled": True, "lag_s": 0.15, "strength": 0.4, "share": 1.0, "windows": 1, "tonal": 0, "spans": [[0, 3]]})
    row = {r["key"]: r for r in st.run(None, gpu=False, only=["delivery_echo"])["checks"]}["delivery_echo"]
    assert row["verdict"] == "fail" and "هشدار کاذب" in row["reason_fa"]
    monkeypatch.setattr(loudness, "settle", lambda *a, **k: {"before": -18.0, "lufs": -18.0, "rounds": 0})          # a correction that did nothing
    row = {r["key"]: r for r in st.run(None, gpu=False, only=["delivery_loudness"])["checks"]}["delivery_loudness"]
    assert row["verdict"] == "fail" and "باید در" in row["reason_fa"]
    monkeypatch.setattr(audioqc, "np", None)
    for k in KEYS:
        row = {r["key"]: r for r in st.run(None, gpu=False, only=[k])["checks"]}[k]
        assert row["verdict"] == "warn" and "numpy" in row["reason_en"] and "numpy" in row["reason_fa"]
