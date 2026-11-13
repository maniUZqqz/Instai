"""Ready-made choice stories and mini-series seasons: every one passes the same validators the owner's own work must pass, uses only existing backgrounds / poses /
characters, fits the picture limits, and can be started from the API; the planner falls back to them (instead of placeholder text) when no model answers."""
from __future__ import annotations

import pytest

from instai.channel import planner, season_templates
from instai.choice import graph as G
from instai.choice import story_templates as T
from instai.render.stick import poses, scenes
from instai.render.stick import spec as stick_spec
from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)

EXPRESSIONS = set(stick_spec.EXPRESSIONS)


def graph_of(t):
    nodes = [G.new_node(p["id"], title=p["title"], text=p["text"], kind=p["kind"], ending=p["ending"], choices=p["choices"],
                        scene={"location": p["location"], "pose": p["pose"], "expression": p["expression"], "characters": p["characters"]}) for p in t["posts"]]
    return G.renumber(G.normalize({"nodes": nodes}))[0]


@pytest.mark.parametrize("t", T.TEMPLATES, ids=[t["key"] for t in T.TEMPLATES])
def test_every_ready_made_story_is_a_valid_branching_graph(t):
    g = graph_of(t)
    v = G.validate(g)
    assert v["ok"], v["errors"]
    assert not v["warnings"], v["warnings"]                           # label and text limits, choice counts: nothing to warn about
    st = v["stats"]
    assert st["endings"].get("good", 0) >= 1 and st["endings"].get("bad", 0) >= 2 and st["paths"] >= 6
    nums = G.numbers(g)
    assert all(nums[to] > nums[a] for a, to, _c in G.edges(g))      # every choice points forward in posting order
    assert 12 <= len(g["nodes"]) <= 20 and g["nodes"][0]["kind"] == "start"
    assert not G.unresolved(g)


@pytest.mark.parametrize("t", T.TEMPLATES, ids=[t["key"] for t in T.TEMPLATES])
def test_story_scenes_use_real_backgrounds_poses_expressions_and_cast(t):
    cast = {c["name"] for c in t["cast"]}
    assert len(cast) == len(t["cast"]) and 2 <= len(cast) <= 4
    for p in t["posts"]:
        assert p["location"] in scenes.BACKGROUNDS, p["id"]
        assert p["pose"] in poses.POSES, p["id"]
        assert p["expression"] in EXPRESSIONS, p["id"]
        assert p["characters"] and set(p["characters"]) <= cast, p["id"]
        assert 40 <= len(p["text"]) <= 220, (p["id"], len(p["text"]))
        assert all(0 < len(c["label"]) <= G.MAX_LABEL for c in p["choices"]), p["id"]
        assert len(p["choices"]) in (0, 1, 2, 3)
        assert not ("TODO" in p["text"] or "..." in p["text"] or "صحنهٔ" in p["text"] and "باید تصمیم بگیری" in p["text"])        # no placeholder text
    for c in t["cast"]:
        assert c["spec"] and stick_spec.normalize(c["spec"], name=c["name"])["limb_colour"]


def test_the_gallery_lists_every_genre_the_story_form_offers_and_the_brand_story():
    from instai.choice import services

    genres = {t["genre"] for t in T.listing()}
    assert genres >= {g for g in services.GENRES if g != "custom"}
    assert "chagher_coach" in {t["key"] for t in T.listing()}
    assert T.for_genre("custom") is None and T.for_genre("prison_escape")["key"] == "prison_escape"
    row = next(t for t in T.listing() if t["key"] == "prison_escape")
    assert row["posts"] == 16 and row["endings"] == {"bad": 5, "good": 1, "secret": 1} and row["cast"][0]["name"] == "رامین"


def test_the_brand_story_states_no_invented_numbers_prices_or_testimonials():
    t = T.get("chagher_coach")
    text = " ".join(p["text"] + " " + p["title"] for p in t["posts"])
    assert "۶۰۰" not in text and "٪" not in text and "درصد" not in text and "تومان" not in text and "تضمین" not in text and "جایگزین مربی" not in text
    assert "پیش‌نویس" in text and "تصمیم" in text and "چغر" in text
    assert any("کمتر از یک دقیقه" in p["text"] for p in t["posts"])


@pytest.mark.parametrize("s", season_templates.TEMPLATES, ids=[s["key"] for s in season_templates.TEMPLATES])
def test_every_ready_made_season_passes_the_season_validator_without_a_single_warning(s):
    from instai.channel import conventions

    g = conventions.genre(s["genre"])
    v = planner.validate(season_templates.plan_of(s)["episodes"], cast_names=[c["name"] for c in s["cast"]], runtime=s["runtime_sec"], genre_runtime=(g["runtime"]["min"], g["runtime"]["max"]))
    assert v["ok"], v["errors"]
    assert not v["warnings"], v["warnings"]
    assert all(t["closed"] for t in v["threads"]) and len(s["episodes"]) == 6
    assert s["genre"] in conventions.GENRES and all(c["role"] in conventions.CAST_ROLES for c in s["cast"])
    cast = {c["name"] for c in s["cast"]}
    assert all(set(e["characters"]) <= cast for e in s["episodes"])
    assert all(e["location"] in scenes.BACKGROUNDS for e in s["episodes"])
    assert [e["number"] for e in s["episodes"]] == list(range(1, 7))


def test_start_a_story_from_a_template_through_the_api_with_a_locked_cast_and_a_valid_graph(api, worker):
    page = api.post("/api/pages", {"name": "پیج", "format": "choice_story", "languages": ["fa"], "idea": "x", "automation_level": "manual", "characters": []}, format="json").json()
    assert {t["key"] for t in api.get("/api/choice/templates").json()["templates"]} == {t["key"] for t in T.TEMPLATES}
    r = api.post(f"/api/pages/{page['id']}/choice-stories", {"template": "prison_escape"}, format="json")
    assert r.status_code == 201, r.content
    s = r.json()
    assert s["title"] == "فرار از زندان شمارهٔ ۷" and s["posts"] == 16 and s["genre"] == "prison_escape" and s["status"] == "planned"
    rep = api.get(f"/api/choice-stories/{s['id']}/report").json()
    assert rep["validation"]["ok"] and rep["stats"]["endings"]["secret"] == 1
    nodes = api.get(f"/api/choice-stories/{s['id']}").json()["graph"]["nodes"]
    assert nodes[0]["scene"]["characters"] == ["رامین"] and all("{go:" in n["caption"] or n["kind"] == "ending" for n in nodes)
    from instai.pages.models import Character

    assert set(Character.objects.filter(page_id=page["id"]).values_list("name", flat=True)) >= {"رامین", "ناصر", "سروان"}
    from instai.identity.models import CharacterLock

    locks = list(CharacterLock.objects.filter(character__page_id=page["id"]))
    assert len(locks) == 3 and all(l.status == "locked" and l.stick for l in locks)
    assert api.post(f"/api/pages/{page['id']}/choice-stories", {"template": "nope"}, format="json").status_code == 404
    # it renders and packages like any other story (approved, pictures drawn by code, real numbers in the captions)
    assert api.post(f"/api/choice-stories/{s['id']}/approve", {}, format="json").json()["status"] == "approved"
    j = finish(api, worker, api.post(f"/api/choice-stories/{s['id']}/render", {}, format="json"))
    assert j["result"]["rendered"] == 16
    caps = api.get(f"/api/choice-stories/{s['id']}/captions/text").json()["text"]
    assert "{go:" not in caps and "{?" not in caps
    # loading another template into the same story replaces the graph and keeps the old one as a version
    again = api.post(f"/api/choice-stories/{s['id']}/template", {"key": "haunted_house"}, format="json")
    assert again.status_code == 200 and again.json()["posts"] == 14 and again.json()["status"] == "planned"
    versions = api.get(f"/api/choice-stories/{s['id']}/versions").json()
    assert len(versions) == 1 and versions[0]["posts"] == 16


def test_the_planner_falls_back_to_the_ready_story_of_the_genre_when_no_model_answers(api, worker, monkeypatch):
    from instai.agents.runner import AgentError
    from instai.choice import jobs

    def boom(*a, **k):
        raise AgentError("no model", errors=["x"])

    monkeypatch.setattr(jobs.roles, "choice_planner", boom)
    page = api.post("/api/pages", {"name": "پیج", "format": "choice_story", "languages": ["fa"], "idea": "x", "automation_level": "manual", "characters": []}, format="json").json()
    sid = api.post(f"/api/pages/{page['id']}/choice-stories", {"title": "زامبی", "genre": "zombie_survival", "post_count": 10}, format="json").json()["id"]
    j = finish(api, worker, api.post(f"/api/choice-stories/{sid}/plan", {}, format="json"))
    assert j["result"]["fallback"] is True and j["result"]["provider"] == "template" and j["result"]["posts"] == 15
    rep = api.get(f"/api/choice-stories/{sid}/report").json()
    assert rep["validation"]["ok"]
    texts = " ".join(n["text"] for n in api.get(f"/api/choice-stories/{sid}").json()["graph"]["nodes"])
    assert "پناهگاه" in texts and "صحنهٔ" not in texts
    # a genre without a ready story still gets the skeleton
    sid2 = api.post(f"/api/pages/{page['id']}/choice-stories", {"title": "دلخواه", "genre": "custom", "post_count": 9}, format="json").json()["id"]
    j2 = finish(api, worker, api.post(f"/api/choice-stories/{sid2}/plan", {}, format="json"))
    assert j2["result"]["provider"] == "skeleton" and j2["result"]["posts"] == 9


def make_series(api):
    from instai.pages.models import ContentPage
    from instai.story import services as svc

    page = api.post("/api/pages", {"name": "کانال", "format": "mini_series_channel", "languages": ["fa"], "idea": "آدمک چوبی", "automation_level": "manual", "characters": []}, format="json").json()
    return page, svc.create_series(ContentPage.objects.get(pk=page["id"]), {"title": "فصل", "premise": "بقا", "target_episodes": 6})


def test_start_a_channel_from_a_ready_season_then_approve_and_write_the_episodes(api, worker):
    from instai.story.models import Episode

    page, s = make_series(api)
    assert {t["key"] for t in api.get("/api/channel/templates").json()["templates"]} == {t["key"] for t in season_templates.TEMPLATES}
    d = api.post(f"/api/series/{s.pk}/channel/template", {"key": "silent_city"}, format="json")
    assert d.status_code == 200, d.content
    d = d.json()
    assert d["validation"]["ok"] and not d["validation"]["warnings"] and len(d["channel"]["slate"]) == 6 and d["channel"]["status"] == "planned"
    assert [c["name"] for c in d["channel"]["cast"]] == ["ماهان", "نیلا", "عمو انباردار"] and all(c["character"] for c in d["channel"]["cast"])
    assert d["channel"]["genre"] == "stick_survival" and d["channel"]["season_title"] == "شهرِ خاموش" and len(d["schedule"]) == 6
    assert api.post(f"/api/series/{s.pk}/channel/template", {"key": "nope"}, format="json").status_code == 404
    assert api.post(f"/api/series/{s.pk}/channel/approve", {}, format="json").json()["channel"]["status"] == "approved"
    assert api.post(f"/api/series/{s.pk}/channel/apply", {}, format="json").json()["applied"] is True
    eps = list(Episode.objects.filter(series=s).order_by("number"))
    assert len(eps) == 6 and eps[0].title == "بیداری" and "hook:" in eps[0].notes
    from instai.identity.models import CharacterLock

    assert CharacterLock.objects.filter(character__page_id=page["id"], status="locked").count() == 3
    from instai.pages.models import Character

    assert Character.objects.get(page_id=page["id"], name="ماهان").role == "قهرمان"          # the Characters tab shows the role in Persian, not the channel key


def test_the_season_planner_falls_back_to_the_ready_season_when_no_model_answers(api, worker, monkeypatch):
    from instai.agents.runner import AgentError
    from instai.channel import jobs

    def boom(*a, **k):
        raise AgentError("no model", errors=["x"])

    monkeypatch.setattr(jobs.roles, "season_planner", boom)
    page, s = make_series(api)
    j = finish(api, worker, api.post(f"/api/series/{s.pk}/channel/plan", {}, format="json"))
    assert j["result"]["fallback"] is True and j["result"]["provider"] == "template" and j["result"]["ok"] is True and j["result"]["episodes"] == 6
    d = api.get(f"/api/series/{s.pk}/channel").json()
    assert d["validation"]["ok"] and "ماهان" in " ".join(e["hook"] for e in d["channel"]["slate"])
