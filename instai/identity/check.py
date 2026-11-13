"""The consistency check: is the character in this picture still the locked character?

Three layers, cheapest first, all optional except the first:
  1. colour key - every signature colour of the locked palette (hair, outfit, accent...) must be visible in the picture. Exact for flat 2D,
     cartoon and stick styles, weak for painterly ones (the report says which colours are missing, in words the owner can act on);
  2. structure - the picture's colour/structure embedding against the approved sheet (the existing `production.consistency` embedding; it
     catches big drift only and its thresholds are heuristics until calibrated on the owner's PC);
  3. vision - a local vision model (Ollama, e.g. qwen3-vl) is shown the sheet and the picture and asked whether it is the same character.
     Used only when such a model is installed and the owner asked for the deep check; failures are reported as "not run", never as "ok".
A failed check is a FLAG for the director (a retake request can be opened from it); nothing is regenerated or deleted automatically.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image

from instai.assets.models import Asset
from instai.production import consistency as base_consistency

from . import service
from .models import CharacterLock, ConsistencyCheck

COLOUR_TOL = 52                 # RGB distance (0-441) within which a pixel counts as the palette colour
MIN_SHARE = 0.00003             # a signature colour must cover at least this share of the picture: measured shares of a small scarf on a 0.3-height figure are 0.00005..0.0003, a wrong-coloured character 0 (tests/test_stick_kit.py)
PALETTE_OK = 0.67               # share of signature colours that must be present
SIGNATURE_MIN_SAT = 40          # colours closer to grey than this (white paper, black ink) are not signature colours
VISION_OK = 7.0


def _rgb(hx: str) -> tuple[int, int, int]:
    h = hx.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def signature_colours(palette: list[dict]) -> list[dict]:
    """The palette entries that identify the character: not near-white, not near-black, not grey."""
    out = []
    for p in palette or []:
        try:
            r, g, b = _rgb(p["hex"])
        except (KeyError, ValueError, IndexError):
            continue
        if max(r, g, b) - min(r, g, b) < SIGNATURE_MIN_SAT:
            continue
        out.append(p)
    return out


def colour_shares(img: Image.Image, palette: list[dict], tol: int = COLOUR_TOL) -> list[dict]:
    """For every palette colour the share of pixels within `tol` of it."""
    im = img.convert("RGB")
    im.thumbnail((320, 320))
    px = list(im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata())
    n = max(1, len(px))
    rows = []
    for p in palette:
        r, g, b = _rgb(p["hex"])
        hit = sum(1 for (x, y, z) in px if (x - r) ** 2 + (y - g) ** 2 + (z - b) ** 2 <= tol * tol)
        rows.append({"role": p.get("role", ""), "hex": p["hex"], "name": p.get("name", ""), "share": round(hit / n, 5), "found": hit / n >= MIN_SHARE})
    return rows


def check_image(image_path: Path, lock: CharacterLock, sheet_path: Path | None = None) -> dict:
    """{palette_score, structure_score, ok, colours[], notes[{code, ...}], thresholds}"""
    with Image.open(image_path) as im:
        img = im.convert("RGB").copy()
    notes: list[dict] = []
    sig = signature_colours(lock.palette)
    palette_score = None
    colours: list[dict] = []
    if sig:
        colours = colour_shares(img, sig)
        palette_score = round(sum(1 for c in colours if c["found"]) / len(colours), 3)
        for c in colours:
            if not c["found"]:
                notes.append({"code": "colour_missing", "role": c["role"], "name": c["name"], "hex": c["hex"]})
    structure = None
    if sheet_path is not None and Path(sheet_path).exists():
        with Image.open(sheet_path) as s_:
            structure = base_consistency.palette_similarity(img, s_.convert("RGB"))
    # the colour key decides when the character has signature colours (exact for flat styles); the structure score decides only when it has none
    # (a black-and-white or painterly character) - a scene's big background colours would otherwise make a correct picture look different from the sheet
    if palette_score is not None:
        ok = palette_score >= PALETTE_OK
    else:
        ok = structure is None or structure >= base_consistency.SHEET_OK
        if structure is not None and not ok:
            notes.append({"code": "sheet_colours_differ", "value": structure})
    return {"palette_score": palette_score, "structure_score": structure, "ok": bool(ok), "colours": colours, "notes": notes,
            "thresholds": {"palette": PALETTE_OK, "structure": base_consistency.SHEET_OK, "min_share": MIN_SHARE},
            "method": "palette+structure" if structure is not None else "palette"}


# ------------------------------------------------------------------ vision (optional)

def _b64_png(path: Path, size: int = 768) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _vision_model(url: str) -> str:
    from instai.providers.ollama import OllamaProvider

    try:
        models = OllamaProvider(url, "x").list_models()
    except Exception:  # noqa: BLE001
        return ""
    for m in models:
        low = m.lower()
        if "-vl" in low or "vl:" in low or "llava" in low or "minicpm-v" in low or "gemma3" in low:
            return m
    return ""


def vision_call(sheet: Path, image: Path, name: str, url: str, model: str) -> dict | None:
    """Ask the vision model; {"same": bool, "score": 0-10, "differences": [str]} or None when it cannot answer."""
    import requests

    prompt = (f"Image 1 is the approved model sheet of the character '{name}'. Image 2 is a new picture. Is the character in image 2 the same character "
              "(same face/head shape, hair, outfit, colours, proportions) as on the sheet? Reply ONLY with JSON: "
              '{"same": true|false, "score": 0-10, "differences": ["short English phrases"]}')
    body = {"model": model, "stream": False, "format": "json", "options": {"temperature": 0.1},
            "messages": [{"role": "user", "content": prompt, "images": [_b64_png(sheet), _b64_png(image)]}]}
    try:
        r = requests.post(url.rstrip("/") + "/api/chat", json=body, timeout=300)
        r.raise_for_status()
        data = json.loads(r.json()["message"]["content"])
        return {"same": bool(data.get("same")), "score": float(data.get("score", 0)), "differences": [str(x)[:120] for x in (data.get("differences") or [])][:5]}
    except Exception:  # noqa: BLE001 - a vision model that fails is "not run"
        return None


def vision_check(sheet: Path, image: Path, name: str) -> dict | None:
    from instai.core import settings_store

    url = str(settings_store.effective("ollama_url"))
    model = _vision_model(url)
    if not model:
        return None
    res = vision_call(sheet, image, name, url, model)
    if res is not None:
        res["model"] = model
    return res


# ------------------------------------------------------------------ shots and episodes

def current_keyframe(shot) -> Asset | None:
    return Asset.objects.filter(shot=shot, role="keyframe", is_current=True).order_by("-version").first()


def check_shot(shot, ep, *, deep: bool = False) -> list[ConsistencyCheck]:
    """Check the current keyframe of `shot` against every locked character that appears in it. Stores one ConsistencyCheck per character."""
    kf = current_keyframe(shot)
    if kf is None:
        return []
    from instai.assets import storage as asset_storage

    if not asset_storage.storage.exists(kf.path):
        return []
    path = asset_storage.storage.path_for(kf.path)
    out = []
    for ident in service.identities_for_shot(shot, ep):
        sheet = ident.refs[0] if ident.refs else None
        res = check_image(path, ident.lock, sheet)
        vision = None
        if deep and sheet is not None:
            vision = vision_check(sheet, path, ident.character.name)
            if vision is not None and (not vision["same"] or vision["score"] < VISION_OK):
                res["ok"] = False
                res["notes"].append({"code": "vision_differs", "score": vision["score"], "differences": vision["differences"]})
            elif vision is None:
                res["notes"].append({"code": "vision_not_run"})
        res["method"] = res["method"] + ("+vision" if vision else "")
        row = ConsistencyCheck.objects.create(character=ident.character, shot=shot, asset=kf, lock_version=ident.lock.version, palette_score=res["palette_score"],
                                              structure_score=res["structure_score"], vision_score=vision["score"] if vision else None, method=res["method"],
                                              ok=res["ok"], notes=res["notes"])
        out.append(row)
    return out


def check_dict(c: ConsistencyCheck) -> dict:
    return {"id": c.pk, "character": c.character_id, "character_name": c.character.name, "shot": c.shot_id, "asset": c.asset_id, "lock_version": c.lock_version,
            "palette_score": c.palette_score, "structure_score": c.structure_score, "vision_score": c.vision_score, "method": c.method, "ok": c.ok, "notes": c.notes,
            "created_at": c.created_at}


def episode_report(ep) -> dict:
    """The newest check of every (shot, character) of the episode, grouped by character, with the list of flagged shots."""
    from instai.story import services as story_services

    shots = story_services.all_shots(ep)
    latest: dict[tuple[int, int], ConsistencyCheck] = {}
    for c in ConsistencyCheck.objects.filter(shot__in=shots).select_related("character").order_by("id"):
        latest[(c.shot_id, c.character_id)] = c
    rows = []
    for s in shots:
        idents = service.identities_for_shot(s, ep)
        kf = current_keyframe(s)
        checks = [latest.get((s.pk, i.character.pk)) for i in idents]
        stale = [c for c in checks if c is not None and kf is not None and c.asset_id != kf.pk]
        rows.append({"shot": s.pk, "label": f"{s.scene.index}.{s.index}", "keyframe_url": kf.url if kf else None,
                     "characters": [{"id": i.character.pk, "name": i.character.name, "lock_version": i.lock.version,
                                     "check": check_dict(latest[(s.pk, i.character.pk)]) if (s.pk, i.character.pk) in latest else None} for i in idents],
                     "stale": bool(stale)})
    flagged = [r for r in rows if any(c["check"] and not c["check"]["ok"] for c in r["characters"])]
    checked = [c for r in rows for c in r["characters"] if c["check"]]
    return {"shots": rows, "flagged": [r["shot"] for r in flagged], "checked": len(checked), "ok": len([c for c in checked if c["check"]["ok"]]),
            "locked_characters": sorted({c["name"] for r in rows for c in r["characters"]})}


def run_episode(ep, *, deep: bool = False) -> dict:
    from instai.story import services as story_services

    n = 0
    for s in story_services.all_shots(ep):
        n += len(check_shot(s, ep, deep=deep))
    rep = episode_report(ep)
    rep["ran"] = n
    return rep


def open_retakes(ep, shot_ids: list[int] | None = None, *, mode: str = "preview") -> list:
    """A retake request (keyframe) for every flagged shot (or the given ones): the director's note says what was wrong. Existing open requests are not repeated."""
    from instai.studio import preprod
    from instai.studio.models import RetakeRequest
    from instai.story.models import Shot

    rep = episode_report(ep)
    wanted = set(shot_ids) if shot_ids else set(rep["flagged"])
    made = []
    for row in rep["shots"]:
        if row["shot"] not in wanted:
            continue
        shot = Shot.objects.get(pk=row["shot"])
        if RetakeRequest.objects.filter(shot=shot, status="open", reason__startswith="[identity]").exists():
            continue
        bits = []
        for c in row["characters"]:
            if c["check"] and not c["check"]["ok"]:
                bits += [f"{c['name']}: " + (n.get("code", "") + (" " + n.get("name", "") if n.get("name") else "")) for n in c["check"]["notes"]]
        r, _jobs = preprod.request_retake(shot, "keyframe", "[identity] " + "; ".join(bits)[:1800], mode=mode, actor="system")
        made.append(r)
    return made
