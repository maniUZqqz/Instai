"""The branching graph of an interactive choice story (pure Python, no database): validate, number in posting order, plan a skeleton, walk paths.

A choice story is posted as a numbered series of posts. Each post ends with choices ("if you choose A go to post N+2, if B see post M"), so the numbers
are part of the story: every number written in a caption must be the post's real position in the posting order. The rules this module enforces:

  * post 1 is the only start; every post is reachable from it; only ENDING posts have no choices (no dead ends unless the author marks one intended);
  * numbering = posting order, and every choice points FORWARD (to a higher number) - a reader never has to jump to a post that is not yet published when the
    story is released in order. A deliberate "try again" loop is allowed only when the choice is flagged `loop: true`;
  * 2 choices per decision (3 at most is advised, 4 the hard limit), every label short enough for a picture, at least one ending, ideally a good one.

Captions never contain hard-coded numbers: they carry `{go:<post id>}` placeholders that `resolve` fills from the current numbering, so reordering or inserting a
post can never leave a wrong number behind.
"""
from __future__ import annotations

import copy
import re
from collections import deque

from instai.render.fa_text import digits_fa

KINDS = ("start", "story", "choice", "ending")
ENDINGS = ("good", "bad", "secret", "neutral")
GO = re.compile(r"\{go:([A-Za-z0-9_\-]+)\}")
MAX_CHOICES_HARD = 4
MAX_CHOICES_ADVISED = 3
MAX_LABEL = 28
MAX_TEXT = 220


# ------------------------------------------------------------------ small helpers

def nodes_of(graph: dict) -> list[dict]:
    return list((graph or {}).get("nodes") or [])


def by_id(graph: dict) -> dict[str, dict]:
    return {n["id"]: n for n in nodes_of(graph) if isinstance(n, dict) and n.get("id")}


def edges(graph: dict, *, include_loops: bool = True) -> list[tuple[str, str, dict]]:
    out = []
    for n in nodes_of(graph):
        for c in n.get("choices") or []:
            if include_loops or not c.get("loop"):
                out.append((n["id"], c.get("to", ""), c))
    return out


def start_id(graph: dict) -> str:
    starts = [n["id"] for n in nodes_of(graph) if n.get("kind") == "start"]
    return starts[0] if starts else (nodes_of(graph)[0]["id"] if nodes_of(graph) else "")


def new_node(nid: str, **kw) -> dict:
    base = {"id": nid, "number": 0, "title": "", "text": "", "kind": "story", "ending": "", "choices": [], "scene": {}, "caption": "", "hashtags": [], "alt": "",
            "intended_dead_end": False, "asset_id": None, "image_hash": ""}
    base.update(kw)
    return base


def normalize(graph: dict) -> dict:
    """Clean shape of a graph coming from a model or the UI: known fields only, kinds fixed from the choices, choices trimmed."""
    out = []
    seen = set()
    for raw in nodes_of(graph):
        if not isinstance(raw, dict) or not str(raw.get("id") or "").strip():
            continue
        nid = str(raw["id"]).strip()
        if nid in seen:
            continue
        seen.add(nid)
        node = new_node(nid, number=int(raw.get("number") or 0), title=str(raw.get("title") or "")[:160], text=str(raw.get("text") or "")[:600],
                        ending=str(raw.get("ending") or "") if str(raw.get("ending") or "") in ENDINGS else "", caption=str(raw.get("caption") or "")[:2200],
                        hashtags=[str(h)[:40] for h in (raw.get("hashtags") or [])][:12], alt=str(raw.get("alt") or "")[:300],
                        intended_dead_end=bool(raw.get("intended_dead_end")), asset_id=raw.get("asset_id"), image_hash=str(raw.get("image_hash") or ""))
        sc = raw.get("scene") if isinstance(raw.get("scene"), dict) else {}
        node["scene"] = {k: (sc.get(k) if k != "characters" else [str(c)[:80] for c in (sc.get(k) or [])][:3]) for k in ("location", "characters", "pose", "expression", "background") if sc.get(k)}
        for k in ("location", "pose", "expression"):          # the planner role writes these on the node itself
            if raw.get(k) and k not in node["scene"]:
                node["scene"][k] = raw[k]
        if raw.get("characters") and "characters" not in node["scene"]:
            node["scene"]["characters"] = [str(c)[:80] for c in raw["characters"]][:3]
        choices = []
        for c in raw.get("choices") or []:
            if isinstance(c, dict) and str(c.get("to") or "").strip():
                row = {"label": str(c.get("label") or "").strip()[:80], "to": str(c["to"]).strip()}
                if c.get("loop"):
                    row["loop"] = True
                choices.append(row)
        node["choices"] = choices[:MAX_CHOICES_HARD]
        kind = str(raw.get("kind") or "")
        if node["ending"] or kind == "ending":
            node["kind"] = "ending"
            node["ending"] = node["ending"] or "neutral"
        elif kind == "start":
            node["kind"] = "start"
        else:
            node["kind"] = "choice" if len(choices) >= 2 else "story"
        out.append(node)
    g = {"nodes": out, "meta": dict((graph or {}).get("meta") or {})}
    if out and not any(n["kind"] == "start" for n in out):
        out[0]["kind"] = "start" if out[0]["kind"] != "ending" else out[0]["kind"]
    return g


# ------------------------------------------------------------------ structure

def levels(graph: dict) -> dict[str, int]:
    """Longest distance from the start along non-loop edges (the depth a post sits at); unreachable posts get -1."""
    nodes = by_id(graph)
    s = start_id(graph)
    if s not in nodes:
        return {}
    indeg: dict[str, int] = {i: 0 for i in nodes}
    adj: dict[str, list[str]] = {i: [] for i in nodes}
    for a, b, c in edges(graph, include_loops=False):
        if a in nodes and b in nodes and a != b:
            adj[a].append(b)
            indeg[b] += 1
    order, q = [], deque(i for i, d in indeg.items() if d == 0)
    while q:
        u = q.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    lvl = {i: -1 for i in nodes}
    lvl[s] = 0
    for u in order:
        if lvl[u] < 0:
            continue
        for v in adj[u]:
            lvl[v] = max(lvl[v], lvl[u] + 1)
    return lvl


def reachable(graph: dict) -> set[str]:
    nodes = by_id(graph)
    s = start_id(graph)
    seen: set[str] = set()
    if s not in nodes:
        return seen
    q = deque([s])
    seen.add(s)
    while q:
        u = q.popleft()
        for c in nodes[u].get("choices") or []:
            t = c.get("to")
            if t in nodes and t not in seen:
                seen.add(t)
                q.append(t)
    return seen


def find_cycles(graph: dict) -> list[list[str]]:
    """Cycles among NON-loop edges (a flagged `loop` choice is an intended 'try again' and is ignored here)."""
    nodes = by_id(graph)
    adj = {i: [b for a, b, c in edges(graph, include_loops=False) if a == i and b in nodes] for i in nodes}
    state: dict[str, int] = {}
    cycles: list[list[str]] = []
    stack: list[str] = []

    def dfs(u: str) -> None:
        state[u] = 1
        stack.append(u)
        for v in adj[u]:
            if state.get(v, 0) == 0:
                dfs(v)
            elif state.get(v) == 1 and len(cycles) < 5:
                cycles.append(stack[stack.index(v):] + [v])
        stack.pop()
        state[u] = 2

    for i in nodes:
        if state.get(i, 0) == 0:
            dfs(i)
    return cycles


def renumber(graph: dict) -> tuple[dict, dict[str, int]]:
    """Posting-order numbers: by depth (longest distance from the start), ties by the order the posts are listed. Returns (new graph, {id: number}).
    Because every non-loop edge raises the depth, every choice then points to a higher number."""
    g = copy.deepcopy(graph)
    lvl = levels(g)
    nodes = nodes_of(g)
    pos = {n["id"]: i for i, n in enumerate(nodes)}
    unreachable = [n["id"] for n in nodes if lvl.get(n["id"], -1) < 0]
    order = sorted((n["id"] for n in nodes if lvl.get(n["id"], -1) >= 0), key=lambda i: (lvl[i], pos[i])) + sorted(unreachable, key=lambda i: pos[i])
    num = {i: k + 1 for k, i in enumerate(order)}
    for n in nodes:
        n["number"] = num[n["id"]]
    g["nodes"] = sorted(nodes, key=lambda n: n["number"])
    return g, num


def numbers(graph: dict) -> dict[str, int]:
    return {n["id"]: int(n.get("number") or 0) for n in nodes_of(graph)}


# ------------------------------------------------------------------ validation

def issue(code: str, node: str = "", **detail) -> dict:
    return {"code": code, "node": node, **detail}


def validate(graph: dict, *, allow_back_edges: bool = False, require_good_ending: bool = True) -> dict:
    """{ok, errors[], warnings[], stats}. `ok` means: it can be posted. Codes are translated by the UI (choice.issue.<code>)."""
    errors: list[dict] = []
    warnings: list[dict] = []
    nodes = nodes_of(graph)
    if not nodes:
        return {"ok": False, "errors": [issue("no_nodes")], "warnings": [], "stats": {"nodes": 0}}
    ids = [n.get("id") for n in nodes]
    for i in sorted({x for x in ids if ids.count(x) > 1}):
        errors.append(issue("duplicate_id", i))
    idx = by_id(graph)
    starts = [n["id"] for n in nodes if n.get("kind") == "start"]
    if len(starts) != 1:
        errors.append(issue("start_count", count=len(starts)))
    num = numbers(graph)
    if starts and num.get(starts[0], 1) != 1 and any(num.values()):
        errors.append(issue("start_not_first", starts[0], number=num.get(starts[0])))
    seq = sorted(v for v in num.values() if v)
    if any(num.values()) and seq != list(range(1, len(nodes) + 1)):
        errors.append(issue("numbering_gap", expected=len(nodes)))
    for n in nodes:
        nid = n["id"]
        ch = n.get("choices") or []
        if n.get("kind") == "ending":
            if ch:
                errors.append(issue("ending_has_choices", nid))
            if n.get("ending") not in ENDINGS:
                warnings.append(issue("ending_type_missing", nid))
        else:
            if not ch and not n.get("intended_dead_end"):
                errors.append(issue("dead_end", nid))
            if n.get("kind") == "choice" and len(ch) < 2:
                warnings.append(issue("choice_post_single", nid))
        if len(ch) > MAX_CHOICES_HARD:
            errors.append(issue("too_many_choices", nid, count=len(ch)))
        elif len(ch) > MAX_CHOICES_ADVISED:
            warnings.append(issue("many_choices", nid, count=len(ch)))
        seen_to = set()
        for c in ch:
            to = c.get("to")
            if to not in idx:
                errors.append(issue("unknown_target", nid, to=to))
                continue
            if to == nid:
                errors.append(issue("self_loop", nid))
            if to in seen_to:
                errors.append(issue("duplicate_target", nid, to=to))
            seen_to.add(to)
            if not str(c.get("label") or "").strip():
                errors.append(issue("empty_label", nid, to=to))
            elif len(c["label"]) > MAX_LABEL:
                warnings.append(issue("long_label", nid, length=len(c["label"])))
            if to in num and nid in num and num[to] and num[nid] and num[to] <= num[nid] and not c.get("loop") and not allow_back_edges:
                errors.append(issue("backward_edge", nid, to=to, from_number=num[nid], to_number=num[to]))
        if len(n.get("text") or "") > MAX_TEXT:
            warnings.append(issue("long_text", nid, length=len(n["text"])))
        if not (n.get("text") or "").strip():
            warnings.append(issue("empty_text", nid))
    for cyc in find_cycles(graph):
        errors.append(issue("cycle", cyc[0], path=cyc))
    if starts:
        seen = reachable(graph)
        for n in nodes:
            if n["id"] not in seen:
                errors.append(issue("unreachable", n["id"]))
    endings = [n for n in nodes if n.get("kind") == "ending"]
    if not endings:
        errors.append(issue("no_ending"))
    elif require_good_ending and not any(n.get("ending") == "good" for n in endings):
        warnings.append(issue("no_good_ending"))
    reach_end = _can_reach_ending(graph)
    for n in nodes:
        if n["id"] in reach_end:
            continue
        if n.get("kind") != "ending" and (n.get("choices") or []) and not any(i["code"] in ("dead_end", "cycle") and i["node"] == n["id"] for i in errors):
            errors.append(issue("no_path_to_ending", n["id"]))
    return {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats(graph)}


def _can_reach_ending(graph: dict) -> set[str]:
    nodes = by_id(graph)
    rev: dict[str, list[str]] = {i: [] for i in nodes}
    for a, b, _c in edges(graph):
        if a in nodes and b in nodes:
            rev[b].append(a)
    q = deque(i for i, n in nodes.items() if n.get("kind") == "ending")
    ok = set(q)
    while q:
        u = q.popleft()
        for p in rev[u]:
            if p not in ok:
                ok.add(p)
                q.append(p)
    return ok


def stats(graph: dict, path_cap: int = 5000) -> dict:
    nodes = by_id(graph)
    kinds: dict[str, int] = {}
    for n in nodes.values():
        kinds[n.get("kind", "story")] = kinds.get(n.get("kind", "story"), 0) + 1
    endings: dict[str, int] = {}
    for n in nodes.values():
        if n.get("kind") == "ending":
            endings[n.get("ending") or "neutral"] = endings.get(n.get("ending") or "neutral", 0) + 1
    lvl = levels(graph)
    indeg: dict[str, int] = {i: 0 for i in nodes}
    for a, b, _c in edges(graph):
        if b in indeg:
            indeg[b] += 1
    paths = count_paths(graph, cap=path_cap)
    ch = [len(n.get("choices") or []) for n in nodes.values() if n.get("choices")]
    return {"nodes": len(nodes), "kinds": kinds, "endings": endings, "depth": max([v for v in lvl.values()] + [0]), "merges": sum(1 for d in indeg.values() if d > 1),
            "paths": paths["count"], "paths_capped": paths["capped"], "shortest_path": paths["shortest"], "longest_path": paths["longest"],
            "avg_choices": round(sum(ch) / len(ch), 2) if ch else 0}


def count_paths(graph: dict, cap: int = 5000) -> dict:
    """Number of distinct start -> ending routes (non-loop edges), with the shortest and longest length in posts."""
    nodes = by_id(graph)
    s = start_id(graph)
    memo: dict[str, tuple[int, int, int]] = {}

    def go(u: str, depth: int) -> tuple[int, int, int]:
        if u in memo:
            return memo[u]
        n = nodes[u]
        nxt = [c["to"] for c in n.get("choices") or [] if c.get("to") in nodes and not c.get("loop")]
        if n.get("kind") == "ending" or not nxt:
            memo[u] = (1, 1, 1)
            return memo[u]
        total, lo, hi = 0, 10 ** 6, 0
        for v in nxt:
            c, a, b = go(v, depth + 1)
            total += c
            lo, hi = min(lo, a + 1), max(hi, b + 1)
        memo[u] = (min(total, cap * 100), lo, hi)
        return memo[u]

    if s not in nodes or find_cycles(graph):
        return {"count": 0, "capped": False, "shortest": 0, "longest": 0}
    c, lo, hi = go(s, 0)
    return {"count": min(c, cap), "capped": c > cap, "shortest": lo, "longest": hi}


def enumerate_paths(graph: dict, limit: int = 60) -> list[list[str]]:
    """Up to `limit` routes from the start to an ending, as lists of post ids (depth-first, choices in the order written)."""
    nodes = by_id(graph)
    s = start_id(graph)
    out: list[list[str]] = []

    def go(u: str, trail: list[str]) -> None:
        if len(out) >= limit:
            return
        trail = trail + [u]
        nxt = [c["to"] for c in nodes[u].get("choices") or [] if c.get("to") in nodes and not c.get("loop") and c["to"] not in trail]
        if nodes[u].get("kind") == "ending" or not nxt:
            out.append(trail)
            return
        for v in nxt:
            go(v, trail)

    if s in nodes:
        go(s, [])
    return out


def layout(graph: dict) -> dict:
    """Columns = depth, rows = order inside the column; for the SVG map in the UI."""
    lvl = levels(graph)
    cols: dict[int, list[str]] = {}
    for n in sorted(nodes_of(graph), key=lambda n: (n.get("number") or 0)):
        cols.setdefault(max(lvl.get(n["id"], 0), 0), []).append(n["id"])
    pos = {i: [c, r] for c, ids in cols.items() for r, i in enumerate(ids)}
    return {"levels": lvl, "positions": pos, "columns": max(cols) + 1 if cols else 0, "rows": max((len(v) for v in cols.values()), default=0)}


# ------------------------------------------------------------------ resolving numbers in text

def resolve(text: str, graph: dict, *, fa: bool = True) -> str:
    """Fill every {go:ID} with the post number of ID (Persian digits for Persian text). An unknown id stays visible as {?ID} so it cannot be posted unnoticed."""
    num = numbers(graph)

    def sub(m: re.Match) -> str:
        n = num.get(m.group(1))
        if not n:
            return "{?" + m.group(1) + "}"
        return digits_fa(n) if fa else str(n)

    return GO.sub(sub, text or "")


def unresolved(graph: dict) -> list[dict]:
    """Placeholders in captions that point to a post that does not exist."""
    ids = set(by_id(graph))
    out = []
    for n in nodes_of(graph):
        for m in GO.finditer(n.get("caption") or ""):
            if m.group(1) not in ids:
                out.append(issue("unknown_placeholder", n["id"], to=m.group(1)))
    return out


def choice_lines(node: dict, graph: dict, *, fa: bool = True) -> list[dict]:
    """The lines drawn on the picture of a post: [{letter, label, number, ending}] for its choices (letters A, B, C / الف، ب، ج)."""
    num = numbers(graph)
    idx = by_id(graph)
    letters = ["الف", "ب", "ج", "د"] if fa else ["A", "B", "C", "D"]
    out = []
    for k, c in enumerate(node.get("choices") or []):
        out.append({"letter": letters[k], "label": c.get("label", ""), "to": c.get("to"), "number": num.get(c.get("to"), 0), "loop": bool(c.get("loop")),
                    "ending": (idx.get(c.get("to")) or {}).get("ending", "")})
    return out


def default_caption(node: dict, graph: dict, *, fa: bool = True) -> str:
    """A complete caption with placeholders, written without a model (used when no model answered or the author wants the plain form)."""
    lines = [node.get("text", "")]
    ch = node.get("choices") or []
    if node.get("kind") == "ending":
        lines.append({"good": "پایان خوب 🎉", "bad": "پایان بد 💀", "secret": "پایان مخفی 🔑", "neutral": "پایان."}.get(node.get("ending"), "پایان.") if fa else
                     {"good": "Good ending 🎉", "bad": "Bad ending 💀", "secret": "Secret ending 🔑", "neutral": "The end."}.get(node.get("ending"), "The end."))
    elif len(ch) == 1:
        lines.append(f"ادامه ← پست {{go:{ch[0]['to']}}}" if fa else f"Continue → post {{go:{ch[0]['to']}}}")
    else:
        letters = ["الف", "ب", "ج", "د"] if fa else ["A", "B", "C", "D"]
        for k, c in enumerate(ch):
            lines.append((f"{letters[k]}) {c['label']} ← پست {{go:{c['to']}}}") if fa else f"{letters[k]}) {c['label']} → post {{go:{c['to']}}}")
    return "\n".join(x for x in lines if x)


# ------------------------------------------------------------------ operations used by the editor

def add_node(graph: dict, node: dict | None = None, *, after: str = "") -> tuple[dict, str]:
    g = copy.deepcopy(graph)
    ids = set(by_id(g))
    k = len(ids) + 1
    while f"p{k}" in ids:
        k += 1
    nid = (node or {}).get("id") or f"p{k}"
    n = new_node(nid, **{k_: v for k_, v in (node or {}).items() if k_ != "id"})
    g.setdefault("nodes", []).append(n)
    return normalize(g), nid


def remove_node(graph: dict, nid: str) -> dict:
    g = copy.deepcopy(graph)
    g["nodes"] = [n for n in nodes_of(g) if n["id"] != nid]
    for n in g["nodes"]:
        n["choices"] = [c for c in n.get("choices") or [] if c.get("to") != nid]
    return normalize(g)


def set_choice(graph: dict, nid: str, index: int, label: str, to: str, *, loop: bool = False) -> dict:
    g = copy.deepcopy(graph)
    n = by_id(g)[nid]
    ch = n.setdefault("choices", [])
    row = {"label": label, "to": to, **({"loop": True} if loop else {})}
    if index >= len(ch):
        ch.append(row)
    else:
        ch[index] = row
    return normalize(g)


def remove_choice(graph: dict, nid: str, index: int) -> dict:
    g = copy.deepcopy(graph)
    n = by_id(g)[nid]
    if 0 <= index < len(n.get("choices") or []):
        n["choices"].pop(index)
    return normalize(g)


# ------------------------------------------------------------------ skeleton planner (also the fake provider's output and the fallback)

LOC = ["cell", "corridor", "yard", "room", "street", "forest", "rooftop", "cave", "lab", "sewer", "bridge", "desert"]
POSES = ["think", "sneak", "run_a", "hide", "point_right", "shock", "stand", "hands_up", "crouch", "walk_a"]
EXPR = ["scared", "neutral", "surprised", "angry", "smirk", "sad", "happy"]
LABELS_FA = [("از در اصلی برو", "پنهان شو"), ("بدو!", "صبر کن"), ("به نگهبان اعتماد کن", "تنها برو"), ("پنجره", "راهرو"), ("مبارزه کن", "فرار کن"), ("کلید را بردار", "رهایش کن")]
LABELS_EN = [("Take the main door", "Hide"), ("Run!", "Wait"), ("Trust the guard", "Go alone"), ("The window", "The corridor"), ("Fight", "Flee"), ("Take the key", "Leave it")]
BAD_FA = ["گیر افتادی؛ بازی تمام.", "نگهبان تو را دید.", "راه بن‌بست بود و صبح شد.", "پایین افتادی."]
BAD_EN = ["Caught. Game over.", "The guard saw you.", "A dead end, and then morning came.", "You fell."]


def _pid(k: int) -> str:
    return f"p{k}"


def skeleton_plan(n: int, *, fa: bool = True, title: str = "", tag: str = "") -> dict:
    """A valid branching plan of exactly `n` posts (6..60): a spine of decisions with bad-ending detours, side routes that merge back, ending in a good ending
    (and one secret ending when there is room). The texts are generic placeholders marked with `tag`; a model or the author rewrites them. Deterministic."""
    n = max(6, min(60, int(n)))
    labels, bad = (LABELS_FA, BAD_FA) if fa else (LABELS_EN, BAD_EN)
    cont = "ادامه" if fa else "Continue"
    spine_len = max(4, round(n * 0.5))
    budget = n - spine_len
    decisions = [i for i in range(1, spine_len - 1) if i % 2 == 1]
    detour: dict[int, str] = {}
    side: list[dict] = []
    counter = {"n": spine_len}

    def new_id() -> str:
        counter["n"] += 1
        return _pid(counter["n"])

    for k, i in enumerate(decisions):
        if budget <= 0:
            break
        if budget >= 2 and k % 2 == 1:
            d1, d2 = new_id(), new_id()
            budget -= 2
            side.append({"id": d1, "kind": "story", "ending": "", "choices": [{"label": cont, "to": d2}]})
            side.append({"id": d2, "kind": "story", "ending": "", "choices": [{"label": cont, "to": _pid(i + 2)}]})
            detour[i] = d1
        else:
            d = new_id()
            budget -= 1
            side.append({"id": d, "kind": "ending", "ending": "bad", "choices": []})
            detour[i] = d
    ext = 0
    while budget > 0:                      # spare posts lengthen the detours: a bad ending becomes a story post that leads on to a new ending
        ends = [s for s in side if s["kind"] == "ending"]
        host = ends[ext % len(ends)]
        nd = new_id()
        budget -= 1
        ext += 1
        host.update(kind="story", ending="", choices=[{"label": cont, "to": nd}])
        side.append({"id": nd, "kind": "ending", "ending": "secret" if (ext % 3 == 0 and any(x.get("ending") == "bad" for x in side)) else "bad", "choices": []})
    spine: list[dict] = []
    for i in range(1, spine_len + 1):
        pid = _pid(i)
        if i == spine_len:
            spine.append({"id": pid, "kind": "ending", "ending": "good", "choices": []})
        elif i in detour:
            a, b = labels[(i // 2) % len(labels)]
            spine.append({"id": pid, "kind": "start" if i == 1 else "choice", "ending": "", "choices": [{"label": a, "to": _pid(i + 1)}, {"label": b, "to": detour[i]}]})
        else:
            spine.append({"id": pid, "kind": "start" if i == 1 else "story", "ending": "", "choices": [{"label": cont, "to": _pid(i + 1)}]})
    out = []
    for k, node in enumerate(spine + side):
        end = node["ending"]
        if end == "bad":
            text = bad[k % len(bad)]
        elif end == "good":
            text = "از دیوار بالا رفتی و آزاد شدی!" if fa else "You climbed the wall and you are free!"
        elif end == "secret":
            text = "یک تونل مخفی پیدا کردی…" if fa else "You found a hidden tunnel…"
        else:
            text = (f"{tag} صحنهٔ {k + 1}: باید تصمیم بگیری." if fa else f"{tag} Scene {k + 1}: you must decide.").strip()
        word = {"good": ("خوب", "good"), "bad": ("بد", "bad"), "secret": ("مخفی", "secret")}.get(end, ("", ""))
        out.append({"id": node["id"], "title": (f"پست {k + 1}" if fa else f"Post {k + 1}") if not end else (("پایان " + word[0]) if fa else ("Ending " + word[1])), "text": text,
                    "kind": node["kind"], "location": LOC[k % len(LOC)], "characters": [],
                    "pose": POSES[k % len(POSES)] if not end else {"good": "cheer", "bad": "lying", "secret": "think"}.get(end, "stand"),
                    "expression": EXPR[k % len(EXPR)] if not end else {"good": "happy", "bad": "sad", "secret": "surprised"}.get(end, "neutral"), "ending": end,
                    "choices": node["choices"]})
    return {"title": title or ("فرار از زندان" if fa else "Prison escape"), "posts": out}
