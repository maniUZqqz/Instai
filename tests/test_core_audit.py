"""Audit batch "ia_core" (2026-11-14): the first script of an episode with the language model off, the worker's automation tick,
plain-Persian provider hints, the idea -> series hand-over, Persian digits and the update badge. Everything with the fake providers."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from instai.jobs import queue
from instai.jobs.context import JobCancelled
from instai.jobs.models import Job, Worker
from instai.providers.base import ProviderError
from instai.story import services, states
from instai.story.models import Episode, EpisodeEvent
from tests.conftest import finish, run_jobs
from tests.test_story_flow import make_page

pytestmark = pytest.mark.django_db(transaction=True)


def planned_episode(api, worker) -> int:
    page = make_page(api, worker, "recurring_character", "گربه‌ی کارتونی و دردسرهای خانه")
    sid = api.get(f"/api/pages/{page['id']}/series").json()[0]["id"]
    j = finish(api, worker, api.post(f"/api/series/{sid}/plan", {"episodes_count": 3}, format="json"))
    r = api.post(f"/api/series/{sid}/apply-plan", {"plan": j["result"]["plan"]}, format="json")
    assert r.status_code == 200, r.content
    return r.json()["episodes"][0]["id"]


def release_waiting(job_id: int) -> None:
    Job.objects.filter(pk=job_id).update(run_after=timezone.now() - timedelta(seconds=1))


# ------------------------------------------------------------------ 1. the first script with the model off

def _down(*a, **k):
    raise ProviderError("Ollama is not reachable", code="ollama_down", wait="ollama_down", fa="مدل زبانی روشن نیست.")


def test_script_with_the_model_off_waits_and_the_episode_stays_planned(api, worker, monkeypatch):
    ep_id = planned_episode(api, worker)
    from instai.jobs.handlers import story as handlers

    monkeypatch.setattr(handlers.roles, "scriptwriter", _down)
    r = api.post(f"/api/episodes/{ep_id}/generate-script")
    assert r.status_code == 202, r.content
    job_id = r.json()["job"]["id"]
    run_jobs(worker)
    job = Job.objects.get(pk=job_id)
    # not failed with "invalid_transition": parked in the durable queue with the Persian reason, no attempt used
    assert job.status == Job.QUEUED and job.wait_code == "ollama_down" and job.attempts == 0 and job.error_code != "invalid_transition", (job.status, job.error)
    assert "مدل زبانی" in job.waiting_reason
    ep = api.get(f"/api/episodes/{ep_id}").json()
    assert ep["state"] == "planned", "the page must not say 'writing the script' while nothing is writing"
    assert Episode.objects.get(pk=ep_id).state == states.PLANNED
    # the model comes back: the SAME job finishes by itself and the episode reaches review
    monkeypatch.undo()
    release_waiting(job_id)
    run_jobs(worker)
    assert Job.objects.get(pk=job_id).status == Job.SUCCEEDED
    assert api.get(f"/api/episodes/{ep_id}").json()["state"] == "script_review"


def test_a_real_script_error_fails_the_job_with_its_own_message_and_releases_the_episode(api, worker, monkeypatch):
    ep_id = planned_episode(api, worker)
    from instai.jobs.handlers import story as handlers

    def bad(*a, **k):
        raise ProviderError("the model returned garbage", retryable=False, code="llm_invalid_output")

    monkeypatch.setattr(handlers.roles, "scriptwriter", bad)
    job_id = api.post(f"/api/episodes/{ep_id}/generate-script").json()["job"]["id"]
    run_jobs(worker)
    job = Job.objects.get(pk=job_id)
    assert job.status == Job.FAILED and job.error_code == "llm_invalid_output", (job.status, job.error_code, job.error)   # the ORIGINAL error, not invalid_transition
    assert api.get(f"/api/episodes/{ep_id}").json()["state"] == "planned"
    # and a retry is possible (the transition / retry endpoints are not 409)
    monkeypatch.undo()
    assert api.post(f"/api/jobs/{job_id}/retry").status_code == 200
    run_jobs(worker)
    assert api.get(f"/api/episodes/{ep_id}").json()["state"] == "script_review"


def test_cancelling_the_script_job_leaves_the_episode_planned(api, worker, monkeypatch):
    ep_id = planned_episode(api, worker)
    from instai.jobs.handlers import story as handlers

    def cancelled(*a, **k):
        raise JobCancelled()

    monkeypatch.setattr(handlers.roles, "scriptwriter", cancelled)
    job_id = api.post(f"/api/episodes/{ep_id}/generate-script").json()["job"]["id"]
    run_jobs(worker)
    assert Job.objects.get(pk=job_id).status == Job.CANCELLED
    assert api.get(f"/api/episodes/{ep_id}").json()["state"] == "planned"
    last = EpisodeEvent.objects.filter(episode_id=ep_id).order_by("-id").first()
    assert (last.from_state, last.to_state, last.actor) == ("scripting", "planned", "system")


def test_regenerating_a_script_with_the_model_off_returns_to_review_with_the_old_script(api, worker, monkeypatch):
    ep_id = planned_episode(api, worker)
    finish(api, worker, api.post(f"/api/episodes/{ep_id}/generate-script"))
    assert api.get(f"/api/episodes/{ep_id}").json()["state"] == "script_review"
    from instai.jobs.handlers import story as handlers

    monkeypatch.setattr(handlers.roles, "scriptwriter", _down)
    api.post(f"/api/episodes/{ep_id}/generate-script")
    run_jobs(worker)
    ep = api.get(f"/api/episodes/{ep_id}").json()
    assert ep["state"] == "script_review" and len(ep["script"]["blocks"]) >= 3, "the owner keeps the script he had"


def test_an_episode_stuck_in_scripting_without_a_job_heals_when_its_page_opens(api, worker):
    ep_id = planned_episode(api, worker)
    Episode.objects.filter(pk=ep_id).update(state=states.SCRIPTING)          # what an older version left behind
    ep = api.get(f"/api/episodes/{ep_id}").json()
    assert ep["state"] == "planned"
    assert EpisodeEvent.objects.filter(episode_id=ep_id, from_state="scripting", to_state="planned", actor="system").exists()


def test_an_episode_whose_script_job_is_still_queued_is_not_healed(api, worker):
    ep_id = planned_episode(api, worker)
    ep = Episode.objects.get(pk=ep_id)
    queue.enqueue("story.script", {"episode_id": ep_id}, episode=ep, title="x")
    Episode.objects.filter(pk=ep_id).update(state=states.SCRIPTING)
    assert api.get(f"/api/episodes/{ep_id}").json()["state"] == "scripting"
    assert services.heal_stuck_scripting() == 0


def test_the_worker_tick_heals_every_stuck_episode_and_the_manual_way_back_is_allowed(api, worker):
    ep_id = planned_episode(api, worker)
    Episode.objects.filter(pk=ep_id).update(state=states.SCRIPTING)
    assert states.can_transition(states.SCRIPTING, states.PLANNED)
    assert services.heal_stuck_scripting() == 1
    assert Episode.objects.get(pk=ep_id).state == states.PLANNED
    Episode.objects.filter(pk=ep_id).update(state=states.SCRIPTING)
    assert api.post(f"/api/episodes/{ep_id}/transition", {"to": "planned"}, format="json").status_code == 200


# ------------------------------------------------------------------ 3. one failing step of the tick does not skip the rest

def test_a_failing_tick_step_does_not_skip_the_steps_after_it():
    from instai.jobs.worker import run_tick_steps

    ran = []

    def boom():
        raise RuntimeError("automation exploded")

    errors = run_tick_steps([("automation", boom), ("vram", lambda: ran.append("vram")), ("styles", lambda: ran.append("styles"))])
    assert ran == ["vram", "styles"]
    assert list(errors) == ["automation"] and "automation exploded" in errors["automation"]


def test_the_real_tick_runs_every_step_even_when_automation_tick_raises(monkeypatch):
    from instai.gpu import coexist
    from instai.jobs.worker import WorkerRunner
    from instai.production import automation
    from instai.styles import previews

    seen = []
    monkeypatch.setattr(automation, "tick", lambda: (_ for _ in ()).throw(RuntimeError("tick broke")))
    monkeypatch.setattr(coexist, "release_idle", lambda: seen.append("vram"))
    monkeypatch.setattr(previews, "auto_queue", lambda: seen.append("styles"))
    w = WorkerRunner("tick-test")
    Worker.objects.create(name="tick-test", last_seen=timezone.now())
    w._automation_tick()
    assert seen == ["vram", "styles"]
    row = Worker.objects.get(name="tick-test")
    assert "automation" in row.info["tick_errors"] and "tick broke" in row.info["tick_errors"]["automation"]["error"]


def test_the_monitor_names_the_broken_step_in_persian_and_the_heartbeat_keeps_it(api):
    from instai.jobs.worker import WorkerRunner

    w = WorkerRunner("tick-mon")
    w._heartbeat_row()
    w._record_tick_errors({"vram": "OSError: nvidia-smi"})
    w._heartbeat_row()                                                   # the next heartbeat must not wipe it
    mon = api.get("/api/monitor").json()
    row = next(x for x in mon["workers"] if x["name"] == "tick-mon")
    err = row["tick_errors"][0]
    assert err["step"] == "vram" and "حافظهٔ کارت گرافیک" in err["label_fa"] and err["label_en"] and "nvidia-smi" in err["error"]
    w._record_tick_errors({})                                            # fixed: the warning goes away
    row = next(x for x in api.get("/api/monitor").json()["workers"] if x["name"] == "tick-mon")
    assert row["tick_errors"] == []


# ------------------------------------------------------------------ 2. silent downgrades are warnings, not "healthy"

def storyboard_episode(api, worker, fmt="recurring_character"):
    from tests.test_pipeline_e2e import build_episode

    return build_episode(api, worker, fmt)


def set_techniques(ep_id: int, techniques: list[str]) -> None:
    from instai.story.models import Shot

    for shot, tech in zip(Shot.objects.filter(scene__episode_id=ep_id).order_by("scene__index", "index"), techniques):
        Shot.objects.filter(pk=shot.pk).update(technique=tech)


def test_shot_list_names_every_downgrade_in_persian_and_never_says_phase(api, worker):
    page, sid, ep_id = storyboard_episode(api, worker)
    set_techniques(ep_id, ["puppet_2d", "parallax_25d", "three_d", "still_kenburns"])
    ep = api.get(f"/api/episodes/{ep_id}").json()
    by = {f["code"]: f for f in ep["fallbacks"]}
    assert {"no_rig", "no_layers", "not_implemented"} <= set(by), ep["fallbacks"]
    for f in ep["fallbacks"]:
        assert f["fa"] and f["en"] and "Phase" not in f["fa"] + f["en"], f
        assert "تصویرِ ثابت با حرکت دوربین" in f["fa"].replace("تصویر ثابت", "تصویرِ ثابت") or "تصویر ثابت با حرکت دوربین" in f["fa"]
        assert not any(c.isascii() and c.isalpha() for c in f["fa"].replace("Wan", "")), f["fa"]          # a Persian sentence, no English words
    assert "عروسک" in by["no_rig"]["fa"] and "پارالاکس" in by["no_layers"]["fa"]
    assert ep["fallbacks"][0]["shot"] and ep["fallbacks"][0]["technique"] == "puppet_2d"


def test_preflight_offers_the_puppet_and_one_click_makes_it(api, worker):
    page, sid, ep_id = storyboard_episode(api, worker)
    set_techniques(ep_id, ["puppet_2d", "puppet_2d", "still_kenburns"])
    pf = api.get(f"/api/episodes/{ep_id}/preflight").json()
    from instai.story.models import Shot

    puppets = Shot.objects.filter(scene__episode_id=ep_id, technique="puppet_2d").count()      # the storyboard may already hold more puppet shots
    n = len(pf["needs_rig"])
    assert n >= 1 and sum(r["shots"] for r in pf["needs_rig"]) == puppets >= 2 and pf["rigs_path"] == "/lab/rigs"
    made = api.post(f"/api/episodes/{ep_id}/preflight", {}, format="json").json()
    assert len(made["rigs_made"]) == n and made["needs_rig"] == [] and made["fallbacks"] == []
    from instai.production.models import CharacterRig

    assert CharacterRig.objects.filter(source="stick").count() == n
    # asking again changes nothing (idempotent)
    again = api.post(f"/api/episodes/{ep_id}/preflight", {}, format="json").json()
    assert again["rigs_made"] == [] and CharacterRig.objects.filter(source="stick").count() == n
    assert api.get(f"/api/episodes/{ep_id}").json()["fallbacks"] == []


def test_produce_with_auto_rig_makes_the_puppet_first_and_without_it_still_works(api, worker):
    page, sid, ep_id = storyboard_episode(api, worker)
    set_techniques(ep_id, ["puppet_2d", "puppet_2d", "still_kenburns"])
    from instai.production.models import CharacterRig

    r = api.post(f"/api/episodes/{ep_id}/produce", {"mode": "preview", "auto_rig": True}, format="json")
    assert r.status_code == 202 and len(r.json()["rigs_made"]) >= 1 and CharacterRig.objects.count() == len(r.json()["rigs_made"])
    assert api.get(f"/api/episodes/{ep_id}/preflight").json()["needs_rig"] == []


def test_quality_check_warns_when_shots_fell_back_and_is_ok_when_none_did():
    from instai.production import fallbacks

    ok = fallbacks.qc_check([])
    assert ok["level"] == "ok"
    rows = [{"shot": 1, "scene": 1, "index": 2, "technique": "puppet_2d", "code": "no_rig", "character": "نیما", "fa": "x", "en": "x"},
            {"shot": 2, "scene": 1, "index": 3, "technique": "puppet_2d", "code": "no_rig", "character": "نیما", "fa": "x", "en": "x"},
            {"shot": 3, "scene": 2, "index": 1, "technique": "parallax_25d", "code": "no_layers", "fa": "x", "en": "x"}]
    w = fallbacks.qc_check(rows)
    assert w["level"] == "warn" and "۳ شات" in w["message"] and "۱٫۲" in w["message"] and "شخصیت‌های پاپت" in w["message"] and "نیما" in w["message"]
    assert "Phase" not in w["message"]


def test_a_render_with_puppet_and_parallax_shots_without_rig_is_a_warning_not_healthy(api, worker, ffmpeg_available):
    from instai.assets.models import Asset
    from instai.jobs.models import JobLog
    from tests.test_pipeline_e2e import produce

    page, sid, ep_id = storyboard_episode(api, worker)
    set_techniques(ep_id, ["puppet_2d", "parallax_25d", "puppet_2d", "still_kenburns"])
    ep = produce(api, worker, ep_id, "preview")
    qc = ep["qc"]
    fb = next(c for c in qc["checks"] if c["name"] == "fallbacks")
    assert fb["level"] == "warn" and qc["warnings"] >= 1, qc
    assert "عروسک" in fb["message"] and "پارالاکس" in fb["message"]
    video = Asset.objects.get(pk=next(v for v in ep["videos"] if v["role"] == "preview")["id"])
    assert {f["code"] for f in video.provenance["fallbacks"]} == {"no_rig", "no_layers"}
    from instai.jobs import logtext

    lines = list(JobLog.objects.filter(job__episode_id=ep_id, level="warning"))
    shown_fa = " ".join(logtext.texts(l.code, l.params)[0] or l.message for l in lines)
    assert "Phase" not in shown_fa + " ".join(l.message for l in lines) and "عروسک" in shown_fa, shown_fa     # the report shows the Persian sentence, never a phase number


# ------------------------------------------------------------------ 5. an idea started as a project shows up in the development room

def idea_of_format(api, fmt: str) -> dict:
    rows = api.get("/api/ideas").json()["ideas"]
    return next(i for i in rows if i["format"] == fmt)


@pytest.mark.parametrize("fmt", ["recurring_character", "concept_explainer"])
def test_start_project_fills_the_first_step_and_shows_the_idea_card(api, fmt):
    idea = idea_of_format(api, fmt)
    r = api.post(f"/api/ideas/{idea['key']}/start", {"page_name": "صفحهٔ آزمایشی", "language": "fa"}, format="json")
    assert r.status_code == 201, r.content
    out = r.json()
    assert out["page_name"] == "صفحهٔ آزمایشی"
    dev = api.get(f"/api/series/{out['series_id']}/development").json()
    card = dev["start_idea"]
    assert card["key"] == idea["key"] and card["title_fa"] and card["logline_fa"] and card["hook_fa"]
    first = dev["steps"][0]
    if first["kind"] == "profile":                                    # the character brief is not empty any more
        brief = first["data"]["brief"]
        assert idea["title_fa"] in brief and idea["logline_fa"] in brief and first["status"] == "active"
    else:                                                             # a brainstorm board starts with the idea as its first approved card
        cards = dev["ideas"][first["params"].get("board", first["key"])]
        assert len(cards) == 1 and cards[0]["title"] == idea["title_fa"] and cards[0]["status"] == "approved"


def test_start_project_rejects_an_empty_page_name_but_names_the_page_after_the_idea_when_none_is_sent(api):
    idea = idea_of_format(api, "recurring_character")
    bad = api.post(f"/api/ideas/{idea['key']}/start", {"page_name": "   "}, format="json")
    assert bad.status_code == 400 and "page_name" in bad.json()["error"]["details"]
    ok = api.post(f"/api/ideas/{idea['key']}/start", {}, format="json")
    assert ok.status_code == 201 and ok.json()["page_name"] == idea["title_fa"]            # the answer says which name was used


def test_a_series_not_started_from_an_idea_has_no_idea_card(api, worker):
    page = make_page(api, worker, "recurring_character", "گربه‌ی کارتونی")
    sid = api.get(f"/api/pages/{page['id']}/series").json()[0]["id"]
    assert api.get(f"/api/series/{sid}/development").json()["start_idea"] is None
