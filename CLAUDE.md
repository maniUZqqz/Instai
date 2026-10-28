# InstAI - working rules

Full product and engineering brief: `docs/BRIEF.md` (read it first in every new session).
Decisions made so far: `docs/DECISIONS.md`. Measured numbers: `docs/BENCHMARKS.md`. Models and licences: `docs/MODELS.md`.

## Working with the owner (brief section 0)
- The owner reads **Persian only**. Every report, question and summary to him is plain Persian: short, facts and numbers, no jargon.
  Code, identifiers and commit messages stay in English.
- He is not a command-line user. Anything he must run is a double-click `.bat` file or a button in the UI.
  Never tell him to type a command with flags. Console text inside `.bat` files is **English/ASCII** (the Windows console garbles Persian).
- Work in phases (brief section 11). Each phase ends with: a running app, green tests, a commit/push to `main`,
  and a Persian report (what works, what was measured, what is not done, what he must decide).
- Ask him only what is truly his decision: content, taste, money, accounts, licences. Decide engineering questions
  yourself and write them in `docs/DECISIONS.md`, one line each, with the reason.
- Never claim quality or speed that was not measured on his hardware. Measured numbers go to `docs/BENCHMARKS.md`.

## Engineering rules (brief section 12)
- Tests for every service: unit tests, an end-to-end pipeline test with **fake providers** (runs without a GPU),
  Playwright checks of the main screens, and a GPU smoke test that runs only on the real machine (`pytest -m gpu`).
- Structured logs, health checks, migrations, `.env.example`. No secrets, no models, no user data in git.
- Idempotent jobs and resumable downloads. Never delete user files; move them aside instead.
- Keep the app usable while a long render runs. Realistic ETAs come from measured runs.
- Small, readable modules. Comments only where the reason is not obvious.
- Commit after every working step. Push to `main` at the end of each phase.

## Project rules
- InstAI is a **separate product** from NMarketing (repo `Qasem`). Never modify Qasem, never import it at runtime;
  code adapted from it carries a one-line `Adapted from Qasem: <path>` note.
- Python 3.10-3.13 compatible (no `datetime.UTC`, `tomllib`, `StrEnum`, `typing.Self`).
- Everything must be testable with the **fake** providers; hardware/model detection degrades to "not found".
- The project is local-only (single user, no server). Never put API keys in code or logs; they live in `.env`.
- Built UI is committed in `instai/static/app/`; sources in `frontend/`.

## Handy commands (developer only)
- Tests: `.venv\Scripts\python -m pytest -q` (GPU/Playwright/slow markers: see `pytest.ini`).
- UI build: `cd frontend && npm install && npm run build` (writes to `instai/static/app/`).
