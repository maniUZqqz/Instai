"""The idea bank: 100+ built-in ideas in six categories (Persian + English, each with a logline and a hook), the owner's own two ideas, search and filters,
his own ideas and favourites, more ideas from the text model, and «شروعِ پروژه از این ایده» (a series with the look chosen once for the project)."""
from __future__ import annotations

import re

import pytest

from instai.ideabank import bank
from instai.ideabank.seed_base import CATEGORIES
from instai.ideabank.seeds import BUILTIN_IDEAS
from instai.pages import formats
from instai.styles import library

pytestmark = pytest.mark.django_db(transaction=True)
PERSIAN = re.compile(r"[؀-ۿ]")


@pytest.fixture(autouse=True)
def _fresh_library():
    library.clear_cache()
    yield
    library.clear_cache()


def test_the_bank_is_big_and_every_idea_is_complete_in_both_languages():
    assert len(BUILTIN_IDEAS) >= 100
    per = {c: sum(1 for i in BUILTIN_IDEAS.values() if i["category"] == c) for c in CATEGORIES}
    assert set(per) == {"psychology", "personal_development", "economy", "success", "business", "mystery"} and min(per.values()) >= 15, per
    titles_en, titles_fa = set(), set()
    for key, i in BUILTIN_IDEAS.items():
        for f in ("title", "logline", "hook"):
            assert i[f"{f}_fa"] and i[f"{f}_en"], f"{key}: {f} missing in one language"
            assert PERSIAN.search(i[f"{f}_fa"]), f"{key}: {f}_fa is not Persian"
            assert not PERSIAN.search(i[f"{f}_en"]), f"{key}: {f}_en holds Persian text"
        assert i["format"] in formats.FORMATS and i["tags"] and 1 <= i["episodes"] <= 30, key
        assert i["suggested_styles"] and all(library.get_style(s) for s in i["suggested_styles"]), f"{key}: unknown suggested style"
        assert len(i["hook_en"]) <= 300 and len(i["logline_en"]) <= 600, key
        assert i["title_en"].lower() not in titles_en and i["title_fa"] not in titles_fa, f"{key}: duplicate title"
        titles_en.add(i["title_en"].lower())
        titles_fa.add(i["title_fa"])
    assert len(BUILTIN_IDEAS) == len({k for k in BUILTIN_IDEAS}), "keys are unique"


def test_the_owners_two_ideas_are_in_the_bank_with_his_wording():
    tele = next(i for i in BUILTIN_IDEAS.values() if "teleport" in i["title_en"].lower())
    assert tele["category"] == "mystery" and "owner" in tele["tags"]
    assert "where did all my previous trips go" in tele["premise_en"] and "both sure they are the original" in tele["premise_en"]
    assert "When teleportation was invented, many people died." in tele["premise_en"] and "glass booth in New York" in tele["premise_en"]
    assert "تلپورت" in tele["premise_fa"] and "نیویورک" in tele["premise_fa"] and "توکیو" in tele["premise_fa"]
    escape = next(i for i in BUILTIN_IDEAS.values() if "million" in i["title_en"].lower())
    assert escape["category"] == "mystery" and "You have just stolen a million dollars and have to escape" in escape["premise_en"]
    assert "interactive" in escape["tags"]


def test_list_search_and_filters(api):
    r = api.get("/api/ideas").json()
    assert r["total"] >= 100 and len(r["ideas"]) == r["total"] and [c["key"] for c in r["categories"]] == list(CATEGORIES)
    assert all(c["count"] >= 15 for c in r["categories"]) and r["tags"] and r["formats"]
    one = api.get("/api/ideas?category=economy").json()
    assert one["shown"] and all(i["category"] == "economy" for i in one["ideas"])
    # Persian and English words, digit alphabets, either field
    assert any("teleport" in i["title_en"].lower() for i in api.get("/api/ideas?q=teleport").json()["ideas"])
    assert any("تلپورت" in i["title_fa"] for i in api.get("/api/ideas?q=تلپورت").json()["ideas"])
    assert api.get("/api/ideas?q=" + "ساندویچ").json()["shown"] >= 1
    assert api.get("/api/ideas?q=zzzzqqq").json()["shown"] == 0
    multi = api.get("/api/ideas?q=million escape").json()["ideas"]
    assert multi and all("million" in (i["title_en"] + i["logline_en"] + i["premise_en"] + i["hook_en"]).lower() for i in multi)
    tag = api.get("/api/ideas?tag=habits").json()
    assert tag["shown"] >= 2 and all("habits" in i["tags"] for i in tag["ideas"])
    fmt = api.get("/api/ideas?fmt=concept_explainer").json()
    assert fmt["shown"] and all(i["format"] == "concept_explainer" for i in fmt["ideas"])
    both = api.get("/api/ideas?category=mystery&q=lighthouse").json()
    assert both["shown"] == 1
    assert api.get("/api/ideas?source=mine").json()["shown"] == 0 and api.get("/api/ideas?source=builtin").json()["shown"] == r["total"]


def test_favourites_and_hidden_ideas(api):
    key = next(iter(BUILTIN_IDEAS))
    r = api.post(f"/api/ideas/{key}/mark", {"favorite": True}, format="json").json()
    assert r["favorite"] is True
    assert api.get("/api/ideas?favorite=1").json()["shown"] == 1
    assert api.get("/api/ideas").json()["ideas"][0]["key"] == key, "favourites come first"
    api.post(f"/api/ideas/{key}/mark", {"hidden": True}, format="json")
    assert key not in [i["key"] for i in api.get("/api/ideas").json()["ideas"]]
    assert key in [i["key"] for i in api.get("/api/ideas?hidden=1").json()["ideas"]]
    assert api.post("/api/ideas/nope/mark", {"favorite": True}, format="json").status_code == 404


def test_own_ideas_create_edit_copy_delete_and_builtins_are_read_only(api):
    r = api.post("/api/ideas", {"title_en": "My story", "title_fa": "داستان من", "logline_fa": "یک جمله", "category": "success", "tags": "a, b،c", "episodes": 99,
                                "suggested_styles": ["pixel_art_16bit", "no_such_style"], "evil": 1}, format="json")
    assert r.status_code == 201
    mine = r.json()
    assert mine["builtin"] is False and mine["origin"] == "user" and mine["tags"] == ["a", "b", "c"] and mine["episodes"] == 30
    assert mine["suggested_styles"] == ["pixel_art_16bit"] and "evil" not in mine and mine["key"].startswith("u_my_story")
    assert api.post("/api/ideas", {"title_en": "No logline"}, format="json").status_code == 400
    assert api.post("/api/ideas", {"logline_en": "No title"}, format="json").status_code == 400
    assert api.patch(f"/api/ideas/{mine['key']}", {"hook_fa": "قلاب", "category": "business"}, format="json").json()["category"] == "business"
    assert api.get("/api/ideas?source=mine").json()["shown"] == 1
    builtin = next(iter(BUILTIN_IDEAS))
    assert api.patch(f"/api/ideas/{builtin}", {"title_en": "x"}, format="json").status_code == 409
    assert api.delete(f"/api/ideas/{builtin}").status_code == 409
    copy = api.post(f"/api/ideas/{builtin}/duplicate", {}, format="json").json()
    assert copy["builtin"] is False and copy["based_on"] == builtin and copy["title_en"].endswith("(copy)") and copy["title_fa"].endswith("(کپی)")
    assert api.get(f"/api/ideas/{copy['key']}").json()["logline_en"] == BUILTIN_IDEAS[builtin]["logline_en"]
    assert api.delete(f"/api/ideas/{mine['key']}").status_code == 204
    assert api.get(f"/api/ideas/{mine['key']}").status_code == 404 and api.delete(f"/api/ideas/{mine['key']}").status_code == 404


def test_random_idea(api):
    r = api.get("/api/ideas/random?category=mystery").json()
    assert r["category"] == "mystery"
    assert api.get("/api/ideas/random").status_code == 200


def test_start_a_project_on_a_new_page_picks_the_look_once(api):
    from instai.ideabank.models import IdeaUse
    from instai.pages.models import ContentPage
    from instai.story.models import Series

    key = next(k for k, i in BUILTIN_IDEAS.items() if "teleport" in i["title_en"].lower())
    r = api.post(f"/api/ideas/{key}/start", {"language": "fa", "style_key": "voxel_art", "page_name": "کانال تلپورت"}, format="json")
    assert r.status_code == 201, r.content
    out = r.json()
    page, series = ContentPage.objects.get(pk=out["page_id"]), Series.objects.get(pk=out["series_id"])
    assert out["series_url"] == f"/series/{series.pk}" and out["page_created"] is True
    assert page.name == "کانال تلپورت" and page.format == formats.CUSTOM and page.languages == ["fa"]
    assert series.title == BUILTIN_IDEAS[key]["title_fa"] and "تلپورت" in series.premise and BUILTIN_IDEAS[key]["hook_fa"] in series.premise
    assert series.target_episodes == BUILTIN_IDEAS[key]["episodes"] and series.languages == ["fa"]
    assert series.look["style_key"] == "voxel_art" and series.look["theme_key"] == library.get_style("voxel_art")["theme_key"]
    vis = page.profile("visual")
    assert vis["style_key"] == "voxel_art" and vis["aspect_ratio"] == "9:16" and vis["negative_prompt"]
    assert IdeaUse.objects.filter(key=key, series=series).count() == 1
    assert api.get(f"/api/ideas/{key}").json()["uses"] == 1
    # the studio sees the look and it is the project's own
    dev = api.get(f"/api/series/{series.pk}/development").json()
    assert dev["look"]["style_key"] == "voxel_art" and dev["look"]["inherited"] is False
    # no style given for a NEW page: the idea's best-fitting look is used
    r2 = api.post(f"/api/ideas/{key}/start", {"language": "en"}, format="json").json()
    s2 = Series.objects.get(pk=r2["series_id"])
    assert s2.look["style_key"] == BUILTIN_IDEAS[key]["suggested_styles"][0] and s2.title == BUILTIN_IDEAS[key]["title_en"]
    assert "Opening hook" in s2.premise and s2.languages == ["en"]


def test_start_a_project_on_an_existing_page_keeps_the_pages_look_unless_one_is_chosen(api):
    from instai.story.models import Series

    page = api.post("/api/pages", {"name": "p", "format": "concept_explainer", "languages": ["fa"]}, format="json").json()
    api.post(f"/api/pages/{page['id']}/apply-look", {"style_key": "whiteboard_explainer"}, format="json")
    key = next(k for k, i in BUILTIN_IDEAS.items() if i["format"] == "concept_explainer")
    s1 = Series.objects.get(pk=api.post(f"/api/ideas/{key}/start", {"page_id": page["id"]}, format="json").json()["series_id"])
    assert s1.look == {} and s1.page_id == page["id"], "no look chosen: the project inherits the page's look"
    assert s1.content_rules, "explainers get the neutral and sourced rules"
    s2 = Series.objects.get(pk=api.post(f"/api/ideas/{key}/start", {"page_id": page["id"], "style_key": "pixel_art_16bit", "theme_key": "mono_paper",
                                                                    "episodes": 3, "title": "نام دلخواه"}, format="json").json()["series_id"])
    assert s2.look == {"style_key": "pixel_art_16bit", "realism": "graphic", "theme_key": "mono_paper"} and s2.target_episodes == 3 and s2.title == "نام دلخواه"
    from instai.production import pipeline
    from instai.story.models import Episode

    ep = Episode.objects.create(series=s2, number=1, title="e")
    ep = Episode.objects.select_related("series__page").get(pk=ep.pk)
    assert "pixel art" in pipeline.style_prompt(ep).lower(), "the chosen look reaches generation"
    assert api.post(f"/api/ideas/{key}/start", {"page_id": 99999}, format="json").status_code == 400
    assert api.post(f"/api/ideas/{key}/start", {"style_key": "nope"}, format="json").status_code == 400
    assert api.post("/api/ideas/nope/start", {}, format="json").status_code == 404
    assert api.get(f"/api/ideas/{key}").json()["uses"] == 2


def test_more_ideas_from_the_model_are_saved_as_mine_and_never_repeat_titles(api, worker):
    from tests.conftest import finish

    before = api.get("/api/ideas?category=mystery").json()["shown"]
    j = finish(api, worker, api.post("/api/ideas/generate", {"category": "mystery", "count": 3}, format="json"))
    assert len(j["result"]["created"]) == 3 and j["result"]["meta"]["provider"] == "fake"
    after = api.get("/api/ideas?category=mystery").json()
    assert after["shown"] == before + 3
    mine = api.get("/api/ideas?source=mine").json()["ideas"]
    assert len(mine) == 3 and all(i["origin"] == "generated" and i["category"] == "mystery" and i["format"] == formats.CUSTOM for i in mine)
    assert all(PERSIAN.search(i["title_fa"]) and i["logline_en"] for i in mine)
    j2 = finish(api, worker, api.post("/api/ideas/generate", {"category": "economy", "count": 2, "instruction": "about prices"}, format="json"))
    assert len(j2["result"]["created"]) == 2
    assert all(i["format"] == formats.EXPLAINER for i in api.get("/api/ideas?category=economy&source=mine").json()["ideas"])
    assert api.post("/api/ideas/generate", {"category": "nope"}, format="json").status_code == 400


def test_the_generator_prompt_names_the_category_rules_and_existing_titles(api, worker):
    from instai.providers import registry
    from instai.providers.fake import FakeProvider
    from tests.conftest import finish

    fake = FakeProvider()
    registry.set_provider_for_tests(fake)
    key = next(k for k, i in BUILTIN_IDEAS.items() if i["category"] == "psychology")
    api.post(f"/api/ideas/{key}/mark", {"favorite": True}, format="json")
    finish(api, worker, api.post("/api/ideas/generate", {"category": "psychology", "count": 2}, format="json"))
    call = next(c for c in fake.calls if c["task"] == "bank_ideas")
    system = call["messages"][0]["content"]
    assert "Never invent studies" in system and "BOTH Persian (fa) and English (en)" in system
    user = call["messages"][1]["content"]
    assert BUILTIN_IDEAS[key]["title_en"] in user and "liked" in user, "the favourites steer it and existing titles are listed so it does not repeat them"


def test_job_title_exists_in_the_queue_texts():
    from instai.jobs.describe import KIND_TEXT

    assert KIND_TEXT["ideas.generate"][0] and KIND_TEXT["styles.preview"][1]


def test_the_bank_routes_do_not_swallow_the_studio_boards_idea_ids():
    """`/api/ideas/<number>` belongs to the development-room idea cards; a bank key always starts with a letter (found by test_studio)."""
    from django.urls import resolve

    def owner(url: str) -> str:
        f = resolve(url).func
        return getattr(f, "cls", f).__module__

    assert owner("/api/ideas/7").startswith("instai.studio") and owner("/api/ideas/7/rate").startswith("instai.studio")
    assert owner("/api/ideas/mind_anchoring").startswith("instai.ideabank") and owner("/api/ideas/u_my_idea/start").startswith("instai.ideabank")
    assert owner("/api/ideas/random").startswith("instai.ideabank") and owner("/api/ideas/generate").startswith("instai.ideabank")


def test_fitness_and_coaching_ideas_are_in_the_personal_development_category():
    rows = [i for i in BUILTIN_IDEAS.values() if "fitness" in i["tags"] or "coaching" in i["tags"]]
    assert len(rows) >= 8 and {i["category"] for i in rows} == {"personal_development"}
    text = " ".join(i["logline_fa"] + i["logline_en"] + i["hook_fa"] + i["hook_en"] for i in rows)
    assert not re.search(r"\d+\s*(%|٪|درصد|percent)", text), "no invented statistics"


def test_every_builtin_tag_has_a_persian_name_in_the_interface():
    """The tag chips of the idea page are Persian in the Persian interface (frontend/src/ideaTags.ts); a tag without a name would show as an English word."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "ideaTags.ts").read_text(encoding="utf-8")
    named = dict(re.findall(r"^\s*'([a-z0-9\-]+)':\s*'([^']+)'", src, flags=re.M))
    tags = {t for i in BUILTIN_IDEAS.values() for t in i["tags"]}
    assert sorted(tags - set(named)) == [], "tags without a Persian name"
    assert all(PERSIAN.search(v) for v in named.values()), "every name is Persian"
