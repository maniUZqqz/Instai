"""Mini-series channel mode: genre conventions, the season planner and its checks (hooks, cliffhangers, open threads, recurring cast, variety), the schedule,
the API flow plan -> review -> approve -> write the episodes, and the channel context the script writer receives."""
from __future__ import annotations

import pytest

from instai.channel import conventions, planner
from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)


def season(n=8, runtime=30, fa=True, cast=("رامین", "نگهبان")):
    return planner.skeleton_season(n, runtime, fa=fa, characters=list(cast), title="فرار")["episodes"]


def codes(v, level="errors"):
    return sorted({e["code"] for e in v[level]})


def test_conventions_cover_format_length_pacing_and_hooks():
    pub = conventions.public()
    assert {"stick_survival", "stick_escape", "stick_comedy"} <= {g["key"] for g in pub["genres"]}
    assert {c["key"] for c in pub["conventions"]} >= {"hook", "cliffhanger", "fast_cuts", "one_location", "recap", "regular_schedule"}
    plan = conventions.beat_plan("stick_survival", 30)
    assert [b["name"] for b in plan] == ["hook", "setup", "escalation", "twist", "crisis", "cliffhanger"]
    assert plan[0]["start_sec"] == 0 and plan[-1]["end_sec"] == 30 and abs(sum(b["seconds"] for b in plan) - 30) < 0.5
    assert all(g["hook_sec"] == 2 for g in conventions.GENRES.values()) and conventions.genre("nope")["title_en"].startswith("Survival")
    assert len(pub["hook_types"]) >= 5 and len(pub["cliffhanger_types"]) >= 5 and set(pub["cast_roles"]) >= {"protagonist", "rival", "ally"}


@pytest.mark.parametrize("n", [2, 3, 6, 8, 12, 24])
def test_skeleton_season_is_valid_and_threads_close(n):
    eps = season(n)
    v = planner.validate(eps, cast_names=["رامین", "نگهبان"])
    assert len(eps) == n and v["ok"], v["errors"]
    assert all(t["closed"] for t in v["threads"]) and not [w for w in v["warnings"] if w["code"] in ("repeated_hook", "repeated_cliffhanger")]
    assert eps[0]["payoff_of_previous"] == "" and all(e["payoff_of_previous"] for e in eps[1:])


def test_validator_finds_the_problems_of_a_weak_season():
    eps = season(8)
    eps[2]["hook"] = ""
    eps[3]["cliffhanger"] = ""
    eps[4]["hook"] = eps[5]["hook"]
    eps[6]["opens"] = ["x1", "x2", "x3", "x4", "x5"]
    eps[1]["characters"] = []
    eps[5]["location"] = eps[4]["location"] = eps[3]["location"]
    eps[7]["closes"] = []
    eps[6]["runtime_sec"] = 300
    v = planner.validate(eps, cast_names=["رامین", "نگهبان", "ناشناس"])
    assert not v["ok"]
    assert {"missing_hook", "missing_cliffhanger", "thread_never_closed"} <= set(codes(v))
    assert {"repeated_hook", "no_characters", "location_repeat", "too_many_open_threads", "runtime_off", "cast_never_appears"} <= set(codes(v, "warnings"))
    assert planner.validate([])["errors"][0]["code"] == "no_episodes"
    eps2 = season(4)
    eps2[1]["number"] = 7
    assert "numbering" in codes(planner.validate(eps2))


def test_schedule_follows_the_weekdays_and_the_local_time():
    s = planner.schedule("2026-11-21", ["sat", "mon", "wed"], "20:00", 6, utc_offset_minutes=210)   # 2026-11-21 is a Saturday
    assert [x["local"][:10] for x in s] == ["2026-11-21", "2026-11-23", "2026-11-25", "2026-11-28", "2026-11-30", "2026-12-02"]
    assert s[0]["utc"].startswith("2026-11-21T16:30")
    assert planner.schedule("2026-11-21", [], "08:00", 2)[1]["local"].startswith("2026-11-23")      # default days


def make_series(api, level="manual"):
    page = api.post("/api/pages", {"name": "کانال", "format": "mini_series_channel", "languages": ["fa"], "idea": "آدمک چوبی", "automation_level": level,
                                   "characters": [{"name": "رامین", "appearance": "x"}, {"name": "نگهبان", "appearance": "y"}, {"name": "سارا", "appearance": "z"}]}, format="json").json()
    from instai.story.models import Series
    from instai.story import services as svc
    from instai.pages.models import ContentPage

    s = svc.create_series(ContentPage.objects.get(pk=page["id"]), {"title": "فرار بزرگ", "premise": "گیر افتادن و فرار", "target_episodes": 6})
    return page, s


def test_channel_flow_plan_review_approve_and_write_episodes(api, worker):
    from instai.story import services as svc
    from instai.studio import ladder
    from instai.story.models import Episode

    page, s = make_series(api)
    d = api.get(f"/api/series/{s.pk}/channel").json()
    assert d["channel"]["genre"] == "stick_survival" and d["channel"]["cast"][0]["role"] == "protagonist" and len(d["channel"]["cast"]) == 3
    assert d["channel"]["cadence"]["days"] and d["validation"]["ok"] is False
    assert api.post(f"/api/series/{s.pk}/channel/approve", {}, format="json").status_code == 409
    assert api.post(f"/api/series/{s.pk}/channel/apply", {}, format="json").status_code == 409
    d = api.put(f"/api/series/{s.pk}/channel", {"episodes_per_season": 6, "runtime_sec": 30, "cadence": {"start": "2026-12-05", "days": ["sat", "tue"], "time": "19:30"},
                                                  "cast": [{"character": d["channel"]["cast"][0]["character"], "role": "protagonist", "marker": "blue scarf", "catchphrase": ""}]}, format="json").json()
    assert d["channel"]["cadence"]["time"] == "19:30" and d["per_week"] == 2
    j = finish(api, worker, api.post(f"/api/series/{s.pk}/channel/plan", {}, format="json"))
    assert j["result"]["episodes"] == 6 and j["result"]["ok"] is True
    d = api.get(f"/api/series/{s.pk}/channel").json()
    assert len(d["channel"]["slate"]) == 6 and d["validation"]["ok"] and len(d["schedule"]) == 6 and d["schedule"][0]["local"].startswith("2026-12-05T19:30")
    assert [b["name"] for b in d["beats"]][-1] == "cliffhanger"
    # the owner edits one episode: removing a hook is caught, putting it back is fine
    slate = d["channel"]["slate"]
    slate[2]["hook"] = ""
    bad = api.put(f"/api/series/{s.pk}/channel", {"slate": slate}, format="json").json()
    assert not bad["validation"]["ok"] and api.post(f"/api/series/{s.pk}/channel/approve", {}, format="json").status_code == 409
    slate[2]["hook"] = "یک قلاب تازه"
    api.put(f"/api/series/{s.pk}/channel", {"slate": slate}, format="json")
    assert api.post(f"/api/series/{s.pk}/channel/approve", {}, format="json").json()["channel"]["status"] == "approved"
    out = api.post(f"/api/series/{s.pk}/channel/apply", {}, format="json").json()
    assert out["applied"] is True
    eps = list(Episode.objects.filter(series=s).order_by("number"))
    assert [e.number for e in eps] == [1, 2, 3, 4, 5, 6] and eps[1].cliffhanger and eps[0].duration_sec == 30 and "hook:" in eps[0].notes
    docs = ladder.latest(ladder.doc(s, eps[0], "beat_sheet"))                         # every episode starts its beat sheet from the plan
    assert [b["name"] for b in docs.data["beats"]][0] == "hook" and docs.author == "system"
    # the script writer now receives the channel rules and this episode's slate row
    from instai.jobs.handlers.story import episode_meta

    meta = episode_meta(eps[1])
    assert meta["channel"]["hook_within_sec"] == 2 and meta["channel"]["episode_plan"]["cliffhanger"] and meta["channel"]["beats"][0]["name"] == "hook"
    assert meta["beats"][0]["name"] == "hook"
    assert api.post(f"/api/series/{s.pk}/channel/revoke", {}, format="json").json()["channel"]["status"] == "planned"


def test_a_bad_cadence_date_is_rejected_and_the_conventions_endpoint_works(api):
    page, s = make_series(api)
    assert api.put(f"/api/series/{s.pk}/channel", {"cadence": {"start": "not-a-date"}}, format="json").status_code == 400
    assert api.get("/api/channel/conventions").json()["default_genre"] == "stick_survival"


def test_mini_series_and_choice_story_are_formats_with_their_own_development_steps(api):
    t = {x["key"]: x for x in api.get("/api/templates").json()["templates"]}
    assert {"mini_series_channel", "choice_story"} <= set(t)
    assert [s["kind"] for s in t["mini_series_channel"]["steps"]][:3] == ["brainstorm", "profile", "brainstorm"]
    fmts = {f["key"] for f in api.get("/api/pages/registry").json()["formats"]} if api.get("/api/pages/registry").status_code == 200 else set()
    assert not fmts or {"mini_series_channel", "choice_story"} <= fmts
