"""Real-series lookup (What-If and any template with a "source" step).

The owner types a title; we ask public catalogues and return CANDIDATES to pick from. Nothing is trusted blindly and the internet may be
slow or blocked, so every provider is optional and manual entry always works. Terms of use (checked 2026-10-28, see docs/STUDIO_PIPELINE.md):

* AniList  - free for low-volume, on-demand lookups; no bulk harvesting or data hoarding; above ~$150 revenue/month a commercial licence is
             required; its rate limit is 30-90 requests/minute. We fetch one title at a time and keep the text only as internal notes.
* Wikipedia / Fandom - CC BY-SA text. Fine as internal research notes; text (or a close paraphrase) that reaches a published script needs
             attribution and share-alike, so scripts are written from our own bible, never pasted.
* Jikan (unofficial MyAnimeList scraper) - MAL's terms are personal / non-commercial and forbid scraping, so Jikan is OFF by default.
"""
from __future__ import annotations

import difflib
import html as _html
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

SEARCH_UA = {"User-Agent": "InstAI/0.1 (local single-user research helper; low-volume on-demand lookups)"}
HTTP_TIMEOUT = (5, 12)
DEFAULT_PROVIDERS = ["anilist", "wikipedia"]
ALL_PROVIDERS = ["anilist", "wikipedia", "fandom", "jikan", "fake"]


class SearchError(Exception):
    pass


def http_get(url: str, **kw):
    kw.setdefault("headers", SEARCH_UA)
    kw.setdefault("timeout", HTTP_TIMEOUT)
    return requests.get(url, **kw)


def http_post(url: str, **kw):
    kw.setdefault("headers", SEARCH_UA)
    kw.setdefault("timeout", HTTP_TIMEOUT)
    return requests.post(url, **kw)


def _check(resp, name: str) -> dict:
    if resp.status_code == 429:
        raise SearchError(f"{name}: rate limit reached, try again in a minute")
    if resp.status_code >= 400:
        raise SearchError(f"{name}: HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as e:
        raise SearchError(f"{name}: unreadable answer") from e


def clean_text(s: str | None, limit: int = 0) -> str:
    s = re.sub(r"<br\s*/?>|</?(?:p|div|li|ul|ol|h[1-6])\b[^>]*>", "\n", s or "", flags=re.I)
    s = _html.unescape(re.sub(r"<[^>]+>", "", s))  # inline tags (b, i, span ...) vanish without leaving a gap
    s = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", s)).strip()
    return s[:limit].rstrip() if limit else s


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9؀-ۿ]+", "", (t or "").lower())


def _cand(provider: str, id_, title: str, **kw) -> dict:
    base = {"provider": provider, "id": str(id_), "title": title, "title_romaji": "", "title_native": "", "year": None, "format": "", "episodes": None,
            "status": "", "genres": [], "description": "", "cover_url": "", "url": "", "score": 0.0}
    base.update(kw)
    return base


# ------------------------------------------------------------------ AniList

ANILIST_URL = "https://graphql.anilist.co"
ANILIST_SEARCH = ("query ($s: String, $n: Int) { Page(perPage: $n) { media(search: $s, type: ANIME, sort: SEARCH_MATCH) { id title { romaji english native } "
                  "seasonYear format episodes status genres averageScore description(asHtml: false) coverImage { large } siteUrl } } }")
ANILIST_DETAIL = ("query ($id: Int) { Media(id: $id, type: ANIME) { id title { romaji english native } seasonYear format episodes status genres "
                  "description(asHtml: false) siteUrl characters(sort: ROLE, perPage: 25) { edges { role node { name { full } description(asHtml: false) } } } "
                  "relations { edges { relationType node { title { romaji } format } } } } }")


def parse_anilist_media(m: dict) -> dict:
    t = m.get("title") or {}
    title = t.get("english") or t.get("romaji") or t.get("native") or ""
    return _cand("anilist", m.get("id"), title, title_romaji=t.get("romaji") or "", title_native=t.get("native") or "", year=m.get("seasonYear"),
                 format=m.get("format") or "", episodes=m.get("episodes"), status=m.get("status") or "", genres=(m.get("genres") or [])[:6],
                 description=clean_text(m.get("description"), 500), cover_url=(m.get("coverImage") or {}).get("large") or "",
                 url=m.get("siteUrl") or f"https://anilist.co/anime/{m.get('id')}", score=(m.get("averageScore") or 0) / 100)


def search_anilist(query: str, limit: int = 6) -> list[dict]:
    j = _check(http_post(ANILIST_URL, json={"query": ANILIST_SEARCH, "variables": {"s": query, "n": limit}}), "AniList")
    if j.get("errors"):
        raise SearchError("AniList: " + str(j["errors"][0].get("message", "error"))[:120])
    return [parse_anilist_media(m) for m in (j.get("data", {}).get("Page", {}).get("media") or [])]


def material_anilist(cand: dict) -> list[dict]:
    j = _check(http_post(ANILIST_URL, json={"query": ANILIST_DETAIL, "variables": {"id": int(cand["id"])}}), "AniList")
    m = (j.get("data") or {}).get("Media") or {}
    if not m:
        raise SearchError("AniList: title not found")
    base = parse_anilist_media(m)
    head = f"AniList: {base['title']}"
    out = [{"title": f"{head} (overview)", "url": base["url"], "publisher": "AniList", "verified": True,
            "extract": f"{clean_text(m.get('description'), 3500)}\nGenres: {', '.join(m.get('genres') or [])}. Format: {base['format']}. "
                       f"Episodes: {base['episodes']}. Year: {base['year']}."}]
    chars = []
    for e in (m.get("characters") or {}).get("edges") or []:
        node = e.get("node") or {}
        n = (node.get("name") or {}).get("full")
        if n:
            chars.append(f"{n} ({str(e.get('role', '')).lower()}): {clean_text(node.get('description'), 280)}")
    if chars:
        out.append({"title": f"{head} (characters)", "url": base["url"], "publisher": "AniList", "verified": True, "extract": "\n".join(chars)[:4000]})
    rel = [f"{e.get('relationType', '')}: {((e.get('node') or {}).get('title') or {}).get('romaji', '')}" for e in (m.get("relations") or {}).get("edges") or []]
    if rel:
        out.append({"title": f"{head} (relations)", "url": base["url"], "publisher": "AniList", "verified": True, "extract": "\n".join(rel)[:1500]})
    return out


# ------------------------------------------------------------------ Jikan (opt-in)

JIKAN = "https://api.jikan.moe/v4"


def search_jikan(query: str, limit: int = 6) -> list[dict]:
    j = _check(http_get(f"{JIKAN}/anime", params={"q": query, "limit": limit, "sfw": "true"}), "Jikan")
    out = []
    for m in j.get("data") or []:
        out.append(_cand("jikan", m.get("mal_id"), m.get("title_english") or m.get("title") or "", title_romaji=m.get("title") or "",
                         title_native=m.get("title_japanese") or "", year=m.get("year"), format=m.get("type") or "", episodes=m.get("episodes"),
                         status=m.get("status") or "", genres=[g.get("name") for g in (m.get("genres") or [])][:6],
                         description=clean_text(m.get("synopsis"), 500), cover_url=((m.get("images") or {}).get("jpg") or {}).get("image_url") or "",
                         url=m.get("url") or "", score=(m.get("score") or 0) / 10))
    return out


def material_jikan(cand: dict) -> list[dict]:
    j = _check(http_get(f"{JIKAN}/anime/{cand['id']}/full"), "Jikan")
    m = j.get("data") or {}
    out = [{"title": f"MyAnimeList: {cand['title']} (synopsis)", "url": m.get("url", ""), "publisher": "MyAnimeList via Jikan", "verified": True,
            "extract": clean_text(m.get("synopsis"), 3500)}]
    time.sleep(1.0)  # Jikan allows 3 requests per second
    c = _check(http_get(f"{JIKAN}/anime/{cand['id']}/characters"), "Jikan")
    lines = [f"{(e.get('character') or {}).get('name', '')} ({e.get('role', '')})" for e in (c.get("data") or [])[:30]]
    if lines:
        out.append({"title": f"MyAnimeList: {cand['title']} (characters)", "url": m.get("url", ""), "publisher": "MyAnimeList via Jikan", "verified": True,
                    "extract": "\n".join(lines)})
    return out


# ------------------------------------------------------------------ Wikipedia

_WIKI_WANTED = ("plot", "premise", "synopsis", "story", "summary", "setting", "characters", "overview", "themes", "world", "arcs", "episodes")


def wiki_sections(text: str, limit: int = 9000) -> str:
    """From a plain-text MediaWiki extract keep the lead plus the sections a writer needs (plot, premise, characters...), up to `limit` chars."""
    parts = re.split(r"\n(={2,}[^=\n]+={2,})\n", "\n" + (text or ""))
    keep = [parts[0].strip()] if parts[0].strip() else []
    for i in range(1, len(parts) - 1, 2):
        head = parts[i].strip("= ").strip()
        if any(w in head.lower() for w in _WIKI_WANTED):
            keep.append(f"{head}\n{parts[i + 1].strip()}")
    return "\n\n".join(keep)[:limit].rstrip()


def _wiki_api(lang: str) -> str:
    return f"https://{lang if lang in ('fa', 'en', 'ar', 'de', 'fr', 'es', 'ja') else 'en'}.wikipedia.org/w/api.php"


def search_wikipedia(query: str, limit: int = 5, language: str = "en") -> list[dict]:
    lang = language[:2]
    j = _check(http_get(_wiki_api(lang), params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": limit}), "Wikipedia")
    out = []
    for hit in (j.get("query") or {}).get("search") or []:
        title = hit.get("title", "")
        out.append(_cand("wikipedia", title, title, format="article", description=clean_text(hit.get("snippet"), 300), lang=lang,
                         url=f"https://{lang}.wikipedia.org/wiki/{requests.utils.quote(title.replace(' ', '_'))}"))
    return out


def material_wikipedia(cand: dict, language: str = "en") -> list[dict]:
    lang = cand.get("lang") or language[:2]
    j = _check(http_get(_wiki_api(lang), params={"action": "query", "prop": "extracts", "explaintext": 1, "titles": cand["id"], "format": "json",
                                                  "formatversion": 2, "redirects": 1}), "Wikipedia")
    pages = (j.get("query") or {}).get("pages") or []
    text = wiki_sections((pages[0].get("extract") if pages else "") or "")
    if not text:
        raise SearchError("Wikipedia: empty article")
    return [{"title": f"Wikipedia ({lang}): {cand['id']}", "url": cand.get("url") or f"https://{lang}.wikipedia.org/wiki/{cand['id'].replace(' ', '_')}",
             "publisher": f"Wikipedia ({lang}) - CC BY-SA", "verified": True, "extract": text}]


# ------------------------------------------------------------------ Fandom wikis (MediaWiki api.php per wiki)

def _fandom_api(wiki: str) -> str:
    return f"https://{re.sub(r'[^a-z0-9-]', '', (wiki or '').lower())}.fandom.com/api.php"


def fandom_wikitext_to_text(w: str, limit: int = 9000) -> str:
    """Crude wikitext -> plain text: drop references, templates, files and link markup."""
    w = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>|<!--.*?-->", "", w or "", flags=re.S)
    for _ in range(4):  # nested templates
        w = re.sub(r"\{\{[^{}]*\}\}", "", w)
    w = re.sub(r"\[\[(?:File|Image|Category):[^\]]*\]\]", "", w, flags=re.I)
    w = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", w)
    w = re.sub(r"\[\[([^\]]*)\]\]", r"\1", w)
    w = re.sub(r"'{2,}", "", w)
    w = re.sub(r"<[^>]+>", "", w)
    return re.sub(r"\n{3,}", "\n\n", w).strip()[:limit]


def search_fandom(query: str, wiki: str, limit: int = 4) -> list[dict]:
    if not wiki:
        raise SearchError("Fandom: the wiki name is needed (for example 'jujutsu-kaisen')")
    j = _check(http_get(_fandom_api(wiki), params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": limit}), "Fandom")
    return [_cand("fandom", f"{wiki}|{h.get('title', '')}", h.get("title", ""), format="wiki page", description=clean_text(h.get("snippet"), 300),
                  url=f"https://{wiki}.fandom.com/wiki/{requests.utils.quote(h.get('title', '').replace(' ', '_'))}")
            for h in (j.get("query") or {}).get("search") or []]


def material_fandom(cand: dict) -> list[dict]:
    wiki, _, title = cand["id"].partition("|")
    j = _check(http_get(_fandom_api(wiki), params={"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "titles": title,
                                                    "format": "json", "formatversion": 2, "redirects": 1}), "Fandom")
    pages = (j.get("query") or {}).get("pages") or []
    rev = (((pages[0].get("revisions") or [{}])[0].get("slots") or {}).get("main") or {}).get("content", "") if pages else ""
    text = fandom_wikitext_to_text(rev)
    if not text:
        raise SearchError("Fandom: empty page")
    return [{"title": f"Fandom ({wiki}): {title}", "url": cand.get("url", ""), "publisher": f"Fandom ({wiki}) - CC BY-SA", "verified": True, "extract": text}]


# ------------------------------------------------------------------ fake (tests and demo mode)

def search_fake(query: str, limit: int = 6, language: str = "en") -> list[dict]:
    fa = language.startswith("fa")
    base = ["سریال نمونه الف" if fa else "Sample Series A", "سریال نمونه ب" if fa else "Sample Series B"]
    return [_cand("fake", f"fake-{i}", f"{t} - {query}", year=2020 + i, format="TV", episodes=12 + i, status="FINISHED", genres=["Action", "Drama"],
                  description="توضیح نمونه" if fa else "A sample description", url=f"https://example.org/series/{i}", score=0.8 - i * 0.1)
            for i, t in enumerate(base)][:limit]


def material_fake(cand: dict, language: str = "en") -> list[dict]:
    fa = language.startswith("fa")
    t = cand["title"]
    return [{"title": f"Sample overview: {t}", "url": cand.get("url", ""), "publisher": "example.org (demo)", "verified": True,
             "extract": (f"{t} داستان گروهی است که با یک تصمیم سرنوشت‌ساز روبه‌رو می‌شود. قهرمان در نبرد پایانی یک انتخاب مهم می‌کند." if fa
                         else f"{t} follows a group facing a fateful decision. In the final battle the hero makes an important choice.")},
            {"title": f"Sample characters: {t}", "url": cand.get("url", ""), "publisher": "example.org (demo)", "verified": True,
             "extract": "آرتا (قهرمان): شجاع. نیلا (هم‌پیمان): باهوش." if fa else "Arta (protagonist): brave. Nila (ally): clever."}]


# ------------------------------------------------------------------ public entry points

def _rank(cands: list[dict], query: str) -> list[dict]:
    q = _norm_title(query)
    seen: dict[str, dict] = {}
    for c in cands:
        names = [c.get("title"), c.get("title_romaji"), c.get("title_native")]
        sim = max((difflib.SequenceMatcher(None, q, _norm_title(n or "")).ratio() for n in names if n), default=0.0)
        c["match"] = round(sim, 2)
        key = _norm_title(c.get("title_romaji") or c.get("title", "")) + str(c.get("year") or "")
        if key not in seen or (seen[key]["provider"] in ("wikipedia", "fandom") and c["provider"] not in ("wikipedia", "fandom")):
            seen[key] = c
    order = {"anilist": 0, "jikan": 1, "fake": 0, "wikipedia": 2, "fandom": 3}
    return sorted(seen.values(), key=lambda c: (-c["match"], order.get(c["provider"], 9)))


def search_series(query: str, providers: list[str] | None = None, language: str = "en", fandom_wiki: str = "", limit: int = 6) -> dict:
    """{candidates, errors: [{provider, message}], tried}. Never raises: failures are reported so the UI can say what went wrong."""
    query = (query or "").strip()
    providers = [p for p in (providers or DEFAULT_PROVIDERS) if p in ALL_PROVIDERS] or list(DEFAULT_PROVIDERS)
    if not query:
        return {"candidates": [], "errors": [], "tried": providers}

    def run(p: str):
        try:
            if p == "anilist":
                return p, search_anilist(query, limit), None
            if p == "jikan":
                return p, search_jikan(query, limit), None
            if p == "wikipedia":
                return p, search_wikipedia(query, 4, language), None
            if p == "fandom":
                return p, search_fandom(query, fandom_wiki), None
            return p, search_fake(query, limit, language), None
        except SearchError as e:
            return p, [], str(e)
        except requests.RequestException as e:
            return p, [], f"{p}: {type(e).__name__} (the site is slow or blocked from here)"

    with ThreadPoolExecutor(max_workers=len(providers)) as ex:
        results = list(ex.map(run, providers))
    cands = [c for _, items, _ in results for c in items]
    return {"candidates": _rank(cands, query)[: limit + 4], "errors": [{"provider": p, "message": e} for p, _, e in results if e], "tried": providers}


def fetch_material(cand: dict, language: str = "en", extra_wikipedia: bool = True, fandom_wiki: str = "") -> dict:
    """Canon material of ONE chosen candidate: {material: [{title, url, publisher, extract, verified}], errors}. Wikipedia is added for plot text."""
    out: list[dict] = []
    errors: list[str] = []

    def attempt(fn, *a):
        try:
            out.extend(fn(*a))
        except SearchError as e:
            errors.append(str(e))
        except requests.RequestException as e:
            errors.append(f"{cand.get('provider')}: {type(e).__name__} (slow or blocked)")

    p = cand.get("provider")
    if p == "anilist":
        attempt(material_anilist, cand)
    elif p == "jikan":
        attempt(material_jikan, cand)
    elif p == "wikipedia":
        attempt(material_wikipedia, cand, language)
    elif p == "fandom":
        attempt(material_fandom, cand)
    elif p == "fake":
        out.extend(material_fake(cand, language))
    if extra_wikipedia and p in ("anilist", "jikan"):
        try:
            hits = search_wikipedia(cand.get("title") or cand.get("title_romaji") or "", 1, "en")
            if hits:
                attempt(material_wikipedia, hits[0], "en")
        except (SearchError, requests.RequestException) as e:
            errors.append(f"Wikipedia: {type(e).__name__}")
    if fandom_wiki:
        try:
            hits = search_fandom(cand.get("title") or "", fandom_wiki, 1)
            if hits:
                attempt(material_fandom, hits[0])
        except (SearchError, requests.RequestException) as e:
            errors.append(f"Fandom: {e}")
    return {"material": out, "errors": errors}
