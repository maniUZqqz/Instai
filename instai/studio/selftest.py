"""Automatic acceptance checks of the animation-studio pipeline (stick-figure kit, character consistency, ladder, choice stories, mini-series, and - when the GPU PC is on - the
real text model, the multi-reference identity workflow and the vision check).

The owner asked that nothing be left for him to do once the GPU PC is on: every feature must start working AND be tested by itself. So:

* CPU checks need nothing but Python and run once for every new version (or when a ready-made story / season changes): `auto_queue()` is called from the automation tick.
* GPU checks run by themselves as soon as the machine can do them (an Ollama model answers / ComfyUI has the workflow and its model files), at most once every six hours,
  at low priority, and again after every new version. A check whose models are not installed is "skipped" with the reason and what to do - never reported as "ok".
* Every result is kept in `data/selftest/studio.json` and shown on the Studio ladder screen ("Automatic self-test"); a failing check is a result, never a crashed job.

Switch off with `INSTAI_STUDIO_SELFTEST_AUTO=0` or the setting `studio_selftest_auto`. Nothing here writes to the owner's database or publishes anything.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from instai.jobs import describe
from instai.jobs.registry import handler

log = logging.getLogger("instai.selftest")

describe.KIND_TEXT.update({"studio.selftest": ("آزمون خودکار استودیو", "Automatic studio self-test")})

AUTO_EVERY_S = 300
GPU_RETRY_S = 6 * 3600
GPU_REFRESH_S = 7 * 24 * 3600
_LAST_AUTO = [0.0]


def report_path() -> Path:
    return Path(settings.DATA_DIR) / "selftest" / "studio.json"


def load_report() -> dict | None:
    try:
        return json.loads(report_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_report(rep: dict) -> None:
    p = report_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def stamp() -> str:
    """Changes with the version and with the ready-made stories / seasons / ladder catalogue, so new content is tested again by itself."""
    from instai.channel import season_templates
    from instai.choice import story_templates
    from instai.studio import ladder_stages
    from instai.version import read_version

    blob = json.dumps([story_templates.TEMPLATES, season_templates.TEMPLATES, ladder_stages.STAGES], ensure_ascii=False, sort_keys=True, default=str)
    return f"{read_version()}-{hashlib.sha256(blob.encode()).hexdigest()[:10]}"


def _r(verdict: str, fa: str, en: str, **metrics) -> dict:
    return {"verdict": verdict, "reason_fa": fa, "reason_en": en, "metrics": metrics}


# ------------------------------------------------------------------------------------------------------------------------------ CPU checks

def _sample_spec(name: str = "رامین") -> dict:
    from instai.choice import story_templates
    from instai.render.stick import spec as stick_spec

    row = next(c for t in story_templates.TEMPLATES for c in t["cast"] if c["name"] == name)
    return stick_spec.normalize(row["spec"], name=name)


def check_stick_kit(work: Path) -> dict:
    from PIL import Image

    from instai.render.stick import compose

    spec = _sample_spec()
    sheet = work / "sheet.png"
    compose.model_sheet(spec, sheet, work / "w", title="رامین", language="fa")
    scene = {"aspect": "4:5", "background": "cell", "caption": {"text": "پست ۳ - شب اول در زندان؛ باید فرار کنی!", "position": "top"},
             "actors": [{"spec": spec, "x": 0.5, "y": 0.9, "height": 0.52, "pose": "think", "expression": "scared"}], "bubbles": [{"actor": 0, "text": "الان چه کار کنم؟", "kind": "say"}]}
    a, b = work / "a.png", work / "b.png"
    compose.compose_still(scene, a, work / "w")
    compose.compose_still(scene, b, work / "w")
    with Image.open(sheet) as s, Image.open(a) as ia:
        sz_sheet, sz_still = s.size, ia.size
        colours = len(ia.convert("RGB").resize((96, 120)).getcolors(20000) or [])
    same = hashlib.sha256(a.read_bytes()).hexdigest() == hashlib.sha256(b.read_bytes()).hexdigest()
    ok = sz_still == (1080, 1350) and sz_sheet[0] >= 1500 and colours > 12 and same
    return _r("ok" if ok else "fail", "قلم آدمک چوبی: برگهٔ مدل و یک صحنه با متن فارسی کشیده شد و دو بار کشیدنش یک تصویر داد." if ok else "قلم آدمک چوبی درست کار نکرد.",
              "Stick kit: the model sheet and a scene with Persian text were drawn and drawing twice gave the same picture." if ok else "The stick kit did not work.",
              sheet=list(sz_sheet), still=list(sz_still), colours=colours, deterministic=same)


def check_identity_colour_key(work: Path) -> dict:
    from instai.identity import check
    from instai.render.stick import compose, spec as stick_spec

    spec = _sample_spec()
    sig = check.signature_colours(stick_spec.palette(spec))
    found = []
    for k, pose in enumerate(("stand", "run_a", "sit")):
        p = work / f"id{k}.png"
        compose.compose_still({"aspect": "4:5", "background": "plain", "actors": [{"spec": spec, "x": 0.5, "y": 0.9, "height": 0.5, "pose": pose, "expression": "happy"}]}, p, work / "w")
        from PIL import Image

        with Image.open(p) as im:
            rows = check.colour_shares(im, sig)
        found.append(sum(1 for r in rows if r["found"]) / max(1, len(rows)))
    wrong = dict(spec, limb_colour="#e0568f", neck_colour="#8a4fd1", hat_colour="#2e9e5b")
    p = work / "wrong.png"
    compose.compose_still({"aspect": "4:5", "background": "plain", "actors": [{"spec": wrong, "x": 0.5, "y": 0.9, "height": 0.5, "pose": "stand", "expression": "happy"}]}, p, work / "w")
    with Image.open(p) as im:
        bad = [r["found"] for r in check.colour_shares(im, sig)]
    ok = min(found) >= check.PALETTE_OK and sum(bad) / max(1, len(bad)) < check.PALETTE_OK
    return _r("ok" if ok else "fail", "بررسی ثبات شخصیت: رنگ‌های هویت در هر سه ژست دیده شد و شخصیتِ با رنگ اشتباه رد شد." if ok else "بررسی ثبات شخصیت درست تشخیص نداد.",
              "Consistency check: the identity colours were found in all three poses and a wrongly coloured character was rejected." if ok else "The consistency check did not separate right from wrong.",
              poses=[round(x, 2) for x in found], wrong=[bool(x) for x in bad])


def check_choice_stories(work: Path) -> dict:
    from instai.choice import graph as G
    from instai.choice import story_templates

    bad: list[str] = []
    for t in story_templates.TEMPLATES:
        nodes = [G.new_node(p["id"], title=p["title"], text=p["text"], kind=p["kind"], ending=p["ending"], choices=p["choices"]) for p in t["posts"]]
        v = G.validate(G.renumber(G.normalize({"nodes": nodes}))[0])
        if not v["ok"]:
            bad.append(t["key"])
    for n in (6, 10, 14, 24, 40, 60):
        nodes = [G.new_node(p["id"], choices=p["choices"], kind=p["kind"], ending=p["ending"], text=p["text"]) for p in G.skeleton_plan(n)["posts"]]
        g = G.renumber(G.normalize({"nodes": nodes}))[0]
        if len(g["nodes"]) != n or not G.validate(g)["ok"]:
            bad.append(f"skeleton{n}")
    ok = not bad
    return _r("ok" if ok else "fail", f"داستان‌های انتخابی: {len(story_templates.TEMPLATES)} داستان آماده و برنامه‌ریز پایه همه معتبرند (بدون بن‌بست، شمارهٔ رو به جلو)." if ok else "نمودار این داستان‌ها معتبر نیست: " + "، ".join(bad),
              f"Choice stories: the {len(story_templates.TEMPLATES)} ready-made stories and the basic planner are all valid (no dead ends, forward numbering)." if ok else "These graphs are invalid: " + ", ".join(bad),
              stories=len(story_templates.TEMPLATES), invalid=bad)


def check_mini_series(work: Path) -> dict:
    from instai.channel import conventions, planner, season_templates

    bad: list[str] = []
    for t in season_templates.TEMPLATES:
        g = conventions.genre(t["genre"])
        v = planner.validate(season_templates.plan_of(t)["episodes"], cast_names=[c["name"] for c in t["cast"]], runtime=t["runtime_sec"], genre_runtime=(g["runtime"]["min"], g["runtime"]["max"]))
        if not v["ok"] or v["warnings"]:
            bad.append(t["key"])
    for n in (2, 6, 12, 24):
        if not planner.validate(planner.skeleton_season(n, 30, characters=["الف"])["episodes"], cast_names=["الف"])["ok"]:
            bad.append(f"skeleton{n}")
    ok = not bad
    return _r("ok" if ok else "fail", f"مینی‌سریال: {len(season_templates.TEMPLATES)} فصل آماده بدون خطا و هشدار تأیید شد (قلاب، پایان باز، رشته‌های بسته)." if ok else "این فصل‌ها اشکال دارند: " + "، ".join(bad),
              f"Mini-series: the {len(season_templates.TEMPLATES)} ready-made seasons pass with no error or warning (hooks, cliffhangers, closed threads)." if ok else "These seasons have problems: " + ", ".join(bad),
              seasons=len(season_templates.TEMPLATES), invalid=bad)


def check_ladder(work: Path) -> dict:
    from instai.agents import pipeline_fake
    from instai.agents.pipeline_roles import ROLES
    from instai.studio import ladder_stages as S

    keys = [s["key"] for s in S.STAGES]
    problems: list[str] = []
    for i, s in enumerate(S.STAGES):
        for n in s["needs"]:
            if n not in keys or keys.index(n) >= i:
                problems.append(f"{s['key']} needs {n}")
        if s["gen"] == "llm" and s["task"] not in ROLES:
            problems.append(f"{s['key']}: no role {s['task']}")
    fake_ok = all(callable(getattr(pipeline_fake, s["task"], None)) for s in S.STAGES if s["gen"] == "llm")
    ok = not problems and fake_ok and len(keys) == 21
    return _r("ok" if ok else "fail", f"نردبان استودیو: {len(keys)} مرحله، ترتیب پیش‌نیازها درست و برای هر مرحلهٔ مدلی نقش نوشته شده." if ok else "نردبان استودیو اشکال دارد: " + "؛ ".join(problems),
              f"Studio ladder: {len(keys)} stages, prerequisites in order and a role for every model-written stage." if ok else "The ladder has problems: " + "; ".join(problems), stages=len(keys), problems=problems)


# ------------------------------------------------------------------------------------------------------------------------------ GPU / model checks

def _ollama_ok() -> tuple[bool, list[str]]:
    from instai.core import settings_store
    from instai.providers.ollama import OllamaProvider

    h = OllamaProvider(str(settings_store.effective("ollama_url")), "x").health()
    return bool(h.get("ok")), list(h.get("models") or [])


def check_text_model(ctx, work: Path) -> dict:
    """A real text model writes a logline and a small choice-story graph; the answer is checked by the same validators the owner's own work must pass."""
    from instai.agents import llm
    from instai.agents import pipeline_roles as roles
    from instai.agents.runner import AgentError
    from instai.choice import graph as G
    from instai.gpu.arbiter import ARBITER
    from instai.providers.base import ProviderError

    prov = llm.resolve(None, "choice_plan")
    if prov.name != "fake":
        up, _models = _ollama_ok() if prov.name == "ollama" else (True, [])
        if not up:
            return _r("skip", "مدل متنی در دسترس نیست؛ وقتی رایانهٔ GPU روشن شد خودکار آزمایش می‌شود.", "No text model is reachable; it is tested by itself when the GPU PC is on.")
    t0 = time.time()
    try:
        with ARBITER.hold(ctx, "llm", llm.effective_model(prov)) if prov.resource == "gpu" else _null():
            ll = roles.logline_writer({"title": "فرار", "premise": "زندانی بی‌گناهی می‌خواهد در یک شب از زندان فرار کند", "language": "fa"}, provider=prov)
            plan = roles.choice_planner({"language": "fa", "title": "فرار", "premise": "فرار از زندان در یک شب", "genre": "prison_escape", "post_count": 8, "characters": [], "tone": ""}, provider=prov)
    except (ProviderError, AgentError) as e:
        return _r("fail" if isinstance(e, AgentError) else "skip", f"مدل متنی جواب معتبر نداد: {e}" if isinstance(e, AgentError) else "مدل متنی در دسترس نبود.",
                  f"The text model gave no valid answer: {e}" if isinstance(e, AgentError) else "The text model was not reachable.")
    nodes = [G.new_node(str(p["id"]), choices=p.get("choices") or [], kind=p.get("kind") or "story", ending=p.get("ending") or "") for p in plan.data.get("posts", [])]
    valid = bool(nodes) and G.validate(G.renumber(G.normalize({"nodes": nodes}))[0])["ok"]
    secs = round(time.time() - t0, 1)
    model = getattr(plan, "model", "") or llm.effective_model(prov)
    if valid:
        return _r("ok", f"مدل «{model}» لاگ‌لاین و یک نمودار هشت‌پستی معتبر نوشت ({secs} ثانیه).", f"Model «{model}» wrote a logline and a valid eight-post graph ({secs} s).", model=model, seconds=secs, logline=str(ll.data.get("logline", ""))[:160])
    return _r("warn", f"مدل «{model}» نمودار معتبر ننوشت؛ در برنامه‌ریزی، داستان آمادهٔ همان ژانر جایگزین می‌شود.", f"Model «{model}» did not write a valid graph; planning falls back to the ready-made story of the genre.", model=model, seconds=secs)


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def check_multiref_identity(ctx, work: Path) -> dict:
    """The Qwen multi-reference workflow draws a NEW scene from two stick model sheets; each character's colour key must be visible in the result."""
    from PIL import Image

    from instai.gpu import compute
    from instai.identity import check
    from instai.production import hero
    from instai.providers.base import ProviderError
    from instai.providers.comfy.workflows import get_workflow
    from instai.render.stick import compose, spec as stick_spec

    wid = "qwen_image_edit_multiref"
    try:
        have = compute.workflow_available(wid)
    except Exception:  # noqa: BLE001
        have = False
    if not have:
        return _r("skip", "گردش‌کار چندمرجعی در دسترس نیست (ComfyUI یا مدل‌های Qwen-Image-Edit نصب نیست). در صفحهٔ «مدل‌ها» پیشنهاد «Qwen-Image-Edit» را بپذیرید؛ بعد خودکار آزمایش می‌شود.",
                  "The multi-reference workflow is not available (ComfyUI or the Qwen-Image-Edit models are missing). Accept the «Qwen-Image-Edit» offer on the Models page; it is tested by itself afterwards.", workflow=wid)
    a, b = _sample_spec("رامین"), _sample_spec("ناصر")
    for k, sp in enumerate((a, b), 1):
        compose.model_sheet(sp, work / f"ref{k}.png", work / "w", title=sp["name"], language="fa")
    prompt = ("image 1 is the model sheet of Ramin, image 2 is the model sheet of Naser. Draw Ramin and Naser together in a prison corridor, keeping each character's exact design, "
              "proportions and colours, flat vector cartoon, stick figures")
    spec = get_workflow(wid)
    inputs = {"prompt": prompt, "image": "@input:ref1.png", "image2": "@input:ref2.png", "width": 832, "height": 1472, "seed": 42}
    res = compute.run_task(ctx, "comfy.graph", {"graph": spec.build(inputs), "workflow": wid, "timeout": 1800, "expected": spec.expected_seconds},
                           inputs={"ref1.png": work / "ref1.png", "ref2.png": work / "ref2.png"})
    try:
        pics = res.of_kind(*hero.IMAGE_SUFFIX)
        if not pics:
            raise ProviderError("ComfyUI returned no image", retryable=True)
        out = work / "multiref.png"
        shutil.move(str(pics[0]), out)
    finally:
        res.cleanup()
    with Image.open(out) as im:
        size = im.size
        shares = [check.colour_shares(im, check.signature_colours(stick_spec.palette(sp))) for sp in (a, b)]
    frac = [round(sum(1 for r in rows if r["found"]) / max(1, len(rows)), 2) for rows in shares]
    big = out.stat().st_size > 50_000
    # keep the picture next to the report so the owner can look at it
    keep = report_path().parent / "multiref-sample.png"
    keep.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, keep)
    if big and min(frac) >= check.PALETTE_OK:
        return _r("ok", f"تصویر تازه ساخته شد ({size[0]}×{size[1]}) و رنگ‌های هویت هر دو شخصیت در آن دیده شد.", f"A new picture was made ({size[0]}x{size[1]}) and both characters' identity colours are visible in it.",
                  size=list(size), colours=frac, device=res.device, sample="multiref-sample.png")
    return _r("warn", f"تصویر ساخته شد ولی همهٔ رنگ‌های هویت دیده نشد (سهم رنگ‌ها: {frac}). برای آدمک‌های چوبی همان راهبرد «آدمک چوبی با کد» بهتر است.",
              f"A picture was made but not every identity colour is visible (shares {frac}). For stick figures the by-code strategy stays the better one.", size=list(size), colours=frac, device=res.device, sample="multiref-sample.png")


def check_vision(ctx, work: Path) -> dict:
    """A local vision model compares two pictures of the same stick character (different pose) and of two different characters: same must score higher."""
    from instai.core import settings_store
    from instai.identity import check
    from instai.render.stick import compose

    url = str(settings_store.effective("ollama_url"))
    model = check._vision_model(url)
    if not model:
        return _r("skip", "مدل بینایی (مثل qwen3-vl) روی Ollama پیدا نشد؛ بررسی عمیق ثبات اجرا نمی‌شود.", "No vision model (such as qwen3-vl) was found on Ollama; the deep consistency check is not run.")
    a, b = _sample_spec("رامین"), _sample_spec("ناصر")
    paths = {}
    for k, (sp, pose) in {"sheet": (a, "stand"), "same": (a, "run_a"), "other": (b, "run_a")}.items():
        paths[k] = work / f"v_{k}.png"
        compose.compose_still({"aspect": "1:1", "background": "plain", "actors": [{"spec": sp, "x": 0.5, "y": 0.9, "height": 0.7, "pose": pose, "expression": "happy"}]}, paths[k], work / "w")
    from instai.gpu.arbiter import ARBITER

    with ARBITER.hold(ctx, "llm", model):
        same = check.vision_call(paths["sheet"], paths["same"], a["name"], url, model)
        other = check.vision_call(paths["sheet"], paths["other"], a["name"], url, model)
    if same is None or other is None:
        return _r("warn", f"مدل «{model}» جواب قابل‌استفاده نداد.", f"Model «{model}» gave no usable answer.", model=model)
    ok = same["score"] > other["score"] and same["score"] >= check.VISION_OK - 2
    return _r("ok" if ok else "warn", f"مدل بینایی «{model}»: همان شخصیت با ژست دیگر {same['score']:g} و شخصیت دیگر {other['score']:g} از ۱۰ گرفت." + ("" if ok else " تفاوت قابل‌اعتماد نیست؛ این بررسی فقط نشانه است."),
              f"Vision model «{model}»: the same character in another pose scored {same['score']:g} and a different character {other['score']:g} out of 10." + ("" if ok else " The difference is not reliable; treat this check as a hint only."),
              model=model, same=same["score"], other=other["score"])


CHECKS = [
    {"key": "stick_kit", "group": "cpu", "fa": "قلم آدمک چوبی", "en": "Stick-figure kit", "fn": check_stick_kit},
    {"key": "identity_colour_key", "group": "cpu", "fa": "بررسی ثبات (کلید رنگ)", "en": "Consistency check (colour key)", "fn": check_identity_colour_key},
    {"key": "choice_stories", "group": "cpu", "fa": "داستان‌های انتخابی", "en": "Choice stories", "fn": check_choice_stories},
    {"key": "mini_series", "group": "cpu", "fa": "مینی‌سریال", "en": "Mini-series", "fn": check_mini_series},
    {"key": "ladder", "group": "cpu", "fa": "نردبان استودیو", "en": "Studio ladder", "fn": check_ladder},
    {"key": "text_model", "group": "gpu", "fa": "مدل متنی واقعی (لاگ‌لاین و نمودار)", "en": "Real text model (logline and graph)", "fn": check_text_model},
    {"key": "multiref_identity", "group": "gpu", "fa": "شخصیت ثابت با مدل تصویر (چندمرجعی)", "en": "Consistent characters with the image model (multi-reference)", "fn": check_multiref_identity},
    {"key": "vision", "group": "gpu", "fa": "بررسی عمیق با مدل بینایی", "en": "Deep check with the vision model", "fn": check_vision},
]


def run(ctx=None, *, gpu: bool = False, only: list[str] | None = None) -> dict:
    """Run the checks and keep the report. CPU checks always; GPU checks only with `gpu=True`. A check that raises is a failed check, never a crashed run."""
    from instai.providers.base import ProviderError
    from instai.version import read_version

    old = load_report() or {}
    work_root = Path(tempfile.mkdtemp(prefix="selftest-"))
    rows: list[dict] = []
    started = datetime.now(timezone.utc)
    try:
        todo = [c for c in CHECKS if (not only or c["key"] in only)]
        for k, c in enumerate(todo):
            if c["group"] == "gpu" and not gpu:
                prev = next((r for r in old.get("checks", []) if r["key"] == c["key"]), None)
                rows.append(prev or {"key": c["key"], "group": "gpu", "fa": c["fa"], "en": c["en"], **_r("pending", "وقتی رایانهٔ GPU روشن و آماده باشد خودکار آزمایش می‌شود.", "Tested by itself once the GPU PC is on and ready."), "seconds": 0, "at": None})
                continue
            if ctx is not None:
                ctx.check()
                ctx.progress(k / max(1, len(todo)), c["key"])
            work = work_root / c["key"]
            (work / "w").mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            try:
                res = c["fn"](work) if c["group"] == "cpu" else c["fn"](ctx, work)
            except ProviderError as e:
                res = _r("skip", getattr(e, "fa", "") or "سرویس در دسترس نبود؛ بعداً دوباره آزمایش می‌شود.", f"The service was not reachable: {e}")
            except Exception as e:  # noqa: BLE001 - a broken check is a result
                log.exception("self-test %s failed", c["key"])
                res = _r("fail", f"آزمون با خطا تمام شد: {type(e).__name__}: {str(e)[:160]}", f"The check ended with an error: {type(e).__name__}: {str(e)[:160]}")
            rows.append({"key": c["key"], "group": c["group"], "fa": c["fa"], "en": c["en"], **res, "seconds": round(time.time() - t0, 1), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        if only:                                           # keep the rows of the checks that were not asked for
            rows += [r for r in old.get("checks", []) if r["key"] not in {x["key"] for x in rows}]
            order = {c["key"]: i for i, c in enumerate(CHECKS)}
            rows.sort(key=lambda r: order.get(r["key"], 99))
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
    summary = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("ok", "warn", "fail", "skip", "pending")}
    rep = {"stamp": stamp(), "version": read_version(), "started_at": started.isoformat(timespec="seconds"), "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "gpu_run_at": datetime.now(timezone.utc).isoformat(timespec="seconds") if gpu else old.get("gpu_run_at"), "gpu_stamp": stamp() if gpu else old.get("gpu_stamp"),
           "checks": rows, "summary": summary, "ok": summary["fail"] == 0}
    save_report(rep)
    return rep


@handler("studio.selftest", resource=lambda payload: "gpu" if payload.get("gpu") else "cpu", timeout=3 * 3600)
def selftest_job(ctx):
    rep = run(ctx, gpu=bool(ctx.payload.get("gpu")), only=[str(k) for k in (ctx.payload.get("only") or [])] or None)
    return {"summary": rep["summary"], "ok": rep["ok"], "stamp": rep["stamp"]}


# ------------------------------------------------------------------------------------------------------------------------------ automatic start

def gpu_ready() -> bool:
    """Can a GPU check do something useful right now? A text model answers, or ComfyUI can run the multi-reference workflow."""
    try:
        up, models = _ollama_ok()
        if up and models:
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from instai.gpu import compute

        return bool(compute.workflow_available("qwen_image_edit_multiref"))
    except Exception:  # noqa: BLE001
        return False


def auto_queue(force: bool = False):
    """Queue the self-test by itself (called from the automation tick): the CPU checks once per new version/content, the GPU checks as soon as the machine can do them. Returns the job or None."""
    from instai.core import settings_store
    from instai.jobs import queue
    from instai.jobs.models import Job

    if not force and time.time() - _LAST_AUTO[0] < AUTO_EVERY_S:
        return None
    _LAST_AUTO[0] = time.time()
    if os.environ.get("INSTAI_TESTING") == "1" and not force:        # the test suite never gets surprise jobs; the self-test's own tests pass force=True
        return None
    if os.environ.get("INSTAI_STUDIO_SELFTEST_AUTO", "1") == "0" or settings_store.get_setting("studio_selftest_auto", True) in (False, 0, "0"):
        return None
    if Job.objects.filter(kind="studio.selftest", status__in=[Job.QUEUED, Job.RUNNING]).exists():
        return None
    rep = load_report() or {}
    cur = stamp()
    if rep.get("stamp") != cur:
        return queue.enqueue("studio.selftest", {"gpu": False, "auto": True}, title="آزمون خودکار استودیو (بدون GPU)", priority=-10)
    last_gpu = rep.get("gpu_run_at")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(last_gpu)).total_seconds() if last_gpu else 10 ** 9
    if (rep.get("gpu_stamp") != cur and age > GPU_RETRY_S) or age > GPU_REFRESH_S:
        if gpu_ready():
            return queue.enqueue("studio.selftest", {"gpu": True, "auto": True}, title="آزمون خودکار استودیو (با GPU)", priority=-10)
    return None
