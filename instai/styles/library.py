"""The style & theme library: built-ins (code) + user presets (database), with duplicate / edit / export / import and prompt composition."""
from __future__ import annotations

import time
from typing import Any

from django.db import DatabaseError

from instai.core.errors import DomainError

from . import schema
from .aliases import known_as, terms_for
from .builtin_styles import BUILTIN_STYLES, LEGACY_ALIASES, REALISM_ORDER
from .builtin_themes import BUILTIN_THEMES
from .models import StylePreview, UserPreset

BUNDLE_FORMAT = "instai.styles@1"
_BUILTIN = {"style": BUILTIN_STYLES, "theme": BUILTIN_THEMES}
_NORMALIZE = {"style": schema.normalize_style, "theme": schema.normalize_theme}

_CACHE: dict[str, Any] = {"at": 0.0, "rows": None, "previews": None}
_TTL = 2.0
GROUP_ORDER = [k for k, _ in sorted(schema.GROUPS.items(), key=lambda kv: kv[1]["order"])]


def clear_cache() -> None:
    _CACHE.update(at=0.0, rows=None, previews=None)


def _user_rows() -> list[UserPreset]:
    """All user presets, cached for a moment (the worker is another process, so keep the TTL short)."""
    now = time.monotonic()
    if _CACHE["rows"] is not None and now - _CACHE["at"] < _TTL:
        return _CACHE["rows"]
    try:
        rows = list(UserPreset.objects.all())
    except DatabaseError:  # not migrated yet
        rows = []
    _CACHE.update(at=now, rows=rows, previews=None)
    return rows


def _preview_urls() -> dict[str, str]:
    """style key -> URL of the GPU-made sample image (only styles that have one)."""
    _user_rows()   # refreshes the cache window
    if _CACHE["previews"] is None:
        try:
            _CACHE["previews"] = {r.style_key: r.asset.url for r in StylePreview.objects.select_related("asset") if r.asset_id}
        except DatabaseError:  # not migrated yet
            _CACHE["previews"] = {}
    return _CACHE["previews"]


def _entry(kind: str, key: str, data: dict, *, builtin: bool, based_on: str = "", origin: str = "builtin") -> dict:
    out = {"key": key, "kind": kind, "builtin": builtin, "based_on": based_on, "origin": origin, **data}
    if kind == "style":
        if data.get("thumbnail_asset"):
            from instai.assets.models import Asset

            a = Asset.objects.filter(pk=data["thumbnail_asset"]).first()
            out["thumbnail_url"] = a.url if a else None
        elif key in _preview_urls():
            out["thumbnail_url"] = _preview_urls()[key]
        # the built-in swatch (a small SVG drawn from the palette) is always available; the GPU sample, when there is one, is `thumbnail_url`
        out["preview_url"] = f"/api/library/style/{key}/preview.svg"
        out["search_terms"] = terms_for(key) if builtin else []
        out["known_as"] = known_as(key) if builtin else ""
    return out


def list_presets(kind: str) -> list[dict]:
    out = [_entry(kind, k, v, builtin=True) for k, v in _BUILTIN[kind].items()]
    out += [_entry(kind, r.key, _NORMALIZE[kind](r.data), builtin=False, based_on=r.based_on, origin=r.origin) for r in _user_rows() if r.kind == kind]
    if kind == "style":
        out.sort(key=lambda s: (GROUP_ORDER.index(s["group"]) if s["group"] in GROUP_ORDER else 99,
                                REALISM_ORDER.index(s["realism"]) if s["realism"] in REALISM_ORDER else 99, s["builtin"] is False, s["name_en"].lower()))
    else:
        out.sort(key=lambda t: (not t["builtin"], t["name_en"].lower()))
    return out


def resolve_key(kind: str, key: str) -> str:
    return LEGACY_ALIASES.get(key, key) if kind == "style" else key


def get_preset(kind: str, key: str) -> dict | None:
    key = resolve_key(kind, key or "")
    if key in _BUILTIN[kind]:
        return _entry(kind, key, _BUILTIN[kind][key], builtin=True)
    for r in _user_rows():
        if r.kind == kind and r.key == key:
            return _entry(kind, key, _NORMALIZE[kind](r.data), builtin=False, based_on=r.based_on, origin=r.origin)
    return None


def get_style(key: str) -> dict | None:
    return get_preset("style", key)


def get_theme(key: str) -> dict | None:
    return get_preset("theme", key)


def _unique_key(kind: str, wanted: str) -> str:
    taken = set(_BUILTIN[kind]) | {r.key for r in UserPreset.objects.filter(kind=kind)}
    base, n, key = schema.slug(wanted), 2, schema.slug(wanted)
    while key in taken:
        key = f"{base}_{n}"[:64]
        n += 1
    return key


def _validate(kind: str, data: dict) -> dict:
    norm = _NORMALIZE[kind](data)
    if not (norm["name_fa"] or norm["name_en"]):
        raise DomainError("validation_error", "نام پیش‌تنظیم لازم است.", http_status=400, details={"name_fa": ["required"]})
    if kind == "style" and not norm["image_positive"]:
        raise DomainError("validation_error", "متنِ مثبتِ تصویر لازم است.", http_status=400, details={"image_positive": ["required"]})
    return norm


def create_preset(kind: str, data: dict, *, key: str | None = None, based_on: str = "", origin: str = "user") -> dict:
    norm = _validate(kind, data)
    k = _unique_key(kind, key or norm["name_en"] or norm["name_fa"] or kind)
    UserPreset.objects.create(kind=kind, key=k, data=norm, based_on=based_on, origin=origin)
    clear_cache()
    return get_preset(kind, k)  # type: ignore[return-value]


def duplicate_preset(kind: str, key: str, overrides: dict | None = None) -> dict:
    src = get_preset(kind, key)
    if not src:
        raise DomainError("not_found", http_status=404)
    data = {k: src[k] for k in _NORMALIZE[kind]({})}
    data.update({k: v for k, v in (overrides or {}).items() if k in data})
    if not (overrides or {}).get("name_en"):
        data["name_en"] = (src["name_en"] or src["name_fa"]) + " (copy)"
    if not (overrides or {}).get("name_fa"):
        data["name_fa"] = (src["name_fa"] or src["name_en"]) + " (کپی)"
    data["thumbnail_asset"] = None if kind == "style" else data.get("thumbnail_asset")
    return create_preset(kind, data, based_on=src["key"], origin="duplicate")


def update_preset(kind: str, key: str, data: dict) -> dict:
    if key in _BUILTIN[kind]:
        raise DomainError("conflict", "پیش‌تنظیم‌های پیش‌فرض قابل ویرایش نیستند؛ از آن کپی بگیرید.")
    row = UserPreset.objects.filter(kind=kind, key=key).first()
    if not row:
        raise DomainError("not_found", http_status=404)
    merged = {**_NORMALIZE[kind](row.data), **{k: v for k, v in data.items() if k in _NORMALIZE[kind]({})}}
    row.data = _validate(kind, merged)
    row.save()
    clear_cache()
    return get_preset(kind, key)  # type: ignore[return-value]


def delete_preset(kind: str, key: str) -> None:
    if key in _BUILTIN[kind]:
        raise DomainError("conflict", "پیش‌تنظیم‌های پیش‌فرض حذف نمی‌شوند.")
    n, _ = UserPreset.objects.filter(kind=kind, key=key).delete()
    if not n:
        raise DomainError("not_found", http_status=404)
    clear_cache()


# ------------------------------------------------------------------ export / import

def export_bundle(style_keys: list[str] | None = None, theme_keys: list[str] | None = None) -> dict:
    """User presets by default; named keys (including built-ins) are exported as plain copies."""
    def pick(kind: str, keys: list[str] | None) -> list[dict]:
        rows = list_presets(kind)
        sel = [r for r in rows if (r["key"] in keys if keys else not r["builtin"])]
        fields = _NORMALIZE[kind]({}).keys()
        return [{"key": r["key"], **{f: r[f] for f in fields if f != "thumbnail_asset"}} for r in sel]
    return {"format": BUNDLE_FORMAT, "styles": pick("style", style_keys), "themes": pick("theme", theme_keys)}


def import_bundle(bundle: dict) -> dict:
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT:
        raise DomainError("validation_error", "این فایل، بستهٔ استایل InstAI نیست.", http_status=400, details={"format": ["invalid"]})
    made = {"styles": [], "themes": []}
    skipped: list[str] = []
    for kind, field in (("style", "styles"), ("theme", "themes")):
        for item in (bundle.get(field) or [])[:200]:
            if not isinstance(item, dict):
                continue
            try:
                p = create_preset(kind, item, key=str(item.get("key") or ""), origin="imported")
                made[field].append(p["key"])
            except DomainError:
                skipped.append(str(item.get("key") or item.get("name_en") or "?"))
    return {"imported": made, "skipped": skipped}


# ------------------------------------------------------------------ prompt composition

def _join(*parts: str) -> str:
    seen: list[str] = []
    for p in parts:
        for piece in [x.strip() for x in (p or "").split(",")]:
            if piece and piece.lower() not in [s.lower() for s in seen]:
                seen.append(piece)
    return ", ".join(seen)


def compose(style_key: str, theme_key: str = "", notes: str = "", extra_negative: str = "") -> dict:
    """Prompt fragments for image and video models from a style + a theme (+ the page's own notes).

    A style with its own default theme uses it when `theme_key` is empty. Unknown keys simply contribute nothing."""
    st = get_style(style_key) or {}
    th = get_theme(theme_key or st.get("theme_key", "")) or {}
    return {
        "positive": _join(st.get("image_positive", ""), th.get("prompt_fragment", ""), notes),
        "negative": _join(st.get("image_negative", ""), th.get("negative_fragment", ""), extra_negative),
        "video_positive": _join(st.get("video_positive", ""), th.get("prompt_fragment", "")),
        "video_negative": _join(st.get("video_negative", "")),
        "style": st.get("key", ""), "theme": th.get("key", ""), "palette": th.get("palette") or st.get("palette") or [],
        "lighting": th.get("lighting") or st.get("lighting", ""), "mood": th.get("mood") or st.get("mood", ""),
        "subtitle": schema.subtitle_profile(th) if th else {},
        # advice for the image/video model of this look (steps are applied by production; the rest is shown to the owner)
        "gen": st.get("gen") or schema.normalize_gen({}), "group": st.get("group", ""), "suitability": st.get("suitability") or [],
    }


def look_of(page, series=None) -> dict:
    """The look in force: the series' own pick (made once per project) over the page's visual profile.

    A series that picks only a style gets THAT style's default colour theme, never the page's theme of another style. The page's free-text
    style notes always apply."""
    vis = page.profile("visual")
    own = (getattr(series, "look", None) or {}) if series is not None else {}
    if own.get("style_key"):
        theme = own.get("theme_key") or (get_style(own["style_key"]) or {}).get("theme_key", "")
        return {"style_key": own["style_key"], "theme_key": theme, "style_notes": vis.get("style_notes", ""), "realism": own.get("realism", ""), "own": True}
    return {"style_key": vis.get("style_key", ""), "theme_key": own.get("theme_key") or vis.get("theme_key", ""), "style_notes": vis.get("style_notes", ""),
            "realism": vis.get("realism", ""), "own": bool(own)}


def compose_for(page, series=None) -> dict:
    lk = look_of(page, series)
    return compose(lk["style_key"], lk["theme_key"], lk["style_notes"])


def visual_patch(style_key: str, theme_key: str | None = None, *, realism: str = "", style_notes: str | None = None) -> dict:
    """The visual-profile fields one chosen look implies: style, realism, colour theme, the subtitle look of the theme, the composed negative
    prompt and the palette. `theme_key=None` takes the style's own default theme. Raises a Persian validation error for an unknown key."""
    st = get_style(style_key) if style_key else None
    if style_key and not st:
        raise DomainError("validation_error", "استایل نامعتبر است.", http_status=400, details={"style_key": ["invalid"]})
    theme = (st or {}).get("theme_key", "") if theme_key is None else theme_key
    th = get_theme(theme) if theme else None
    if theme and not th:
        raise DomainError("validation_error", "تمِ رنگی نامعتبر است.", http_status=400, details={"theme_key": ["invalid"]})
    patch: dict = {"theme_key": theme or ""}
    if st:
        comp = compose(st["key"], theme or "")
        patch.update(style_key=st["key"], realism=realism or st["realism"], negative_prompt=comp["negative"], palette=(th or st)["palette"])
    if th:
        patch["subtitle"] = schema.subtitle_profile(th)
    if style_notes is not None:
        patch["style_notes"] = str(style_notes or "")
    return patch


def compose_for_page(page) -> dict:
    return compose_for(page)


def compose_for_series(series) -> dict:
    return compose_for(series.page, series)


def compose_for_episode(ep) -> dict:
    return compose_for(ep.series.page, ep.series)


# ------------------------------------------------------------------ search

def _fold(text: str) -> str:
    """Lower-case and unify the Arabic/Persian letter variants and the digit alphabets, so a search finds the word however it was typed."""
    t = (text or "").lower().replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").replace("\u200c", " ").replace("-", " ")
    return t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))


_FILLER = {"style", "styles", "look", "looks", "سبک", "استایل"}     # "Dan Koe style", "PS2 style": the word "style" is not part of any name


def matches(entry: dict, q: str) -> bool:
    """Does a style/theme entry answer this search? Every word must hit the names, descriptions, tags or the search-only aliases."""
    words = [w for w in _fold(q).split() if w]
    words = [w for w in words if w not in _FILLER] or words
    if not words:
        return True
    hay = _fold(" ".join([entry.get("name_fa", ""), entry.get("name_en", ""), entry.get("description_fa", ""), entry.get("description_en", ""),
                          " ".join(entry.get("tags") or []), " ".join(entry.get("search_terms") or []), entry.get("key", "").replace("_", " ")]))
    return all(w in hay for w in words)


def filter_styles(rows: list[dict], *, q: str = "", group: str = "", realism: str = "", suitability: str = "", family: str = "") -> list[dict]:
    out = []
    for r in rows:
        if group and r.get("group") != group:
            continue
        if realism and r.get("realism") != realism:
            continue
        if family and r.get("family") != family:
            continue
        if suitability and suitability not in (r.get("suitability") or []):
            continue
        if q and not matches(r, q):
            continue
        out.append(r)
    return out


def live_style_entries() -> list[dict]:
    """Entries shaped like formats.STYLES, so production code that looks a style up by `style_key` finds user presets too."""
    out = []
    for k, v in BUILTIN_STYLES.items():
        out.append({"key": k, "label_fa": v["name_fa"], "label_en": v["name_en"], "prompt": v["image_positive"]})
    for a, target in LEGACY_ALIASES.items():
        out.append({"key": a, "label_fa": BUILTIN_STYLES[target]["name_fa"], "label_en": BUILTIN_STYLES[target]["name_en"],
                    "prompt": BUILTIN_STYLES[target]["image_positive"]})
    for r in _user_rows():
        if r.kind == "style":
            d = schema.normalize_style(r.data)
            out.append({"key": r.key, "label_fa": d["name_fa"] or d["name_en"], "label_en": d["name_en"] or d["name_fa"], "prompt": d["image_positive"]})
    return out
