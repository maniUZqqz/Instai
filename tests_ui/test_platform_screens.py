"""Platform screens (0.6.0) in a real browser against the real server + worker: the version badge on EVERY screen (studio, /lab, the not-found
page), the processing queue (a job waiting for the offline second PC), the computers report (timeline, load, errors in plain words, logs,
date filter, CSV links) and the scheduled downloads - Persian RTL and English LTR, desktop and phone width.

Run:  python -m pytest tests_ui/test_platform_screens.py -q   (needs playwright + pytest and Django in the same Python; uses Chrome or Edge if
Playwright has no chromium of its own).  Screenshots go to $INSTAI_UI_SHOTS (default: the temp folder).
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = ROOT / ".venv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 390, "height": 844}}
SHOTS = Path(os.environ.get("INSTAI_UI_SHOTS", tempfile.gettempdir())) / "instai-ui-shots"
PERSIAN = re.compile(r"[؀-ۿ]")
SCREENS = ["/", "/lab", "/queue", "/report", "/downloads", "/whats-new", "/monitor", "/models", "/no-such-page"]

SEED = textwrap.dedent('''
    import os, django
    os.environ["DJANGO_SETTINGS_MODULE"] = "instai.settings"
    django.setup()
    from datetime import timedelta
    from django.utils import timezone
    from instai.jobs import queue, workers
    from instai.jobs.models import Job, JobLog, RemoteTask, WorkerNode
    from instai.ops.models import NodeEvent, NodeSample, NodeSession
    now = timezone.now()
    b = WorkerNode.objects.create(name="PC-B", token_hash=workers.hash_secret("x"), enabled=True, last_seen=now - timedelta(hours=2),
                                  capabilities=["gpu", "comfy:flux_dev_fp8_t2i", "downloads"], vram_total_mb=4096, vram_free_mb=3000, gpu_name="GTX 1650",
                                  info={"host": "PC-B", "instai": "0.5.0"})
    for node, start_h, end_h, ver in (("PC-B", 70, 60, "0.5.0"), ("PC-B", 40, 30, "0.5.0"), ("PC-B", 20, 2, "0.5.0")):
        NodeSession.objects.create(node=node, started_at=now - timedelta(hours=start_h), last_seen=now - timedelta(hours=end_h), ended_at=now - timedelta(hours=end_h), version=ver,
                                   info={"gpu_name": "GTX 1650", "host": "PC-B"})
        NodeEvent.objects.create(node=node, at=now - timedelta(hours=start_h), kind="online", data={"version": ver})
        NodeEvent.objects.create(node=node, at=now - timedelta(hours=end_h), kind="offline", level="warning")
    NodeSession.objects.create(node="local", started_at=now - timedelta(hours=72), last_seen=now - timedelta(hours=1), ended_at=now - timedelta(hours=1), version="0.5.0")
    NodeSession.objects.create(node="local", started_at=now - timedelta(minutes=50), last_seen=now + timedelta(hours=2), version="0.6.0", info={"gpu_name": "RTX 3060"})
    for i in range(0, 600, 5):
        t = now - timedelta(hours=40) + timedelta(minutes=i * 4)
        NodeSample.objects.create(node="PC-B", at=t, gpu_util=20 + (i * 7) % 70, gpu_temp=55 + i % 20, vram_used_mb=1000 + (i * 13) % 2800, vram_total_mb=4096,
                                  ram_used_mb=9000 + (i * 17) % 6000, ram_total_mb=23000, disk_free_gb=120 - i / 100, disk_total_gb=500)
        NodeSample.objects.create(node="local", at=t, gpu_util=10 + (i * 11) % 85, gpu_temp=50 + i % 25, vram_used_mb=2000 + (i * 29) % 9000, vram_total_mb=12288,
                                  ram_used_mb=10000 + (i * 19) % 9000, ram_total_mb=24000, disk_free_gb=300 - i / 50, disk_total_gb=500)
    NodeEvent.objects.create(node="PC-B", at=now - timedelta(hours=19), level="warning", kind="log", message="ComfyUI did not answer within 60 s; retrying")
    def mk(kind, status, node="", dur=60, wait=8, error="", code="", dev=None, ago=5):
        j = Job.objects.create(kind=kind, title=kind, status=status, payload={}, resource="gpu", node=node, error=error, error_code=code)
        t0 = now - timedelta(hours=ago)
        Job.objects.filter(pk=j.pk).update(created_at=t0, ready_at=t0, first_started_at=t0 + timedelta(seconds=wait), started_at=t0 + timedelta(seconds=wait),
            finished_at=t0 + timedelta(seconds=wait + dur), duration_sec=dur, gpu_seconds=dur * 0.8, devices=dev or {(node or "local"): dur * 0.8})
        JobLog.objects.create(job=j, level="info", message="started (attempt 1/3) by w")
        if status == "failed":
            JobLog.objects.create(job=j, level="error", message="failed: " + error[:120])
        return j
    for i in range(6): mk("prod.keyframes", "succeeded", dur=90 + i * 10, wait=5 + i * 3, ago=30 - i)
    for i in range(3): mk("prod.clips", "succeeded", node="PC-B", dur=400 + i * 50, wait=40, ago=25 - i, dev={"PC-B": 380, "local": 20})
    mk("prod.tts", "succeeded", dur=12, ago=20)
    mk("prod.clips", "failed", node="PC-B", dur=30, error="CUDA out of memory. Tried to allocate 2.00 GiB", code="gpu_oom", ago=18)
    mk("story.script", "failed", dur=4, error="Ollama is not reachable at http://127.0.0.1:11434", code="ollama_down", ago=12)
    mk("prod.assemble", "cancelled", dur=3, ago=10)
    RemoteTask.objects.create(kind="comfy.graph", status="succeeded", worker=b, seconds=300)
    RemoteTask.objects.create(kind="comfy.graph", status="failed", worker=b, error="worker stopped sending heartbeats", error_code="worker_lost")
    w = queue.enqueue("prod.clips", {}, resource="gpu", title="waiting clip")
    Job.objects.filter(pk=w.pk).update(wait_code="worker_offline", waiting_since=now - timedelta(minutes=12), deferrals=9, run_after=now + timedelta(seconds=45),
        waiting_reason="رایانهٔ «PC-B» خاموش یا بدون ارتباط است؛ کار می‌ماند و همین که روشن شد خودش انجام می‌شود.")
    q1 = queue.enqueue("prod.keyframes", {}, resource="gpu", title="turn 1")
    q2 = queue.enqueue("prod.keyframes", {}, resource="gpu", title="turn 2")
    queue.enqueue("downloads.run", {"packages": ["ffmpeg"], "target": "local", "target_name": "local"}, title="دانلود: ffmpeg", window="02:00-07:00",
                  run_after=now + timedelta(hours=3))
    print("seeded")
''')


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base():
    external = os.environ.get("INSTAI_UI_PLATFORM_BASE", "").rstrip("/")   # a server that already runs with the SEED data below (e.g. on another machine, reached through a tunnel)
    if external:
        yield external
        return
    data = tempfile.mkdtemp(prefix="instai-ui-platform-")
    port = free_port()
    env = {**os.environ, "INSTAI_DATA_DIR": os.path.join(data, "data"), "INSTAI_PORT": str(port), "INSTAI_SECRET_KEY": "ui-test-key", "INSTAI_LLM_PROVIDER": "fake",
           "INSTAI_TTS_ENGINE": "fake", "INSTAI_IMAGE_ENGINE": "placeholder", "INSTAI_RESEARCH_FETCH": "fake", "INSTAI_SFX_ENGINE": "fake", "INSTAI_MUSIC_ENGINE": "fake",
           "INSTAI_OLLAMA_URL": "http://127.0.0.1:9", "INSTAI_COMFYUI_URL": "http://127.0.0.1:9", "INSTAI_SCAN_DEFAULTS": "0", "PYTHONIOENCODING": "utf-8"}
    env.pop("INSTAI_TESTING", None)
    # only the server: with a worker running it would take the seeded jobs (and run their real handlers); this PC's "online" is seeded instead
    procs = [subprocess.Popen([str(PY), "-m", "instai.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
    url = f"http://127.0.0.1:{port}"
    end = time.time() + 240
    while time.time() < end:
        try:
            urllib.request.urlopen(url + "/api/health", timeout=2)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    else:
        for p in procs:
            p.kill()
        raise RuntimeError("server did not start")
    r = subprocess.run([str(PY), "-c", SEED], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert "seeded" in r.stdout, r.stderr[-1500:]
    yield url
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(15)
        except subprocess.TimeoutExpired:
            p.kill()


@pytest.fixture(scope="module")
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = None
        for attempt in (lambda: p.chromium.launch(), lambda: p.chromium.launch(channel="chrome"), lambda: p.chromium.launch(channel="msedge")):
            try:
                b = attempt()
                break
            except Exception:  # noqa: BLE001
                continue
        if b is None:
            pytest.skip("no browser available for Playwright")
        yield b
        b.close()


def open_page(browser, base, size, path, lang="fa", wait="main"):
    ctx = browser.new_context(viewport=VIEWPORTS[size], locale="fa-IR" if lang == "fa" else "en-US", has_touch=(size == "phone"))
    ctx.add_init_script(f"try {{ localStorage.setItem('instai.lang', '{lang}'); sessionStorage.clear(); }} catch (e) {{}}")
    page = ctx.new_page()
    problems: list[str] = []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "favicon" not in r.url and "no-such-page" not in r.url else None)
    page.goto(base + path, wait_until="domcontentloaded")
    page.wait_for_selector(wait, timeout=20000)
    page.wait_for_timeout(900)
    return ctx, page, problems


def shot(page, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / name), full_page=True)


def overflowers(page) -> list[str]:
    """Elements that stick out of the viewport (not counting what sits inside a scrolling .table-wrap / .log-view): the cause of a sideways page scroll."""
    return page.evaluate("""() => {
      const iw = window.innerWidth, out = [];
      for (const el of document.querySelectorAll('body *')) {
        if (el.closest('.table-wrap, .log-view, aside.sidebar')) continue;   // the sidebar is an off-screen drawer on a phone, by design
        const r = el.getBoundingClientRect();
        if (r.width && (r.right > iw + 1 || r.left < -1)) out.push(el.tagName.toLowerCase() + '.' + String(el.className).split(' ').join('.') + ' [' + Math.round(r.left) + ',' + Math.round(r.right) + ']');
      }
      return out.slice(0, 6);
    }""")


def digits(s: str) -> str:
    return (s or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


@pytest.mark.parametrize("size", ["desktop", "phone"])
@pytest.mark.parametrize("lang", ["fa", "en"])
def test_the_version_badge_is_in_the_corner_of_every_screen(browser, base, size, lang):
    bad = []
    for path in SCREENS:
        ctx, page, problems = open_page(browser, base, size, path, lang)
        try:
            badge = page.locator("[data-testid=version-badge]")
            if badge.count() != 1:
                bad.append(f"{path}: {badge.count()} badges")
                continue
            if badge.inner_text().strip() != f"v{VERSION}":
                bad.append(f"{path}: text {badge.inner_text()!r}")
            box = badge.bounding_box()
            vw, vh = VIEWPORTS[size]["width"], VIEWPORTS[size]["height"]
            if not box or box["y"] + box["height"] > vh + 1 or box["x"] + box["width"] > vw + 1 or box["x"] < 0:
                bad.append(f"{path}: badge outside the viewport {box}")
            if problems:
                bad.append(f"{path}: {problems[:2]}")
        finally:
            ctx.close()
    assert bad == [], bad


def test_clicking_the_badge_opens_whats_new_in_a_new_tab(browser, base):
    ctx, page, _ = open_page(browser, base, "desktop", "/")
    try:
        with ctx.expect_page() as new:
            page.locator("[data-testid=version-badge]").click()
        tab = new.value
        tab.wait_for_load_state("domcontentloaded")
        tab.wait_for_selector("main h1", timeout=30000)
        tab.wait_for_timeout(1500)
        assert tab.url.endswith("/whats-new")
        text = tab.locator("main").inner_text()
        assert PERSIAN.search(text) and f"v{VERSION}" in text and "0.1.0" in text
        shot(tab, "platform-whats-new-fa.png")
    finally:
        ctx.close()


@pytest.mark.parametrize("size", ["phone", "desktop"])      # desktop last: it cancels the waiting job
def test_queue_page_shows_why_a_job_waits_and_the_header_counter(browser, base, size):
    ctx, page, problems = open_page(browser, base, size, "/queue", wait="[data-testid^=job-]")
    try:
        html = page.locator("html")
        assert html.get_attribute("dir") == "rtl"
        text = page.locator("main").inner_text()
        assert "صفِ پردازش" in text and "ناموفق نمی‌شود" in text, "the page explains that waiting is not failing"
        waiting = page.locator("tr.q-waiting_node")
        assert waiting.count() == 1
        wt = waiting.inner_text()
        assert "PC-B" in wt and "منتظر" in wt and "۱۲" in wt, wt
        assert "نفر ۱ام" in text and "نفر ۲ام" in text, "place in line"
        assert "زمان‌بندی‌شده" in text or "بازهٔ شبانه" in text
        page.wait_for_selector("[data-testid=queue-badge]", timeout=15000)
        assert "منتظر" in page.locator("[data-testid=queue-badge]").inner_text() or page.locator("[data-testid=queue-badge]").get_attribute("aria-label")
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert sw <= iw + 1, f"horizontal scroll {sw} > {iw}: {overflowers(page)}"
        offline = page.locator("[data-testid=node-PC-B]").inner_text()
        assert "آفلاین" in offline
        shot(page, f"platform-queue-{size}.png")
        if size == "desktop":              # cancel the waiting job from the page: it ends at once, no answer from PC B needed
            waiting.locator("button", has_text="لغو").click()
            page.locator(".modal button.danger, .modal .btn.danger").first.click()
            page.wait_for_timeout(1500)
            page.locator("button[role=tab]", has_text="ناموفق و لغوشده").click()
            assert page.locator("tr.q-cancelled").count() >= 1
        assert problems == [], problems
    finally:
        ctx.close()


@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_report_page_numbers_timeline_errors_logs_and_date_filter(browser, base, size):
    ctx, page, problems = open_page(browser, base, size, "/report", wait="[data-testid=report-node-PC-B]")
    try:
        main = page.locator("main").inner_text()
        assert "گزارش کامپیوترهای پردازش" in main
        assert page.locator("[data-testid=report-node-local]").count() == 1 and page.locator("[data-testid=report-node-PC-B]").count() == 1
        b = page.locator("[data-testid=report-node-PC-B]")
        bt = b.inner_text()
        assert "GTX 1650" in bt and ("آنلاین بود" in bt) and "ساخت کلیپ‌های ویدئویی" in bt
        assert page.locator(".tl").count() == 2 and page.locator(".tl > i").count() >= 3, "online stretches are drawn"
        assert page.locator(".spark-svg").count() >= 6, "load charts"
        # the old version of PC-B is called out
        assert "نسخهٔ 0.5.0" in main or "0.5.0" in main
        # errors in plain words
        assert page.locator("[data-testid=error-out_of_memory]").count() == 1 and page.locator("[data-testid=error-ollama_down]").count() == 1
        assert "حافظهٔ کارت گرافیک" in page.locator("[data-testid=error-out_of_memory]").inner_text()
        # logs with search
        page.get_by_label("جست‌وجو در لاگ").fill("CUDA")
        page.wait_for_timeout(1200)
        logs = page.locator("[role=log]").inner_text()
        assert "CUDA" in logs and "started (attempt" not in logs
        # date filter: "today" has no seeded history of the second PC
        page.locator("div.seg button", has_text="امروز").click()
        page.wait_for_timeout(1500)
        assert page.locator("[data-testid=report-node-local]").count() == 1
        # CSV links
        page.locator("div.seg button", has_text="۷ روز").click()
        hrefs = page.locator("a[href*='export.csv']").evaluate_all("els => els.map(e => e.getAttribute('href'))")
        assert len(hrefs) == 7 and any("section=jobs" in h for h in hrefs)
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert sw <= iw + 1, f"horizontal scroll {sw} > {iw}: {overflowers(page)}"
        shot(page, f"platform-report-{size}.png")
        assert problems == [], problems
        with page.expect_download() as dl:
            page.locator("a[href*='section=jobs']").first.click()
        assert dl.value.suggested_filename.endswith(".csv")
    finally:
        ctx.close()


def test_report_page_in_english_is_ltr_and_has_no_persian_chrome(browser, base):
    ctx, page, problems = open_page(browser, base, "desktop", "/report", lang="en", wait="[data-testid=report-node-PC-B]")
    try:
        assert page.locator("html").get_attribute("dir") == "ltr"
        txt = page.locator("main").inner_text()
        assert "Processing computers report" in txt and "Average run time" in txt
        persian_lines = [ln for ln in txt.splitlines() if PERSIAN.search(ln)]
        assert all("کامپیوتر" in ln for ln in persian_lines) or persian_lines == [], persian_lines[:5]    # only server-provided computer names may stay Persian
        assert problems == [], problems
        shot(page, "platform-report-en.png")
    finally:
        ctx.close()


def test_downloads_page_schedules_a_download_for_the_night(browser, base):
    ctx, page, problems = open_page(browser, base, "desktop", "/downloads", wait="[data-testid^=dl-]")
    try:
        text = page.locator("main").inner_text()
        assert "دانلودها و زمان‌بندی" in text and "ffmpeg" in text
        card = page.locator("section", has=page.get_by_role("heading", name="دانلود تازه", exact=True))     # the curated library card above has its own schedule choice
        card.get_by_label("در بازهٔ شبانه").check()
        card.get_by_role("button", name="ثبت دانلود").first.click()
        page.wait_for_function("document.querySelectorAll('[data-testid^=dl-]').length >= 2", timeout=30000)   # (the server first asks the downloader what exists)
        assert page.locator("[data-testid^=dl-]").count() >= 2
        assert "بازهٔ شبانه" in page.locator("main").inner_text()
        r = json.loads(urllib.request.urlopen(base + "/api/downloads/queue", timeout=10).read())
        assert any(j["window"] == "02:00-07:00" for j in r["jobs"])
        shot(page, "platform-downloads-fa.png")
        assert problems == [], problems
    finally:
        ctx.close()
