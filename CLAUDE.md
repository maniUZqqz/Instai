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

## Model discovery (Models page)
- Never ask the owner for paths: `instai/core/discovery.py` finds ComfyUI / NMarketing voice engines / Piper / Ollama; `core/model_status.py` is the registry, the Models page payload and the offers. Use `runtime.comfyui_dir()`, `services.paths(key)`, `runtime.find_tool("piper")`; never hard-code a folder.
- Tests: `INSTAI_SCAN_DEFAULTS=0` (root conftest) keeps discovery off the real disk; give fake trees via `INSTAI_SCAN_ROOTS` or the `model_paths` setting (see tests/test_discovery.py).
- Optional downloads are `offer` blocks in `manifests/*.json`; they are fetched only after `confirm: true` from the UI. Pin a commit and sha256 for every new file.

## GPU use, model tests, queue status (2026-11-02; reasons in `docs/DECISIONS.md`)
- The owner saw Task Manager's GPU idle. ComfyUI is started only by `providers/comfy/launcher.py` (the .bat's own python, never `--cpu`, clean env) and `ensure_running` refuses a ComfyUI that works on the CPU; the default Ollama model is chosen by fit to the VRAM (`providers/ollama_fit.py`), never `names[0]`.
- Ollama is called streamed (`providers/ollama.py`): limit SILENCE, not total time; errors carry a Persian first line (`ProviderError.fa`). Do not go back to one fixed read timeout.
- A handler/provider reports what it is doing with `JobContext.live()` (or `jobs.context.report_live`); `jobs/describe.py` turns it into the queue text. Add a `KIND_TEXT` entry (fa + en) for every new job kind.
- Diagnostics: `core/gpu_diag.py` (+ `scripts/gpu_verdict.py` for `Test-GPU.bat`); model tests: `core/model_tests.py` (job kind `models.test`). New GPU-using code must go through `gpu/compute.run_task` so these checks apply.

## Phase 3/4 notes
- Two-PC design (worker agent, LAN gate, GPU task router): `docs/DECISIONS.md` section "Phase 3 / 4". PC B runs `START-WORKER.bat`; only `/api/worker/*` is ever exposed to the LAN.
- GPU work goes through `instai/gpu/compute.py` (`run_task` / `fan_out`), never straight to ComfyUI, so a worker PC can take it.
- The UI area for this work is the "Production lab" (`/lab`, `frontend/src/lab/`, own i18n namespace). Do not commit the built UI (`instai/static/app`) from worker sessions; the lead builds it.
- Never auto-publish: automatic posting needs per-page enablement + the adapter flag + every requirement (`publishing/adapters.can_auto_publish`).

## Platform: durable queue, computers report, scheduled downloads, version (0.6.0; audit in `docs/PLATFORM_AUDIT_fa.md`)
- **Waiting is not failing.** A `ProviderError` whose `wait` / `code` is in `jobs/queue.WAIT_CODES` (`worker_offline`, `worker_lost`, `ollama_down`, `comfy_down`, `gpu_busy`) makes `worker.execute` call `queue.defer`: the job goes back to `queued` with a Persian reason, the attempt is given back, no maximum wait (optional `ops_config.max_wait_hours`). Only a real error (after `max_attempts`) or Cancel ends a job. A new "service is not there" error must set `ProviderError(..., wait="...")` or use one of those codes; a handler may also raise `JobDeferred`.
- A dead worker process re-queues its jobs without an attempt (`reap_expired`, up to `MAX_LOST_FREE`). `compute.run_task` raises `worker_offline` when a paired PC that could do the task is offline; a worker that vanished mid-task is `RemoteTask.error_code = "worker_lost"`.
- Short queue writes are `@retry_on_lock` (`core/dbretry.py`); the worker API answers 503 + Retry-After on a stuck lock. Never retry inside `atomic()`.
- Downloads: `ops/downloads.py` (`start_packages`, `start_ollama`, `reschedule`), clock rules in `jobs/schedule.py` (local time of the PC; a window may pass midnight). A job with `Job.window` is claimed only inside it and `JobContext.check()` stops it (`JobDeferred`, no attempt) when the window closes. Every new download goes through these, never straight to `download_models.py`. Targets: this PC or a paired PC (`download.pack` task; needs the `downloads` capability).
- Report data: `ops/report.py` (`record_heartbeat` from this PC's worker and from `/api/worker/hello`, `maintain`, `explain` for plain-language errors); `Job.node/devices` say which computer did the GPU work. A new error kind worth explaining: add a rule to `EXPLAIN_RULES` (fa + en).
- **Version:** edit `VERSION` and add the newest entry (fa + en) to `CHANGELOG.json` together (`tests/test_platform_version.py` checks they agree). The badge is in `App.tsx` outside `<Routes>`; every .bat window reads `VERSION`.
- New screens use the `ops.*` keys in `frontend/src/i18n/packs/ops.ts`; server-sent texts come as `*_fa` / `*_en` pairs and the UI picks one.

## Style library v2 and the idea bank (0.7.0; docs in `docs/STYLE_LIBRARY.md`, `docs/IDEA_BANK.md`)
- The MAIN library is the art/animation styles (`styles/builtin_styles.py` + `styles_more.py`, 8 groups, `suitability`, `gen` hints); the old "theme" is called **Color theme** / «تمِ رنگی» in every UI text (the API keeps `theme`). A new style = one `mk(...)` row + search names in `aliases.py`; **never** put a studio, brand or creator name in a style's name, description, tags or prompt (aliases are search-only).
- Generation code takes the look from `styles.library.compose_for_episode / compose_for_series / look_of` (series pick over page look), never from the page profile directly. New generation paths must do the same and put the look in their staleness hash.
- Ideas: `instai/ideabank` (seeds in `seeds_*.py`, no invented statistics, made-up people only; both languages for every field). A new job kind still needs `KIND_TEXT` + `job.kind.<kind>` in both languages.
