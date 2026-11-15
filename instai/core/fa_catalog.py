"""Persian pages get Persian catalogue texts (audit 2026-11-14: English sentences and command lines on /settings, /models, /downloads, /system,
/lab/voices for an owner who reads Persian only and never types a command).

`translate(payload, "fa")` walks an API answer and replaces the known English texts of the catalogue fields (title, name, role, licence, vram,
notes, verified, detail, badge, hint ...) by their Persian twin from `fa_catalog_data`; the English original stays beside it as `<field>_en`
(the «اطلاعات فنی» view and the English interface read it). `PersianCatalogMiddleware` applies it to the catalogue endpoints when the
browser asks for Persian (the `X-Lang` header the interface sends on every call; anything but `en` means Persian).
Only exact texts that are in the tables are touched, only in those fields, only on those endpoints: user content is never rewritten.
"""
from __future__ import annotations

import json
import re

from . import fa_catalog_data as D

# field name -> the tables that may hold its English text
FIELDS: dict[str, tuple[dict, ...]] = {
    "title": (D.TITLE, D.NAME, D.SERVICE), "name": (D.NAME, D.TITLE, D.SERVICE), "label": (D.SERVICE, D.NAME), "role": (D.ROLE,), "licence": (D.LICENCE,),
    "vram": (D.VRAM,), "notes": (D.NOTE,), "note": (D.NOTE,), "verified": (D.VERIFIED,), "detail": (D.SERVICE,), "badge": (D.SERVICE,), "hint": (D.SERVICE,),
    "auto_note": (D.SERVICE,),
}
PREFIXES = ("/api/models", "/api/downloads/catalog", "/api/system/hardware", "/api/voices/engines", "/api/anime/candidates")

# two or more lowercase English words in a row (product names are Capitalised / ALLCAPS / carry digits, so they pass)
_WORD = r"[a-z][a-z'\-]{2,}"
ENGLISH = re.compile(rf"(?<![\w])({_WORD})(?![\w'\-])(?:[\s,;:/()+]+{_WORD}(?![\w'\-]))+")
COMMAND = re.compile(r"Download-Models|pip install|\.exe\b|--[a-z]|python -m|npm |tools\\|\w+\\\w+")


def looks_english(text: str) -> bool:
    """A sentence in English: two or more plain lowercase English words in a row."""
    return bool(text) and bool(ENGLISH.search(text))


def looks_like_command(text: str) -> bool:
    """A command line or a Windows path: nothing the owner should have to read or type."""
    return bool(text) and bool(COMMAND.search(text))


# a state line with a variable part: (pattern, Persian template with {0} for the first group)
DETAIL_RULES = [
    (re.compile(r"^voice (.+) is not downloaded"), "صدای «{0}» دانلود نشده است"),
    (re.compile(r"^piper\.exe not found"), "Piper نصب نیست"),
]


def persian(field: str, value: str) -> str | None:
    for table in FIELDS.get(field, ()):
        fa = table.get(value) or table.get(value.strip())
        if fa:
            return fa
    if field == "detail":
        for rx, tpl in DETAIL_RULES:
            m = rx.match(value)
            if m:
                return tpl.format(*m.groups())
    return None


def translate(obj, lang: str = "fa"):
    """The same structure with the Persian twins in place (and `<field>_en` holding the original). Anything but 'fa' returns `obj` untouched."""
    if lang != "fa":
        return obj
    return _walk(obj)


def _walk(o):
    if isinstance(o, list):
        return [_walk(x) for x in o]
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if isinstance(v, str) and k in FIELDS:
                fa = persian(k, v)
                out[k] = fa if fa else v
                if fa and f"{k}_en" not in o:
                    out[f"{k}_en"] = v
            else:
                out[k] = _walk(v) if isinstance(v, (dict, list)) else v
        return out
    return o


class PersianCatalogMiddleware:
    """Persian catalogue texts on the catalogue endpoints of a Persian page (see the module docstring)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if (request.method == "GET" and request.path.startswith(PREFIXES) and response.status_code == 200
                    and str(request.headers.get("X-Lang", "")).lower()[:2] != "en" and "json" in (response.get("Content-Type") or "")):
                data = json.loads(response.content.decode("utf-8"))
                response.content = json.dumps(translate(data, "fa"), ensure_ascii=False).encode("utf-8")
                if response.has_header("Content-Length"):
                    response["Content-Length"] = str(len(response.content))
        except Exception:  # noqa: BLE001 - a translation problem must never break the page: the English answer is still correct
            pass
        return response
