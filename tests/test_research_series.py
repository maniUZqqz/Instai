"""Real-series lookup: AniList / Wikipedia / Fandom / Jikan parsing with canned answers (no internet), failure handling, and the What-If chain
(source search -> canon research -> ideas -> map -> bible -> composition -> episode -> animatic) with the HTTP layer mocked."""
from __future__ import annotations

import pytest
import requests

from instai import research_series as rs
from tests.conftest import finish
from tests.test_studio import dev, make_page, make_series, run_job, step

ANILIST_SEARCH = {"data": {"Page": {"media": [
    {"id": 113415, "title": {"romaji": "Sample Kaisen", "english": "Sample Sorcery", "native": "サンプル"}, "seasonYear": 2020, "format": "TV", "episodes": 24, "status": "FINISHED",
     "genres": ["Action", "Fantasy"], "averageScore": 86, "description": "A boy joins a school.<br><br>(Source: Somewhere)", "coverImage": {"large": "https://img/x.jpg"},
     "siteUrl": "https://anilist.co/anime/113415"},
    {"id": 2, "title": {"romaji": "Other Show", "english": None, "native": None}, "seasonYear": 2010, "format": "TV", "episodes": 12, "status": "FINISHED", "genres": [],
     "averageScore": 50, "description": None, "coverImage": None, "siteUrl": None}]}}}
ANILIST_DETAIL = {"data": {"Media": {"id": 113415, "title": {"romaji": "Sample Kaisen", "english": "Sample Sorcery", "native": None}, "seasonYear": 2020, "format": "TV", "episodes": 24,
                                      "status": "FINISHED", "genres": ["Action"], "description": "<i>Plot</i> text of the sample.", "siteUrl": "https://anilist.co/anime/113415",
                                      "characters": {"edges": [{"role": "MAIN", "node": {"name": {"full": "Arta Sample"}, "description": "A brave <b>boy</b>."}},
                                                               {"role": "SUPPORTING", "node": {"name": {"full": "Nila Sample"}, "description": None}}]},
                                      "relations": {"edges": [{"relationType": "ADAPTATION", "node": {"title": {"romaji": "Sample Manga"}, "format": "MANGA"}}]}}}}
WIKI_SEARCH = {"query": {"search": [{"title": "Sample Sorcery", "snippet": "a <span>2020</span> series"}]}}
WIKI_TEXT = "Sample Sorcery is a series.\n\n== Premise ==\nA boy joins a school of sorcerers.\n\n== Production ==\nMade by a studio.\n\n== Characters ==\nArta is brave.\n\n== Reception ==\nLoved."
WIKI_EXTRACT = {"query": {"pages": [{"title": "Sample Sorcery", "extract": WIKI_TEXT}]}}
FANDOM_SEARCH = {"query": {"search": [{"title": "Arta", "snippet": "the hero"}]}}
FANDOM_PAGE = {"query": {"pages": [{"title": "Arta", "revisions": [{"slots": {"main": {"content": "{{Infobox|a=b}}'''Arta''' is the [[Hero|hero]].<ref>x</ref> [[File:a.png]]\n\nHe is brave."}}}]}]}}


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        if self._d is None:
            raise ValueError("no json")
        return self._d


def fake_http(monkeypatch, *, anilist=True, wiki=True, fandom=True):
    def post(url, **kw):
        if "anilist" in url:
            if not anilist:
                raise requests.ConnectionError("blocked")
            return Resp(ANILIST_DETAIL if "Media(id" in kw["json"]["query"] else ANILIST_SEARCH)
        raise AssertionError(url)

    def get(url, **kw):
        p = kw.get("params") or {}
        if "wikipedia" in url:
            if not wiki:
                raise requests.ConnectionError("blocked")
            return Resp(WIKI_SEARCH if p.get("list") == "search" else WIKI_EXTRACT)
        if "fandom" in url:
            if not fandom:
                raise requests.ConnectionError("blocked")
            return Resp(FANDOM_SEARCH if p.get("list") == "search" else FANDOM_PAGE)
        raise AssertionError(url)

    monkeypatch.setattr(rs, "http_post", post)
    monkeypatch.setattr(rs, "http_get", get)


def test_anilist_search_and_material_parse(monkeypatch):
    fake_http(monkeypatch)
    res = rs.search_series("Sample", ["anilist"])
    c = res["candidates"][0]
    assert c["provider"] == "anilist" and c["title"] == "Sample Sorcery" and c["year"] == 2020 and c["episodes"] == 24 and "<br" not in c["description"]
    assert res["errors"] == [] and res["candidates"][1]["title"] == "Other Show"
    mat = rs.fetch_material(c, extra_wikipedia=False)["material"]
    assert [m["title"].split("(")[-1] for m in mat] == ["overview)", "characters)", "relations)"]
    assert "Arta Sample (main): A brave boy." in mat[1]["extract"] and "ADAPTATION: Sample Manga" in mat[2]["extract"] and all(m["verified"] for m in mat)


def test_wikipedia_sections_and_dedupe(monkeypatch):
    fake_http(monkeypatch)
    t = rs.wiki_sections(WIKI_TEXT)
    assert "Premise" in t and "Characters" in t and "Production" not in t and "Reception" not in t and t.startswith("Sample Sorcery is a series.")
    res = rs.search_series("Sample Sorcery", ["anilist", "wikipedia"])
    assert {c["provider"] for c in res["candidates"]} >= {"anilist"} and len([c for c in res["candidates"] if c["title"] == "Sample Sorcery"]) >= 1
    got = rs.fetch_material(res["candidates"][0])  # AniList candidate + the Wikipedia article for plot text
    pubs = [m["publisher"] for m in got["material"]]
    assert "AniList" in pubs and any("Wikipedia" in p and "CC BY-SA" in p for p in pubs) and got["errors"] == []


def test_fandom_wikitext_is_cleaned(monkeypatch):
    fake_http(monkeypatch)
    cand = rs.search_fandom("Arta", "sample-wiki")[0]
    assert cand["id"] == "sample-wiki|Arta" and "sample-wiki.fandom.com" in cand["url"]
    m = rs.material_fandom(cand)[0]
    assert m["extract"].startswith("Arta is the hero.") and "{{" not in m["extract"] and "<ref" not in m["extract"] and "File:" not in m["extract"]
    assert rs.search_series("x", ["fandom"])["errors"][0]["message"].startswith("Fandom: the wiki name is needed")


def test_failures_are_reported_never_raised(monkeypatch):
    fake_http(monkeypatch, anilist=False, wiki=False)
    r = rs.search_series("Sample", ["anilist", "wikipedia"])
    assert r["candidates"] == [] and len(r["errors"]) == 2 and all("blocked" in e["message"] for e in r["errors"])
    monkeypatch.setattr(rs, "http_post", lambda *a, **k: Resp({}, 429))
    assert "rate limit" in rs.search_series("x", ["anilist"])["errors"][0]["message"]
    monkeypatch.setattr(rs, "http_post", lambda *a, **k: Resp(None, 200))
    assert "unreadable" in rs.search_series("x", ["anilist"])["errors"][0]["message"]
    monkeypatch.setattr(rs, "http_post", lambda *a, **k: Resp({"errors": [{"message": "Too many"}]}))
    assert "Too many" in rs.search_series("x", ["anilist"])["errors"][0]["message"]
    assert rs.search_series("", ["anilist"]) == {"candidates": [], "errors": [], "tried": ["anilist"]}
    # one provider failing must not hide the other's answer
    fake_http(monkeypatch, anilist=False)
    r = rs.search_series("Sample Sorcery", ["anilist", "wikipedia"])
    assert r["candidates"] and r["errors"] and r["errors"][0]["provider"] == "anilist"


def test_jikan_is_off_by_default_and_parses_when_asked(monkeypatch):
    assert "jikan" not in rs.DEFAULT_PROVIDERS
    monkeypatch.setattr(rs, "http_get", lambda url, **kw: Resp({"data": [{"mal_id": 7, "title": "Sample Kaisen", "title_english": "Sample Sorcery", "year": 2020, "type": "TV", "episodes": 24,
                                                                         "status": "Finished Airing", "genres": [{"name": "Action"}], "synopsis": "Synopsis.", "score": 8.6,
                                                                         "url": "https://myanimelist.net/anime/7", "images": {"jpg": {"image_url": "https://i/x.jpg"}}}]}))
    c = rs.search_series("Sample", ["jikan"])["candidates"][0]
    assert c["provider"] == "jikan" and c["id"] == "7" and c["score"] == 0.86


@pytest.mark.django_db(transaction=True)
def test_whatif_chain_with_mocked_internet_to_animatic(api, worker, monkeypatch, ffmpeg_available):
    """What-If: search (AniList + Wikipedia, mocked) -> choose -> canon -> ideas -> approve -> map -> timeline -> bible -> approve -> composition ->
    approval -> episode script -> storyboard -> animatic. The bible's characters and the canon text reach the prompts of later steps."""
    from instai.core import settings_store
    from instai.providers.fake import FakeProvider
    from instai.providers.registry import use_provider

    fake_http(monkeypatch)
    settings_store.set_setting("research_fetch", "off")
    settings_store.set_setting("tts_engine", "fake")
    settings_store.set_setting("image_engine", "placeholder")
    page = make_page(api, "anime_whatif", "manual")
    s = make_series(api, page["id"], title="What if Arta stayed home")
    sid = s["id"]
    prov = FakeProvider()
    with use_provider(prov):
        j = run_job(api, worker, api.post(f"/api/series/{sid}/source/search", {"query": "Sample Sorcery", "providers": ["anilist", "wikipedia"], "language": "en"}, format="json"))
        cand = next(c for c in j["result"]["candidates"] if c["provider"] == "anilist")
        api.post(f"/api/series/{sid}/source", {"candidate": cand}, format="json")
        run_job(api, worker, api.post(f"/api/series/{sid}/research", {"mode": "canon", "language": "en"}, format="json"))
        d = dev(api, sid)
        assert {src["publisher"].split(" ")[0] for src in d["sources"]} >= {"AniList", "Wikipedia"}
        canon_call = next(c for c in prov.calls if c["task"] == "canon")
        assert any("Premise" in s_["extract"] for s_ in canon_call["meta"]["sources"]), "the Wikipedia plot section reached the researcher"
        run_job(api, worker, api.post(f"/api/series/{sid}/ideas/generate", {"board": "divergence", "language": "en"}, format="json"))
        idea = api.get(f"/api/series/{sid}/ideas?board=divergence").json()[0]
        assert "Premise" not in str(prov.calls[-1]["meta"].get("sources", ""))
        assert prov.calls[-1]["meta"]["canon"]["characters"], "the brainstorm sees the canon research"
        api.post(f"/api/ideas/{idea['id']}/status", {"status": "approved"}, format="json")
        for key, path in (("map", "map"), ("timeline", "timeline")):
            run_job(api, worker, api.post(f"/api/series/{sid}/dev/steps/{key}/generate", {"language": "en"}, format="json"))
        run_job(api, worker, api.post(f"/api/series/{sid}/bible/generate", {"language": "en"}, format="json"))
        bible_call = next(c for c in prov.calls if c["task"] == "bible")
        assert bible_call["meta"]["approved_ideas"] and bible_call["meta"]["map"] and bible_call["meta"]["timeline"] and bible_call["meta"]["canon"]
        api.post(f"/api/series/{sid}/bible/approve")
        j = run_job(api, worker, api.post(f"/api/series/{sid}/plan", {"episodes_count": 3}, format="json"))
        plan_call = next(c for c in prov.calls if c["task"] == "series_plan")
        assert plan_call["meta"]["bible"]["characters"], "the composition is built on the bible"
        api.post(f"/api/series/{sid}/apply-plan", {"plan": j["result"]["plan"]}, format="json")
        api.post(f"/api/series/{sid}/dev/steps/composition/status", {"status": "done"}, format="json")
        assert api.post(f"/api/series/{sid}/development/approve").json()["dev_status"] == "approved"
        ep = api.get(f"/api/series/{sid}/episodes").json()[0]["id"]
        run_job(api, worker, api.post(f"/api/episodes/{ep}/generate-script"))
        script_call = next(c for c in prov.calls if c["task"] == "script")
        assert script_call["meta"]["bible"] and script_call["meta"]["is_fan_content"] is True
        r = api.post(f"/api/episodes/{ep}/approve-script")
        finish(api, worker, type("R", (), {"status_code": 202, "content": b"", "json": lambda self: {"job": r.json()["job"]}})())
        run_job(api, worker, api.post(f"/api/episodes/{ep}/generate-storyboard"))
        j = run_job(api, worker, api.post(f"/api/episodes/{ep}/studio/animatic"))
    assert j["result"]["duration"] > 3
    st = api.get(f"/api/episodes/{ep}/studio").json()
    assert st["animatic"]["status"] == "fresh" and {x["key"]: x for x in st["report"]["stages"]}["animatic"]["status"] == "ready"
