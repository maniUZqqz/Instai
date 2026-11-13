"""Character identity: create / edit / lock the identity of a character, and turn it into what a keyframe needs (identity words, colour key,
seed, reference pictures, the workflow that can use them). The pipeline calls `plan_for_shot`, `hash_part` and `default_seed`; nothing here
changes behaviour for a character that has no LOCKED identity."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from instai.assets import storage as asset_storage
from instai.core.errors import DomainError
from instai.pages.models import Character, CharacterReference
from instai.production import consistency as base_consistency
from instai.render.stick import spec as stick_spec

from . import strategies
from .models import CharacterLock

IDENTITY_NEGATIVE = "different outfit, different hairstyle, different colours, inconsistent character design, extra accessories, redesigned character"


# ------------------------------------------------------------------ the lock row

def get_lock(character: Character) -> CharacterLock | None:
    return CharacterLock.objects.filter(character=character).first()


def _seed_for(character: Character) -> int:
    return int(hashlib.sha256(f"{character.pk}|{character.name}".encode("utf-8")).hexdigest()[:8], 16) % (2 ** 31)


def ensure_lock(character: Character) -> CharacterLock:
    lock = get_lock(character)
    if lock is None:
        lock = CharacterLock.objects.create(character=character, seed=_seed_for(character), anchor=(character.appearance or "")[:600])
    return lock


def look_series(page, series_id: int | None = None):
    """The series whose art style (chosen once on the ladder) must also dress this page's characters: the one the job names, else the page's only series that has
    a look of its own. None = the page's own visual profile applies. A page with several different series is never guessed: the page's profile stays in force."""
    from instai.story.models import Series

    if series_id:
        s = Series.objects.filter(pk=series_id, page=page).first()
        if s is not None:
            return s
    own = [s for s in Series.objects.filter(page=page) if (s.look or {}).get("style_key")]
    return own[0] if len(own) == 1 else None


def _bad(code: str, fa: str, en: str, status: int = 409) -> DomainError:
    return DomainError(code, fa, http_status=status, message_en=en)


def edit_lock(character: Character, data: dict) -> CharacterLock:
    lock = ensure_lock(character)
    if lock.status == "locked":
        raise _bad("conflict", "هویت قفل است؛ برای ویرایش ابتدا قفل را باز کنید.", "The identity is locked; unlock it first to edit.")
    if "anchor" in data:
        lock.anchor = str(data["anchor"] or "").strip()[:900]
    if "avoid" in data:
        lock.avoid = str(data["avoid"] or "").strip()[:600]
    if "seed" in data:
        try:
            lock.seed = max(0, min(2 ** 31 - 1, int(data["seed"])))
        except (TypeError, ValueError):
            raise _bad("validation_error", "دانه باید عدد باشد.", "The seed must be a number.", 400)
    if "strategy" in data:
        if data["strategy"] not in dict(CharacterLock.STRATEGIES):
            raise _bad("validation_error", "راهبرد ناشناخته است.", "Unknown strategy.", 400)
        lock.strategy = data["strategy"]
    if "palette" in data:
        pal = []
        for row in (data["palette"] or [])[:10]:
            hx = stick_spec._hex(row.get("hex") if isinstance(row, dict) else row, "")
            if hx:
                pal.append({"role": str((row.get("role") if isinstance(row, dict) else "") or "colour")[:24], "hex": hx, "name": stick_spec.colour_name(hx)})
        lock.palette = pal
    if "notes" in data:
        lock.notes = str(data["notes"] or "")[:1000]
    lock.save()
    return lock


def reference_paths(lock: CharacterLock) -> list[Path]:
    """The approved sheets of the lock that exist on disk, sheet first (the model sheet), then the expression sheet, then extras."""
    ids = [lock.refs.get("sheet"), lock.refs.get("expressions")] + list(lock.refs.get("extra") or [])
    out: list[Path] = []
    for rid in ids:
        if not rid:
            continue
        ref = CharacterReference.objects.filter(pk=rid, character=lock.character).exclude(asset=None).select_related("asset").first()
        if ref and asset_storage.storage.exists(ref.asset.path):
            out.append(asset_storage.storage.path_for(ref.asset.path))
    return out


def suggest_palette(image_path: Path, n: int = 6) -> list[dict]:
    """The main flat colours of a model sheet (paper white and near-black ignored): [{role, hex, name}] for the owner to name and keep."""
    from PIL import Image

    with Image.open(image_path) as im:
        small = im.convert("RGB")
        small.thumbnail((320, 320))
    q = small.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    out: list[dict] = []
    for cnt, idx in counts:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        if min(r, g, b) > 232 or max(r, g, b) < 42:
            continue
        hx = "#%02x%02x%02x" % (r, g, b)
        if all(sum((a - c) ** 2 for a, c in zip(stick_spec.hex_rgba(hx)[:3], stick_spec.hex_rgba(o["hex"])[:3])) > 40 ** 2 for o in out):
            out.append({"role": f"colour {len(out) + 1}", "hex": hx, "name": stick_spec.colour_name(hx)})
        if len(out) >= n:
            break
    return out


def signature_of(image_path: Path) -> list[float]:
    from PIL import Image

    with Image.open(image_path) as im:
        return [round(x, 5) for x in base_consistency.hist_embedding(im.convert("RGB"))]


def lock_identity(character: Character) -> CharacterLock:
    """Approve the identity: needs identity words and at least one reference picture (or a stick spec). Approves the referenced sheets."""
    lock = ensure_lock(character)
    refs = reference_paths(lock)
    if not lock.anchor.strip():
        raise _bad("not_ready", "برای قفل کردن، توصیف هویت (anchor) لازم است.", "The identity words (anchor) are needed before locking.")
    if not refs and not lock.stick:
        raise _bad("not_ready", "برای قفل کردن، حداقل یک برگهٔ مدل لازم است.", "At least one model sheet is needed before locking.")
    ids = [lock.refs.get("sheet"), lock.refs.get("expressions")] + list(lock.refs.get("extra") or [])
    CharacterReference.objects.filter(pk__in=[i for i in ids if i], character=character).update(approved=True)
    if refs:
        lock.signature = {"hist": signature_of(refs[0]), "path": refs[0].name}
    lock.status, lock.locked_at = "locked", timezone.now()
    lock.version += 1
    lock.save()
    character.approved = True
    character.save(update_fields=["approved"])
    return lock


def unlock_identity(character: Character) -> CharacterLock:
    lock = ensure_lock(character)
    lock.status = "draft"
    lock.save(update_fields=["status", "updated_at"])
    return lock


# ------------------------------------------------------------------ stick characters

def build_stick(character: Character, spec_in: dict | None = None) -> CharacterLock:
    """Draw (or redraw) the character as a stick figure: the rig for puppet videos, the model sheet picture, the identity words and the colour key.
    The result is a DRAFT lock; the owner looks at the sheet and locks it."""
    from instai.production.models import CharacterRig
    from instai.render.stick import compose, parts

    lock = ensure_lock(character)
    if lock.status == "locked":
        raise _bad("conflict", "هویت قفل است؛ ابتدا قفل را باز کنید.", "The identity is locked; unlock it first.")
    base = lock.stick or {}
    spec = stick_spec.normalize({**base, **(spec_in or {})}, name=character.name)
    root = Path(settings.MEDIA_ROOT)
    last = CharacterRig.objects.filter(character=character).order_by("-version").first()
    version = (last.version + 1) if last else 1
    folder = root / "characters" / str(character.pk) / f"stick{version}"
    rig_spec = parts.make_rig_spec(spec, folder, root)
    CharacterRig.objects.create(character=character, version=version, name=f"{character.name} (stick)", source="stick", spec=rig_spec, approved=False)
    work = root / "characters" / str(character.pk) / "stickwork"
    sheet_png = folder / "_sheet-tmp.png"
    language = (character.page.language or "fa")[:2]
    compose.model_sheet(spec, sheet_png, work, title=character.name, language=language if language in ("fa", "en") else "fa")
    asset = asset_storage.register(sheet_png, f"characters/{character.pk}/stick{version}/model-sheet.png", kind="image", role="reference", page=character.page,
                                   provenance={"purpose": "model_sheet", "engine": "stick", "spec": spec, "spec_hash": stick_spec.spec_hash(spec)})
    ref = CharacterReference.objects.create(character=character, kind="sheet", label=f"stick model sheet v{version}", asset=asset, approved=False)
    lock.stick, lock.source = spec, "stick"
    lock.anchor = stick_spec.anchor_text(spec)
    lock.avoid = "shading, gradients, realistic anatomy, different colours, extra accessories, thin lines, filled bodies"
    lock.palette = stick_spec.palette(spec)
    lock.refs = {**lock.refs, "sheet": ref.pk}
    lock.save()
    return lock


# ------------------------------------------------------------------ what a keyframe needs

@dataclass
class Identity:
    character: Character
    lock: CharacterLock
    refs: list[Path] = field(default_factory=list)
    lora: str = ""


@dataclass
class Plan:
    workflow: str            # "" = the page's own image workflow
    inputs: dict
    files: dict
    note: str
    strategy: str
    identities: list[Identity]


def characters_in_shot(shot, ep) -> list[Character]:
    page = ep.series.page
    chars = {c.name: c for c in page.characters.all()}
    found: list[Character] = []

    def add(c: Character | None) -> None:
        if c is not None and c not in found:
            found.append(c)

    if shot.speaker:
        add(chars.get(shot.speaker.strip()))
    for c in shot.scene.characters.all():
        add(c)
    text = f"{shot.description} {shot.image_prompt}".lower()
    for name, c in chars.items():
        if name and name.lower() in text:
            add(c)
    return found[:3]


def _approved_lora(character: Character) -> str:
    from instai.production.models import CharacterLora

    row = CharacterLora.objects.filter(character=character, approved=True, status="trained").exclude(lora_file="").first()
    return row.lora_file if row else ""


def identities_for_shot(shot, ep) -> list[Identity]:
    return identities_for_characters(characters_in_shot(shot, ep))


def hash_part(shot, ep) -> str:
    """Changes when a locked identity that appears in the shot changes (so only those pictures are made again)."""
    ids = identities_for_shot(shot, ep)
    if not ids:
        return ""
    return "|".join(f"{i.character.pk}:{i.lock.version}:{i.lock.strategy}:{len(i.refs)}:{i.lora}" for i in ids)


def default_seed(shot, ep) -> int | None:
    """The identity seed of the character when exactly one locked non-stick character is in the shot, else None (the pipeline's own seed)."""
    ids = [i for i in identities_for_shot(shot, ep) if i.lock.source != "stick"]
    return int(ids[0].lock.seed) if len(ids) == 1 and ids[0].lock.seed else None


def identity_text(ids: list[Identity]) -> str:
    bits = []
    for i in ids:
        pal = ", ".join(f"{p['name']} {p['role']}" for p in (i.lock.palette or [])[:6] if p.get("name"))
        bits.append(f"{i.character.name}: {i.lock.anchor}" + (f" (colour key: {pal})" if pal else ""))
    return "Characters, keep every design exactly the same as always: " + "; ".join(bits)


def _usable(strategy: str, ids: list[Identity], wf) -> bool:
    if strategy == "multiref_edit":
        return all(i.refs for i in ids) and strategies._workflow_ok(["qwen_image_edit_multiref"])
    if strategy == "sheet_edit":
        return bool(ids[0].refs) and bool(wf())
    if strategy == "lora":
        return len(ids) == 1 and bool(ids[0].lora) and strategies._workflow_ok(["flux_dev_fp8_t2i_lora"])
    return strategy == "anchor_seed"


def identities_for_characters(chars: list[Character]) -> list[Identity]:
    out = []
    for c in chars:
        lock = get_lock(c)
        if lock is not None and lock.status == "locked":
            out.append(Identity(c, lock, reference_paths(lock), _approved_lora(c)))
    return out


def plan_for_shot(shot, ep, base_inputs: dict, reference_workflow=lambda: None) -> Plan | None:
    """How to draw this shot's keyframe so its locked characters stay identical; None when no locked character appears (nothing to do)."""
    return _plan([i for i in identities_for_shot(shot, ep) if i.lock.source != "stick"], base_inputs, reference_workflow)


def plan_for_characters(chars: list[Character], base_inputs: dict, reference_workflow=lambda: None) -> Plan | None:
    """The same plan for any picture that shows these characters (choice-story posts, covers)."""
    return _plan([i for i in identities_for_characters(chars[:3]) if i.lock.source != "stick"], base_inputs, reference_workflow)


def _plan(ids: list[Identity], base_inputs: dict, reference_workflow) -> Plan | None:
    if not ids:
        return None
    pref = ids[0].lock.strategy
    chain = ([pref] if pref not in ("auto", "stick_rig", "") else []) + [s for s in strategies.ORDER if s != "stick_rig"]
    strategy = next((s for s in chain if _usable(s, ids, reference_workflow)), "anchor_seed")
    note_code = "as_chosen" if (pref == strategy) else ("auto" if pref in ("auto", "") else "fallback")
    negative = ", ".join(x for x in (base_inputs.get("negative_prompt", ""), IDENTITY_NEGATIVE, *[i.lock.avoid for i in ids if i.lock.avoid]) if x)
    seed = base_inputs.get("seed")
    if len(ids) == 1 and ids[0].lock.seed and strategy in ("anchor_seed", "lora"):
        seed = int(ids[0].lock.seed)
    prompt = f"{identity_text(ids)}. {base_inputs['prompt']}"
    inputs = dict(base_inputs, negative_prompt=negative, seed=seed)
    files: dict = {}
    wid = ""
    if strategy == "multiref_edit":
        wid = "qwen_image_edit_multiref"
        names = ", ".join(f"image {n + 1} is the model sheet of {i.character.name}" for n, i in enumerate(ids))
        inputs["prompt"] = f"{names}. Draw {', '.join(i.character.name for i in ids)} together in this scene, keeping each character's exact design, proportions and colours: {base_inputs['prompt']}"
        inputs["image"] = "@input:ref.png"
        files["ref.png"] = ids[0].refs[0]
        for n, i in enumerate(ids[1:3], start=2):
            inputs[f"image{n}"] = f"@input:ref{n}.png"
            files[f"ref{n}.png"] = i.refs[0]
        inputs.pop("steps", None)
    elif strategy == "sheet_edit":
        wid = reference_workflow() or ""
        inputs["prompt"] = prompt + ", keep exactly the same character design, face, hair and outfit as in the reference image"
        inputs["image"] = "@input:ref.png"
        files["ref.png"] = ids[0].refs[0]
        if wid != "flux_dev_fp8_img2img":
            inputs.pop("width", None)
            inputs.pop("height", None)
            inputs.pop("steps", None)
    elif strategy == "lora":
        wid = "flux_dev_fp8_t2i_lora"
        inputs["prompt"] = prompt
        inputs["lora_name"] = ids[0].lora
    else:
        inputs["prompt"] = prompt
    names = ", ".join(i.character.name for i in ids)
    note = f"identity: {names} - {strategy} ({note_code})"
    return Plan(wid, inputs, files, note, strategy, ids)
