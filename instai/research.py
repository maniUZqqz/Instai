"""Source retrieval for explainers. The model never invents sources: only text the SYSTEM fetched (or the owner added) becomes a
Source, and only fetched text is marked verified. Providers: off (owner adds sources by hand), wikipedia, fake (tests)."""
from __future__ import annotations

import abc

import requests

from instai.core import settings_store


class SourceFetcher(abc.ABC):
    name = "base"

    @abc.abstractmethod
    def search(self, query: str, language: str = "en", limit: int = 2) -> list[dict]:
        """[{title, url, publisher, extract, verified}]"""


class NullFetcher(SourceFetcher):
    name = "off"

    def search(self, query, language="en", limit=2):
        return []


class WikipediaFetcher(SourceFetcher):
    name = "wikipedia"
    UA = {"User-Agent": "InstAI/0.1 (local research helper)"}

    def search(self, query, language="en", limit=2):
        lang = language[:2] if language[:2] in ("fa", "en", "ar", "de", "fr", "es") else "en"
        base = f"https://{lang}.wikipedia.org"
        out = []
        try:
            r = requests.get(base + "/w/api.php", params={"action": "query", "list": "search", "srsearch": query, "format": "json",
                                                          "srlimit": limit}, headers=self.UA, timeout=10)
            for hit in r.json().get("query", {}).get("search", [])[:limit]:
                title = hit["title"]
                s = requests.get(f"{base}/api/rest_v1/page/summary/{requests.utils.quote(title.replace(' ', '_'))}", headers=self.UA, timeout=10)
                j = s.json()
                if j.get("extract"):
                    out.append({"title": j.get("title", title), "url": j.get("content_urls", {}).get("desktop", {}).get("page", ""),
                                "publisher": f"Wikipedia ({lang})", "extract": j["extract"], "verified": True})
        except (requests.RequestException, ValueError):
            return out
        return out


class FakeFetcher(SourceFetcher):
    """Deterministic sources for tests/demo. Marked verified like a real fetch so the pipeline paths are exercised."""

    name = "fake"

    def search(self, query, language="en", limit=2):
        fa = language.startswith("fa")
        return [{"title": (f"مدخل نمونه: {query}" if fa else f"Sample entry: {query}"), "url": f"https://example.org/wiki/{query.replace(' ', '_')}",
                 "publisher": "example.org (demo)", "extract": (f"{query} مفهومی است که در متن نمونه تعریف شده است." if fa
                                                              else f"{query} is a concept defined in this sample text."), "verified": True}]


def get_fetcher(name: str | None = None) -> SourceFetcher:
    name = name or str(settings_store.effective("research_fetch") or "off")
    return {"wikipedia": WikipediaFetcher, "fake": FakeFetcher}.get(name, NullFetcher)()
