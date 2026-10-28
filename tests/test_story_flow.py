"""Phase 1 acceptance, through the real HTTP API with the fake provider: for each launch format create a page, get a reviewed
5-episode plan, then one full script and storyboard, continuity and (explainers) sourced research."""
from __future__ import annotations

import pytest

from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)

CASES = [
    ("anime_whatif", "اگر قهرمان در نبرد آخر متحدش را نجات نمی‌داد"),
    ("recurring_character", "گربه‌ی کارتونی و دردسرهای خانه"),
    ("concept_explainer", "سرمایه‌داری چیست؟"),
]


def make_page(api, worker, fmt, idea):
    j = finish(api, worker, api.post("/api/strategy", {"page_name": "صفحه‌ی آزمایشی", "format": fmt, "language": "fa", "idea": idea}, format="json"))
    strat = j["result"]["strategy"]
    assert strat["content_pillars"] and strat["series_ideas"]
    r = api.post("/api/pages", {"name": "صفحه‌ی آزمایشی", "format": fmt, "languages": ["fa"], "idea": idea, "strategy": strat,
                                "series": {**strat["series_ideas"][0], "episodes": 5}}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


@pytest.mark.parametrize("fmt,idea", CASES)
def test_format_acceptance(api, worker, fmt, idea):
    page = make_page(api, worker, fmt, idea)
    assert set(page["profiles"]) == {"identity", "strategy", "visual", "audio", "production", "publishing"}
    series = api.get(f"/api/pages/{page['id']}/series").json()
    assert len(series) == 1
    sid = series[0]["id"]

    # 5-episode plan: proposal (job) -> owner edits -> apply
    j = finish(api, worker, api.post(f"/api/series/{sid}/plan", {"episodes_count": 5}, format="json"))
    plan = j["result"]["plan"]
    assert [e["number"] for e in plan["episodes"]] == [1, 2, 3, 4, 5]
    plan["episodes"][0]["title"] = "عنوانِ ویرایش‌شده"
    r = api.post(f"/api/series/{sid}/apply-plan", {"plan": plan}, format="json")
    assert r.status_code == 200, r.content
    s = r.json()
    assert len(s["episodes"]) == 5 and all(e["state"] == "planned" for e in s["episodes"])
    assert s["episodes"][0]["title"] == "عنوانِ ویرایش‌شده"
    if fmt == "anime_whatif":
        assert plan.get("branch_point") and s["branch_point"]

    ep_id = s["episodes"][0]["id"]
    if fmt == "concept_explainer":
        j = finish(api, worker, api.post(f"/api/episodes/{ep_id}/research", {"topic": "سرمایه‌داری"}, format="json"))
        assert j["result"]["sources"] >= 1
        ep = api.get(f"/api/episodes/{ep_id}").json()
        assert ep["research"]["claims"] and ep["sources"]
        stances = {c["stance"] for c in ep["research"]["claims"]}
        assert {"established", "contested"} <= stances
        assert all(src["verified"] for src in ep["sources"])  # fetched by the system, not invented by the model

    # script
    finish(api, worker, api.post(f"/api/episodes/{ep_id}/generate-script"))
    ep = api.get(f"/api/episodes/{ep_id}").json()
    assert ep["state"] == "script_review"
    assert len(ep["script"]["blocks"]) >= 3 and ep["script_checks"]["word_count"] > 20
    assert ep["script"]["hook"]

    # approve script -> storyboarding + continuity job; then storyboard
    r = api.post(f"/api/episodes/{ep_id}/approve-script")
    assert r.status_code == 200 and r.json()["episode"]["state"] == "storyboarding"
    finish(api, worker, type("R", (), {"status_code": 202, "content": b"", "json": lambda self: {"job": r.json()["job"]}})())
    mem = api.get(f"/api/series/{sid}/memory").json()
    assert mem["entries"]["episode_summary"], "continuity must write the episode summary into StoryMemory"
    finish(api, worker, api.post(f"/api/episodes/{ep_id}/generate-storyboard"))
    ep = api.get(f"/api/episodes/{ep_id}").json()
    shots = [sh for sc in ep["scenes"] for sh in sc["shots"]]
    assert shots and all(sh["technique"] and sh["estimate"]["cpu_seconds"] > 0 for sh in shots)
    assert ep["estimate"]["modes"]["preview"]["gpu_seconds"] <= ep["estimate"]["modes"]["final"]["gpu_seconds"]
    # every spoken word is covered by some shot
    spoken = " ".join(b["text"] for b in ep["script"]["blocks"]).split()
    shot_words = " ".join(sh["narration"] for sh in shots).split()
    assert len(shot_words) >= 0.85 * len(spoken)
    r = api.post(f"/api/episodes/{ep_id}/approve-storyboard")
    assert r.status_code == 200 and r.json()["state"] == "asset_generation"


def test_fan_content_notice_and_originals_default(api, worker):
    page = make_page(api, worker, "anime_whatif", "ایده")
    assert any(n["key"] == "fan" for n in page["notices"])
    series = api.get(f"/api/pages/{page['id']}/series").json()[0]
    assert series["is_fan_content"] is False and series["notices"] == []
    r = api.patch(f"/api/series/{series['id']}", {"is_fan_content": True, "franchise": "Some Franchise"}, format="json")
    assert r.json()["is_fan_content"] is True and r.json()["notices"], "marking fan content shows the notice"
    assert all(c["is_original"] for c in page["characters"])


def test_invalid_state_transition_is_rejected_in_persian(api, worker):
    page = make_page(api, worker, "recurring_character", "ایده")
    sid = api.get(f"/api/pages/{page['id']}/series").json()[0]["id"]
    api.post(f"/api/series/{sid}/apply-plan", {"plan": finish(api, worker, api.post(f"/api/series/{sid}/plan", {}, format="json"))["result"]["plan"]}, format="json")
    ep = api.get(f"/api/series/{sid}/episodes").json()[0]
    r = api.post(f"/api/episodes/{ep['id']}/transition", {"to": "approved"}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    assert "مجاز نیست" in r.json()["error"]["message"]


def test_llm_repair_and_retry_with_broken_provider(api, worker):
    """The first two answers are garbage; the third (after the problems are sent back) is valid."""
    from instai.providers.fake import FakeProvider
    from instai.providers.registry import use_provider

    with use_provider(FakeProvider(fail_first=2)) as p:
        j = finish(api, worker, api.post("/api/strategy", {"page_name": "x", "format": "anime_whatif", "language": "fa", "idea": "i"}, format="json"))
    assert j["result"]["meta"]["attempts"] == 3
    assert len(p.calls) == 3


def test_llm_gives_up_with_persian_error(api, worker):
    from instai.providers.fake import FakeProvider
    from instai.providers.registry import use_provider

    with use_provider(FakeProvider(fail_first=99)):
        r = api.post("/api/strategy", {"page_name": "x", "format": "anime_whatif", "idea": "i"}, format="json")
        job_id = r.json()["job"]["id"]
        from instai.jobs.models import Job

        Job.objects.filter(pk=job_id).update(max_attempts=1)
        j = finish(api, worker, r, expect="failed")
    assert j["error_code"] == "llm_invalid_output"
