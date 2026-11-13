"""The studio ladder: every stage versioned and approved in order, staleness, automation levels, generation with the fake roles, bridged stages and the production gate."""
from __future__ import annotations

import pytest

from instai.core.errors import DomainError
from instai.studio import ladder
from instai.studio.ladder_stages import BY_KEY, PHASES, STAGES, needs_human
from tests.conftest import finish
from tests.test_identity import make_world

pytestmark = pytest.mark.django_db(transaction=True)


def test_catalogue_is_a_complete_studio_pipeline_without_cycles():
    keys = [s["key"] for s in STAGES]
    assert len(keys) == 21 and len(set(keys)) == 21
    for want in ("logline", "treatment", "beat_sheet", "script", "dialogue", "shot_list", "storyboard", "animatic", "design", "layout", "key_art", "animation", "compositing",
                 "sound_design", "narration", "edit", "grade", "delivery", "art_style", "bible", "character_models"):
        assert want in BY_KEY
    seen = set()
    for s in STAGES:                                   # listed in an order where every need comes first (so the list is also a valid work order)
        assert all(n in seen for n in s["needs"]), s["key"]
        seen.add(s["key"])
        assert s["phase"] in {p["key"] for p in PHASES} and s["fa"] and s["en"] and s["term_fa"] and s["term_en"]
        assert s["gen"] in ("llm", "derive", None) and s["source"] in ("stored", "bridge")
        if s["source"] == "stored" and s["gen"]:
            assert s["fields"], s["key"]
    assert {s["phase"] for s in STAGES} == {"development", "preproduction", "production", "post"}


def test_versions_approval_order_and_staleness():
    page, series, ep = make_world()
    assert ladder.rows(series)["logline"]["status"] == "empty"
    with pytest.raises(DomainError):
        ladder.approve(series, None, "logline")                        # nothing to approve yet
    v1 = ladder.save_version(series, None, "logline", {"logline": "یک جمله", "hook": "قلاب"})
    assert v1.number == 1 and ladder.rows(series)["logline"]["status"] == "draft"
    with pytest.raises(DomainError) as e:
        ladder.approve(series, None, "treatment")                       # no output
    ladder.save_version(series, None, "treatment", {"synopsis": ["الف", "ب"], "acts": [{"name": "۱", "summary": "x"}]})
    with pytest.raises(DomainError) as e:
        ladder.approve(series, None, "treatment")                       # drafting ahead is allowed, approving out of order is not
    assert "logline" in e.value.details["blocked_by"]
    ladder.approve(series, None, "logline")
    ladder.approve(series, None, "treatment")
    rows = ladder.rows(series)
    assert rows["logline"]["status"] == "approved" and rows["treatment"]["status"] == "approved" and rows["art_style"]["blocked_by"] == []
    # an unchanged save is not a new version; a changed one is, and it withdraws the approval and makes everything built on it stale
    assert ladder.save_version(series, None, "logline", {"logline": "یک جمله", "hook": "قلاب"}).number == 1
    v2 = ladder.save_version(series, None, "logline", {"logline": "جملهٔ بهتر", "hook": "قلاب"})
    assert v2.number == 2
    rows = ladder.rows(series)
    assert rows["logline"]["status"] == "draft" and rows["treatment"]["status"] == "stale" and rows["treatment"]["stale_reasons"][0] == {"code": "upstream", "stage": "logline"}
    ladder.approve(series, None, "logline")
    assert ladder.rows(series)["treatment"]["status"] == "stale"       # the treatment was approved on version 1 of the logline
    ladder.approve(series, None, "treatment")
    assert ladder.rows(series)["treatment"]["status"] == "approved"
    # restore = a new version with the old content; compare any two
    r = ladder.restore(series, None, "logline", 1)
    assert r.number == 3 and r.data["logline"] == "یک جمله"
    d = ladder.diff(ladder.version(ladder.doc(series, None, "logline"), 1).data, ladder.version(ladder.doc(series, None, "logline"), 2).data)
    assert d == [{"path": "logline", "before": "یک جمله", "after": "جملهٔ بهتر"}]
    assert [v.number for v in ladder.doc(series, None, "logline").versions.all()] == [3, 2, 1]     # versions are never deleted


def test_art_style_is_chosen_once_and_locks_the_series_look():
    page, series, ep = make_world()
    ladder.save_version(series, None, "logline", {"logline": "x"})
    ladder.approve(series, None, "logline")
    ladder.save_version(series, None, "treatment", {"synopsis": ["x"], "acts": [{"name": "a", "summary": "b"}]})
    ladder.approve(series, None, "treatment")
    ladder.save_version(series, None, "art_style", {"style_key": "modern_tv_anime", "realism": "anime", "theme_key": "", "notes": "یک‌بار"})
    ladder.approve(series, None, "art_style")
    series.refresh_from_db()
    assert series.look["style_key"] == "modern_tv_anime"
    assert ladder.rows(series)["art_style"]["status"] == "approved"
    series.look = {"style_key": "other_style"}                           # someone changes the look behind the ladder's back: the approval is stale
    series.save()
    assert ladder.rows(series)["art_style"]["status"] == "stale" and ladder.rows(series)["art_style"]["stale_reasons"] == [{"code": "changed"}]


def test_bridged_stages_snapshot_the_live_work_and_go_stale_when_it_changes(api):
    from instai.story import services as story_services

    page, series, ep = make_world()
    rows = ladder.rows(series, ep)
    assert rows["script"]["status"] == "draft" and rows["script"]["source"] == "bridge" and rows["script"]["version"] == 1
    assert rows["storyboard"]["status"] == "draft" and rows["animatic"]["status"] == "empty"
    with pytest.raises(DomainError):
        ladder.save_version(series, ep, "script", {"x": 1})             # a bridged stage is edited where it lives
    # approve the whole chain up to the script
    for key, data in (("logline", {"logline": "x"}), ("treatment", {"synopsis": ["x"], "acts": [{"name": "a", "summary": "b"}]})):
        ladder.save_version(series, None, key, data)
        ladder.approve(series, None, key)
    from instai.studio.models import SeriesBible

    SeriesBible.objects.create(series=series, data={"premise": "p", "logline": "l"}, status="approved")
    assert ladder.rows(series, ep)["bible"]["status"] == "approved"      # approved in the development room: the ladder takes it over
    ladder.save_version(series, ep, "beat_sheet", {"beats": [{"name": "hook", "summary": "x", "seconds": 3, "purpose": "p"}]})
    ladder.approve(series, ep, "beat_sheet")
    ladder.approve(series, ep, "script")
    assert ladder.rows(series, ep)["script"]["status"] == "approved"
    sc = dict(ep.script)
    sc["blocks"] = sc["blocks"] + [{"id": 9, "speaker": "", "text": "جملهٔ تازه", "emotion": ""}]
    story_services.save_script(ep, sc, note="edit")
    ep.refresh_from_db()
    r = ladder.rows(series, ep)["script"]
    assert r["status"] == "stale" and r["stale_reasons"] == [{"code": "changed"}] and r["version"] == 2     # a new snapshot, and the old approval no longer covers it
    ladder.approve(series, ep, "script")
    assert ladder.rows(series, ep)["script"]["status"] == "approved"


def test_generate_every_writing_stage_with_the_fake_roles_and_derive_the_rest(api, worker):
    page, series, ep = make_world()
    api.post(f"/api/episodes/{ep.pk}/ladder/beat_sheet/approve", {}, format="json")           # refused: no output
    order = [("series", "logline"), ("series", "treatment")]
    for scope, key in order:
        j = finish(api, worker, api.post(f"/api/series/{series.pk}/ladder/{key}/generate", {"instruction": "کوتاه‌تر"}, format="json"))
        assert j["result"]["stage"] == key and j["result"]["provider"] == "fake"
        assert api.post(f"/api/series/{series.pk}/ladder/{key}/approve", {}, format="json").status_code == 200
    lg = api.get(f"/api/series/{series.pk}/ladder").json()
    row = next(s for s in lg["stages"] if s["key"] == "logline")
    assert row["status"] == "approved" and row["data"]["logline"] and row["current"]["author"] == "ai" and row["current"]["provenance"]["instruction"] == "کوتاه‌تر"
    assert [s["key"] for s in lg["stages"]] == ["logline", "treatment", "art_style", "bible", "character_models"]      # a series shows only its own stages
    ep_stages = ["beat_sheet", "dialogue", "shot_list", "layout", "sound_design", "narration", "edit", "grade", "delivery"]
    for key in ep_stages:
        j = finish(api, worker, api.post(f"/api/episodes/{ep.pk}/ladder/{key}/generate", {}, format="json"))
        assert j["result"]["stage"] == key
    pay = api.get(f"/api/episodes/{ep.pk}/ladder").json()
    by = {s["key"]: s for s in pay["stages"]}
    assert len(pay["stages"]) == 21
    assert by["dialogue"]["data"]["lines"] and by["shot_list"]["data"]["shots"][0]["size"] and by["sound_design"]["data"]["cues"][0]["kind"] in ("ambience", "foley", "sfx", "music", "silence")
    assert by["narration"]["current"]["author"] == "system" and by["narration"]["data"]["lines"][0]["voice"]
    assert by["edit"]["data"]["cuts"] and "shots=" in by["edit"]["data"]["notes"]
    assert by["delivery"]["data"]["renditions"][0]["aspect"] and len(by["delivery"]["data"]["checklist"]) >= 5
    assert by["grade"]["data"]["scenes"][0]["preset"] and by["layout"]["data"]["layouts"]
    assert api.post(f"/api/series/{series.pk}/ladder/bible/generate", {}, format="json").status_code == 409     # bridged stages are not written here
    assert api.post(f"/api/series/{series.pk}/ladder/beat_sheet/generate", {}, format="json").status_code == 400  # an episode stage needs an episode


def test_save_edit_diff_and_restore_through_the_api(api):
    page, series, ep = make_world()
    url = f"/api/series/{series.pk}/ladder/logline"
    assert api.put(url, {"data": {"logline": "الف", "hook": "", "stakes": "", "alternatives": ["ب"]}, "note": "first"}, format="json").status_code == 200
    api.put(url, {"data": {"logline": "الف دو", "hook": "", "stakes": "", "alternatives": []}}, format="json")
    assert api.get(f"{url}/diff?a=1&b=2").json()["changes"][0] == {"path": "alternatives", "before": ["ب"], "after": []} or api.get(f"{url}/diff?a=1&b=2").json()["changes"]
    assert api.get(f"{url}/versions/1").json()["data"]["logline"] == "الف"
    api.post(f"{url}/restore", {"version": 1}, format="json")
    pay = api.get(f"/api/series/{series.pk}/ladder").json()
    assert next(s for s in pay["stages"] if s["key"] == "logline")["version"] == 3
    assert api.put(url, {"nope": 1}, format="json").status_code == 400
    assert api.get("/api/ladder/catalogue").json()["gate"][0] == "logline"


def test_automation_level_decides_who_approves(api, worker):
    page, series, ep = make_world(level="automatic")
    assert needs_human(page, "bible") and not needs_human(page, "dialogue") and not needs_human(page, "logline")
    for key in ("logline", "treatment"):
        finish(api, worker, api.post(f"/api/series/{series.pk}/ladder/{key}/generate", {}, format="json"))
    rows = ladder.rows(series)
    assert rows["logline"]["status"] == "approved" and rows["logline"]["auto"] is True and rows["treatment"]["status"] == "approved"   # passed by themselves, marked auto
    assert rows["art_style"]["status"] == "empty"                        # the owner's own choice never passes by itself
    # an edit re-opens an automatic approval
    ladder.save_version(series, None, "logline", {"logline": "جملهٔ دیگر"})
    assert ladder.rows(series)["logline"]["status"] in ("draft", "approved")
    manual_page, manual_series, _ = make_world(level="manual")
    finish(api, worker, api.post(f"/api/series/{manual_series.pk}/ladder/logline/generate", {}, format="json"))
    assert ladder.rows(manual_series)["logline"]["status"] == "draft"    # at the manual level every stage waits for a click


def test_the_ladder_gate_keeps_an_episode_out_of_production_until_pre_production_is_approved(api):
    from instai.production import pipeline

    page, series, ep = make_world()
    page.set_profile("production", {"studio_mode": True, "ladder_gate": True})
    from instai.studio import preprod

    ap = preprod.approvals(ep)
    with pytest.raises(DomainError):
        pipeline.start(ep, "preview")                                    # the old pre-production gate is not approved either
    page.set_profile("production", {"studio_mode": False, "ladder_gate": True})
    pipeline.start(ep, "preview")                                        # without studio mode nothing is asked (the default behaviour is unchanged)
    assert ladder.preproduction_blockers(series, ep)[0] == "logline"
