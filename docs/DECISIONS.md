# Engineering decisions (one line each, with the reason)

Decisions the owner must take are in the last section; everything else was decided by engineering and can be revisited.

## Platform
- **Django 5.2 LTS + DRF, SQLite in WAL mode, Python 3.10-3.13** - runs on the dev PC (3.10/3.13) and on a GPU PC with 3.12; LTS gets security fixes; SQLite needs nothing installed (Postgres optional later).
- **waitress + whitenoise instead of `runserver`** - a pure-Python, threaded server that behaves on Windows; whitenoise serves the committed UI and fonts.
- **Server binds to 127.0.0.1 and only accepts localhost host names** - single-user local app; protects the local API from DNS-rebinding pages. Opening it to the LAN needs an explicit env change.
- **No Redis/Celery: durable DB-backed queue** (`jobs` app) - claim = compare-and-set UPDATE (SQLite has no row locks), lease + heartbeat, exponential backoff, timeouts, cooperative cancel (subprocesses are killed), idempotency keys, progress, logs, time/GPU accounting. An expired lease re-queues the job, so a crashed worker loses nothing.
- **Worker lanes: one GPU lane + N CPU/network lanes** - GPU jobs are serialised, ffmpeg/Piper/API calls run in parallel.
- **GPU arbiter** - one heavy job at a time; switching occupant unloads the others (Ollama `keep_alive: 0`, ComfyUI `/free`); another program's VRAM (> max(2.5 GB, 25 %) after our unload) makes the job wait and shows "GPU busy"; we never kill foreign processes. No GPU/`nvidia-smi` = no waiting.
- **Secrets only in `.env`** (git-ignored); the API never returns a key (only "set" + last 4 characters); logs redact bearer tokens and keys.
- **Built UI is committed** (`instai/static/app`) - the GPU PC needs only Python. `START.bat` rebuilds only when Node exists and the **source hash** (not timestamps, which git rewrites) changed.
- **Own tiny JSON-schema validator/repairer** instead of the `jsonschema` package - zero extra dependencies, and "repair" (coerce types, drop unknown fields, clamp) is needed anyway.

## Generation
- **Every LLM call goes through one function** (`agents/runner.py`): structured output natively when the backend supports it (Ollama `format`, OpenAI `json_schema`/`json_object`), then extract -> repair -> validate -> semantic checks -> send the problem list back and retry (3 attempts). A gateway that rejects `response_format` is retried without it (not counted as a failure).
- **Storyboard falls back to a deterministic script->shots builder** when the model cannot cover the script after retries - a weak model never stalls the pipeline; the fallback is logged and flagged.
- **Agents are roles, not models; they never write to the database** - results are persisted only by `story/services.py`.
- **Proposals (strategy, series plan) are not saved until the owner edits/accepts them** - the owner stays in control; the wizard shows editable fields.
- **Continuity = typed StoryMemory entries, never chat history** - the digest (latest state per subject, still-open threads, last summaries) is injected into prompts; re-running an episode replaces only that episode's entries; threads are resolved by matching text.
- **Continuity is updated when the script is approved**, not when generated - unreviewed text does not pollute the memory.
- **Storyboard is reviewed in the `storyboarding` state; pressing "produce" approves it** - fewer clicks for a non-technical owner; the state history records it.
- **Explainers: only system-fetched or owner-added text becomes a Source** (`verified` = fetched by the system); a claim without a source cannot be "established"; numbers in the script that appear in no claim/source are flagged. Source retrieval is off by default (owner adds sources) with Wikipedia as an optional fetcher.
- **Anime What-If defaults to original characters**; fan content is an explicit per-series switch and always shows the "no commercial rights" notice. Real-looking presenters: synthetic or consented only (notice).
- **Never auto-publish.** `automation_level` is stored but changes nothing until Phase 4; publishing in release 1 is a manual-export zip (video, cover, caption, hashtags, reminder) behind an adapter interface.

## Production
- **Hash-based staleness**: every asset stores the hash of the inputs that produced it. Editing one shot makes only its keyframe/narration/clip stale; approved assets are reused; editing clears the approval of the assets it makes stale; a failed video job never touches script/storyboard (tested).
- **`advance()` is re-entrant and runs after a job is marked done** - two steps finishing together cannot both see the other as "still running".
- **Preview vs final**: preview = 360x640 @15 fps, ultrafast x264, small keyframes (448x800); final = 1080x1920 @30 fps. Estimated GPU time is shown for both before anything runs, labelled "estimate" until the benchmark replaces it.
- **Camera**: Ken Burns via `zoompan` over a 1.5x/2x oversampled still (no jitter); parallax needs RGBA cut-out layers (BiRefNet, Phase 3) so until then it falls back to Ken Burns and says so in the QC notes. Techniques without a renderer yet (puppet_2d, motion_graphics, talking_video, three_d) fall back the same way.
- **Two-stage assembly**: silent per-shot clips are cached as assets, then one pass joins (xfade/concat with normalised timebase), places each narration at its shot start, mixes, loudness-normalises (-16 LUFS) and burns subtitles. Narration length drives shot length - speech is never cut.
- **Persian subtitles = ASS burned by libass** (HarfBuzz + FriBidi shaping) with the **Vazirmatn font bundled** (SIL OFL, licence text included) so output is identical on every PC; an RTL mark prevents numbers/Latin at a line start from flipping the paragraph. Verified visually on a rendered frame.
- **ComfyUI graphs are versioned JSON templates** adapted from the owner's NMarketing graphs (`flux_dev_fp8_t2i@1`, `wan22_i2v_a14b_fp8@1`); each declares input schema, nodes, model files, VRAM, licence and expected time; availability is checked against `/object_info` including the model file names. Wan at 480x832 portrait (9:16), <= 81 frames @16 fps, 8-step lightx2v.
- **Image engine `auto` never silently uses placeholders**: no ComfyUI = a clear Persian error. Placeholders/fake voices/fake LLM only through the explicit **demo mode** switch.
- **TTS**: Piper through its CLI, MOSS through the existing server protocol (`/health`, `/run`); `auto` prefers MOSS, then Piper, never the fake engine. Pocket-TTS and Edge TTS are excluded (licence).
- **QC**: technical (codec, resolution, audio, duration, loudness within 3 LU, black/frozen frames), script (completeness, length, reading speed), continuity (speakers known), explainer claims. Warnings do not block; failures keep the episode in quality review.

## Setup and delivery
- **`START.bat` is the only entry point**: finds Python 3.12/3.13/3.11/3.10, else installs 3.12.10 per-user (pinned size + sha256, no admin), creates `.venv`, installs pinned requirements (PyPI, then mirrors), fetches ffmpeg, builds the UI if possible, migrates, prints an English checklist, starts server + worker (each restarts itself), opens the browser. Folder names with spaces/parentheses are supported (relative paths only).
- **ffmpeg comes from PyPI first** (the `imageio-ffmpeg` 0.6.0 wheel contains the same Gyan 7.1 essentials build with libass/x264/zoompan/xfade; PyPI gives the sha256) with the GitHub zip as fallback. Measured from the dev PC in Iran: GitHub release assets 15-70 KB/s with timeouts, PyPI ~450 KB/s. The wheel has no ffprobe, so probing falls back to parsing `ffmpeg -i`.
- **Downloader is stdlib-only** (runs before the venv exists): manifest driven, resumable (Range), size + sha256 verified (a missing hash is recorded on first use and checked afterwards), HF mirror fallback, reuses files ComfyUI already has, never deletes (bad files are renamed), refuses to start without free space + 2 GB. Default set is small (ffmpeg + Piper); Wan/FLUX/MOSS/ACE-Step are optional packs.
- **Hash/URL data for big models was copied from the owner's Qasem manifests** (pinned commits); Piper/Rhubarb/FLUX only have sizes (no hash) and are marked unverified.
- **Tests never touch the real data folder**: pytest gets a temp data dir and a file-based test database; real adapters are tested against in-process fake Ollama/OpenAI/ComfyUI/MOSS servers.
- **UTC in the database, Jalali dates in the UI** (`Intl` with the Persian calendar) - no date library.
- **UI**: React + TS + Vite with only react, react-dom, react-router-dom; own components, logical CSS properties for RTL, Persian first with an English dictionary, light/dark, Vazirmatn bundled, no CDN.

## Needs the owner (also in the Persian report)
1. **FLUX.1 [dev] licence** - may its outputs be used commercially under the owner's circumstances? (Otherwise Qwen-Image / Z-Image will be benchmarked.)
2. **Which text model/provider for scripts** - local Ollama (measure Persian quality with the benchmark) or the MetisAI-compatible API (costs money; key goes in Settings).
3. **Persian narration voice** - MOSS-TTS + LoRA (best, needs its server) or Piper `fa_IR-gyro-medium` (CPU fallback); licence of the voice for published content.
4. **Anime video model** (Phase 3) - AniSora / AnimeGen / Wan + LoRA: licences must be read before testing.
5. **Whether Computer B joins later** (Phase 5) - nothing in this phase depends on it.
