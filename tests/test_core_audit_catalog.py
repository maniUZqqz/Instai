"""Audit batch "ia_core" (2026-11-14), item 4: a Persian page shows Persian catalogue texts, no command line, no English sentence.
Every source text of the catalogue must have a Persian twin (a new package or model cannot ship in English only)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from instai.core import fa_catalog as fc
from instai.core import licences, model_status
from instai.providers.comfy.workflows import WORKFLOWS

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[1]
TECHNICAL_KEYS = {"id", "kind", "roots", "vendor", "missing_ids", "en", "file", "aliases", "packages", "uses", "workflow", "status", "path", "url", "licence_url", "group", "package", "folder", "exe", "root", "dir", "launcher", "key", "engine", "version", "model",
                  "resource", "tech", "name_en", "title_en", "licence_en", "notes_en", "note_en", "role_en", "vram_en", "verified_en", "detail_en", "badge_en", "hint_en",
                  "label_en", "files", "dest", "urls", "sha256", "missing", "missing_models", "missing_nodes", "required_nodes", "input_schema", "voices", "voice", "dirs",
                  "scanned_at", "checked_at", "cpu", "os", "gpu", "driver", "python", "found_at", "default_voice", "voice_id", "language", "needs_node", "node", "nodes"}


def manifest_rows():
    for path in sorted((ROOT / "manifests").glob("*.json")):
        yield json.loads(path.read_text(encoding="utf-8"))


def strings(o, key=""):
    """(key, text) of every string of a JSON value, skipping the technical keys."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in TECHNICAL_KEYS or k.endswith("_en"):
                continue
            yield from strings(v, k)
    elif isinstance(o, list):
        for x in o:
            yield from strings(x, key)
    elif isinstance(o, str):
        yield key, o


# ------------------------------------------------------------------ every source text has a Persian twin

def test_every_package_and_item_of_the_manifests_has_a_persian_twin():
    missing = []
    for m in manifest_rows():
        for pid, p in (m.get("packages") or {}).items():
            row = p if isinstance(p, dict) else {"title": p}
            for field in ("title", "licence", "note"):
                v = row.get(field)
                if v and fc.looks_english(v) and not fc.persian(field, v):
                    missing.append((pid, field, v))
        for it in m.get("items") or []:
            v = it.get("title")
            if v and fc.looks_english(v) and not fc.persian("title", v):
                missing.append((it["id"], "title", v))
    assert missing == [], "add these to instai/core/fa_catalog_data.py:\n" + "\n".join(map(str, missing[:60]))


def test_every_licence_row_and_workflow_has_a_persian_twin():
    missing = []
    for r in licences.table():
        for field in ("name", "role", "licence", "vram", "notes", "verified"):
            v = r.get(field)
            if isinstance(v, str) and v and fc.looks_english(v) and not fc.persian(field, v):
                missing.append((r["id"], field, v))
    for w in WORKFLOWS.values():
        d = w.describe()
        for field in ("title", "licence", "notes"):
            v = d.get(field)
            if isinstance(v, str) and v and fc.looks_english(v) and not fc.persian(field, v):
                missing.append((w.id, field, v))
    assert missing == [], "add these to instai/core/fa_catalog_data.py:\n" + "\n".join(map(str, missing[:60]))


def test_the_tables_hold_only_persian_text():
    from instai.core import fa_catalog_data as D

    for table in (D.LICENCE, D.VERIFIED, D.ROLE, D.NOTE, D.TITLE, D.SERVICE, D.VRAM, D.NAME):
        for en, fa in table.items():
            assert fa and not fc.looks_english(fa), (en, fa)
            assert not fc.looks_like_command(fa), (en, fa)


# ------------------------------------------------------------------ the answers of a Persian page

def get(api, path: str, lang: str = "fa"):
    r = api.get(path, HTTP_X_LANG=lang)
    assert r.status_code == 200, (path, r.content[:200])
    return r.json()


_PATH = re.compile(r"[\w.~:-]*[/\\][\w./\\~:-]*")


def english_or_command(payload) -> list[str]:
    """Strings that are an English sentence or a command. A path or an address inside a text («n8.1.3 - /usr/local/bin/ffmpeg») is technical and skipped."""
    return [f"{k}: {s}" for k, s in strings(payload)
            if (fc.looks_english(_PATH.sub(" ", s)) or fc.looks_like_command(s)) and not s.startswith(("http", "/"))]


@pytest.mark.parametrize("path", ["/api/models?comfy=0", "/api/downloads/catalog", "/api/models/found"])
def test_catalogue_answers_in_persian_have_no_english_sentence_and_no_command(api, path):
    bad = english_or_command(get(api, path))
    assert bad == [], "\n".join(bad[:40])


def test_the_same_answers_in_english_are_untouched(api):
    fa = get(api, "/api/models?comfy=0", "fa")
    en = get(api, "/api/models?comfy=0", "en")
    flux = next(r for r in en["models"] if r["id"] == "flux-schnell")
    assert flux["notes"].startswith("The commercially usable FLUX") and "notes_en" not in flux
    flux_fa = next(r for r in fa["models"] if r["id"] == "flux-schnell")
    assert flux_fa["notes"].startswith("نسخهٔ FLUX") and flux_fa["notes_en"] == flux["notes"]           # the original stays beside it
    assert fa["packages"]["flux-schnell"]["licence"] == "Apache-2.0 (طبق صفحهٔ مدل)" and fa["packages"]["flux-schnell"]["licence_en"].endswith("(model card license field)")
    assert next(w for w in fa["workflows"] if w["id"] == "flux_dev_fp8_t2i")["title"].startswith("FLUX.1 [dev] FP8 — تصویر از متن")


def test_system_check_in_persian_has_buttons_not_commands(api):
    hw = get(api, "/api/system/hardware?refresh=1")
    items = {i["id"]: i for i in hw["items"]}
    assert english_or_command({"items": [{k: v for k, v in i.items() if k not in ("tech", "data")} for i in hw["items"]]}) == []
    piper = items["tts_piper"]
    assert piper["status"] != "ok" and piper["action"] == {"package": "piper"} and "Download-Models.bat --only piper" in piper["tech"]
    assert "Download-Models" not in piper["hint"] and "Download-Models" not in piper["detail"]
    moss = items["tts_moss"]
    assert moss["action"] == {"package": "moss-tts"} and moss["detail"] == "MOSS-TTS نصب نیست و نشانیِ سرورش هم داده نشده است"
    edge = items["tts_edge"]                                          # the package is installed on some PCs: the command exists only when it is missing
    assert edge["action"] is None and "pip" not in edge["hint"] and ("pip install" in edge["tech"] or edge["status"] == "ok")
    assert items["rhubarb"]["action"] == {"package": "rhubarb"} and "فاز" not in items["rhubarb"]["label"] + items["rhubarb"]["hint"]
    for i in hw["items"]:
        assert "action" in i and "tech" in i


def test_voice_engines_in_persian_have_persian_badges_and_details(api):
    d = get(api, "/api/voices/engines?language=fa")
    rows = d.get("engines") or d
    flat = " | ".join(s for _k, s in strings(rows))                    # the original English sits beside as <field>_en and is not shown
    for english in ("MIT engine; voice licence varies", "UNOFFICIAL ONLINE ENDPOINT", "synthetic audio for tests", "piper.exe not found"):
        assert english not in flat, english
    assert "سرویسِ آنلاینِ غیررسمی" in flat


def test_every_speech_and_audio_error_has_a_persian_first_line():
    from instai.providers.base import ProviderError
    from instai.providers.tts import PiperTTS

    p = PiperTTS()
    with pytest.raises(ProviderError) as e:
        p.synthesize("سلام", Path("x.wav"))
    assert e.value.fa.startswith("Piper") and "نصب" in e.value.fa
    assert e.value.user_text().splitlines()[0] == e.value.fa
    src = (ROOT / "instai" / "providers" / "tts" / "__init__.py").read_text(encoding="utf-8") + (ROOT / "instai" / "providers" / "audio" / "__init__.py").read_text(encoding="utf-8")
    import re

    raises = re.findall(r"raise ProviderError\((.*?)\)(?: from e)?\n", src)
    assert raises and all("fa=" in r for r in raises if "available" not in r), [r for r in raises if "fa=" not in r]


def test_the_catalogue_is_only_translated_on_its_own_endpoints_and_fields(api):
    """User content that happens to equal a catalogue text is never rewritten (a page called "Apache-2.0", a character role "text")."""
    page = api.post("/api/pages", {"name": "text", "format": "recurring_character", "languages": ["fa"], "idea": "image"}, format="json")
    assert page.status_code == 201
    got = api.get(f"/api/pages/{page.json()['id']}", HTTP_X_LANG="fa").json()
    assert got["name"] == "text"
    assert fc.translate({"role": "text", "other": "text"}, "fa") == {"role": "متن", "role_en": "text", "other": "text"}
