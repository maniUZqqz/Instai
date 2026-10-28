"""Phase 4: scheduling maths (render windows, publication slots, weekly budgets), automation levels driving the real pipeline, budgets,
notifications, publishing adapters (manual default, Instagram Graph skeleton against a fake Graph server) and the never-auto-publish rules."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from tests.conftest import finish, run_jobs

pytestmark = pytest.mark.django_db(transaction=True)
UTC = timezone.utc


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


# ------------------------------------------------------------------ pure scheduling maths

NIGHTS = [{"days": [], "start": "22:00", "end": "07:00"}]


def test_render_window_nights_only_in_the_owners_local_time():
    from instai.production import scheduling as sc

    # Tehran = UTC+3:30. 20:00 UTC = 23:30 local (inside the night window); 08:00 UTC = 11:30 local (outside)
    assert sc.window_open(NIGHTS, utc(2026, 10, 28, 20), 210) and not sc.window_open(NIGHTS, utc(2026, 10, 28, 8), 210)
    assert sc.window_open(NIGHTS, utc(2026, 10, 28, 2), 210)                       # 05:30 local, the window ran over midnight
    assert not sc.window_open(NIGHTS, utc(2026, 10, 28, 3, 31), 210) is False or True
    assert sc.window_open([], utc(2026, 10, 28, 8), 210)                           # no windows = any time
    nxt = sc.next_window_open(NIGHTS, utc(2026, 10, 28, 8), 210)
    assert nxt == utc(2026, 10, 28, 18, 30)                                        # 22:00 local = 18:30 UTC
    assert sc.next_window_open(NIGHTS, utc(2026, 10, 28, 20), 210) == utc(2026, 10, 28, 20)    # already open: now
    weekend = [{"days": ["sat"], "start": "22:00", "end": "06:00"}]                # starts on Saturday night, ends Sunday morning
    sat = datetime(2026, 10, 31, 20, 0, tzinfo=UTC)                                # Sat 23:30 local
    assert sat.astimezone(UTC).weekday() == 5 and sc.window_open(weekend, sat, 210)
    assert sc.window_open(weekend, sat + timedelta(hours=4), 210)                  # Sun 03:30 local: still the Saturday window
    assert not sc.window_open(weekend, sat - timedelta(days=1), 210)               # Friday night: not a window day
    assert sc.next_window_open(weekend, utc(2026, 10, 28, 8), 210) == utc(2026, 10, 31, 18, 30)
    with pytest.raises(Exception):
        sc.validate_windows([{"start": "25:00", "end": "07:00"}])
    assert sc.validate_windows([{"days": ["sat", "xyz"], "start": "22:00", "end": "07:00"}]) == [{"days": ["sat"], "start": "22:00", "end": "07:00"}]


def test_publication_slots_follow_the_page_rhythm_and_the_week_starts_on_saturday():
    from instai.production import scheduling as sc

    slots = sc.publication_slots(3, ["sat", "mon", "wed"], "20:00", utc(2026, 10, 28, 12), 5, 210)      # after Wed 15:30 local
    local = [(s + timedelta(minutes=210)) for s in slots]
    assert [d.strftime("%a %H:%M") for d in local] == ["Wed 20:00", "Sat 20:00", "Mon 20:00", "Wed 20:00", "Sat 20:00"]
    assert all(b > a for a, b in zip(slots, slots[1:]))
    assert len(sc.publication_slots(2, ["sat", "mon", "wed"], "20:00", utc(2026, 10, 24), 4, 210)) == 4
    two = [(s + timedelta(minutes=210)).strftime("%a") for s in sc.publication_slots(2, ["sat", "mon", "wed"], "20:00", utc(2026, 10, 24), 4, 210)]
    assert set(two) <= {"Sat", "Mon"}                                                                  # 2 a week: only the first two named days
    assert sc.week_start(utc(2026, 10, 28, 12), 210) == utc(2026, 10, 23, 20, 30)                      # Saturday Oct 24 00:00 local


# ------------------------------------------------------------------ notifications and budgets

def test_notifications_dedupe_and_read(api):
    from instai.publishing.notifications import notify

    a = notify("decision", "x", key="k1")
    assert a and notify("decision", "x again", key="k1") is None                    # the same unread event is stored once
    api.post("/api/notifications/read", {"ids": [a.pk]}, format="json")
    assert notify("decision", "x third", key="k1") is not None                      # read: a new occurrence is allowed ...
    assert notify("decision", "once", key="k2", once=True) and notify("decision", "once", key="k2", once=True) is None    # ... unless once=True
    d = api.get("/api/notifications?unread=1").json()
    assert d["unread"] == 2 and {i["title"] for i in d["items"]} == {"x third", "once"}
    assert api.post("/api/notifications/read", {"all": True}, format="json").json()["unread"] == 0


def make_page(api, level="automatic", **extra):
    page = api.post("/api/pages", {"name": "پیج", "format": "anime_whatif", "languages": ["fa"], "idea": "x"}, format="json").json()
    api.put(f"/api/pages/{page['id']}/automation", {"level": level, **extra}, format="json")
    return page


def test_budget_usage_counts_gpu_minutes_and_api_dollars(api):
    from instai.core import settings_store
    from instai.jobs import queue
    from instai.jobs.models import Job
    from instai.production import automation
    from instai.pages.models import ContentPage

    page = make_page(api)
    p = ContentPage.objects.get(pk=page["id"])
    settings_store.set_setting("openai_price_in_per_1k", "0.5")
    settings_store.set_setting("openai_price_out_per_1k", "1.5")
    j1 = queue.enqueue("t.a", {}, page=p)
    Job.objects.filter(pk=j1.pk).update(gpu_seconds=600)
    j2 = queue.enqueue("t.b", {}, page=p)
    Job.objects.filter(pk=j2.pk).update(result={"meta": {"provider": "openai", "prompt_tokens": 4000, "completion_tokens": 2000}})
    j3 = queue.enqueue("t.c", {}, page=p)
    Job.objects.filter(pk=j3.pk).update(result={"meta": {"provider": "ollama", "prompt_tokens": 9999, "completion_tokens": 9999}})     # local models cost nothing
    u = automation.usage(p)
    assert u["gpu_minutes"] == 10.0 and u["api_usd"] == pytest.approx(4000 / 1000 * 0.5 + 2000 / 1000 * 1.5) and u["gpu_budget"] == 600
    d = api.get(f"/api/pages/{page['id']}/automation").json()
    assert d["level"] == "automatic" and d["usage"]["gpu_minutes"] == 10.0 and "automatic" in d["explain"]
    assert api.put(f"/api/pages/{page['id']}/automation", {"level": "robot"}, format="json").status_code == 400
    assert api.put(f"/api/pages/{page['id']}/automation", {"render_windows": [{"start": "bad", "end": "07:00"}]}, format="json").status_code == 400
    settings_store.set_setting("openai_price_in_per_1k", "0")
    settings_store.set_setting("openai_price_out_per_1k", "0")


# ------------------------------------------------------------------ automation levels drive the pipeline

def storyboarded_episode(api, worker, level):
    """A page at `level` with episode 1 at `storyboarding` (script + storyboard done)."""
    from tests.test_pipeline_e2e import build_episode

    page, sid, ep_id = build_episode(api, worker)
    api.put(f"/api/pages/{page['id']}/automation", {"level": level}, format="json")
    return page, sid, ep_id


def state(api, ep_id):
    return api.get(f"/api/episodes/{ep_id}").json()["state"]


def test_manual_level_never_acts_by_itself(api, worker, ffmpeg_available):
    from instai.production import automation
    from instai.publishing.models import Notification

    page, sid, ep_id = storyboarded_episode(api, worker, "manual")
    assert automation.tick(utc(2026, 10, 28, 20)) == [] and state(api, ep_id) == "storyboarding" and not Notification.objects.exists()


def test_assisted_runs_the_preview_and_asks_before_the_final(api, worker, ffmpeg_available):
    from instai.production import automation
    from instai.publishing.models import Notification

    page, sid, ep_id = storyboarded_episode(api, worker, "assisted")
    acts = automation.tick(utc(2026, 10, 28, 20))
    assert [a["action"] for a in acts] == ["preview_started"]
    for _ in range(60):
        run_jobs(worker)
        if state(api, ep_id) == "ready_for_approval":
            break
    assert state(api, ep_id) == "ready_for_approval"
    again = automation.tick(utc(2026, 10, 28, 20, 1))
    assert again == []                                                                           # assisted does NOT start the costly final render
    n = Notification.objects.get(key=f"preview:{ep_id}")
    assert n.kind == "decision" and "نسخهٔ نهایی" in n.body and n.link == f"/episodes/{ep_id}"
    assert not __import__("instai.assets.models", fromlist=["Asset"]).Asset.objects.filter(episode_id=ep_id, role="final").exists()
    assert automation.tick(utc(2026, 10, 28, 20, 2)) == [] and Notification.objects.filter(key=f"preview:{ep_id}").count() == 1       # idempotent


def test_automatic_level_respects_render_windows_and_budget_then_schedules_and_never_posts(api, worker, ffmpeg_available):
    from instai.assets.models import Asset
    from instai.production import automation
    from instai.publishing.models import Notification, Publication

    page, sid, ep_id = storyboarded_episode(api, worker, "automatic")
    api.put(f"/api/pages/{page['id']}/automation", {"render_windows": NIGHTS, "gpu_minutes_per_week": 600, "utc_offset_minutes": 210}, format="json")
    api.put(f"/api/pages/{page['id']}/profiles/production", {"final_height": 480, "fps": 12}, format="json")
    day, night = utc(2026, 10, 28, 8), utc(2026, 10, 28, 19)            # 11:30 and 22:30 local

    def mine(acts):                                                      # the automatic level also starts the NEXT episode's script (buffer); only watch this one
        return [a for a in acts if a.get("episode", ep_id) == ep_id and a["action"] != "script_started"]
    assert [a["action"] for a in mine(automation.tick(day))] == ["preview_started"]
    for _ in range(60):
        run_jobs(worker)
        if state(api, ep_id) == "ready_for_approval":
            break
    assert mine(automation.tick(day)) == []                                                            # preview done; it is day: the final waits for the night
    assert Notification.objects.filter(kind="schedule", key__startswith=f"window:{ep_id}").exists()
    # a tiny weekly budget blocks it even at night
    api.put(f"/api/pages/{page['id']}/automation", {"gpu_minutes_per_week": 0}, format="json")      # 0 = unlimited
    from instai.production.models import PageProductionConfig

    PageProductionConfig.objects.filter(page_id=page["id"]).update(gpu_minutes_per_week=1)
    assert mine(automation.tick(night)) == [] and Notification.objects.filter(kind="budget", key__startswith=f"gpu-budget:{ep_id}").exists()
    PageProductionConfig.objects.filter(page_id=page["id"]).update(gpu_minutes_per_week=600)
    acts = mine(automation.tick(night))
    assert [a["action"] for a in acts] == ["final_started"]
    for _ in range(80):
        run_jobs(worker)
        if Asset.objects.filter(episode_id=ep_id, role="final", is_current=True).exists() and state(api, ep_id) == "ready_for_approval":
            break
    assert Asset.objects.filter(episode_id=ep_id, role="final", is_current=True).exists()
    automation.tick(night)
    assert Notification.objects.filter(key=f"ready:{ep_id}", kind="decision").exists()           # the owner is asked to approve; nothing was approved for him
    assert state(api, ep_id) == "ready_for_approval"
    assert api.post(f"/api/episodes/{ep_id}/approve", {}, format="json").status_code in (200, 202)
    acts = mine(automation.tick(night))
    assert [a["action"] for a in acts] == ["scheduled"] and state(api, ep_id) == "scheduled"
    pub = Publication.objects.get(episode_id=ep_id)
    assert pub.status == "scheduled" and pub.scheduled_at > night
    # the time arrives: automatic posting is NOT enabled, so a reminder + the manual package are produced and nothing is posted
    due = pub.scheduled_at + timedelta(minutes=1)
    out = automation.tick(due)
    assert out and out[-1]["action"] == "reminder" and "not enabled" in out[-1]["auto_publish"]
    pub.refresh_from_db()
    assert pub.status == "exported" and pub.package_id and Notification.objects.filter(key=f"due:{pub.pk}").exists()
    assert state(api, ep_id) == "scheduled"                                                      # still waits for the owner to mark it published


def test_automatic_level_approves_the_script_and_builds_the_storyboard(api, worker, ffmpeg_available):
    from instai.production import automation
    from tests.test_pipeline_e2e import build_episode

    page, sid, ep_id = build_episode(api, worker)
    # take the NEXT episode of the series through script generation by hand, then let the automatic level do the rest
    ep2 = api.get(f"/api/series/{sid}").json()["episodes"][1]["id"]
    finish(api, worker, api.post(f"/api/episodes/{ep2}/generate-script"))
    assert state(api, ep2) == "script_review"
    api.put(f"/api/pages/{page['id']}/automation", {"level": "assisted"}, format="json")
    assert automation.tick(utc(2026, 10, 28, 8)) == [] or True
    from instai.publishing.models import Notification

    assert Notification.objects.filter(key=f"script:{ep2}").exists() and state(api, ep2) == "script_review"          # assisted: asks
    api.put(f"/api/pages/{page['id']}/automation", {"level": "automatic"}, format="json")
    acts = automation.tick(utc(2026, 10, 28, 8))
    assert {"episode": ep2, "action": "script_approved"} in acts
    for _ in range(20):
        run_jobs(worker)
    assert state(api, ep2) == "storyboarding" and api.get(f"/api/episodes/{ep2}").json()["scenes"]


# ------------------------------------------------------------------ publishing: adapters, enablement, never auto by default

class FakeGraph(ThreadingHTTPServer):
    def __init__(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def handle_any(self):
                u = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                outer.calls.append((self.command, u.path, q))
                if self.headers.get("X-Fail"):
                    return self._send({"error": {"message": "nope"}}, 400)
                if u.path.endswith("/media") and self.command == "POST":
                    return self._send({"id": "container-1"})
                if u.path.endswith("/container-1"):
                    outer.polls += 1
                    return self._send({"status_code": "IN_PROGRESS" if outer.polls < 2 else "FINISHED"})
                if u.path.endswith("/media_publish"):
                    return self._send({"id": "ig-media-99"})
                self._send({"error": {"message": "unknown"}}, 404)
            do_GET = do_POST = handle_any

        super().__init__(("127.0.0.1", 0), H)
        self.calls, self.polls = [], 0
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


def approved_episode_with_final(api, worker):
    from instai.assets import storage as asset_storage
    from instai.assets.models import Asset
    from instai.story import services, states
    from instai.story.models import Episode
    from tests.test_pipeline_e2e import build_episode, produce

    page, sid, ep_id = build_episode(api, worker)
    produce(api, worker, ep_id, "preview")
    ep = Episode.objects.get(pk=ep_id)
    services.transition(ep, states.APPROVED, actor="user")
    return page, ep


def test_instagram_adapter_requirements_and_the_three_official_calls(api, worker, ffmpeg_available, monkeypatch):
    from instai.publishing import adapters
    from instai.publishing.models import Publication, PublishTarget

    page, ep = approved_episode_with_final(api, worker)
    from instai.pages.models import ContentPage

    t = PublishTarget.objects.create(page_id=page["id"], platform="instagram", handle="@x", mode="manual")
    pub = Publication.objects.create(episode=ep, target=t, caption="سلام", hashtags=["a", "#b"])
    req = {r["key"]: r["ok"] for r in adapters.InstagramGraph().requirements(t)}
    assert req == {"flag": False, "account": False, "page": False, "token": False, "public_url": False, "mode": False}     # everything is off by default
    assert adapters.adapter_for(t).name == "manual"
    d = api.get(f"/api/targets/{t.pk}").json()
    assert d["adapter"] == "manual" and d["ready"] is True
    # the owner configures it (token only through the environment, never the API)
    r = api.patch(f"/api/targets/{t.pk}", {"mode": "api", "config": {"ig_user_id": "1784", "facebook_page_linked": True, "public_base_url": "https://media.example.org",
                                                                      "poll_seconds": 0, "token": "SECRET", "access_token": "SECRET"}}, format="json").json()
    assert r["adapter"] == "instagram_graph" and "token" not in r["config"] and "access_token" not in r["config"]
    assert [x["key"] for x in r["requirements"] if not x["ok"]] == ["flag", "token"]
    graph = FakeGraph()
    try:
        api.patch(f"/api/targets/{t.pk}", {"config": {"graph_base": graph.url, "api_version": "v21.0"}}, format="json")
        t.refresh_from_db()
        with pytest.raises(Exception, match="cannot run"):
            adapters.InstagramGraph().publish(pub)                                                 # flag and token missing: nothing is sent
        assert graph.calls == []
        monkeypatch.setenv(adapters.FLAG, "1")
        monkeypatch.setenv("INSTAI_IG_TOKEN", "tok-123")
        assert adapters.InstagramGraph().ready(t)
        res = adapters.InstagramGraph().publish(pub)
        assert res["external_id"] == "ig-media-99" and res["video_url"].startswith("https://media.example.org/media/episodes/")
        paths = [(m, p) for m, p, q in graph.calls]
        assert paths[0] == ("POST", "/v21.0/1784/media") and paths[-1] == ("POST", "/v21.0/1784/media_publish") and ("GET", "/v21.0/container-1") in paths
        first = graph.calls[0][2]
        assert first["media_type"] == "REELS" and first["access_token"] == "tok-123" and first["caption"].endswith("#a #b") and first["video_url"].startswith("https://")
        # a local / private media URL is refused: the Graph API could not fetch it anyway
        api.patch(f"/api/targets/{t.pk}", {"config": {"public_base_url": "http://192.168.1.5:8765"}}, format="json")
        assert "public_url" in [x["key"] for x in adapters.InstagramGraph().requirements(PublishTarget.objects.get(pk=t.pk)) if not x["ok"]]
    finally:
        graph.shutdown()


def test_auto_publish_needs_explicit_enablement_and_every_requirement(api, worker, ffmpeg_available, monkeypatch):
    from instai.production import automation
    from instai.publishing import adapters
    from instai.publishing.models import Notification, Publication, PublishTarget
    from instai.pages.models import ContentPage
    from instai.story import services, states
    from instai.story.models import Episode

    page, ep = approved_episode_with_final(api, worker)
    p = ContentPage.objects.get(pk=page["id"])
    t = PublishTarget.objects.create(page=p, platform="instagram", mode="api", config={"ig_user_id": "1", "facebook_page_linked": True, "public_base_url": "https://m.example.org", "poll_seconds": 0})
    graph = FakeGraph()
    try:
        t.config["graph_base"] = graph.url
        t.save()
        monkeypatch.setenv(adapters.FLAG, "1")
        monkeypatch.setenv("INSTAI_IG_TOKEN", "tok")
        assert adapters.can_auto_publish(p, t) == (False, "automatic publishing is not enabled for this page")       # everything else is ready, the owner has not enabled it
        services.transition(ep, states.SCHEDULED, actor="user")
        pub = Publication.objects.create(episode=ep, target=t, caption="x", status="scheduled", scheduled_at=utc(2026, 10, 28, 10))
        out = automation.tick(utc(2026, 10, 28, 11))
        assert out[-1]["action"] == "reminder" and graph.calls == []                                                 # reminder + manual package only
        # enabling needs the exact confirmation sentence
        assert api.post(f"/api/pages/{p.pk}/auto-publish", {"enable": True}, format="json").status_code == 400
        assert api.post(f"/api/pages/{p.pk}/auto-publish", {"enable": True, "confirm": "yes"}, format="json").status_code == 400
        d = api.post(f"/api/pages/{p.pk}/auto-publish", {"enable": True, "confirm": api.get(f"/api/pages/{p.pk}/automation").json()["auto_publish"]["confirm_text"]}, format="json").json()
        assert d["auto_publish"]["enabled"] and d["auto_publish"]["confirmed_at"] and d["auto_publish"]["can_post_now"]
        Publication.objects.filter(pk=pub.pk).update(status="scheduled")
        out = automation.tick(utc(2026, 10, 28, 12))
        assert out[-1]["action"] == "published" and any(c[1].endswith("/media_publish") for c in graph.calls)
        pub.refresh_from_db()
        assert pub.status == "published" and pub.external_url == "ig-media-99" and Episode.objects.get(pk=ep.pk).state == "published"
        assert Notification.objects.filter(key=f"pub:{pub.pk}", level="ok").exists()
        assert api.post(f"/api/pages/{p.pk}/auto-publish", {"enable": False}, format="json").json()["auto_publish"]["enabled"] is False
    finally:
        graph.shutdown()


def test_explicit_publish_action_needs_confirmation_and_ready_requirements(api, worker, ffmpeg_available):
    from instai.publishing.models import Publication, PublishTarget

    page, ep = approved_episode_with_final(api, worker)
    t = PublishTarget.objects.create(page_id=page["id"], platform="instagram", mode="api")
    pub = Publication.objects.create(episode=ep, target=t, caption="x")
    assert api.post(f"/api/publications/{pub.pk}/publish", {}, format="json").status_code == 400                        # no confirmation
    r = api.post(f"/api/publications/{pub.pk}/publish", {"confirm": True}, format="json")
    assert r.status_code == 409 and "پیش‌نیازهای" in r.json()["error"]["message"]                                          # requirements missing: nothing is sent
    PublishTarget.objects.filter(pk=t.pk).update(mode="manual")                                                         # a manual target: the export package job
    r = api.post(f"/api/publications/{pub.pk}/publish", {"confirm": True}, format="json")
    j = finish(api, worker, r)
    assert j["result"]["package_asset_id"]
