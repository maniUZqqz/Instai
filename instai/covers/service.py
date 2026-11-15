"""The cover maker's service layer: context of an episode / series -> spec -> pictures -> assets, the episode's cover and the downloads.

Everything that touches the database lives here; the engine (``engine/``) is pure Pillow. A cover is made by the job ``covers.make`` (``jobs.py``) in two steps so it never waits for
the GPU: first with the procedural background (done in seconds, on the CPU), then - when the owner asked for an AI background - with the picture the image model draws, which the job
fetches by itself as soon as ComfyUI is available.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import logging
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from PIL import Image

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.core.errors import DomainError

from . import background, subjects
from .engine import formats as F
from .engine import hooks
from .engine import render as R
from .engine import typo
from .engine.styles import STYLES
from .models import Cover

log = logging.getLogger("instai.covers")
LETTERS = "ABCDEF"
MAX_VARIANTS = 6
PREVIEW_SIDE = 720


def err(code: str, fa: str, en: str, status: int = 400) -> DomainError:
    return DomainError(code, fa, message_en=en, http_status=status)


# ───────────────────────────── target and context

def language_of(page) -> str:
    lang = (page.language or "fa")[:2].lower()
    return "en" if lang == "en" else "fa"


def resolve_target(data: dict):
    """The request's ``episode`` / ``series`` / ``page`` ids -> (page, series, episode, kind)."""
    from instai.pages.models import ContentPage
    from instai.story.models import Episode, Series

    ep = se = pg = None
    if data.get("episode"):
        ep = Episode.objects.select_related("series__page").filter(pk=data["episode"]).first()
        if ep is None:
            raise err("not_found", "قسمت پیدا نشد.", "The episode was not found.", 404)
        se, pg = ep.series, ep.series.page
    elif data.get("series"):
        se = Series.objects.select_related("page").filter(pk=data["series"]).first()
        if se is None:
            raise err("not_found", "سریال پیدا نشد.", "The series was not found.", 404)
        pg = se.page
    elif data.get("page"):
        pg = ContentPage.objects.filter(pk=data["page"]).first()
        if pg is None:
            raise err("not_found", "صفحه پیدا نشد.", "The page was not found.", 404)
    else:
        raise err("validation_error", "قسمت، سریال یا صفحه را مشخص کنید.", "Name an episode, a series or a page.")
    kind = data.get("kind") if data.get("kind") in ("episode", "series", "season", "banner") else None
    if ep is not None:
        kind = "episode"
    elif kind in (None, "episode"):
        kind = "series" if se is not None else "banner"
    return pg, se, ep, kind


def _choices_of(series, page) -> list[str]:
    from instai.choice.models import ChoiceStory

    qs = ChoiceStory.objects.filter(page=page)
    if series is not None:
        qs = qs.filter(series=series)
    for story in qs.order_by("-id")[:3]:
        for node in (story.graph or {}).get("nodes", []):
            ch = [str(c.get("label") or c.get("text") or "").strip() for c in (node.get("choices") or []) if isinstance(c, dict)]
            ch = [c for c in ch if c]
            if len(ch) >= 2:
                return ch[:2]
    return []


def build_context(page, series=None, episode=None, kind: str | None = None, lang: str | None = None) -> dict:
    """The facts a cover needs, as the plain dict the engine's ideas read (never a store / price: series, episode, hook line, characters, dialogue, choices, channel)."""
    lang = lang if lang in ("fa", "en") else language_of(page)
    ident = page.profile("identity")
    script = (episode.script if episode is not None else {}) or {}
    blocks = [b for b in (script.get("blocks") or []) if isinstance(b, dict) and len(str(b.get("text") or "")) >= 12]
    arc_cliff = episode.arc.cliffhanger if (episode is not None and episode.arc_id) else ""
    chars = [c.name for c in page.characters.all().order_by("-approved", "id")[:6]]
    return {
        "lang": lang, "kind": kind or ("episode" if episode is not None else "series" if series is not None else "banner"),
        "series": series.title if series is not None else "",
        "episode_number": episode.number if episode is not None else None,
        "episode_title": episode.title if episode is not None else "",
        "logline": (episode.logline if episode is not None else "") or "",
        "hook": str(script.get("hook") or "") if episode is not None else "",
        "cliffhanger": (episode.cliffhanger if episode is not None else "") or arc_cliff or "",
        "premise": series.premise if series is not None else "",
        "branch_point": series.branch_point if series is not None else "",
        "characters": chars, "channel": ident.get("display_name") or page.name,
        "dialogue": [[str(b.get("speaker") or ""), str(b.get("text") or "")] for b in blocks[:4]],
        "choices": _choices_of(series, page),
    }


# ───────────────────────────── the look of the series (colours, font, image prompt)

_TITLE_FONT = {"black": "lalezar", "bold": "sahel", "regular": "vazirmatn"}


def look_of(page, series=None) -> dict:
    """The series look (or the page's when the series has none) as the cover maker needs it: the 6 colour roles, the image prompts and the theme's typography."""
    from instai.styles import library

    lk = library.look_of(page, series)
    comp = library.compose(lk["style_key"], lk["theme_key"], lk["style_notes"])
    theme = library.get_theme(comp.get("theme") or "") if comp.get("theme") else None
    typ = (theme or {}).get("typography") or {}
    roles = [c for c in (comp.get("palette") or page.profile("visual").get("palette") or []) if isinstance(c, str)]
    return {"style_key": lk["style_key"], "theme_key": lk["theme_key"], "own": bool(lk.get("own")), "palette": roles[:6], "positive": comp.get("positive", ""),
            "negative": comp.get("negative", ""), "font": _TITLE_FONT.get(str(typ.get("title_weight") or ""), ""), "upper": typ.get("title_case") == "upper"}


# ───────────────────────────── the spec

def default_spec(page, series, episode, kind: str, *, fmt: str = F.DEFAULT_FORMAT, style: str | None = None, lang: str | None = None, ctx: dict | None = None) -> dict:
    """A ready spec for a target: the best idea for the layout (or the first idea), the series' colours and the characters as subjects."""
    ctx = ctx or build_context(page, series, episode, kind, lang)
    lang = ctx["lang"]
    fmt = fmt if fmt in F.FORMATS else F.DEFAULT_FORMAT
    ideas = hooks.rule_ideas(ctx, fmt=fmt, count=16)
    idea = next((i for i in ideas if style and i["style"] == style), None) or (ideas[0] if ideas else None)
    sk = style if style in STYLES else (idea["style"] if idea else "episode_card")
    raw = R.default_spec()
    raw.update(format=fmt, style=sk, lang=lang)
    if idea:
        raw["content"] = {k: idea.get(k, "") for k in R.CONTENT_LIMITS}
    else:
        raw["content"] = {k: "" for k in R.CONTENT_LIMITS}
        raw["content"].update(title=ctx.get("episode_title") or ctx.get("series") or "", channel=ctx.get("channel", ""))
    look = look_of(page, series)
    if look["font"]:
        raw["font"] = look["font"] if look["font"] in typo.FONTS else typo.AUTO_FONT
    chars = list(page.characters.all().order_by("-approved", "id")[:2])
    if chars:
        raw["subject"]["character"] = chars[0].pk
        if len(chars) > 1:
            raw["subject2"]["character"] = chars[1].pk
    return R.clean_spec(raw, STYLES)


#: the moods the later versions try, in this order (one of each palette branch of ``palette.build``: vivid / warm / cool share one, so they would look the same)
ALT_MOODS = ("dark", "light", "cinema", "neon", "luxury", "vivid")
MOOD_BRANCH = {"vivid": "v", "warm": "v", "cool": "v", "dark": "d", "light": "l", "cinema": "c", "neon": "n", "luxury": "x"}
MOOD_NOTE = {"cool": ("حالِ‌وهوای سرد", "A cool mood"), "warm": ("حالِ‌وهوای گرم", "A warm mood"), "dark": ("حالِ‌وهوای تیره", "A dark mood"), "vivid": ("حالِ‌وهوای پرانرژی", "A vivid mood"),
             "cinema": ("حالِ‌وهوای سینمایی", "A cinematic mood"), "luxury": ("حالِ‌وهوای آرام و لوکس", "A calm, luxurious mood"), "neon": ("حالِ‌وهوای نئونی", "A neon mood"),
             "light": ("حالِ‌وهوای روشن", "A light mood")}


def variant_plan(spec: dict, i: int) -> dict:
    """What version ``i`` (A=0 ...) changes: A is the design itself; B swaps the colours and puts the character on the other side; C to F try other moods (alternating the colour swap)."""
    base = spec["colors"].get("mood") or STYLES[spec["style"]].mood
    if i == 0:
        return {"variation": 0, "mood": "", "fa": "طرحِ اصلی", "en": "The design as it is"}
    if i == 1:
        return {"variation": 1, "mood": "", "fa": "رنگ‌ها جابه‌جا و شخصیت آن‌طرف", "en": "Colours swapped, the character on the other side"}
    pool = [m for m in ALT_MOODS if MOOD_BRANCH[m] != MOOD_BRANCH.get(base, "v")]
    mood = pool[(i - 2) % len(pool)]
    swap = (i - 2) % 2 == 1
    fa, en = MOOD_NOTE[mood]
    return {"variation": 1 if swap else 0, "mood": mood, "fa": fa + (" و رنگ‌های جابه‌جا" if swap else ""), "en": en + (", colours swapped" if swap else "")}


def variant_spec(spec: dict, i: int) -> dict:
    """Version ``i`` of a spec (see ``variant_plan``): another colour variation, often another mood, another seed."""
    sp = copy.deepcopy(spec)
    plan = variant_plan(spec, i)
    sp["colors"]["variation"] = (int(spec["colors"].get("variation") or 0) + plan["variation"]) % 8
    if plan["mood"]:
        sp["colors"]["mood"] = plan["mood"]
    sp["seed"] = (int(spec.get("seed") or 1) + i) % 100000
    return sp


# ───────────────────────────── the pictures a render needs

def build_inputs(spec: dict, page, series, episode, *, bg: Image.Image | None = None) -> tuple[R.Inputs, dict]:
    """The engine's ``Inputs`` from a spec: the character pictures, the logo, the background, the series colours. -> (inputs, info for the report)."""
    ctx_look = look_of(page, series)
    inp = R.Inputs(channel_name=page.name, heading_font=ctx_look["font"], theme_roles=ctx_look["palette"] if len(ctx_look["palette"]) >= 4 else [],
                   brand_colors=ctx_look["palette"][1:3] if len(ctx_look["palette"]) >= 4 else [])
    info: dict = {"subjects": [], "look": {"style": ctx_look["style_key"], "theme": ctx_look["theme_key"], "own": ctx_look["own"]}}
    s1, s2 = spec["subject"], spec["subject2"]
    pic, cut, i1 = subjects.load(page, character_id=s1.get("character"), asset_id=s1.get("asset"), expression=s1.get("expression", ""), episode=episode)
    inp.subject, inp.subject_is_cutout = pic, cut
    info["subjects"].append(i1)
    if STYLES[spec["style"]].needs_second or s2.get("character") or s2.get("asset"):
        pic2, cut2, i2 = subjects.load(page, character_id=s2.get("character"), asset_id=s2.get("asset"), expression=s2.get("expression", ""), episode=episode)
        inp.subject2, inp.subject2_is_cutout = pic2, cut2
        info["subjects"].append(i2)
    lg = spec["logo"]
    if lg.get("show") and lg.get("asset"):
        im = subjects.open_asset(lg["asset"])
        if im is not None:
            inp.logo = im.convert("RGBA")
    if bg is not None:
        inp.background = bg
    elif spec["background"].get("asset"):
        inp.background = subjects.open_asset(spec["background"]["asset"])
    return inp, info


def _guides(fmt, size) -> dict:
    return {"safe": [round(v, 4) for v in (fmt.margin[0], fmt.margin[1], 1 - fmt.margin[2], 1 - fmt.margin[3])],
            "avoid": [{"rect": list(a[:4]), "note_fa": a[4], "note_en": a[5]} for a in fmt.avoid]}


def preview(spec_in: dict, page, series, episode, *, side: int = PREVIEW_SIDE) -> dict:
    """A small JPEG of a spec (as a data URL) with the render's report. No database write, no GPU."""
    import base64

    spec = R.clean_spec(spec_in, STYLES)
    fmt = F.get(spec["format"])
    inp, info = build_inputs(spec, page, series, episode)
    scale = min(1.0, side / float(max(fmt.w, fmt.h)))
    res = R.render(spec, inp, scale=scale)
    buf = io.BytesIO()
    res.image.convert("RGB").save(buf, "JPEG", quality=82)
    return {"image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), "width": res.size[0], "height": res.size[1], "full": [fmt.w, fmt.h],
            "warnings": res.warnings, "texts": [{k: t[k] for k in ("name", "bbox", "px", "lines")} for t in res.texts], "palette": res.palette, "guides": _guides(fmt, res.size),
            "spec": spec, "info": info, "background": {"kind": spec["background"]["kind"], "has_picture": inp.background is not None}}


# ───────────────────────────── making and storing

def _render_key(spec: dict, n: int, bg_asset_id) -> str:
    return hashlib.sha256(json.dumps([spec, n, bg_asset_id, settings_version()], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def settings_version() -> str:
    from instai.version import read_version

    return read_version()


def _folder(cover: Cover) -> str:
    return f"episodes/{cover.episode_id}/covers" if cover.episode_id else f"pages/{cover.page_id}/covers"


def _save_png(img: Image.Image, rel: str, *, cover: Cover, letter: str, variation: int, spec: dict, extra: dict) -> Asset:
    tmp = Path(tempfile.mkdtemp(prefix="cover-", dir=settings.MEDIA_ROOT)) / "cover.png"
    try:
        img.convert("RGB").save(tmp, "PNG", optimize=True)
        # a variant is a plain picture of the design (role "other", no episode) so it never replaces the episode's chosen cover; ``use_cover`` registers the chosen one as role "cover"
        return asset_storage.register(tmp, rel, kind="image", role="other", page=cover.page, provenance={
            "cover": cover.pk, "variant": letter, "variation": variation, "format": spec["format"], "style": spec["style"], "lang": spec.get("lang", "fa"), "tool": "instai.covers", **extra})
    finally:
        import shutil

        shutil.rmtree(tmp.parent, ignore_errors=True)


def render_variants(cover: Cover, spec: dict, inp: R.Inputs, n: int, info: dict, ctx=None) -> dict:
    """Render ``n`` versions of the design and store them; -> the report. Pure CPU (Pillow)."""
    fmt = F.get(spec["format"])
    key = _render_key(spec, n, spec["background"].get("asset"))
    variants, warnings, texts, palette = [], [], [], {}
    for i in range(n):
        if ctx is not None:
            ctx.check()
            ctx.progress(0.05 + 0.6 * i / max(1, n), f"{LETTERS[i]} ({i + 1}/{n})")
        sp = variant_spec(spec, i)
        res = R.render(sp, inp, scale=1.0)
        assert res.image.size == (fmt.w, fmt.h), (res.image.size, fmt.size)
        asset = _save_png(res.image, f"{_folder(cover)}/cover-{cover.pk}-{LETTERS[i].lower()}-{key}.png", cover=cover, letter=LETTERS[i], variation=sp["colors"]["variation"], spec=spec,
                          extra={"render_key": key, "background": "ai" if spec["background"].get("asset") else "procedural"})
        plan = variant_plan(spec, i)
        variants.append({"index": i, "letter": LETTERS[i], "asset": asset.pk, "variation": sp["colors"]["variation"], "mood": sp["colors"].get("mood", ""), "note_fa": plan["fa"], "note_en": plan["en"]})
        if i == 0:
            warnings, palette = res.warnings, res.palette
            texts = [{k: t[k] for k in ("name", "bbox", "px", "lines")} for t in res.texts]
    return {"variants": variants, "warnings": warnings, "report": {"size": [fmt.w, fmt.h], "palette": palette, "texts": texts, "render_key": key, "subjects": info.get("subjects", []),
                                                                  "look": info.get("look", {})}}


def use_cover(cover: Cover, index: int | None = None) -> Cover:
    """Make version ``index`` the cover of the episode: registered as the episode's current cover (role "cover" - what the publishing package ships) and put on every publication
    of the episode that is not published yet."""
    index = cover.chosen if index is None else int(index)
    row = next((v for v in cover.variants if v["index"] == index), None)
    if row is None:
        raise err("not_found", "این نسخه وجود ندارد.", "That version does not exist.", 404)
    src = Asset.objects.get(pk=row["asset"])
    tmp = Path(tempfile.mkdtemp(prefix="cover-", dir=settings.MEDIA_ROOT)) / "cover.png"
    try:
        import shutil

        shutil.copyfile(asset_storage.storage.path_for(src.path), tmp)
        rel = f"{_folder(cover)}/final-{cover.pk}-{row['letter'].lower()}-{src.pk}.png"
        asset = asset_storage.register(tmp, rel, kind="image", role="cover", page=cover.page, episode=cover.episode, provenance={**src.provenance, "from_asset": src.pk, "chosen": True})
    finally:
        import shutil

        shutil.rmtree(tmp.parent, ignore_errors=True)
    cover.asset, cover.chosen = asset, index
    cover.save(update_fields=["asset", "chosen", "updated_at"])
    if cover.episode_id:
        from instai.publishing.models import Publication

        Publication.objects.filter(episode_id=cover.episode_id).exclude(status="published").update(cover=asset)
    return cover


def ai_wanted(spec: dict) -> bool:
    return spec["background"]["kind"] == "ai" and not spec["background"].get("asset")


def make(cover: Cover, ctx) -> dict:
    """The job body of ``covers.make``. Idempotent: a re-run (after a WAIT) re-uses the pictures that are already right and only does the missing step."""
    spec = R.clean_spec(cover.spec, STYLES)
    n = max(1, min(MAX_VARIANTS, int((cover.options or {}).get("variants") or 3)))
    use = bool((cover.options or {}).get("use", True))
    page, series, episode = cover.page, cover.series, cover.episode
    cover.status, cover.error = "rendering", ""
    cover.save(update_fields=["status", "error", "updated_at"])
    inp, info = build_inputs(spec, page, series, episode)
    state = background.engine_state()
    want_ai = ai_wanted(spec) and not state["demo"]
    key = _render_key(spec, n, spec["background"].get("asset"))
    if (cover.report or {}).get("render_key") != key or not cover.variants:
        out = render_variants(cover, spec, inp, n, info, ctx)
        cover.variants, cover.warnings, cover.report = out["variants"], out["warnings"], out["report"]
    cover.format, cover.style = spec["format"], spec["style"]
    cover.spec = spec
    cover.bg_state = "waiting" if want_ai else ("demo" if (spec["background"]["kind"] == "ai" and state["demo"]) else ("ai" if spec["background"].get("asset") else "procedural"))
    cover.status = "waiting_bg" if want_ai else "ready"
    cover.save()
    if use and cover.episode_id and (cover.asset_id is None):
        use_cover(cover, 0)
    if want_ai:
        if ctx is not None:
            ctx.progress(0.7, "background")
        asset = background.generate(ctx, cover, spec, look_of(page, series))          # a WAIT (ProviderError) leaves the finished procedural cover in place and the job queued
        spec["background"]["asset"] = asset.pk
        cover.spec, cover.bg_asset, cover.bg_state = spec, asset, "ai"
        inp2, info2 = build_inputs(spec, page, series, episode)
        out = render_variants(cover, spec, inp2, n, info2, ctx)
        cover.variants, cover.warnings, cover.report = out["variants"], out["warnings"], out["report"]
        cover.status = "ready"
        cover.save()
        if cover.asset_id:
            use_cover(cover, cover.chosen)
    if ctx is not None:
        ctx.progress(1.0, "done")
    return {"cover_id": cover.pk, "variants": len(cover.variants), "status": cover.status, "bg_state": cover.bg_state, "asset": cover.asset_id}


def add_variants(cover: Cover, extra: int, ctx=None) -> Cover:
    """More A/B versions of the same design (up to six in all)."""
    have = len(cover.variants)
    total = min(MAX_VARIANTS, have + max(1, extra))
    cover.options = {**(cover.options or {}), "variants": total}
    spec = R.clean_spec(cover.spec, STYLES)
    inp, info = build_inputs(spec, cover.page, cover.series, cover.episode)
    out = render_variants(cover, spec, inp, total, info, ctx)
    cover.variants, cover.warnings, cover.report = out["variants"], out["warnings"], out["report"]
    cover.save()
    return cover


# ───────────────────────────── downloads

def jpeg_for(image: Image.Image, fmt_key: str) -> bytes:
    f = F.get(fmt_key) if fmt_key in F.FORMATS else F.get(F.DEFAULT_FORMAT)
    return R.to_jpeg_bytes(image, 90, f.max_kb)


def jpeg_of_asset(asset: Asset) -> bytes | None:
    """The platform-ready JPEG (under the format's size cap) of a cover picture; None when the file is gone."""
    if not asset_storage.storage.exists(asset.path):
        return None
    with Image.open(asset_storage.storage.path_for(asset.path)) as im:
        return jpeg_for(im.convert("RGB"), str((asset.provenance or {}).get("format") or F.DEFAULT_FORMAT))


def zip_of(cover: Cover) -> bytes:
    buf = io.BytesIO()
    f = F.get(cover.format)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for v in cover.variants:
            a = Asset.objects.filter(pk=v["asset"]).first()
            if a is None or not asset_storage.storage.exists(a.path):
                continue
            z.write(asset_storage.storage.path_for(a.path), f"cover-{v['letter']}.png")
            jpg = jpeg_of_asset(a)
            if jpg:
                z.writestr(f"cover-{v['letter']}.jpg", jpg)
        z.writestr("README.txt", f"InstAI cover - {f.title_en}\n{f.w}x{f.h} px ({f.aspect_label})\nStyle: {cover.style}\n"
                                 f"{'JPEG files are under ' + str(f.max_kb) + ' KB. ' if f.max_kb else ''}The safe areas are approximate.\n")
    return buf.getvalue()


# ───────────────────────────── serialising

def asset_dict(a: Asset | None) -> dict | None:
    return {"id": a.pk, "url": a.url, "width": a.width, "height": a.height, "size_bytes": a.size_bytes} if a else None


def cover_dict(c: Cover, *, full: bool = False) -> dict:
    assets = {a.pk: a for a in Asset.objects.filter(pk__in=[v["asset"] for v in c.variants])}
    d = {"id": c.pk, "kind": c.kind, "page": c.page_id, "series": c.series_id, "series_title": c.series.title if c.series_id else "", "episode": c.episode_id,
         "episode_number": c.episode.number if c.episode_id else None, "episode_title": c.episode.title if c.episode_id else "", "parent": c.parent_id, "format": c.format,
         "style": c.style, "status": c.status, "bg_state": c.bg_state, "chosen": c.chosen, "asset": asset_dict(c.asset), "bg": asset_dict(c.bg_asset),
         "variants": [{**v, **(asset_dict(assets.get(v["asset"])) or {}), "id": v["asset"]} for v in c.variants], "warnings": c.warnings, "error": c.error, "note": c.note,
         "created_at": c.created_at, "updated_at": c.updated_at, "in_use": bool(c.asset_id and c.episode_id and c.asset.is_current)}
    if full:
        d.update(spec=c.spec, report=c.report, options=c.options)
    return d
