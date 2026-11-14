# Benchmarks (measured on the owner's machine - nothing here is invented)

This file stays empty until the benchmark has run on **Computer A** (RTX 3060 12 GB). The numbers below the line are *planning estimates
from the brief*, shown in the app labelled "estimate" until a measurement replaces them.

## How to run it
- Automatically offered by `START.bat` on the first run on a machine that has a GPU and Ollama or ComfyUI (answer Y within 30 s), or
- in the app: **System** page -> **Run benchmark** (about 30 minutes; the quick option skips the Wan video step).
- Each run writes `data\benchmarks\benchmark-<n>.md` and `.json` (also downloadable from the System page). Paste the Markdown below.
- What is timed: one FLUX image (cold + warm), one Wan 2.2 480p 81-frame shot, one 10-second Persian TTS line per available engine (Piper, MOSS),
  one LLM script draft with 2-3 candidate models (tokens/s, valid-JSON yes/no, attempts). Peak VRAM is sampled with `nvidia-smi`.
- A step whose service is missing is recorded as `skipped` with the reason, never with a made-up number.
- Once a run exists, the app's per-episode GPU-time estimates switch from "planning estimate" to "measured".

## Results

| Run | Date | Machine | Image s (cold / warm) | Wan shot s | TTS line s (engine) | LLM draft s (model, tok/s) |
|---|---|---|---|---|---|---|
| _(none yet - run on Computer A)_ | | | | | | |

## Planning estimates from the brief (NOT measurements)

| Item | Estimate | Source |
|---|---|---|
| Wan 2.2 I2V A14B fp8 + 8-step LoRA, 480p, <= 81 frames | 8-10 GPU minutes per 5 s shot on the 3060 | brief section 2 |
| 60 s episode made only of Wan shots | about 2 hours | brief section 6 |
| FLUX image 832x1472, 24 steps | 60 s (placeholder guess) | InstAI default, to be replaced |
| Layer cut-out / puppet layer | 10 s / 5 s (placeholder guess) | InstAI default |
| FFmpeg 2.5D assembly (CPU) | measured, not estimated: the 4 end-to-end render tests (incl. a 1080x1920 30 fps render of 3 short shots, preview renders, partial regeneration) take 38 s in total on the dev PC (i5-4590, 8 GB RAM, no GPU) | `tests/test_pipeline_e2e.py` |

## Motion-graphics components (0.16.0; measured 2026-11-14, NOT on the owner's PC)

Where: the NMarketing server (Ubuntu 22.04, 2 CPUs, no GPU), Node.js 20.18, Remotion 4.0.538, Chromium headless shell with SOFTWARE GL (`swangle`), the real project (`remotion/`, nothing faked). The owner's PC (a real browser, probably a GPU) is expected to be faster in the browser part; the Python part is the same. Re-measure there with `python -m instai.motion_plan.selftest <folder>` (the PC self-test row `motion_frames` does it and keeps the time in its metrics).

| What | Measured |
|---|---|
| One QA frame of one component (bundle cached, one browser kept open) | 10.5 s for 2 frames including the browser start (`selftest --only title,list --sizes vertical`) |
| ONE frame of every component x 3 sizes = 57 frames, with the geometry of every text block, then `qa.py` over all of it | 187 s (`"seconds": 187.2` in the report); 57 of 57 rendered, 0 render errors |
| Bundle of the whole project (24 compositions) after a source change | about 90 s, once per change (cached under `data/remotion/bundles`) |
| An explainer episode (20 s target, 3-4 motion shots, preview size 360x640, real Remotion, real ffmpeg assembly, narration by the fake engine) | the whole production, plan + QA on real frames + render + assembly, took about 95 s in `tests/test_motion_pipeline.py -k real_toolchain_an_explainer` |
| Layout findings of the 57 frames after the fixes made in this round | 0 errors, 0 warnings, 5 notes (the 1.8 % chip text of the number components, exactly at the least size) |

The first run found, and this round fixed: the before / after wipe ended with only the «before» side visible, a dark label on a white pill turned light (a `label` in the plain style is re-checked against the PAGE background), the end labels of the line chart sat outside the card, and a scale of 0.333 made the preview render fail ("height must be an integer, 638.361").
The planning estimate in `costs.py` (`motion_cpu_per_sec` 4.0 final / 1.5 preview, 25 s fixed) is still a planning figure: the server numbers above are not the owner's PC's.
