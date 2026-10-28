# InstAI — brief for Claude Code

You are the lead engineer of **InstAI**, a new product. You design, build, test and keep improving it in the
repository **https://github.com/maniUZqqz/Instai** (private, currently empty). Build real, working software in
small verified steps, not proposals or static mock-ups.

**First action:** save this brief unchanged as `docs/BRIEF.md`. Then create a short `CLAUDE.md` with the working
rules from §0 and §12 and a pointer to `docs/BRIEF.md`. Commit both, so every later session starts from them.

---

## 0. Working with the owner (read first)

- The owner reads **Persian only**.
  - Every report, question and summary you give him is in plain Persian: short, facts and numbers, no jargon.
  - Code, identifiers and commit messages stay in English.
- He is not a command-line user.
  - Anything he has to run is a double-click `.bat` file or a button in the UI.
  - Never tell him to type a command with flags.
  - Windows console text inside `.bat` files must be **English/ASCII**, because the Windows console garbles Persian.
- Work in phases (§11). Each phase ends with:
  - a running app;
  - green tests;
  - a commit/push to `main`;
  - a Persian report: what works, what was measured, what is not done, what he must decide.
- Ask him only what is truly his decision: content, taste, money, accounts, licences. Decide engineering questions
  yourself and write them down in `docs/DECISIONS.md`, one line each, with the reason.
- Never claim quality or speed you have not measured on his hardware. Put measured numbers in `docs/BENCHMARKS.md`.

## 1. What InstAI is

The owner's first product, **NMarketing** (repo `maniUZqqz/Qasem`), makes marketing content for a registered *store*.
**InstAI is a separate product:**
- the user registers a **content page** (e.g. an Instagram page), not a store;
- the system plans and produces that page's content automatically, mainly **animated** video series;
- the user can configure everything, review it, edit it, and approve it.

Core idea: **one content page → a configurable production system → recurring, consistent, publishable episodes.**

### Launch formats (the platform must not be limited to these)

1. **Anime "What-If"** — like Marvel's *What If…?*, but for anime worlds.
   - It retells a story as if a key event had gone differently: another decision, a swapped role, a battle with
     another ending, an event that never happened.
   - Needs: premise, branch point, alternative timeline, episode goals and cliffhangers, character
     motivations/abilities/knowledge, and continuity across episodes.
2. **Recurring 2D cartoon character** — one character who appears in many scenarios: everyday comedy, activities,
   recurring jokes, short stories.
   - Needs: a character profile and reference sheet, reusable poses/expressions/motions, backgrounds and props, voice,
     and consistency across episodes.
3. **Concept explainer** — a presenter (2D cartoon, stylised 3D, or a real-looking presenter where permitted) who
   explains hard or intimidating ideas in simple words.
   - Example topics: economics, capitalism, fascism and other ideologies, the multiverse, strange scientific names,
     psychology, philosophy, history.
   - Needs: research with stored sources, simplification, analogies, visual metaphors, fact-checking that separates
     established facts from speculation and contested views, narration and subtitles.

### Per-page settings

Everything is configurable per page, including:
- theme and niche, audience, page language(s), tone;
- format;
- number and length of episodes, series structure, aspect ratio, publishing rhythm;
- visual style, characters, voices, music and sound;
- automation level;
- production preset.

The user can arrange and edit the story: premise, arcs, episode plan, scenes, shots.

## 2. The real machine and the models already on it

InstAI runs **locally on the owner's own computer, in one place, for him alone**. It is not a hosted multi-tenant
service. It does not run on the NMarketing web server.

**Computer A — the main machine, where InstAI runs:**
- Windows; Intel Core i5 14th gen;
- NVIDIA **RTX 3060 12 GB**;
- RAM: the owner says 16 GB, but its last report to NMarketing said **24 GB** (detect it, don't assume);
- 500 GB SSD.

**Computer B — optional later worker, never required:**
- Intel Core i3 9th gen, GTX 1650 4 GB, ~23 GB RAM.
- Suitable for light jobs only: TTS, ASR, ffmpeg, Piper, small LLMs.
- GPUs on two computers do not pool VRAM.

Computer A already runs the NMarketing processing agent (`processing-server/agent.py` from the Qasem repo), with the
services below. Last inventory: Oct 2026. **Re-detect everything at start-up and never hard-code availability.**

- **Ollama (`http://127.0.0.1:11434`).** Among others:
  - `qwen3.5:35b/27b/9b/4b`, `qwen3:30b/14b/8b`, `qwq:32b`, `gpt-oss:20b`, `gemma3:27b/12b`
  - `qwen3-vl:30b/8b` (vision), `qwen3-coder:30b`
  - `translategemma:27b/12b`, `Dorna2:Q4_K_M` and `partai:dorna-llama3` (Persian)
  - `bge-m3`, `embeddinggemma` (embeddings)
  - Only ~9–14B models fit fully in 12 GB; larger ones offload to RAM and are slow. Measure before choosing.
- **ComfyUI (`http://127.0.0.1:8188`).** A recent version whose node list includes:
  - `WanFirstLastFrameToVideo`, `WanAnimateToVideo`, `WanVaceToVideo`, `WanPhantomSubjectToVideo`
  - `WanSoundImageToVideo`, `WanInfiniteTalkToVideo`, `WanHuMoImageToVideo`, `WanFunInpaintToVideo`
  - `TextEncodeAceStepAudio1.5`, `FrameInterpolate`, SAM3, `TrainLoraNode`
  - Qwen-Image-Edit, Z-Image and Kandinsky5 nodes, GGUF loaders, VideoHelperSuite, KJNodes, rgthree
- **Models used today by NMarketing:**
  - **FLUX.1 [dev] FP8** (images).
  - **Wan 2.2 I2V A14B fp8** (high/low-noise experts) with `umt5_xxl_fp8_e4m3fn_scaled`, `wan_2.1_vae` and the
    `lightx2v` rank-64 step-distill LoRA (8 steps), at 480p, ≤81 frames (~5 s at 16 fps).
  - Planning estimate on the 3060: **≈8–10 min of GPU time per 5-second 480p shot**. Treat this as a budget to
    measure, not a fact.
- **Voice / audio:** installed or installable through NMarketing's `Download-Models.bat`:
  - Piper (Persian voices gyro, Mana) and Vosk;
  - MOSS-TTS-Realtime + Persian LoRA (Apache-2.0; speech and voice cloning);
  - MOSS-SoundEffect v2.0 (ambience/SFX);
  - ACE-Step 1.5 (MIT; music);
  - Pocket-TTS (**non-commercial, do not use for published content**);
  - Edge TTS (unofficial online endpoint, **not for commercial use**).
- **Image tools:** Real-ESRGAN x4v3 (upscale), BiRefNet-lite (background removal), and a .NET photo/video/voice kit
  (`PersianAiKit`).
- **Blender + MPFB** are installed for the 3D engine (`up3d`).

**One GPU, one heavy job at a time.**
- Never run an LLM, a ComfyUI video job and a voice model on the GPU together.
- Before a job, unload what it doesn't need: Ollama `keep_alive: 0`, ComfyUI `/free`, stop idle voice servers.
- The NMarketing agent may also be using the GPU. Detect busy VRAM with `nvidia-smi`, wait or queue, and show
  "GPU busy" in the UI. Never kill another program's process.

**Network:** the owner is in Iran.
- Hugging Face, PyPI and GitHub generally work. Mirrors (hf-mirror.com, ModelScope, PyPI mirrors) are needed as
  fallbacks.
- NuGet is blocked.
- Downloads must resume, verify size/sha256 and retry.

## 3. Reuse what already works (Qasem repo)

The owner can clone **https://github.com/maniUZqqz/Qasem** (private, same account). Clone it **next to** InstAI as a
read-only reference: `..\Qasem`. Copy and adapt code into InstAI, with a note of the source path. Do not import the
NMarketing Django project wholesale and do not modify Qasem.

Worth reusing:
- **`processing-server/`**
  - `START.bat`: self-check/self-repair checklist.
  - `download_models.py` + `downloads/*.json`: manifest-driven downloader; reuses files ComfyUI already has; shared
    pip cache; mirrors.
  - `agent.py`: `ServiceManager` / `prepare_for` (VRAM juggling of Ollama/ComfyUI/voice), job loop, tolerance of a
    flaky network.
  - `audio/*_server.py`: MOSS-TTS, MOSS-SFX and ACE-Step servers.
  - `upmarket_comfyui_flask/`: working ComfyUI graphs for FLUX and Wan 2.2.
  - `up3d/`: Blender 3D scene engine with characters, mocap clips, cameras and keys.
- **`site-server/backend/services/video/regen/`** — seamless regeneration of one segment with first/last-frame Wan:
  - colour matching, seam scoring;
  - GOP-level smart stitching;
  - audio replace/mute/cut with exact A/V sync.
- **`site-server/backend/services/audio/`** — TTS engine chain, narration + music + SFX mixing with ducking.
- **`site-server/backend/apps/photoedit/`** — server-side image operations and kit operations.

## 4. Architecture (local, Windows, single user)

- **Backend:** Python 3.12, Django + Django REST Framework, SQLite in WAL mode by default (Postgres optional later).
- **Jobs:**
  - **No Redis or Celery requirement** — they are awkward on Windows.
  - Use a durable **DB-backed job queue** plus one worker process started by `START.bat`.
  - Durable means: atomic claim, lease/heartbeat, retries with backoff, timeouts, cancellation, progress, logs,
    idempotency keys, and cost/time accounting.
  - A **GPU arbiter** inside the worker serialises GPU jobs and does the unload/load switching.
  - Light CPU jobs (ffmpeg, Piper, file work) may run in parallel.
- **Frontend:** React + TypeScript + Vite, built and served by Django.
  - **Persian, right-to-left UI first**, English as a second language.
  - Responsive, accessible, real data only. No decorative cards that aren't connected to anything.
- **Media:**
  - FFmpeg (bundle a pinned static build if missing).
  - Explicit metadata for every asset: duration, fps, size, codec, loudness.
  - A storage abstraction over a local folder, ready for object storage later.
- **Providers:** typed interfaces for text, vision, image, video, TTS, ASR, music and SFX.
  - Each concrete **workflow** declares its own input schema, hardware needs, licence and expected time.
  - A registry reports what is available on this machine right now. Inputs are validated before dispatch.
  - Adapters: Ollama, ComfyUI (graphs stored as versioned JSON templates), the local voice servers, and optional
    external APIs (the owner already has a MetisAI OpenAI-compatible key). Keys live in `.env`, never in git or logs.
- **Agents:** a few logical roles (strategist, story architect, scriptwriter, researcher, storyboarder, prompt
  engineer, consistency manager, production coordinator, audio, assembly, QC, publishing).
  - These are roles, not 12 LLMs. Most are plain Python. LLM calls only where language or reasoning is needed.
  - Every agent boundary has a JSON schema; outputs are validated and repaired or retried.
  - Agents cannot write arbitrary DB rows or run shell commands; they go through application services.
- **Launch:**
  - `START.bat` checks and repairs the environment (Python, venv, Node build, ffmpeg, Ollama, ComfyUI, models, disk,
    GPU), starts the server and worker, then opens the browser.
  - Re-running it when all is well takes seconds.
  - `Download-Models.bat` with no arguments fetches the default set; optional packs are installed from a button in
    Settings.
- No Kubernetes, no distributed inference, no extra infrastructure without a measured need.

## 5. Domain model

Use typed models, not one JSON blob. JSON only where flexibility is genuinely useful.

- **Page and its settings:**
  - `ContentPage`, plus settings split into reusable profiles: identity, strategy, visual identity, audio,
    production preset, publishing.
- **Characters and story:**
  - `Character` (profile, personality, voice, appearance) and `CharacterReference` (approved images, sheets, LoRA,
    poses/expressions).
  - `Series`, `StoryArc`, `Episode`, `Scene`, `Shot`.
  - **`StoryMemory`**: established facts, character states, relationships, timeline events, open threads, episode
    summaries, future goals. Never rely on chat history for continuity.
- **Production:**
  - `Asset`, with versions and provenance: which workflow, model, seed and prompt made it.
  - `Job`, `PublishTarget`, `Publication`, `Source` (research references).
- **Episode state machine** with explicit transitions:
  draft → planned → scripting → script review → storyboarding → asset generation → animation → assembly →
  quality review → ready for approval → approved → scheduled → published (+ failed / cancelled).
- **Partial regeneration:**
  - Editing one scene or shot regenerates only that part.
  - A failed video job never forces script or storyboard regeneration.
  - Approved assets are reused.

## 6. Production: spend the GPU where it shows

At ~8–10 GPU-minutes per 5-second Wan shot, a 60-second episode made only of Wan shots is about 2 hours on this card.
So:

- Every episode gets an **estimated GPU time before it runs**, a cheap **preview mode** (fewer frames, lower
  resolution, still images and animatics) and an **overnight batch** mode.
- **Mix techniques per shot** and pick the cheapest one that looks right:
  - Still keyframes (image model) with 2.5D camera motion: parallax layers, Ken Burns.
  - **Layered / cut-out 2D puppet animation**, deterministic and consistent:
    - body parts as layers;
    - a motion library;
    - mouth shapes driven by **Rhubarb Lip Sync (MIT)** from the narration.
    - This is the default for the recurring character and the cartoon presenter.
  - Code-rendered motion graphics and diagrams for explainers (e.g. Manim, MIT, or SVG/Canvas rendered to video).
  - **Wan 2.2 I2V** for hero shots, started from an approved keyframe so style and character stay fixed.
  - **First/last-frame Wan** for transitions and in-betweens.
  - Reuse the regen code for fixing a single bad segment.
  - Audio-driven talking video (Wan S2V / InfiniteTalk / HuMo nodes are present) only after measuring cost and
    licence.
  - The 3D route through the existing Blender engine (`up3d`) for stylised 3D presenters.
- **Character consistency:**
  - An approved character sheet and reference images.
  - A per-character LoRA trained locally (ComfyUI `TrainLoraNode`) if measured to help.
  - Reference-based editing (Qwen-Image-Edit) for new poses and expressions.
  - Stored seeds and prompts.
  - QC compares new frames with the references using a vision model or embeddings.
- **Audio:**
  - Narration and dialogue per character voice.
  - Persian first: MOSS-TTS + Persian LoRA, Piper as fallback. For other languages pick commercially usable voices
    and test them.
  - Music (ACE-Step 1.5), SFX (MOSS-SoundEffect), loudness normalisation, ducking.
  - Subtitles with proper Persian shaping and RTL.
- **Assembly:** FFmpeg timeline, transitions, subtitles, logo/watermark, cover image, per-platform renditions
  (9:16 first).
- **Quality checks:**
  - technical: duration, fps, loudness, black/frozen frames, seam scores;
  - script: completeness, length, reading speed;
  - continuity against `StoryMemory`;
  - character consistency;
  - for explainers, unsupported claims flagged.

## 7. Model choices and licences (the owner publishes commercially)

- **For each candidate model, record in `docs/MODELS.md`:** licence, commercial use, territorial or sanctions
  clauses, VRAM at the chosen quantisation, measured time, and quality notes with sample outputs.
- **Prefer Apache-2.0 / MIT.**
- **Exclude** licences whose terms the owner cannot accept from Iran. For example, LTX-2 requires a representation of
  not being in a sanctioned country, and HunyuanVideo 1.5 has territorial and trade-law clauses and needs ≥14 GB.
- **Check FLUX.1 [dev]'s licence terms** for this use. If it is not acceptable, test Apache alternatives already
  supported by the installed ComfyUI: Qwen-Image / Qwen-Image-Edit, Z-Image.
- **Anime candidates:** test them against plain Wan 2.2 on the same stills with the same seeds before choosing.
  - **Index-AniSora V3.2** (Bilibili; Wan 2.2 base; Apache-2.0 plus extra repo terms for derivatives; community
    GGUF Q4–Q5).
  - **AnimeGen I2V** (AIdeaLab; Wan 2.2 I2V A14B fine-tune; Apache-2.0; GGUF Q4_K_M ≈ 9.7 GB per expert).
  - Wan 2.2 + an anime style LoRA **only if that LoRA's licence allows selling output**. Many popular ones don't.
  - No character/IP LoRAs.
- **Wan 2.5 and later** are API-only (no open weights). Don't plan around them.
- **Talking-head tools:** check every dependency. For example, InsightFace detector weights are non-commercial.

## 8. User interface (Persian, RTL)

1. **Dashboard:** pages, active jobs with progress and ETA, recent episodes, upcoming publications, failures that
   need action, GPU status.
2. **New-page wizard:**
   - name, format, language(s), audience, tone, visual style (with sample previews), characters, automation level,
     production preset;
   - an "idea → strategy" step where the system proposes a series plan the user can edit.
3. **Page workspace:** overview, settings profiles, characters (sheets, voices, approvals), series, episodes, history,
   publishing.
4. **Series builder:** premise, branch point (What-If), arcs, episode plan, continuity view (facts, timeline, open
   threads), content rules.
5. **Episode editor:**
   - script editor;
   - scene/shot list with technique per shot and estimated cost;
   - references, generation controls, previews, version history;
   - per-shot regenerate/approve;
   - the full episode preview.
6. **Production monitor:** queue, progress, logs, measured times, retry/cancel, GPU and VRAM.
7. **Publishing centre:** captions, hashtags, cover, schedule, status, manual export.
8. **Settings:** models and providers (with licence badges), workers, presets, storage, downloads, notifications.

Good empty states, real loading states and useful Persian error messages throughout.

## 9. Publishing

- A publishing adapter interface. Instagram first, but nothing is coupled to it.
- **Release 1:** export a ready package for manual upload (video renditions, cover, caption, hashtags, schedule
  reminder).
- **Later:** the official Instagram Graph API.
  - It requires a Professional (Business/Creator) account, a linked Facebook Page and app permissions.
  - It fetches media from a **public URL**, which a local PC doesn't have.
  - Access from Iran may not be possible.
  - Design for it, but don't block on it.
- Never auto-publish unreviewed content by default. Connect accounts only with explicit user action.
- Never bypass authentication, rate limits or platform controls.

## 10. Content policy built into the product

- **Anime What-If:** fan stories about existing franchises can trigger copyright claims and platform takedowns.
  - Support **original characters and "inspired-by" universes** as the default.
  - Let the owner explicitly mark a series as fan content.
  - Show a clear notice that using franchise characters, names or artwork does not grant commercial rights.
- **Explainers about ideologies, politics, history and science:**
  - neutral and sourced;
  - contested claims labelled as such;
  - no propaganda;
  - sources stored with the episode.
- **Real-looking presenters:** only synthetic or consented identities. Never imitate a real person without consent.
  Label AI-generated content where platforms require it.

## 11. Phases (each one shippable)

- **Phase 0 — inventory and decisions** (≈1 day).
  - Repo scaffold, `START.bat`.
  - Hardware/model detection page.
  - A benchmark script that times, on this machine:
    - one FLUX (or alternative) image;
    - one Wan 2.2 480p 81-frame shot;
    - one 10-second Persian TTS line;
    - one LLM script draft with 2–3 candidate models.
  - Produce `docs/BENCHMARKS.md`, `docs/MODELS.md`, `docs/DECISIONS.md` and a Persian report to the owner.
- **Phase 1 — pages, series and story.**
  - Domain model, settings profiles, new-page wizard, series builder, `StoryMemory`.
  - Script and storyboard generation with schemas, using local Ollama with an optional API provider.
  - Editing and approvals. No video yet.
  - Acceptance: create one page of each format and get a reviewed 5-episode plan plus one full script and storyboard
    each.
- **Phase 2 — production core.**
  - Job queue + GPU arbiter + ComfyUI/voice adapters.
  - Keyframes, TTS, the 2.5D and puppet techniques, FFmpeg assembly with subtitles.
  - Acceptance: one 30–60 s episode per format rendered end-to-end, with measured GPU time and a cheap preview mode.
- **Phase 3 — animation quality.**
  - Wan hero shots and first/last-frame transitions, the anime model comparison, character LoRA/reference
    consistency, Rhubarb lip-sync, Blender 3D presenter.
  - QC checks and per-shot regeneration.
- **Phase 4 — automation and publishing.**
  - Automation levels (manual / assisted / automatic within budgets).
  - Scheduling, export packages, the publishing adapter (Instagram API only if feasible).
  - Simple analytics entry.
- **Phase 5 — optional:** Computer B as a light worker, other platforms, more formats.

## 12. Engineering rules

- Tests for every service:
  - unit tests;
  - an end-to-end test of the pipeline using **fake providers**, so the suite runs without a GPU;
  - Playwright checks of the main screens;
  - a GPU smoke test that runs only on the real machine.
- Structured logs, health checks, migrations, `.env.example`. Nothing secret, no models and no user data in git.
- Idempotent jobs and resumable downloads. Never delete user files; move them aside instead.
- Keep the app usable while a long render runs. Show realistic ETAs learned from measured runs.
- Small, readable modules. Comments only where the reason isn't obvious.
- Commit after every working step. Push to `main` at the end of each phase.

**Start now with Phase 0.** At the end, report to the owner in Persian:
- what runs;
- the measured numbers;
- the model and licence findings;
- the 3–5 decisions that need him.
