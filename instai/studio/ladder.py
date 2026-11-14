"""The studio ladder engine: every stage's output is versioned and has to be approved before the stages that need it can be approved.

Rules (see docs/STUDIO_PIPELINE.md, "The ladder"):
  * a stage is `empty` (nothing yet), `draft` (a version exists, not approved), `approved`, or `stale` (approved, but a stage it was approved on top of has a newer approved
    version, or - for bridged stages - the live content changed since). Staleness is computed, never stored, so nothing can get out of step;
  * approving needs every stage it `needs` to be approved (409 otherwise) - drafting ahead is allowed, approving out of order is not;
  * saving a new version of an approved stage withdraws its approval (a changed output is a new thing to look at);
  * versions are never edited or deleted: an edit, a model run, a restore each add one; `diff` compares any two;
  * the page's automation level decides which stages wait for a human click; the others pass by themselves once they exist and everything before them is approved
    (marked `auto`, still editable; an edit re-opens them). Nothing is ever published automatically.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from instai.core.errors import DomainError

from . import ladder_bridge as bridge
from .ladder_stages import BY_KEY, PHASES, PREPRODUCTION_GATE, STAGES, needs_human
from .models import StageDoc, StageVersion


def _bad(code: str, fa: str, en: str, status: int = 409, **details) -> DomainError:
    return DomainError(code, fa, http_status=status, message_en=en, details=details or None)


def stage(key: str) -> dict:
    if key not in BY_KEY:
        raise DomainError("not_found", http_status=404)
    return BY_KEY[key]


def _scope_ep(st: dict, ep):
    if st["scope"] == "episode":
        if ep is None:
            raise _bad("validation_error", "این مرحله به یک قسمت نیاز دارد.", "This stage needs an episode.", 400)
        return ep
    return None


def doc(series, ep, key: str, *, create: bool = False) -> StageDoc | None:
    st = stage(key)
    e = _scope_ep(st, ep)
    d = StageDoc.objects.filter(series=series, key=key, episode=e).first()
    if d is None and create:
        d = StageDoc.objects.create(series=series, episode=e, key=key)
    return d


def latest(d: StageDoc | None) -> StageVersion | None:
    return d.versions.order_by("-number").first() if d else None


def version(d: StageDoc | None, number: int) -> StageVersion | None:
    return d.versions.filter(number=number).first() if d else None


def has_versions(series, ep, key: str) -> bool:
    d = doc(series, ep, key)
    return bool(d and d.current_version)


def _live(st: dict, series, ep) -> dict | None:
    key = "look" if st.get("live") == "look" else st["key"]
    return bridge.live(key, series, ep) if (st["source"] == "bridge" or st.get("live")) else None


# ------------------------------------------------------------------ statuses

def rows(series, ep=None) -> dict[str, dict]:
    """{key: row} for every stage that applies (series stages always, episode stages when `ep` is given), computed in ladder order."""
    qs = StageDoc.objects.filter(series=series)
    qs = qs.filter(Q(episode__isnull=True) | Q(episode=ep)) if ep is not None else qs.filter(episode__isnull=True)
    docs = {(d.key, d.episode_id): d for d in qs}
    out: dict[str, dict] = {}
    page = series.page
    for st in STAGES:
        if st["scope"] == "episode" and ep is None:
            continue
        key = st["key"]
        d = docs.get((key, ep.pk if (st["scope"] == "episode" and ep is not None) else None))
        lv = _live(st, series, ep)
        if lv is not None and st["source"] == "bridge" and lv["ready"] and (d is None or d.current_version == 0 or latest(d).content_hash != lv["hash"]):
            d = _sync_version(series, ep, st, lv)
        nver = d.current_version if d else 0
        blocked = [n for n in st["needs"] if n in out and out[n]["status"] != "approved"]
        status, reasons = "empty", []
        if nver:
            status = "draft"
            if d.approved_version:
                status = "approved"
                for n in st["needs"]:
                    rec = int((d.approved_inputs or {}).get(n, 0))
                    cur = out[n]["approved_version"] if n in out else 0
                    if rec != cur:
                        reasons.append({"code": "upstream", "stage": n})
                if lv is not None and d.approved_hash and lv["hash"] != d.approved_hash:
                    reasons.append({"code": "changed"})
                if reasons:
                    status = "stale"
        elif lv is not None and lv["ready"]:
            status = "draft"
        if (status == "draft" and nver and lv is not None and st["source"] == "bridge" and lv["approved_elsewhere"] and not blocked and not d.approved_version):
            d.approved_version, d.approved_hash = d.current_version, lv["hash"]            # approved somewhere else in InstAI (dev room, pre-production): take it over
            d.approved_inputs = {n: (out[n]["approved_version"] if n in out else 0) for n in st["needs"]}
            d.auto_approved, d.approved_at = False, timezone.now()
            d.save()
            status = "approved"
        row = {"key": key, "scope": st["scope"], "phase": st["phase"], "source": st["source"], "gen": st["gen"], "needs": st["needs"], "status": status, "stale_reasons": reasons,
               "blocked_by": blocked, "version": nver, "approved_version": d.approved_version if d else 0, "auto": bool(d and d.auto_approved and d.approved_version),
               "approved_at": d.approved_at if d else None, "needs_human": needs_human(page, key), "ready": bool(lv["ready"]) if (lv is not None and st["source"] == "bridge") else nver > 0,
               "live": lv is not None}
        out[key] = row
    return out


def _sync_version(series, ep, st: dict, lv: dict) -> StageDoc:
    d = doc(series, ep, st["key"], create=True)
    last = latest(d)
    if last is None or last.content_hash != lv["hash"]:
        _add_version(d, st, lv["data"], "system", "synced from the live work", {}, lv["hash"], {})
        d.refresh_from_db()
    return d


def _add_version(d: StageDoc, st: dict, data: dict, author: str, note: str, inputs: dict, content_hash: str, provenance: dict) -> StageVersion:
    n = d.current_version + 1
    content_hash = content_hash or bridge.h(data)
    v = StageVersion.objects.create(doc=d, number=n, data=bridge.json_safe(data), author=author, note=note[:300], inputs=bridge.json_safe(inputs), content_hash=content_hash,
                                    provenance=bridge.json_safe(provenance))
    d.current_version = n
    d.save(update_fields=["current_version", "updated_at"])
    return v


def _approved_inputs(series, ep, st: dict) -> dict:
    out = {}
    for n in st["needs"]:
        dn = doc(series, ep, n)
        out[n] = dn.approved_version if dn else 0
    return out


# ------------------------------------------------------------------ writing versions

def normalize_data(key: str, data: dict) -> dict:
    """Keep only the fields of the stage and the right types (rows stay lists of dicts); unknown keys are dropped."""
    st = stage(key)
    if not st["fields"]:
        return dict(data or {})
    out: dict = {}
    for f in st["fields"]:
        v = (data or {}).get(f["key"])
        if f["type"] == "rows":
            cols = {c["key"]: c for c in f["columns"]}
            rws = []
            for r in (v or [])[:200]:
                if isinstance(r, dict):
                    row = {}
                    for ck, c in cols.items():
                        x = r.get(ck)
                        if c["type"] == "number":
                            try:
                                x = float(x) if x not in (None, "") else None
                            except (TypeError, ValueError):
                                x = None
                        elif c["type"] == "bool":
                            x = bool(x)
                        elif isinstance(x, list):
                            x = [str(i) for i in x]
                        else:
                            x = "" if x is None else str(x)
                        row[ck] = x
                    for extra in ("characters", "props"):         # list columns that the table does not show but the roles produce
                        if isinstance(r.get(extra), list):
                            row[extra] = [str(i) for i in r[extra]][:8]
                    rws.append(row)
            out[f["key"]] = rws
        elif f["type"] == "list":
            out[f["key"]] = [str(i) for i in (v or [])][:40] if isinstance(v, list) else ([str(v)] if v else [])
        elif f["type"] == "number":
            try:
                out[f["key"]] = float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                out[f["key"]] = None
        else:
            out[f["key"]] = "" if v is None else str(v)
    return out


@transaction.atomic
def save_version(series, ep, key: str, data: dict, *, author: str = "human", note: str = "", provenance: dict | None = None) -> StageVersion:
    """Add a version. A change to an approved stage withdraws the approval."""
    st = stage(key)
    if st["source"] == "bridge":
        raise _bad("conflict", "این مرحله از جای دیگری ساخته می‌شود و اینجا ویرایش نمی‌شود.", "This stage is made elsewhere and cannot be edited here.")
    clean = normalize_data(key, data)
    d = doc(series, ep, key, create=True)
    last = latest(d)
    if last is not None and last.content_hash == bridge.h(clean) and author != "ai":
        return last                                  # nothing changed: no new version
    v = _add_version(d, st, clean, author, note, _approved_inputs(series, ep, st), bridge.h(clean), provenance or {})
    if d.approved_version:
        d.approved_version, d.approved_hash, d.auto_approved, d.approved_at, d.approved_inputs = 0, "", False, None, {}
        d.save()
    return v


def restore(series, ep, key: str, number: int) -> StageVersion:
    d = doc(series, ep, key)
    old = version(d, number)
    if old is None:
        raise DomainError("not_found", http_status=404)
    return save_version(series, ep, key, old.data, author="human", note=f"restored version {number}")


# ------------------------------------------------------------------ approval

def approve(series, ep, key: str, number: int | None = None, *, auto: bool = False) -> dict:
    st = stage(key)
    _scope_ep(st, ep)
    table = rows(series, ep)
    row = table[key]
    if row["status"] == "empty":
        raise _bad("not_ready", "این مرحله هنوز خروجی ندارد.", "This stage has no output yet.")
    names = [BY_KEY[n]["en"] for n in row["blocked_by"]]
    if row["blocked_by"]:
        raise _bad("not_ready", "ابتدا مرحله‌های پیش‌نیاز را تأیید کنید: " + "، ".join(BY_KEY[n]["fa"] for n in row["blocked_by"]), "Approve the stages before it first: " + ", ".join(names),
                   blocked_by=row["blocked_by"])
    d = doc(series, ep, key, create=True)
    num = int(number or d.current_version)
    if version(d, num) is None:
        raise DomainError("not_found", http_status=404)
    if st["source"] == "bridge" and num != d.current_version:
        raise _bad("conflict", "فقط نسخهٔ جاری یک مرحلهٔ پیوندی را می‌شود تأیید کرد.", "Only the current version of a bridged stage can be approved.")
    d.approved_version, d.approved_inputs = num, _approved_inputs(series, ep, st)
    d.auto_approved, d.approved_at = bool(auto), timezone.now()
    d.save()
    _side_effects(series, ep, key)                       # first: approving the art style writes the series look, and the stale check compares with that
    lv = _live(st, series, ep)
    d.approved_hash = lv["hash"] if lv else ""
    d.save(update_fields=["approved_hash", "updated_at"])
    return rows(series, ep)[key]


def _side_effects(series, ep, key: str) -> None:
    """Keep the older, stage-specific approvals in step (best effort: the ladder record is what counts)."""
    from . import preprod, services

    try:
        if key == "art_style":
            v = latest(doc(series, ep, key))
            look = {k: v.data.get(k, "") for k in ("style_key", "realism", "theme_key") if v and v.data.get(k)}
            if look.get("style_key"):
                series.look = look
                series.save(update_fields=["look", "updated_at"])
        elif key == "bible":
            services.approve_bible(series, auto=True)
        elif key in ("animatic", "design") and ep is not None:
            preprod.approve_stage(ep, key)
    except DomainError:
        pass


def revoke(series, ep, key: str) -> dict:
    st = stage(key)
    _scope_ep(st, ep)
    d = doc(series, ep, key)
    if d and d.approved_version:
        d.approved_version, d.approved_hash, d.auto_approved, d.approved_at, d.approved_inputs = 0, "", False, None, {}
        d.save()
    return rows(series, ep)[key]


def auto_pass(series, ep=None) -> list[str]:
    """Approve, in ladder order, every stage that is allowed to pass without a human at the page's automation level. Returns the keys approved."""
    done: list[str] = []
    for _ in range(len(STAGES)):
        table = rows(series, ep)
        moved = False
        for st in STAGES:
            r = table.get(st["key"])
            if r is None or r["status"] not in ("draft", "stale") or r["needs_human"] or r["blocked_by"] or not r["ready"]:
                continue
            if st["gen"] is None and st["source"] == "stored":      # made by the owner (art style): never passes by itself
                continue
            try:
                approve(series, ep, st["key"], auto=True)
            except DomainError:
                continue
            done.append(st["key"])
            moved = True
            break
        if not moved:
            break
    return done


def preproduction_blockers(series, ep) -> list[str]:
    table = rows(series, ep)
    return [k for k in PREPRODUCTION_GATE if table[k]["status"] != "approved"]


# ------------------------------------------------------------------ reading

def diff(a: dict, b: dict) -> list[dict]:
    """Differences between two version payloads: [{path, before, after}] (lists of rows are compared row by row)."""
    out: list[dict] = []

    def walk(x, y, path: str) -> None:
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                walk(x.get(k), y.get(k), f"{path}.{k}" if path else k)
        elif isinstance(x, list) and isinstance(y, list) and any(isinstance(i, (dict, list)) for i in x + y):
            for i in range(max(len(x), len(y))):
                walk(x[i] if i < len(x) else None, y[i] if i < len(y) else None, f"{path}[{i + 1}]")
        elif x != y:
            out.append({"path": path, "before": x, "after": y})

    walk(a or {}, b or {}, "")
    return out[:200]


def version_dict(v: StageVersion, *, data: bool = False) -> dict:
    out = {"number": v.number, "author": v.author, "note": v.note, "created_at": v.created_at, "inputs": v.inputs, "provenance": v.provenance}
    if data:
        out["data"] = v.data
    return out


def payload(series, ep=None) -> dict:
    """The review screen: every stage with its status, versions and current data."""
    table = rows(series, ep)
    out = []
    for st in STAGES:
        r = table.get(st["key"])
        if r is None:
            continue
        d = doc(series, ep, st["key"])
        cur = latest(d)
        out.append({**r, "fa": st["fa"], "en": st["en"], "term_fa": st["term_fa"], "term_en": st["term_en"], "fields": st["fields"],
                    "data": cur.data if cur else None, "current": version_dict(cur) if cur else None,
                    "versions": [version_dict(v) for v in (d.versions.all()[:30] if d else [])]})
    counts: dict[str, int] = {}
    for r in out:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"phases": PHASES, "stages": out, "counts": counts, "gate": PREPRODUCTION_GATE, "blockers": [k for k in PREPRODUCTION_GATE if k in table and table[k]["status"] != "approved"],
            "level": series.page.automation_level}
