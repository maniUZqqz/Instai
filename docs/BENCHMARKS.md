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
