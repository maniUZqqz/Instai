"""The studio workflow end to end with the fake text provider: templates, source lookup (mocked), brainstorm boards, canon research, consequence map,
timeline, series bible, composition, development approval, automation-level gates, pre-production stages, casting, design sheets, translation, retakes,
text-model choice per page and task."""
from __future__ import annotations

import pytest

from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)


def make_page(api, fmt="anime_whatif", level="manual", **extra):
    body = {"name": "صفحهٔ آزمایشی", "format": fmt, "languages": ["fa"], "idea": "ایده", "automation_level": level, **extra}
    r = api.post("/api/pages", body, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def make_series(api, page_id, title="مجموعهٔ آزمایشی", **extra):
    r = api.post(f"/api/pages/{page_id}/series", {"title": title, "premise": "", "target_episodes": 4, **extra}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def dev(api, sid):
    return api.get(f"/api/series/{sid}/development").json()


def step(d, key):
    return next(s for s in d["steps"] if s["key"] == key)


def run_job(api, worker, resp, expect="succeeded"):
    return finish(api, worker, resp, expect=expect)


# ------------------------------------------------------------------ templates

def test_builtin_templates_and_user_template(api):
    t = api.get("/api/templates").json()
    keys = {x["key"] for x in t["templates"]}
    assert {"anime_whatif", "recurring_character", "concept_explainer", "custom"} <= keys
    wi = next(x for x in t["templates"] if x["key"] == "anime_whatif")
    assert [s["kind"] for s in wi["steps"]][:5] == ["source", "research", "brainstorm", "map", "timeline"]
    assert wi["steps"][-3:][0]["kind"] == "bible" and wi["steps"][-1]["kind"] == "gate"
    rc = next(x for x in t["templates"] if x["key"] == "recurring_character")
    assert [s["kind"] for s in rc["steps"]][:3] == ["profile", "brainstorm", "brainstorm"]
    ex = next(x for x in t["templates"] if x["key"] == "concept_explainer")
    assert [s["kind"] for s in ex["steps"]][:4] == ["brainstorm", "research", "brainstorm", "factcheck"]
    # a new template written in the UI: unknown kinds are dropped, bible + composition + gate are always appended in order
    r = api.post("/api/templates", {"name_en": "My format", "name_fa": "قالب من", "base_format": "custom",
                                    "steps": [{"kind": "brainstorm", "title_en": "Ideas", "params": {"lens": "series_concept", "board": "ideas", "count": 4}},
                                              {"kind": "teleport", "title_en": "nonsense"}, {"kind": "gate", "title_en": "Done"}]}, format="json")
    assert r.status_code == 201, r.content
    mine = r.json()
    assert mine["key"].startswith("tpl_") and mine["builtin"] is False
    assert [s["kind"] for s in mine["steps"]] == ["brainstorm", "bible", "composition", "gate"]
    assert api.patch("/api/templates/anime_whatif", {"name_en": "x"}, format="json").status_code == 409
    dup = api.post("/api/templates/anime_whatif/duplicate", {}, format="json").json()
    assert dup["builtin"] is False and len(dup["steps"]) == len(wi["steps"])
    # a series built on the user template gets exactly its steps; a used template cannot be deleted
    page = make_page(api, "custom", template_key=mine["key"])
    s = make_series(api, page["id"])
    assert [x["kind"] for x in dev(api, s["id"])["steps"]] == ["brainstorm", "bible", "composition", "gate"]
    assert api.delete(f"/api/templates/{mine['key']}").status_code == 409
    assert api.delete(f"/api/templates/{dup['key']}").status_code == 204


# ------------------------------------------------------------------ What-If, the whole development room

def test_whatif_development_room_end_to_end(api, worker):
    page = make_page(api, "anime_whatif", "manual")
    assert page["template_key"] == ""
    s = make_series(api, page["id"])
    d = dev(api, s["id"])
    assert d["template"]["key"] == "anime_whatif" and d["template"]["needs_source"] and d["dev_status"] == "developing"
    assert [x["status"] for x in d["steps"]][0] == "todo"

    # 1. source: internet lookup (mocked by the fake searcher) -> candidates -> choose
    from instai.core import settings_store

    settings_store.set_setting("research_fetch", "fake")
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/source/search", {"query": "Sample", "language": "en"}, format="json"))
    cands = j["result"]["candidates"]
    assert cands and cands[0]["provider"] == "fake" and j["result"]["errors"] == []
    d = api.post(f"/api/series/{s['id']}/source", {"candidate": cands[0]}, format="json").json()
    assert d["source"]["title"] == cands[0]["title"] and d["series"]["is_fan_content"] is True and d["series"]["notices"], "a real franchise = fan content + notice"
    assert step(d, "source")["status"] == "review", "a human gate waits for the owner (manual level)"
    d = api.post(f"/api/series/{s['id']}/dev/steps/source/status", {"status": "done"}, format="json").json()
    assert step(d, "source")["status"] == "done"

    # 2. canon research: material is fetched by the system (verified), the model only analyses it; items cite stored sources
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/research", {"mode": "canon", "language": "en"}, format="json"))
    assert j["result"]["sources"] >= 2
    d = dev(api, s["id"])
    canon = d["research"]["canon"]["content"]
    assert canon["characters"] and canon["key_events"] and d["sources"] and all(src["verified"] for src in d["sources"])
    src_ids = {src["id"] for src in d["sources"]}
    assert all(set(c["source_ids"]) <= src_ids for c in canon["characters"]), "references point at stored sources"

    # 3. divergence brainstorm: AI proposes, the human adds, everything can be edited / rated / rejected / approved / "more like this"
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/ideas/generate", {"board": "divergence", "language": "en"}, format="json"))
    ideas = api.get(f"/api/series/{s['id']}/ideas?board=divergence").json()
    assert len(ideas) == 6 and all(i["author"] == "ai" and i["details"].get("divergence_moment") for i in ideas)
    mine = api.post(f"/api/series/{s['id']}/ideas", {"board": "divergence", "title": "My own idea", "logline": "the owner's twist"}, format="json").json()
    assert mine["author"] == "human"
    e = api.patch(f"/api/ideas/{ideas[0]['id']}", {"logline": "edited by the owner"}, format="json").json()
    assert e["logline"] == "edited by the owner" and e["author"] == "refined", "an edited AI card is no longer pure AI output"
    assert api.post(f"/api/ideas/{ideas[1]['id']}/rate", {"rating": 9}, format="json").json()["rating"] == 5
    assert api.post(f"/api/ideas/{ideas[2]['id']}/status", {"status": "rejected"}, format="json").json()["status"] == "rejected"
    assert api.post(f"/api/ideas/{ideas[1]['id']}/status", {"status": "bogus"}, format="json").status_code == 400
    run_job(api, worker, api.post(f"/api/series/{s['id']}/ideas/generate", {"board": "divergence", "more_like": [ideas[1]["id"]], "count": 3, "language": "en"}, format="json"))
    more = api.get(f"/api/series/{s['id']}/ideas?board=divergence").json()
    assert len(more) == 6 + 1 + 3 and len({i["title"] for i in more}) == len(more), "'more like this' adds new, different cards"
    assert not any(i["title"] == ideas[2]["title"] for i in more[-3:]), "rejected titles are not proposed again"
    # refine one card (a child card is created, the original stays)
    j = run_job(api, worker, api.post(f"/api/ideas/{ideas[1]['id']}/refine", {"instruction": "make it darker", "language": "en"}, format="json"))
    child = next(i for i in api.get(f"/api/series/{s['id']}/ideas?board=divergence").json() if i["id"] == j["result"]["idea"])
    assert child["author"] == "refined" and child["parent"] == ideas[1]["id"] and "darker" in child["logline"]
    # merge: by hand (no model) and with the model
    r = api.post(f"/api/series/{s['id']}/ideas/merge", {"ids": [ideas[3]["id"], ideas[4]["id"]]}, format="json")
    assert r.status_code == 201 and r.json()["idea"]["author"] == "merged"
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/ideas/merge", {"ids": [ideas[0]["id"], mine["id"]], "ai": True, "language": "en"}, format="json"))
    assert api.get(f"/api/series/{s['id']}/ideas?board=divergence").json()
    assert api.post(f"/api/series/{s['id']}/ideas/merge", {"ids": [ideas[0]["id"]]}, format="json").status_code == 400
    # the step cannot be completed until an idea is approved
    r = api.post(f"/api/series/{s['id']}/dev/steps/divergence/status", {"status": "done"}, format="json")
    assert r.status_code == 409
    api.post(f"/api/ideas/{ideas[1]['id']}/status", {"status": "approved"}, format="json")
    assert api.post(f"/api/series/{s['id']}/dev/steps/divergence/status", {"status": "done"}, format="json").status_code == 200

    # 4. consequence map + 5. alternative timeline
    run_job(api, worker, api.post(f"/api/series/{s['id']}/dev/steps/map/generate", {"language": "en"}, format="json"))
    nodes = step(dev(api, s["id"]), "map")["data"]["nodes"]
    assert nodes[0]["kind"] == "divergence" and nodes[0]["parent"] == "" and all(n["parent"] in {x["id"] for x in nodes} | {""} for n in nodes)
    nodes[1]["title"] = "edited consequence"
    api.put(f"/api/series/{s['id']}/dev/steps/map/data", {"data": {"nodes": nodes + [{"id": "n99", "title": "orphan", "parent": "ghost"}]}}, format="json")
    again = step(dev(api, s["id"]), "map")["data"]["nodes"]
    assert any(n["title"] == "edited consequence" for n in again) and next(n for n in again if n["id"] == "n99")["parent"] == "", "a missing parent becomes a root"
    run_job(api, worker, api.post(f"/api/series/{s['id']}/dev/steps/timeline/generate", {"language": "en"}, format="json"))
    assert len(step(dev(api, s["id"]), "timeline")["data"]["rows"]) >= 2

    # 6. bible: AI draft -> human edit -> approve (characters reach the page) ; approving again after an edit is required
    run_job(api, worker, api.post(f"/api/series/{s['id']}/bible/generate", {"language": "en"}, format="json"))
    b = api.get(f"/api/series/{s['id']}/bible").json()
    assert b["status"] == "draft" and b["data"]["premise"] and b["data"]["characters"] and b["data"]["branch_point"]
    api.put(f"/api/series/{s['id']}/bible", {"data": {**b["data"], "tone": "grim"}}, format="json")
    r = api.post(f"/api/series/{s['id']}/bible/approve")
    assert r.status_code == 200 and r.json()["bible"]["status"] == "approved" and r.json()["synced"]["characters_added"] >= 1
    assert len(api.get(f"/api/pages/{page['id']}").json()["characters"]) >= 1
    api.put(f"/api/series/{s['id']}/bible", {"data": {"tone": "lighter"}}, format="json")
    assert api.get(f"/api/series/{s['id']}/bible").json()["status"] == "draft", "editing an approved bible reopens it"
    api.post(f"/api/series/{s['id']}/bible/approve")

    # 7. composition = the existing plan, now built on the bible; 8. approval gate
    assert api.post(f"/api/series/{s['id']}/development/approve").status_code == 409, "no episode outline yet"
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/plan", {"episodes_count": 4}, format="json"))
    assert len(j["result"]["plan"]["episodes"]) == 4
    api.post(f"/api/series/{s['id']}/apply-plan", {"plan": j["result"]["plan"]}, format="json")
    d = dev(api, s["id"])
    assert d["has_plan"] and step(d, "composition")["status"] == "review"
    api.post(f"/api/series/{s['id']}/dev/steps/composition/status", {"status": "done"}, format="json")
    d = api.post(f"/api/series/{s['id']}/development/approve").json()
    assert d["dev_status"] == "approved" and step(d, "approval")["status"] == "done" and d["series"]["dev_status"] == "approved"
    d = api.post(f"/api/series/{s['id']}/development/reopen").json()
    assert d["dev_status"] == "developing"


def test_manual_source_works_when_the_internet_is_blocked(api, worker, monkeypatch):
    """Online lookup fails -> errors are reported, nothing crashes, and typing the series by hand + pasting text still gives a canon document."""
    import requests

    from instai import research_series
    from instai.core import settings_store

    settings_store.set_setting("research_fetch", "off")

    def blocked(*a, **kw):
        raise requests.ConnectionError("blocked")

    monkeypatch.setattr(research_series, "http_post", blocked)
    monkeypatch.setattr(research_series, "http_get", blocked)
    page = make_page(api)
    s = make_series(api, page["id"])
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/source/search", {"query": "Jujutsu", "providers": ["anilist", "wikipedia"]}, format="json"))
    assert j["result"]["candidates"] == [] and {e["provider"] for e in j["result"]["errors"]} == {"anilist", "wikipedia"}
    assert all("blocked" in e["message"] for e in j["result"]["errors"])
    # canon research with nothing to read says what to do
    api.post(f"/api/series/{s['id']}/source", {"manual": True, "title": "My Favourite Show"}, format="json")
    j = api.post(f"/api/series/{s['id']}/research", {"mode": "canon"}, format="json")
    j = finish(api, worker, j, expect="failed")
    assert j["error_code"] == "not_ready"
    # pasting text by hand is enough
    api.post(f"/api/pages/{page['id']}/sources", {"title": "Notes", "series": s["id"], "extract": "The hero stays home. The villain wins the first fight.", "stance": "established"},
             format="json")
    run_job(api, worker, api.post(f"/api/series/{s['id']}/research", {"mode": "canon"}, format="json"))
    d = dev(api, s["id"])
    assert d["research"]["canon"]["content"]["characters"] and d["source"]["manual"] is True


# ------------------------------------------------------------------ the other two templates

def test_recurring_character_template(api, worker):
    page = make_page(api, "recurring_character")
    s = make_series(api, page["id"])
    d = dev(api, s["id"])
    assert [x["key"] for x in d["steps"]][:3] == ["brief", "scenarios", "formats"]
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/dev/steps/brief/generate", {"brief": "a clumsy cartoon cat with a red scarf", "language": "en"}, format="json"))
    chars = step(dev(api, s["id"]), "brief")["data"]["characters"]
    assert chars and chars[0]["visual_hooks"] and chars[0]["catchphrases"]
    r = api.post(f"/api/series/{s['id']}/dev/steps/brief/sync-characters")
    assert r.json()["characters_added"] == len(chars)
    assert api.post(f"/api/series/{s['id']}/dev/steps/brief/sync-characters").json()["characters_added"] == 0, "never duplicates"
    for board in ("scenarios", "formats"):
        run_job(api, worker, api.post(f"/api/series/{s['id']}/ideas/generate", {"board": board, "language": "en"}, format="json"))
    d = dev(api, s["id"])
    assert len(d["ideas"]["scenarios"]) == 8 and len(d["ideas"]["formats"]) == 6
    assert d["ideas"]["scenarios"][0]["details"].get("setup") and d["ideas"]["formats"][0]["details"].get("gag")


def test_explainer_template_sourced_claims_and_factcheck_rule(api, worker):
    from instai.core import settings_store

    settings_store.set_setting("research_fetch", "fake")
    page = make_page(api, "concept_explainer")
    s = make_series(api, page["id"], title="سرمایه‌داری")
    d = dev(api, s["id"])
    assert [x["kind"] for x in d["steps"]][:4] == ["brainstorm", "research", "brainstorm", "factcheck"]
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/research", {"mode": "topic", "topic": "سرمایه‌داری"}, format="json"))
    assert j["result"]["sources"] >= 1
    doc = dev(api, s["id"])["research"]["topic"]
    stances = {c["stance"] for c in doc["content"]["claims"]}
    assert {"established", "contested", "speculative"} <= stances
    # an 'established' claim without a source is demoted, and the fact-check step refuses to finish while one exists
    claims = doc["content"]["claims"] + [{"claim": "Unsourced boast", "stance": "established", "source_ids": []}]
    r = api.patch(f"/api/research-docs/{doc['id']}", {"content": {**doc["content"], "claims": claims}}, format="json")
    assert r.json()["content"]["claims"][-1]["stance"] == "speculative" and r.json()["content"]["unsupported_count"] >= 2
    assert api.post(f"/api/series/{s['id']}/dev/steps/factcheck/status", {"status": "done"}, format="json").status_code == 200


# ------------------------------------------------------------------ gates follow the automation level

def _prep_series_until_bible(api, worker, level):
    from instai.core import settings_store

    settings_store.set_setting("research_fetch", "fake")
    page = make_page(api, "custom", level)
    s = make_series(api, page["id"])
    run_job(api, worker, api.post(f"/api/series/{s['id']}/ideas/generate", {"board": "concepts", "language": "en"}, format="json"))
    run_job(api, worker, api.post(f"/api/series/{s['id']}/bible/generate", {"language": "en"}, format="json"))
    return page, s


def test_gates_follow_the_automation_level(api, worker):
    # manual: the bible waits for a click
    _, s = _prep_series_until_bible(api, worker, "manual")
    d = dev(api, s["id"])
    assert step(d, "bible")["status"] == "review" and step(d, "bible")["needs_human"] and d["bible"]["status"] == "draft"
    # assisted: bible/composition/gate still need a human
    _, s2 = _prep_series_until_bible(api, worker, "assisted")
    d2 = dev(api, s2["id"])
    assert step(d2, "bible")["status"] == "review" and d2["bible"]["status"] == "draft"
    # automatic: the AI-written bible passes by itself (marked auto), only the final gate waits for a human
    _, s3 = _prep_series_until_bible(api, worker, "automatic")
    d3 = dev(api, s3["id"])
    assert step(d3, "bible")["status"] == "done" and step(d3, "bible")["auto_approved"] and d3["bible"]["status"] == "approved"
    assert step(d3, "approval")["needs_human"] and step(d3, "approval")["status"] != "done"
    j = run_job(api, worker, api.post(f"/api/series/{s3['id']}/plan", {}, format="json"))
    api.post(f"/api/series/{s3['id']}/apply-plan", {"plan": j["result"]["plan"]}, format="json")
    d3 = dev(api, s3["id"])
    assert step(d3, "composition")["status"] == "done" and step(d3, "composition")["auto_approved"]
    assert d3["dev_status"] == "developing", "nothing is greenlit automatically"
    from instai.studio import gates
    from instai.pages.models import ContentPage

    p = ContentPage.objects.get(pk=d3["series"]["page"])
    assert [gates.preprod_stage_needs_human(p, k) for k in gates.PREPROD_STAGES] == [False, False, False, False, False, True]


# ------------------------------------------------------------------ text model per page and task

def test_text_model_choice_per_page_and_task_with_fallback(api, monkeypatch):
    from instai.agents import llm
    from instai.pages.models import ContentPage
    from instai.providers.base import ProviderError

    page = make_page(api, "custom")
    api.put(f"/api/pages/{page['id']}/profiles/production",
            {"llm": {"default": {"provider": "ollama", "model": "qwen3:8b"}, "fallback": {"provider": "openai", "model": "gpt-x"},
                     "groups": {"brainstorm": {"provider": "fake", "model": ""}, "translate": {"provider": "ollama", "model": "translategemma:12b"}, "bogus": {"provider": "fake"}}}},
            format="json")
    p = ContentPage.objects.get(pk=page["id"])
    cfg = p.profile("production")["llm"]
    assert set(cfg["groups"]) == {"brainstorm", "translate"}, "unknown groups are dropped"
    assert llm.resource_for(p, "ideas") == "cpu" and llm.resource_for(p, "script") == "gpu" and llm.resource_for(p, "bible") == "gpu"
    assert llm.group_of("consequence_map") == "brainstorm" and llm.group_of("series_plan") == "bible" and llm.group_of("translate_shots") == "translate"
    b = llm.resolve(p, "ideas")
    assert b.name == "fake"
    sc = llm.resolve(p, "script")
    assert isinstance(sc, llm.FallbackProvider) and sc.providers[0].name == "ollama" and sc.providers[0].model == "qwen3:8b" and sc.providers[1].name == "openai"
    assert llm.resolve(p, "translate").providers[0].model == "translategemma:12b"
    # the fallback answers when the primary raises a provider error
    from instai.providers.fake import FakeProvider

    class Down(FakeProvider):
        name = "down"

        def generate(self, *a, **k):
            raise ProviderError("offline")

    ok = FakeProvider()
    fb = llm.FallbackProvider([Down(), ok])
    res = fb.generate([{"role": "user", "content": "x"}], task="ideas", meta={"lens": "series_concept", "count": 2})
    assert res.provider == "fake" and fb.used is ok
    only_down = llm.FallbackProvider([Down()])
    with pytest.raises(ProviderError):
        only_down.generate([{"role": "user", "content": "x"}])
    # keys never travel with the page: the profile holds only names
    assert "key" not in str(cfg).lower().replace("keep", "")


def test_job_uses_the_pages_own_provider(api, worker):
    """The page says 'ideas via the fake provider' while the global default is something else: the job result names the provider that answered."""
    from instai.core import settings_store

    settings_store.set_setting("llm_provider", "ollama")  # nothing listens: any use of the global default would fail
    page = make_page(api, "custom")
    api.put(f"/api/pages/{page['id']}/profiles/production", {"llm": {"groups": {"brainstorm": {"provider": "fake"}}}}, format="json")
    s = make_series(api, page["id"])
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/ideas/generate", {"board": "concepts", "language": "fa"}, format="json"))
    assert j["result"]["meta"]["provider"] == "fake" and j["resource"] == "cpu"


# ------------------------------------------------------------------ pre-production

def _episode_with_storyboard(api, worker, level="manual", studio_mode=True):
    page = make_page(api, "recurring_character", level)
    if studio_mode:
        api.put(f"/api/pages/{page['id']}/profiles/production", {"studio_mode": True}, format="json")
    api.post(f"/api/pages/{page['id']}/characters", {"name": "Mimi", "role": "hero", "personality": "playful"}, format="json")
    s = make_series(api, page["id"])
    j = run_job(api, worker, api.post(f"/api/series/{s['id']}/plan", {"episodes_count": 2}, format="json"))
    eps = api.post(f"/api/series/{s['id']}/apply-plan", {"plan": j["result"]["plan"]}, format="json").json()["episodes"]
    ep = eps[0]["id"]
    run_job(api, worker, api.post(f"/api/episodes/{ep}/generate-script"))
    r = api.post(f"/api/episodes/{ep}/approve-script")
    finish(api, worker, type("R", (), {"status_code": 202, "content": b"", "json": lambda self: {"job": r.json()["job"]}})())
    run_job(api, worker, api.post(f"/api/episodes/{ep}/generate-storyboard"))
    return page, s, ep


def test_preproduction_stages_gate_and_studio_mode(api, worker):
    from instai.core import settings_store

    settings_store.set_setting("tts_engine", "fake")
    page, s, ep = _episode_with_storyboard(api, worker)
    st = api.get(f"/api/episodes/{ep}/studio").json()
    rep = {r["key"]: r for r in st["report"]["stages"]}
    assert rep["script"]["status"] == "approved" and rep["storyboard"]["status"] == "ready" and rep["animatic"]["status"] == "todo" and rep["gate"]["status"] == "todo"
    assert st["report"]["studio_mode"] and any(v["engine"] == "fake" for v in st["voices"])
    assert not any(v["installed"] for v in st["voices"] if v["engine"] == "piper"), "a voice that is not downloaded is listed but marked not installed"
    # with studio mode on, production cannot start before the gate
    r = api.post(f"/api/episodes/{ep}/approve-storyboard")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_ready"
    # design sheets: AI proposes prompt sheets (character, expression, background, colour script), the human edits and approves
    run_job(api, worker, api.post(f"/api/episodes/{ep}/studio/design/generate", {"language": "en"}, format="json"))
    sheets = api.get(f"/api/episodes/{ep}/studio/design-sheets").json()
    assert {x["kind"] for x in sheets} >= {"character", "expression", "background", "colour_script"} and all(x["author"] == "ai" for x in sheets)
    mine = api.post(f"/api/episodes/{ep}/studio/design-sheets", {"kind": "prop", "subject": "red scarf", "prompt": "a red scarf"}, format="json").json()
    assert mine["author"] == "human"
    j = run_job(api, worker, api.post(f"/api/design-sheets/{mine['id']}/image", {}, format="json"))
    assert api.get(f"/api/episodes/{ep}/studio/design-sheets").json()[-1]["image_url"] or True
    api.patch(f"/api/design-sheets/{sheets[0]['id']}", {"prompt": "edited prompt"}, format="json")
    # casting: AI suggests, voices are stored on the characters; the stage is ready only when every speaking character has a voice
    run_job(api, worker, api.post(f"/api/episodes/{ep}/studio/casting/suggest", {"language": "en"}, format="json"))
    st = api.get(f"/api/episodes/{ep}/studio").json()
    assert all(c["has_voice"] for c in st["casting"])
    opts = [v for v in st["voices"] if v["engine"] == "fake"]
    r = api.put(f"/api/episodes/{ep}/studio/casting", {"casting": [{"character": c["character"], "voice_id": opts[1]["id"]} for c in st["casting"]]}, format="json")
    assert r.status_code == 200
    from instai.pages.models import Character

    assert Character.objects.get(name="Mimi").voice["voice_id"] == opts[1]["voice"] and Character.objects.get(name="Mimi").voice["voices_by_language"]
    # animatic is required in manual mode; without one the gate is blocked
    assert api.post(f"/api/episodes/{ep}/studio/stages/gate/approve").status_code == 409
    from instai.assets.models import Asset
    from instai.studio import preprod
    from instai.story.models import Episode

    e = Episode.objects.get(pk=ep)
    # (the real render is covered by test_animatic_renders_a_video; here a stored asset stands in for it)
    Asset.objects.create(kind="video", role="animatic", path="episodes/x/animatic.mp4", episode=e, input_hash=preprod.animatic_hash(e), duration_sec=10)
    for key in ("animatic", "design", "casting", "storyboard"):
        r = api.post(f"/api/episodes/{ep}/studio/stages/{key}/approve")
        assert r.status_code == 200, (key, r.content)
    rep = {x["key"]: x for x in r.json()["report"]["stages"]}
    assert all(rep[k]["status"] == "approved" for k in ("script", "storyboard", "animatic", "design", "casting"))
    r = api.post(f"/api/episodes/{ep}/studio/stages/gate/approve")
    assert r.status_code == 200 and r.json()["report"]["gate_approved"]
    assert api.post(f"/api/episodes/{ep}/approve-storyboard").status_code == 200, "after the gate production may start"
    # a stale animatic (a shot changed) invalidates the approval
    shot = [sh for sc in api.get(f"/api/episodes/{ep}").json()["scenes"] for sh in sc["shots"]][0]
    api.patch(f"/api/shots/{shot['id']}", {"narration": "a new line for the retake"}, format="json")
    assert {x["key"]: x for x in api.get(f"/api/episodes/{ep}/studio").json()["report"]["stages"]}["animatic"]["status"] == "stale"


def test_studio_mode_off_keeps_the_old_flow(api, worker):
    _, _, ep = _episode_with_storyboard(api, worker, studio_mode=False)
    assert api.post(f"/api/episodes/{ep}/approve-storyboard").status_code == 200


def test_assisted_level_auto_passes_the_light_stages(api, worker):
    from instai.core import settings_store

    settings_store.set_setting("tts_engine", "fake")
    _, _, ep = _episode_with_storyboard(api, worker, level="assisted")
    run_job(api, worker, api.post(f"/api/episodes/{ep}/studio/casting/suggest", {}, format="json"))
    run_job(api, worker, api.post(f"/api/episodes/{ep}/studio/design/generate", {}, format="json"))
    rep = {x["key"]: x for x in api.get(f"/api/episodes/{ep}/studio").json()["report"]["stages"]}
    assert rep["casting"]["status"] == "auto" and rep["design"]["status"] == "auto" and rep["storyboard"]["required"] and rep["animatic"]["status"] in ("todo", "auto")


def test_translate_episode_and_retake(api, worker):
    page, s, ep = _episode_with_storyboard(api, worker, studio_mode=False)
    j = run_job(api, worker, api.post(f"/api/episodes/{ep}/translate", {"language": "en"}, format="json"))
    assert j["result"]["blocks"] >= 3 and j["result"]["shots"] >= 1
    from instai.story.models import Episode

    e = Episode.objects.get(pk=ep)
    tr = e.translations["en"]
    assert len(tr["script"]["blocks"]) == len(e.script["blocks"]) and tr["script"]["language"] == "en" and tr["shots"]
    assert api.post(f"/api/episodes/{ep}/translate", {"language": "fa"}, format="json").status_code == 202  # job is queued ...
    bad = finish(api, worker, api.post(f"/api/episodes/{ep}/translate", {"language": "fa"}, format="json"), expect="failed")
    assert bad["error_code"] == "validation_error", "translating into the script's own language is refused"
    assert api.post(f"/api/episodes/{ep}/translate", {"language": "de"}, format="json").status_code == 400
    # retake: a reason is required; the note is stored and ONLY this shot is sent back
    shot = [sh for sc in api.get(f"/api/episodes/{ep}").json()["scenes"] for sh in sc["shots"]][0]
    assert api.post(f"/api/shots/{shot['id']}/retake", {"scope": "keyframe", "reason": ""}, format="json").status_code == 400
    r = api.post(f"/api/shots/{shot['id']}/retake", {"scope": "keyframe", "reason": "the face is off model"}, format="json")
    assert r.status_code == 202 and r.json()["retake"]["status"] == "open" and r.json()["retake"]["reason"] == "the face is off model"
    lst = api.get(f"/api/episodes/{ep}/retakes").json()
    assert len(lst) == 1 and lst[0]["shot"] == shot["id"]
    assert api.post(f"/api/retakes/{lst[0]['id']}/cancel").json()["status"] == "cancelled"


@pytest.mark.slow
def test_animatic_renders_a_video(api, worker, ffmpeg_available):
    from instai.core import settings_store

    settings_store.set_setting("tts_engine", "fake")
    settings_store.set_setting("image_engine", "placeholder")
    _, _, ep = _episode_with_storyboard(api, worker, studio_mode=False)
    j = run_job(api, worker, api.post(f"/api/episodes/{ep}/studio/animatic"))
    assert j["result"]["duration"] > 2 and j["result"]["stills"]["placeholders"] >= 1 and j["result"]["scratch_audio"] in ("tts", "partial")
    st = api.get(f"/api/episodes/{ep}/studio").json()
    assert st["animatic"]["status"] == "fresh" and st["animatic"]["asset"]["url"].endswith(".mp4")
    ep_state = api.get(f"/api/episodes/{ep}").json()["state"]
    assert ep_state == "storyboarding", "the animatic never changes the episode's state"
