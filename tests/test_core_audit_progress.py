"""Audit batch "ia_core", second pass: the short progress line of a running job («shot clip 3/5», «encoding») on the home page and the queue was English
for an owner who reads Persian only. `jobs/progress_text.persian` is its Persian twin and `describe.activity` carries both (`note_fa` / `note_en`)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from instai.jobs import progress_text as pt

ROOT = Path(__file__).resolve().parents[1]
LATIN_DIGIT = re.compile(r"[0-9]")
# files whose progress line is a user's own label (a track title, a query): nothing to translate
USER_LABELS = {"instai/jobs/handlers/phase3.py"}


@pytest.mark.parametrize("text, expected", [
    ("shot clip 3/5", "کلیپِ شاتِ ۳ از ۵"),
    ("keyframe 12/40", "تصویرِ کلیدیِ ۱۲ از ۴۰"),
    ("encoding", "در حال کدگذاریِ ویدئو"),
    ("1/2 clips", "۱ کلیپ از ۲"),
    ("ComfyUI 95s", "ComfyUI، ۹۵ ثانیه"),
    ("image 1/2", "تصویرِ ۱ از ۲"),
    ("QA 12 / 90", "QA فریمِ ۱۲ از ۹۰"),
    ("12 / 90", "فریمِ ۱۲ از ۹۰"),
    ("A (2/6)", "A (۲ از ۶)"),
    ("speaking with piper", "ساختِ صدا با piper"),
])
def test_known_progress_lines_in_persian_with_persian_digits(text, expected):
    assert pt.persian(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "chrome-headless-shell.zip 45%", "downloading 3 files", "فیلم‌نامه"])
def test_anything_else_is_returned_unchanged(text):
    assert pt.persian(text) == (text if text.strip() else "")


def _literal_progress_texts() -> list[tuple[str, int, str]]:
    """Every `.progress(<fraction>, "<text>")` call of the program with a literal (or f-string) text, as a sample of what it writes."""
    found = []
    for path in sorted((ROOT / "instai").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in USER_LABELS or "/migrations/" in rel:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "progress" and len(node.args) == 2):
                continue
            arg = node.args[1]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.append((rel, node.lineno, arg.value))
            elif isinstance(arg, ast.JoinedStr):
                sample = "".join(p.value if isinstance(p, ast.Constant) else "3" for p in arg.values)
                if all(isinstance(p, ast.FormattedValue) for p in arg.values):
                    continue                                              # only a variable: a name the program was given
                found.append((rel, node.lineno, sample))
    return found


def test_every_progress_text_the_program_writes_has_a_persian_twin():
    rows = _literal_progress_texts()
    assert len(rows) > 50, "the scan found too few calls; did the code move?"
    bad = [f"{rel}:{line}  {text!r}" for rel, line, text in rows if pt.persian(text) == text]
    assert bad == [], "no Persian twin for:\n" + "\n".join(bad)


def test_the_persian_progress_lines_have_no_latin_digit_and_no_command():
    from instai.core import fa_catalog as fc

    for rel, line, text in _literal_progress_texts():
        out = pt.persian(text)
        if text in ("3: 3",):
            continue
        assert not LATIN_DIGIT.search(re.sub(r"ComfyUI|Remotion|QA", "", out)), (rel, line, out)
        assert not fc.looks_like_command(out), (rel, line, out)


@pytest.mark.django_db
def test_the_activity_of_a_running_job_carries_the_progress_text_in_both_languages():
    from instai.jobs import describe
    from instai.jobs.models import Job

    job = Job(kind="prod.final", status=Job.RUNNING, payload={}, live={}, progress=0.4, progress_text="shot clip 3/5")
    a = describe.activity(job)
    assert a["note_fa"] == "کلیپِ شاتِ ۳ از ۵" and a["note_en"] == "shot clip 3/5"
    assert a["line_fa"] == "کلیپِ شاتِ ۳ از ۵" and a["line_en"] == "shot clip 3/5"            # with no richer phase the line is the note
    job.live = {"phase": "sampling", "step": 3, "steps": 20}
    a = describe.activity(job)
    assert a["line_fa"] == "گام ۳ از ۲۰" and a["note_fa"] == "کلیپِ شاتِ ۳ از ۵"                   # the richer line and the progress both show, both Persian
    assert describe.activity(Job(kind="prod.final", status=Job.QUEUED, payload={}, live={}))["note_fa"] == ""


@pytest.mark.django_db(transaction=True)
def test_the_dashboard_answer_has_the_persian_note_of_a_running_job(api):
    from instai.jobs.models import Job

    Job.objects.create(kind="prod.final", status=Job.RUNNING, payload={}, progress=0.3, progress_text="narration 2/6", title="x")
    jobs = api.get("/api/dashboard").json()["active_jobs"]
    assert jobs and jobs[0]["progress_text"] == "narration 2/6"                              # the stored text is untouched
    assert jobs[0]["activity"]["note_fa"] == "گفتارِ شاتِ ۲ از ۶" and jobs[0]["activity"]["note_en"] == "narration 2/6"
