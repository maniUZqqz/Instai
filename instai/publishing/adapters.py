"""Publishing adapters. The manual-export package is the working default. The Instagram Graph API adapter is a SKELETON behind a feature flag:
it implements the official three calls (create a Reels container from a public video URL, wait until it is processed, publish it) and
refuses to run unless every requirement is met. Nothing bypasses authentication, rate limits or platform controls, and nothing is ever
posted without explicit enablement (see `can_auto_publish`).

Instagram requirements (official): a Professional (Business or Creator) account, linked to a Facebook Page, a Meta app with the
`instagram_content_publish` permission and a long-lived access token, and the video must be fetchable from a PUBLIC https URL (the Graph API pulls
the file from that URL; a local PC has none - use your own public storage or a tunnel you control). Availability from Iran is not assured.
"""
from __future__ import annotations

import abc
import os
import time

import requests

from instai.core import settings_store
from instai.providers.base import ProviderError

from .models import Publication

FLAG = "INSTAI_FEATURE_INSTAGRAM_API"
GRAPH_BASE = "https://graph.facebook.com"
API_VERSION = "v21.0"


class PublishAdapter(abc.ABC):
    name = "base"
    label = ""

    @abc.abstractmethod
    def requirements(self, target) -> list[dict]: ...

    @abc.abstractmethod
    def publish(self, publication: Publication) -> dict: ...

    def ready(self, target) -> bool:
        return all(r["ok"] for r in self.requirements(target))


class ManualExport(PublishAdapter):
    name, label = "manual", "Manual export package (default)"

    def requirements(self, target) -> list[dict]:
        return [{"key": "none", "ok": True, "text": "No account or key needed: a ZIP with video, cover, caption, hashtags and a reminder to upload by hand."}]

    def publish(self, publication: Publication) -> dict:
        from .services import export_package

        return export_package(publication.pk)


def feature_enabled() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in ("1", "true", "yes", "on")


class InstagramGraph(PublishAdapter):
    name, label = "instagram_graph", "Instagram Graph API (official; feature flag, skeleton)"

    def __init__(self, session: requests.Session | None = None):
        self.http = session or requests.Session()

    @staticmethod
    def cfg(target) -> dict:
        return (target.config if target is not None else None) or {}

    def token(self, target) -> str:
        return os.environ.get(self.cfg(target).get("token_env") or "INSTAI_IG_TOKEN", "").strip()

    def requirements(self, target) -> list[dict]:
        c = self.cfg(target)
        base = str(c.get("public_base_url") or "").rstrip("/")
        public = base.startswith("https://") and not any(h in base for h in ("localhost", "127.", "192.168.", "10.", "172.16.", "0.0.0.0"))
        return [
            {"key": "flag", "ok": feature_enabled(), "text": f"Feature flag {FLAG}=1 in .env (off by default)"},
            {"key": "account", "ok": bool(c.get("ig_user_id")), "text": "Instagram Professional (Business/Creator) account: its numeric Instagram user id"},
            {"key": "page", "ok": bool(c.get("facebook_page_linked")), "text": "The account is linked to a Facebook Page (confirm in the target settings)"},
            {"key": "token", "ok": bool(self.token(target)), "text": "A long-lived access token with instagram_content_publish in .env (never stored in the database)"},
            {"key": "public_url", "ok": public, "text": "A public https base URL that serves the media folder (the Graph API downloads the video from it)"},
            {"key": "mode", "ok": bool(target is not None and target.mode == "api" and target.enabled), "text": "The publish target is switched to mode 'api' and enabled by the owner"},
        ]

    def _call(self, method: str, path: str, target, **params):
        base = str(self.cfg(target).get("graph_base") or GRAPH_BASE).rstrip("/")
        ver = self.cfg(target).get("api_version") or API_VERSION
        try:
            r = self.http.request(method, f"{base}/{ver}/{path}", params={**params, "access_token": self.token(target)}, timeout=60)
        except requests.RequestException as e:
            raise ProviderError(f"Instagram Graph API unreachable ({type(e).__name__}); it may not be reachable from this network", retryable=True) from e
        if r.status_code >= 400:
            msg = ""
            try:
                msg = (r.json().get("error") or {}).get("message", "")
            except ValueError:
                msg = r.text[:160]
            raise ProviderError(f"Instagram refused the request (HTTP {r.status_code}): {msg}", retryable=r.status_code >= 500 and r.status_code != 429)
        return r.json()

    def publish(self, publication: Publication) -> dict:
        target = publication.target
        missing = [r["text"] for r in self.requirements(target) if not r["ok"]]
        if missing:
            raise ProviderError("The Instagram adapter cannot run: " + "; ".join(missing), retryable=False, code="not_ready")
        from .services import best_video

        video = best_video(publication.episode)
        if video is None:
            raise ProviderError("this episode has no video yet", retryable=False, code="not_ready")
        url = str(self.cfg(target)["public_base_url"]).rstrip("/") + video.url
        tags = " ".join(h if h.startswith("#") else "#" + h for h in (publication.hashtags or []))
        caption = (publication.caption or publication.episode.title) + ("\n\n" + tags if tags else "")
        ig = self.cfg(target)["ig_user_id"]
        created = self._call("POST", f"{ig}/media", target, media_type="REELS", video_url=url, caption=caption, share_to_feed="true")
        cid = created.get("id")
        if not cid:
            raise ProviderError("Instagram returned no container id", retryable=True)
        for _ in range(60):                                    # processing a video takes seconds to minutes
            st = self._call("GET", cid, target, fields="status_code")
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise ProviderError(f"Instagram could not process the video ({code})", retryable=False)
            time.sleep(float(self.cfg(target).get("poll_seconds") or 5))
        else:
            raise ProviderError("Instagram did not finish processing in time", retryable=True)
        done = self._call("POST", f"{ig}/media_publish", target, creation_id=cid)
        return {"external_id": done.get("id"), "container": cid, "video_url": url}


ADAPTERS = {"manual": ManualExport, "instagram_graph": InstagramGraph}


def adapter_for(target) -> PublishAdapter:
    if target is not None and target.mode == "api" and target.platform == "instagram":
        return InstagramGraph()
    return ManualExport()


def can_auto_publish(page, target) -> tuple[bool, str]:
    """Automatic posting needs ALL of: the owner's explicit per-page enablement (with a confirmation time), an API target set up by the owner, the feature
    flag and every adapter requirement. Anything missing = nothing is posted (the manual package is prepared instead)."""
    from instai.production.models import PageProductionConfig

    cfg = PageProductionConfig.objects.filter(page=page).first()
    if not (cfg and cfg.auto_publish_enabled and cfg.auto_publish_confirmed_at):
        return False, "automatic publishing is not enabled for this page"
    if target is None or target.mode != "api":
        return False, "no API publish target"
    ad = InstagramGraph()
    missing = [r["key"] for r in ad.requirements(target) if not r["ok"]]
    return (not missing), ("missing: " + ", ".join(missing) if missing else "")


def settings_hint() -> dict:
    return {"price_in": settings_store.get_setting("openai_price_in_per_1k"), "price_out": settings_store.get_setting("openai_price_out_per_1k")}
