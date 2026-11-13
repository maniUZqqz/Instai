"""The automatic self-test of the studio pipeline: CPU checks always, GPU checks only when the machine can do them (skipped with a reason otherwise), the report is kept,
the API shows and starts it, and it queues itself once per new version / content and again when the GPU side becomes ready."""
from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest

from instai.studio import selftest
from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)

@pytest.fixture(autouse=True)
def _clean_report():
    import shutil

    shutil.rmtree(selftest.report_path().parent, ignore_errors=True)         # the report is a file in the data dir: every test starts without one
    selftest._LAST_AUTO[0] = 0.0
    yield
    shutil.rmtree(selftest.report_path().parent, ignore_errors=True)


CPU_KEYS = ("stick_kit", "identity_colour_key", "choice_stories", "mini_series", "ladder")


def ctx():
    return SimpleNamespace(check=lambda: None, progress=lambda *a, **k: None, live=lambda *a, **k: None)


def by_key(rep):
    return {r["key"]: r for r in rep["checks"]}


def done(job):
    return SimpleNamespace(status_code=202, json=lambda: {"job": {"id": job.pk}})


def test_cpu_checks_pass_and_gpu_checks_wait_with_a_reason():
    rep = selftest.run(None, gpu=False)
    rows = by_key(rep)
    assert [k for k, r in rows.items() if r["group"] == "cpu"] == list(CPU_KEYS)
    assert all(rows[k]["verdict"] == "ok" for k in CPU_KEYS), {k: r["reason_en"] for k, r in rows.items() if r["verdict"] != "ok"}
    assert rows["text_model"]["verdict"] == "pending" and rows["multiref_identity"]["verdict"] == "pending" and rows["vision"]["verdict"] == "pending"
    assert rep["ok"] and rep["summary"]["fail"] == 0 and rep["stamp"] == selftest.stamp()
    assert selftest.load_report()["stamp"] == rep["stamp"] and rows["stick_kit"]["metrics"]["deterministic"] is True
    assert rows["identity_colour_key"]["metrics"]["wrong"].count(True) < 3                   # a wrongly coloured character is told apart


def test_gpu_checks_skip_cleanly_when_nothing_is_installed_and_pass_with_the_fake_model():
    rep = selftest.run(ctx(), gpu=True)
    rows = by_key(rep)
    assert rows["text_model"]["verdict"] == "ok" and "نمودار" in rows["text_model"]["reason_fa"]            # the fake provider answers with a valid plan
    assert rows["multiref_identity"]["verdict"] == "skip" and "Qwen-Image-Edit" in rows["multiref_identity"]["reason_en"]
    assert rows["multiref_identity"]["metrics"]["workflow"] == "qwen_image_edit_multiref"
    assert rows["vision"]["verdict"] == "skip" and "qwen3-vl" in rows["vision"]["reason_fa"]
    assert rep["ok"] and rep["gpu_stamp"] == selftest.stamp() and rep["gpu_run_at"]


def test_the_multi_reference_check_judges_the_real_picture(monkeypatch, tmp_path):
    from PIL import Image

    from instai.gpu import compute
    from instai.render.stick import compose

    made = {}

    def fake_run_task(c, kind, payload, inputs=None):
        a, b = selftest._sample_spec("رامین"), selftest._sample_spec("ناصر")
        out = tmp_path / "gen.png"
        scene = {"width": 832, "height": 1472, "background": "corridor", "actors": [{"spec": a, "x": 0.3, "y": 0.9, "height": 0.5}, {"spec": b, "x": 0.7, "y": 0.9, "height": 0.5, "flip": True}]}
        if made.get("wrong"):
            scene["actors"][0]["spec"] = dict(a, limb_colour="#e0568f", hat_colour="#2e9e5b", neck_colour="#8a4fd1")
        compose.compose_still(scene, out, tmp_path / "w")
        Image.open(out).save(out, "PNG")
        return SimpleNamespace(of_kind=lambda *s: [out], cleanup=lambda: None, device="test-gpu")

    monkeypatch.setattr(compute, "workflow_available", lambda wid: True)
    monkeypatch.setattr(compute, "run_task", fake_run_task)
    selftest.run(None, gpu=False)                                            # a first full report, so that "only" has rows to keep
    rep = selftest.run(ctx(), gpu=True, only=["multiref_identity"])
    row = by_key(rep)["multiref_identity"]
    assert row["verdict"] == "ok" and row["metrics"]["colours"] == [1.0, 1.0] and row["metrics"]["device"] == "test-gpu" and row["metrics"]["size"] == [832, 1472]
    assert (selftest.report_path().parent / "multiref-sample.png").exists()
    made["wrong"] = True                                                     # the model forgot the first character's colours: a warning, never a silent pass
    row = by_key(selftest.run(ctx(), gpu=True, only=["multiref_identity"]))["multiref_identity"]
    assert row["verdict"] == "warn" and min(row["metrics"]["colours"]) < 0.67
    assert len(selftest.load_report()["checks"]) == 8                      # the rows of the checks that were not asked for are kept


def test_the_vision_check_compares_the_same_and_another_character(monkeypatch):
    from instai.gpu.arbiter import ARBITER
    from instai.identity import check

    monkeypatch.setattr(check, "_vision_model", lambda url: "qwen3-vl:8b")
    monkeypatch.setattr(ARBITER, "hold", lambda *a, **k: contextlib.nullcontext())
    scores = iter([{"same": True, "score": 9.0, "differences": []}, {"same": False, "score": 2.0, "differences": ["colour"]}])
    monkeypatch.setattr(check, "vision_call", lambda *a, **k: next(scores))
    row = by_key(selftest.run(ctx(), gpu=True, only=["vision"]))["vision"]
    assert row["verdict"] == "ok" and row["metrics"] == {"model": "qwen3-vl:8b", "same": 9.0, "other": 2.0}
    scores2 = iter([{"same": True, "score": 5.0, "differences": []}, {"same": True, "score": 5.0, "differences": []}])
    monkeypatch.setattr(check, "vision_call", lambda *a, **k: next(scores2))
    assert by_key(selftest.run(ctx(), gpu=True, only=["vision"]))["vision"]["verdict"] == "warn"


def test_a_broken_check_is_a_result_not_a_crash(monkeypatch):
    def boom(work):
        raise RuntimeError("kaput")

    monkeypatch.setitem(selftest.CHECKS[0], "fn", boom)
    rep = selftest.run(None, gpu=False, only=["stick_kit"])
    r = by_key(rep)["stick_kit"]
    assert r["verdict"] == "fail" and "kaput" in r["reason_en"] and rep["ok"] is False


def test_api_shows_the_report_and_runs_the_checks_as_a_job(api, worker):
    d = api.get("/api/studio/selftest").json()
    assert d["report"] is None and {c["key"] for c in d["checks"]} >= {"stick_kit", "multiref_identity", "vision", "text_model"} and d["running"] is False
    j = finish(api, worker, api.post("/api/studio/selftest", {"gpu": False}, format="json"))
    assert j["result"]["ok"] is True and j["result"]["summary"]["ok"] == 5
    d = api.get("/api/studio/selftest").json()
    assert d["report"]["summary"]["ok"] == 5 and d["stale"] is False and d["report"]["checks"][0]["reason_fa"]


def test_it_queues_itself_once_per_version_and_again_when_the_gpu_side_is_ready(api, worker, monkeypatch):
    from instai.choice import story_templates
    from instai.jobs.models import Job

    assert selftest.auto_queue() is None                                     # tests never get surprise jobs unless forced
    j = selftest.auto_queue(force=True)
    assert j is not None and j.payload["gpu"] is False and j.payload["auto"] is True
    assert selftest.auto_queue(force=True) is None                           # one at a time
    finish(api, worker, done(j))
    assert selftest.auto_queue(force=True) is None                           # tested for this version; nothing GPU-capable yet
    monkeypatch.setattr(selftest, "gpu_ready", lambda: True)
    g = selftest.auto_queue(force=True)
    assert g is not None and g.payload["gpu"] is True
    finish(api, worker, done(g))
    assert selftest.load_report()["gpu_stamp"] == selftest.stamp() and selftest.auto_queue(force=True) is None
    # new content (a changed story text) changes the stamp, so the CPU checks run again by themselves
    old = story_templates.PRISON["posts"][0]["text"]
    story_templates.PRISON["posts"][0]["text"] = old + " "
    try:
        assert selftest.auto_queue(force=True) is not None
    finally:
        story_templates.PRISON["posts"][0]["text"] = old
    monkeypatch.setenv("INSTAI_STUDIO_SELFTEST_AUTO", "0")
    Job.objects.filter(kind="studio.selftest").update(status=Job.SUCCEEDED)
    story_templates.PRISON["posts"][0]["text"] = old + "!"
    try:
        assert selftest.auto_queue(force=True) is None                       # the owner can switch it off
    finally:
        story_templates.PRISON["posts"][0]["text"] = old
