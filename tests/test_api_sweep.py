"""API sweep (0.8.0, the owner's "it still has lots of problems"): every GET route of the whole app is called against fake services, with
the ids of nothing in particular, and none may answer with a server error or with something that is not JSON. A 404 for an id that does not
exist, a 400 for a missing parameter or a 405 are good answers; a 500, a traceback page or an HTML body under /api/ is a bug.
It walks the URL configuration by itself, so a route another feature adds later is swept without a line here."""
from __future__ import annotations

import re
import uuid

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

pytestmark = pytest.mark.django_db(transaction=True)

SKIP = (r"^api/(?P<rest>.*)$",)           # the catch-all that answers every unknown path with a JSON 404 (checked on its own below)
SAMPLES = {"int": "1", "str": "sample", "slug": "sample", "uuid": str(uuid.UUID(int=1)), "path": "sample/file.txt"}
REGEX_GROUP = re.compile(r"\(\?P<(\w+)>[^)]*\)")
ROUTE_PART = re.compile(r"<(?:(\w+):)?(\w+)>")


def walk(patterns, prefix: str = ""):
    for p in patterns:
        route = str(p.pattern)
        if isinstance(p, URLResolver):
            yield from walk(p.url_patterns, prefix + route)
        elif isinstance(p, URLPattern):
            yield prefix + route


def concrete(route: str) -> str | None:
    if route in SKIP or route.startswith("^media/") or route.startswith("^(?!"):
        return None
    url = ROUTE_PART.sub(lambda m: SAMPLES.get(m.group(1) or "str", "1"), route)
    url = REGEX_GROUP.sub("1", url)
    url = url.replace("^", "").replace("$", "").replace("\\.", ".").replace("(?:", "").replace(")?", "")
    if re.search(r"[()\[\]\\*+?]", url):
        return None                                       # a pattern this helper cannot turn into a plain path
    return "/" + url.lstrip("/")


def all_get_urls() -> list[str]:
    urls = sorted({u for u in (concrete(r) for r in walk(get_resolver().url_patterns)) if u and u.startswith("/api/")})
    return urls


def test_the_sweep_finds_the_routes_of_every_app():
    urls = all_get_urls()
    assert len(urls) > 150, len(urls)
    for must in ("/api/health", "/api/remotion/status", "/api/remotion/kits", "/api/downloads/catalog", "/api/gpu/coexist", "/api/library/style", "/api/jobs"):
        assert any(u.startswith(must) for u in urls), f"{must} is not swept"


def test_every_get_route_answers_without_a_server_error(api):
    bad: list[str] = []
    for url in all_get_urls():
        if url.endswith(("/stream", "/events")):
            continue                                       # long-lived streams
        try:
            r = api.get(url)
        except Exception as e:  # noqa: BLE001 - an exception inside the view is exactly what this finds
            bad.append(f"GET {url}: raised {type(e).__name__}: {str(e)[:120]}")
            continue
        if r.status_code >= 500:
            bad.append(f"GET {url}: HTTP {r.status_code}")
            continue
        ctype = r.headers.get("Content-Type", "")
        if r.status_code != 204 and "json" not in ctype and "download" not in url and "file" not in url and "export" not in url and "/media/" not in url:
            bad.append(f"GET {url}: HTTP {r.status_code} but {ctype or 'no content type'} (an API answer must be JSON)")
    assert not bad, "\n".join(bad[:40])


def test_an_unknown_api_path_is_a_json_404_not_the_page(api):
    r = api.get("/api/no/such/thing")
    assert r.status_code == 404 and "json" in r.headers["Content-Type"]
    assert api.post("/api/no/such/thing", {}, format="json").status_code == 404
