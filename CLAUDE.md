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
- Built UI is committed in `instai/static/app/`; sources in `frontend/`. Feature workstreams do NOT commit the built UI (it is rebuilt once at the end).

## The studio workflow (read `docs/STUDIO_PIPELINE.md`)
- Series go through a **development room** (template steps -> bible -> composition -> approval) and episodes through **pre-production** (script, storyboard, animatic, design, casting, gate) before production; gates follow the page's automation level.
- Apps: `instai/styles` (style & theme library), `instai/studio` (templates, boards, research docs, bible, design sheets, retakes, animatic, jobs), `instai/research_series.py` (real-series lookup), `instai/agents/llm.py` (text model per page and task).
- **Every UI text exists in Persian and English**: `frontend/src/i18n/fa.ts`, `en.ts` and `packs/*.ts`; `tests/test_i18n.py` enforces it. Never put a studio, franchise, artist or character name in a style prompt.
- A new job kind needs a `job.kind.<kind>` title in both languages; a new API error with a specific English text passes `message_en`.

## Handy commands (developer only)
- Tests: `.venv\Scripts\python -m pytest -q` (GPU/Playwright/slow markers: see `pytest.ini`).
- UI build: `cd frontend && npm install && npm run build` (writes to `instai/static/app/`).
