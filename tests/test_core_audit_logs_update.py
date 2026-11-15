"""Audit batch "ia_core" (2026-11-14), items 6 and 7: numbers in Persian digits, job log lines in the interface language, and the
«نسخهٔ تازه آماده است» update badge + button (fake GitHub, no network, no Windows)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.test_story_flow import make_page

pytestmark = pytest.mark.django_db(transaction=True)


# ------------------------------------------------------------------ 6. numbers in Persian digits, log lines in the interface language

@pytest.mark.parametrize("text,expected", [
    ("3.8 گیگابایت (آزاد: 1.7)", "۳٫۸ گیگابایت (آزاد: ۱٫۷)"),
    ("4.7 از 42.0 گیگابایت آزاد", "۴٫۷ از ۴۲٫۰ گیگابایت آزاد"),
    ("x86_64 - 2 هسته", "x86_64 - ۲ هسته"),
    ("0 از 15 فایل مدل؛ 0 از 11 گردش‌کار آماده", "۰ از ۱۵ فایل مدل؛ ۰ از ۱۱ گردش‌کار آماده"),
    ("http://127.0.0.1:9 پاسخ نداد", "http://127.0.0.1:9 پاسخ نداد"),                      # an address is not a number
    ("3.10.12 (Linux 5.15.0-194-generic)", "3.10.12 (Linux 5.15.0-194-generic)"),            # versions stay
    ("NVIDIA GeForce RTX 3060 - 12 GB", "NVIDIA GeForce RTX 3060 - 12 GB"),                  # the numbers of a Latin phrase stay
    ("بازهٔ شبانه 02:00-07:00", "بازهٔ شبانه ۰۲:۰۰-۰۷:۰۰"),
    ("qwen3:8b نصب است", "qwen3:8b نصب است"),
])
def test_persian_digits_only_in_persian_numbers(text, expected):
    from instai.core.fa_digits import fa_numbers

    assert fa_numbers(text) == expected


def test_the_system_check_texts_use_persian_digits():
    from instai.core import hardware

    ram = next(i for i in hardware.check_system() if i["id"] == "ram")
    disk = next(i for i in hardware.check_system() if i["id"] == "disk_project")
    for item in (ram, disk):
        assert "گیگابایت" in item["detail"] and not any(c in item["detail"] for c in "0123456789"), item["detail"]


def test_job_log_lines_carry_a_code_and_render_in_both_languages(api, worker):
    from instai.jobs import logtext
    from instai.jobs.models import JobLog

    make_page(api, worker, "recurring_character", "گربه")
    assert JobLog.objects.filter(code="queued").exists()
    started = JobLog.objects.filter(code="started").first()
    fa, en = logtext.texts(started.code, started.params)
    assert fa.startswith("اجرا شد (تلاش ۱ از ۳)") and "«" in fa and en.startswith("started (attempt 1/3) by ")
    ok = JobLog.objects.filter(code="succeeded").first()
    fa, en = logtext.texts(ok.code, ok.params)
    assert "ثانیه" in fa and en.startswith("succeeded in ") and not any(c in fa for c in "0123456789")
    # the API hands the rendered texts to the interface (queue modal, monitor, report)
    rows = api.get(f"/api/jobs/{started.job_id}/logs").json()
    row = next(r for r in rows if r["code"] == "started")
    assert row["text_fa"].startswith("اجرا شد") and row["text_en"].startswith("started") and row["message"].startswith("started")
    rep = api.get("/api/reports/logs").json()["rows"]
    assert any(r.get("text_fa", "").startswith("اجرا شد") for r in rep)


def test_an_old_log_row_without_a_code_is_shown_as_it_is(api):
    from instai.jobs import logtext, queue

    job = queue.enqueue("story.script", {"episode_id": 0})
    queue.log_job(job, "some old free text line")
    row = next(r for r in api.get(f"/api/jobs/{job.pk}/logs").json() if r["message"] == "some old free text line")
    assert row["code"] == "" and row["text_fa"] == "" and row["text_en"] == ""
    assert logtext.render("no_such_code", {}, "fa") == ""


def test_pipeline_notes_have_a_persian_twin():
    from instai.jobs.logtext import note_fa

    assert note_fa("shot 3.1: Rhubarb is not installed; amplitude-driven mouth used") == "شاتِ ۳٫۱: Rhubarb نصب نیست؛ دهانِ شخصیت از روی بلندیِ صدا حرکت می‌کند"
    assert "تأیید نشده" in note_fa("shot 1.2: the rig is not approved yet (draft rig used)")
    assert note_fa("an unknown note") == ""


# ------------------------------------------------------------------ 7. a newer version is announced and can be installed from the interface

@pytest.fixture
def updater(monkeypatch, tmp_path):
    """The updater with a fake GitHub (no network) and its own status file."""
    from django.conf import settings

    from instai.ops import update

    monkeypatch.setenv("INSTAI_UPDATE_IN_TESTS", "1")                  # the suite's guard (ops/update.disabled) lets this test's fake GitHub through
    monkeypatch.setenv("INSTAI_NO_UPDATE", "0")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(update, "_known_commit", lambda: "")
    state = {"remote": {"commit": "a" * 40, "version": "0.13.0"}, "spawned": [], "asked": 0}

    def remote():
        state["asked"] += 1
        return state["remote"]

    monkeypatch.setattr(update, "_remote", remote)
    monkeypatch.setattr(update, "_spawn", lambda cmd: state["spawned"].append(cmd))
    return state


def current_version() -> str:
    from instai import version

    return version.read_version()


def test_update_status_says_nothing_to_do_when_github_has_the_same_version(api, updater):
    updater["remote"] = {"commit": "a" * 40, "version": current_version()}
    s = api.get("/api/update/status?refresh=1").json()
    assert s["available"] is False and s["current"] == current_version() and s["error"] == ""


def test_update_status_announces_a_newer_version_and_remembers_the_answer(api, updater):
    updater["remote"] = {"commit": "b" * 40, "version": "99.0.0"}
    s = api.get("/api/update/status?refresh=1").json()
    assert s["available"] is True and s["latest"] == "99.0.0" and s["checked_at"]
    asked = updater["asked"]
    api.get("/api/update/status")                                      # the six-hour memory: GitHub is not asked again
    assert updater["asked"] == asked


def test_update_status_survives_github_being_unreachable(api, updater, monkeypatch):
    from instai.ops import update

    monkeypatch.setattr(update, "_remote", lambda: (_ for _ in ()).throw(OSError("blocked")))
    s = api.get("/api/update/status?refresh=1").json()
    assert s["available"] is False and s["error"] == "OSError"


def test_update_is_switched_off_by_the_owners_setting(api, updater, monkeypatch):
    monkeypatch.setenv("INSTAI_NO_UPDATE", "1")
    updater["remote"] = {"commit": "b" * 40, "version": "99.0.0"}
    s = api.get("/api/update/status?refresh=1").json()
    assert s["disabled"] is True and s["available"] is False and updater["asked"] == 0


def test_update_apply_refuses_while_jobs_run_unless_forced_and_starts_the_helper(api, updater):
    from instai.jobs import queue
    from instai.jobs.models import Job

    updater["remote"] = {"commit": "c" * 40, "version": "99.0.0"}
    job = queue.enqueue("story.script", {"episode_id": 0})
    Job.objects.filter(pk=job.pk).update(status=Job.RUNNING)
    r = api.post("/api/update/apply", {}, format="json")
    assert r.status_code == 409 and r.json()["error"]["details"]["running_jobs"] == 1 and updater["spawned"] == []
    r = api.post("/api/update/apply", {"force": True}, format="json")
    assert r.status_code == 202 and r.json()["applying"] is True
    assert len(updater["spawned"]) == 1 and updater["spawned"][0][1].endswith("apply_update.py") and "--wait-idle" not in updater["spawned"][0]
    Job.objects.filter(pk=job.pk).update(status=Job.SUCCEEDED)
    assert api.get("/api/update/status").json()["applying"] is True


def test_update_apply_waits_for_idle_when_no_job_runs(api, updater):
    updater["remote"] = {"commit": "c" * 40, "version": "99.0.0"}
    r = api.post("/api/update/apply", {}, format="json")
    assert r.status_code == 202 and "--wait-idle" in updater["spawned"][0]


def test_update_apply_without_a_newer_version_is_a_clear_refusal(api, updater):
    updater["remote"] = {"commit": "a" * 40, "version": current_version()}
    r = api.post("/api/update/apply", {}, format="json")
    assert r.status_code == 409 and "نسخهٔ تازه" in r.json()["error"]["message"] and updater["spawned"] == []


def test_the_night_check_runs_only_in_the_idle_window_and_once(updater, monkeypatch):
    from instai.ops import update

    updater["remote"] = {"commit": "d" * 40, "version": current_version()}
    monkeypatch.setattr(update, "in_night_window", lambda now=None: False)
    assert update.night_check() is False and updater["asked"] == 0     # daytime: never
    monkeypatch.setattr(update, "in_night_window", lambda now=None: True)
    assert update.night_check() is True and updater["asked"] == 1
    assert update.night_check() is False and updater["asked"] == 1     # answered less than six hours ago


def test_the_update_helper_stops_updates_and_starts_again_in_that_order(monkeypatch):
    p = Path(__file__).resolve().parents[1] / "scripts" / "apply_update.py"
    spec = importlib.util.spec_from_file_location("apply_update_t", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "WINDOWS", True)
    plan = mod.steps("python")
    assert [s[0] for s in plan] == ["stop", "update", "start"]
    assert plan[0][1][-1] == "STOP.bat" and plan[2][1][-1].endswith("START-AUTO.bat") and plan[1][1][1].endswith("self_update.py")
    assert plan[0][2].get("INSTAI_NO_PAUSE") == "1" and plan[2][2].get("INSTAI_NO_BROWSER") == "1"
    assert mod.main(["--dry-run"]) == 0
    monkeypatch.setattr(mod, "WINDOWS", False)
    assert [s[0] for s in mod.steps("python")] == ["update"]            # a developer checkout has no windows to close
