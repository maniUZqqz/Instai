"""Interactive choice stories: the graph rules (no dead ends, forward numbering in posting order, reachable, placeholders), the planner, the editor operations,
approval, the pictures with the right numbers and the posting package."""
from __future__ import annotations

import io
import zipfile

import pytest
from PIL import Image

from instai.choice import graph as G
from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)


def graph_of(posts):
    return G.renumber(G.normalize({"nodes": [G.new_node(p["id"], choices=p.get("choices", []), kind=p.get("kind", "story"), ending=p.get("ending", ""), text=p.get("text", "x")) for p in posts]}))[0]


GOOD = [
    {"id": "a", "kind": "start", "choices": [{"label": "A", "to": "b"}, {"label": "B", "to": "c"}]},
    {"id": "b", "choices": [{"label": "ادامه", "to": "d"}]},
    {"id": "c", "kind": "ending", "ending": "bad"},
    {"id": "d", "kind": "ending", "ending": "good"},
]


def codes(v, level="errors"):
    return sorted({e["code"] for e in v[level]})


# ------------------------------------------------------------------ the graph rules

def test_valid_graph_is_numbered_in_posting_order_and_every_choice_points_forward():
    g = graph_of(GOOD)
    num = G.numbers(g)
    assert sorted(num.values()) == [1, 2, 3, 4] and num["a"] == 1
    assert all(num[to] > num[a] for a, to, _c in G.edges(g))
    v = G.validate(g)
    assert v["ok"] and v["stats"]["endings"] == {"bad": 1, "good": 1} and v["stats"]["paths"] == 2


def test_dead_end_unreachable_unknown_target_and_other_errors_are_found():
    dead = graph_of([{"id": "a", "kind": "start", "choices": [{"label": "x", "to": "b"}]}, {"id": "b"}])
    assert {"dead_end", "no_ending"} <= set(codes(G.validate(dead)))
    ok_dead = graph_of([{"id": "a", "kind": "start", "choices": [{"label": "x", "to": "b"}]}, {"id": "b", "kind": "ending", "ending": "good"}])
    ok_dead["nodes"][0]["intended_dead_end"] = True
    assert G.validate(ok_dead)["ok"]
    orphan = graph_of(GOOD + [{"id": "z", "kind": "ending", "ending": "secret"}])
    assert codes(G.validate(orphan)) == ["unreachable"]
    unknown = graph_of([{"id": "a", "kind": "start", "choices": [{"label": "x", "to": "nope"}, {"label": "y", "to": "e"}]}, {"id": "e", "kind": "ending", "ending": "good"}])
    assert "unknown_target" in codes(G.validate(unknown))
    selfie = graph_of([{"id": "a", "kind": "start", "choices": [{"label": "x", "to": "a"}, {"label": "y", "to": "e"}]}, {"id": "e", "kind": "ending", "ending": "good"}])
    assert "self_loop" in codes(G.validate(selfie))
    dup = graph_of([{"id": "a", "kind": "start", "choices": [{"label": "x", "to": "e"}, {"label": "y", "to": "e"}]}, {"id": "e", "kind": "ending", "ending": "good"}])
    assert "duplicate_target" in codes(G.validate(dup))
    nolabel = graph_of([{"id": "a", "kind": "start", "choices": [{"label": " ", "to": "e"}, {"label": "y", "to": "f"}]}, {"id": "e", "kind": "ending", "ending": "good"}, {"id": "f", "kind": "ending", "ending": "bad"}])
    assert "empty_label" in codes(G.validate(nolabel)) or G.normalize(nolabel)["nodes"][0]["choices"][0]["label"] == ""
    many = graph_of([{"id": "a", "kind": "start", "choices": [{"label": str(i), "to": f"e{i}"} for i in range(5)]}] + [{"id": f"e{i}", "kind": "ending", "ending": "good"} for i in range(5)])
    assert len(many["nodes"][0]["choices"]) == 4                                    # the normaliser keeps at most the hard limit


def test_cycles_and_backward_edges_are_errors_unless_the_loop_is_marked_intended():
    cyc = graph_of([{"id": "a", "kind": "start", "choices": [{"label": "x", "to": "b"}, {"label": "y", "to": "e"}]}, {"id": "b", "choices": [{"label": "back", "to": "a"}]},
                    {"id": "e", "kind": "ending", "ending": "good"}])
    assert "cycle" in codes(G.validate(cyc))
    loop = graph_of([{"id": "a", "kind": "start", "choices": [{"label": "x", "to": "b"}, {"label": "y", "to": "e"}]}, {"id": "b", "choices": [{"label": "try again", "to": "a", "loop": True}]},
                     {"id": "e", "kind": "ending", "ending": "good"}])
    v = G.validate(loop)
    assert v["ok"] and "cycle" not in codes(v)                                      # an intended "try again" loop is neither a cycle nor a backward edge
    unflagged = graph_of([{"id": "a", "kind": "start", "choices": [{"label": "x", "to": "b"}, {"label": "y", "to": "e"}]}, {"id": "b", "choices": [{"label": "back", "to": "e"}]},
                          {"id": "e", "kind": "ending", "ending": "good"}])
    unflagged["nodes"][1]["number"], unflagged["nodes"][2]["number"] = 3, 2
    assert "backward_edge" in codes(G.validate(unflagged)) and "backward_edge" not in codes(G.validate(unflagged, allow_back_edges=True))
    # numbers that do not follow the posting order are caught
    g = graph_of(GOOD)
    g["nodes"][1]["number"], g["nodes"][3]["number"] = g["nodes"][3]["number"], g["nodes"][1]["number"]
    assert "backward_edge" in codes(G.validate(g))
    g2 = graph_of(GOOD)
    g2["nodes"][2]["number"] = 9
    assert "numbering_gap" in codes(G.validate(g2))


def test_placeholders_are_resolved_from_the_current_numbering():
    g = graph_of(GOOD)
    num = G.numbers(g)
    assert G.resolve("برو به پست {go:b} یا {go:c}", g) == f"برو به پست {num['b']} یا {num['c']}".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    assert G.resolve("go {go:b}", g, fa=False) == f"go {num['b']}"
    assert "{?zzz}" in G.resolve("{go:zzz}", g)
    g["nodes"][0]["caption"] = "if A go to post {go:zzz}"
    assert G.unresolved(g)[0]["code"] == "unknown_placeholder"
    # inserting a post in the middle renumbers everything and the captions still point to the right posts
    g2, nid = G.add_node(g, {"title": "new", "text": "t", "kind": "story", "choices": [{"label": "ادامه", "to": "d"}]})
    g2 = G.set_choice(g2, "b", 0, "ادامه", nid)
    g2, num2 = G.renumber(g2)
    assert G.validate(g2)["ok"] and num2[nid] > num2["b"] and num2["d"] > num2[nid]


@pytest.mark.parametrize("n", [6, 7, 9, 12, 14, 20, 33, 47, 60])
def test_the_skeleton_planner_gives_exactly_n_valid_posts(n):
    for fa in (True, False):
        plan = G.skeleton_plan(n, fa=fa)
        g = graph_of(plan["posts"])
        v = G.validate(g)
        assert len(g["nodes"]) == n and v["ok"], (n, fa, v["errors"][:3])
        assert v["stats"]["endings"].get("good") == 1 and v["stats"]["endings"].get("bad", 0) >= 1
        assert all(len(p["choices"]) <= 2 for p in plan["posts"])


def test_paths_layout_and_choice_lines():
    g = graph_of(G.skeleton_plan(14)["posts"])
    paths = G.enumerate_paths(g)
    assert paths and all(p[0] == G.start_id(g) and G.by_id(g)[p[-1]]["kind"] == "ending" for p in paths)
    lay = G.layout(g)
    assert lay["columns"] >= 5 and set(lay["positions"]) == set(G.by_id(g))
    start = G.by_id(g)[G.start_id(g)]
    lines = G.choice_lines(start, g)
    assert [x["letter"] for x in lines] == ["الف", "ب"] and all(x["number"] > 1 for x in lines)
    assert "{go:" in G.default_caption(start, g)


# ------------------------------------------------------------------ the API: plan, edit, approve, pictures, package

def make_page(api, level="manual"):
    r = api.post("/api/pages", {"name": "پیج داستان", "format": "choice_story", "languages": ["fa"], "idea": "فرار از زندان", "automation_level": level,
                                "characters": [{"name": "رامین", "appearance": "x"}, {"name": "نگهبان", "appearance": "y"}]}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def test_story_flow_plan_edit_approve_render_package(api, worker):
    page = make_page(api)
    r = api.post(f"/api/pages/{page['id']}/choice-stories", {"title": "فرار از زندان", "premise": "زندانی‌ای که می‌خواهد فرار کند", "post_count": 12, "genre": "prison_escape"}, format="json")
    assert r.status_code == 201, r.content
    sid = r.json()["id"]
    assert api.post(f"/api/choice-stories/{sid}/approve", {}, format="json").status_code == 409          # nothing planned yet
    j = finish(api, worker, api.post(f"/api/choice-stories/{sid}/plan", {}, format="json"))
    assert j["result"]["posts"] == 12
    rep = api.get(f"/api/choice-stories/{sid}/report").json()
    assert rep["validation"]["ok"] is True, rep["validation"]["errors"]
    assert rep["stats"]["nodes"] == 12 and rep["paths"] and rep["layout"]["columns"] >= 4
    story = api.get(f"/api/choice-stories/{sid}").json()
    nodes = story["graph"]["nodes"]
    assert [n["number"] for n in nodes] == list(range(1, 13)) and nodes[0]["kind"] == "start"
    assert all("{go:" in n["caption"] or n["kind"] == "ending" for n in nodes)
    # model captions (fake) keep placeholders and are applied
    finish(api, worker, api.post(f"/api/choice-stories/{sid}/captions", {}, format="json"))
    story = api.get(f"/api/choice-stories/{sid}").json()
    assert all(n["caption"] for n in story["graph"]["nodes"])
    # editing: break the graph (a dead end), see the error, approval is refused, fix it, approve
    first_story = next(n for n in story["graph"]["nodes"] if n["kind"] == "story")
    original_target = first_story["choices"][0]["to"]
    broken = api.post(f"/api/choice-stories/{sid}/ops", {"op": "remove_choice", "id": first_story["id"], "index": 0}, format="json").json()
    rep = api.get(f"/api/choice-stories/{sid}/report").json()
    assert not rep["validation"]["ok"] and "dead_end" in {e["code"] for e in rep["validation"]["errors"]}
    assert api.post(f"/api/choice-stories/{sid}/approve", {}, format="json").status_code == 409
    api.post(f"/api/choice-stories/{sid}/ops", {"op": "set_choice", "id": first_story["id"], "index": 0, "label": "ادامه", "to": original_target}, format="json")
    assert api.get(f"/api/choice-stories/{sid}/report").json()["validation"]["ok"] is True
    versions = api.get(f"/api/choice-stories/{sid}/versions").json()
    assert len(versions) >= 3
    approved = api.post(f"/api/choice-stories/{sid}/approve", {}, format="json").json()
    assert approved["status"] == "approved"
    # any edit withdraws the approval
    api.post(f"/api/choice-stories/{sid}/ops", {"op": "update_node", "id": first_story["id"], "fields": {"text": "متن تازه"}}, format="json")
    assert api.get(f"/api/choice-stories/{sid}").json()["status"] == "planned"
    api.post(f"/api/choice-stories/{sid}/approve", {}, format="json")
    # pictures: one per post, drawn by code, with the post number badge and the choices
    pv = api.get(f"/api/choice-stories/{sid}/posts/{nodes[0]['id']}/preview").json()
    assert pv["url"].startswith("/media/choice/")
    j = finish(api, worker, api.post(f"/api/choice-stories/{sid}/render", {}, format="json"))
    assert j["result"]["rendered"] == 12
    assert api.get(f"/api/choice-stories/{sid}/report").json()["stale"] == []
    j = finish(api, worker, api.post(f"/api/choice-stories/{sid}/render", {}, format="json"))
    assert j["result"]["rendered"] == 0                                              # nothing changed: nothing is drawn again
    # package: the pictures in posting order, captions with REAL numbers, schedule, graph, map
    j = finish(api, worker, api.post(f"/api/choice-stories/{sid}/package", {}, format="json"))
    assert j["result"]["posts"] == 12
    from instai.assets.models import Asset
    from instai.assets import storage

    z = zipfile.ZipFile(storage.storage.path_for(Asset.objects.get(pk=j["result"]["asset_id"]).path))
    names = set(z.namelist())
    assert {f"{i:03d}.png" for i in range(1, 13)} <= names and {"captions.txt", "schedule.csv", "graph.json", "map.png", "README.txt"} <= names
    caps = z.read("captions.txt").decode()
    assert "{go:" not in caps and "{?" not in caps and "پست ۲" in caps
    with Image.open(io.BytesIO(z.read("001.png"))) as im:
        assert im.size == (1080, 1350)
    sched = api.get(f"/api/choice-stories/{sid}/schedule?start=2026-12-01").json()["posts"]
    assert [p["number"] for p in sched] == list(range(1, 13)) and sched[0]["local"].startswith("2026-12-01T20:00")


def test_restore_a_version_and_bad_requests(api, worker):
    page = make_page(api)
    sid = api.post(f"/api/pages/{page['id']}/choice-stories", {"title": "قصه", "post_count": 8}, format="json").json()["id"]
    finish(api, worker, api.post(f"/api/choice-stories/{sid}/plan", {}, format="json"))
    before = api.get(f"/api/choice-stories/{sid}").json()["graph"]
    api.post(f"/api/choice-stories/{sid}/ops", {"op": "remove_node", "id": before["nodes"][-1]["id"]}, format="json")
    versions = api.get(f"/api/choice-stories/{sid}/versions").json()
    restored = api.post(f"/api/choice-stories/{sid}/restore", {"number": versions[0]["number"]}, format="json").json()
    assert len(restored["graph"]["nodes"]) == 8
    assert api.post(f"/api/choice-stories/{sid}/ops", {"op": "teleport"}, format="json").status_code == 400
    assert api.post(f"/api/pages/{page['id']}/choice-stories", {"title": ""}, format="json").status_code == 400
    assert api.post(f"/api/choice-stories/{sid}/package", {}, format="json").status_code == 409        # not approved yet
    opts = api.get("/api/choice/options").json()
    assert opts["limits"]["label"] == 28 and len(opts["backgrounds"]) >= 12


def test_the_picture_of_a_post_shows_the_right_numbers_and_changes_when_the_numbering_changes(api, worker):
    from instai.choice import render
    from instai.choice.models import ChoiceStory

    page = make_page(api)
    sid = api.post(f"/api/pages/{page['id']}/choice-stories", {"title": "قصه", "post_count": 8}, format="json").json()["id"]
    finish(api, worker, api.post(f"/api/choice-stories/{sid}/plan", {}, format="json"))
    s = ChoiceStory.objects.get(pk=sid)
    start = G.by_id(s.graph)[G.start_id(s.graph)]
    h1 = render.node_hash(s, start, s.graph)
    s2, nid = G.add_node(s.graph, {"title": "t", "text": "x", "kind": "story", "choices": [{"label": "ادامه", "to": s.graph["nodes"][-1]["id"]}]})
    s2 = G.set_choice(s2, start["id"], 0, "الف", nid)
    s2, _ = G.renumber(s2)
    start2 = G.by_id(s2)[start["id"]]
    assert render.node_hash(s, start2, s2) != h1                                    # a changed target number makes this post's picture stale
    from instai.choice import services

    services.save_graph(s, s2, note="x")
    s.refresh_from_db()
    assert start["id"] in render.stale_nodes(s)
