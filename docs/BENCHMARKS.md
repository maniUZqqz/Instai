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

## Delivery (0.16): loudness and sound checks (measured on the dev server, no GPU: Ubuntu 22.04, ffmpeg n8.1.3, Python 3.10, numpy 2.2; `scripts/bench_delivery.py`)

Everything below was measured; nothing is estimated. The mixes are synthetic (noise-excited syllables with moving formants, `render/audiofixtures.py`), encoded like a render: ONE pass of
`loudnorm=I=<target>:TP=-1.5:LRA=11` (what `assemble.build_filter` ends with) and AAC 160k; then `loudness.settle`.

| Mix | Target | One-pass LUFS / dBTP | Settled LUFS / dBTP | Rounds | Gain dB | Within 0.8 LU and TP <= -1 |
|---|---|---|---|---|---|---|
| A: five sentences at -14..-30 dBFS with 2.5 s and 3 s pauses | -14 | -15.2 / -1.5 | -13.9 / -1.1 | 2 | +1.8 | yes |
| A | -16 | -16.4 / -1.5 | -16.4 / -1.5 (already within 0.8: untouched) | 0 | 0 | yes |
| B: narration over a ducked music bed | -14 | -13.9 / -1.5 | -13.9 / -1.5 (untouched) | 0 | 0 | yes |
| B | -16 | -16.0 / -3.5 | -16.0 / -3.5 (untouched) | 0 | 0 | yes |
| C: narration with three loud effect bursts | -14 | -15.6 / -1.4 | -14.2 / -1.0 | 2 | +2.5 | yes |
| C | -16 | -16.4 / -1.4 | -16.4 / -1.4 (untouched) | 0 | 0 | yes |

* The one-pass filter missed -14 by 1.3 LU (A) and 1.6 LU (C); the settle pass landed within 0.1 and 0.2 LU with the true peak at the -1.0 ceiling. A file already within 0.8 LU is not touched (byte-identical).
* The pass costs one measure (about 1 s per minute of video), one or two audio-only re-encodes and a measure after each; the picture is copied.
* **Echo test** (normalised auto-correlation of the whitened, 200-3500 Hz band-limited signal at the echo lag; the line is 0.16, per shot 0.28):
  clean synthetic speech, 30 seeds, 5 s windows: highest 0.081, median 0.056; the same speech plus its own copy 150 ms later: copy at -16 dB 0.140 (below the line: not reported), -12 dB 0.226, -6 dB 0.387, equal 0.489.
  Real TTS narration (4 distinct samples of the NMarketing voice engines, 9.9-16.7 s, 5 s windows every 0.5 s; the files are not in the repository): clean highest 0.199 (one sample; its 90th percentile 0.164),
  the other three 0.078-0.128; with a -6 dB copy at 150 ms every window with speech gave 0.34-0.39. This is why the per-shot line is 0.28 (above the highest clean window) while the whole-file line stays at
  NMarketing's 0.16 with the "same lag in a third of the windows" rule.
* **Tonal guard**: strong peaks more than 25 ms from the highest one in a 6 s window: real narration clean 0-1, real narration doubled 0, noise-like synthetic speech 0, the fake narration engine (sine bursts) 9-11.
* **Music / effects over the voice** on the real assembly with the fake engines (3 shots of the fake narration at about -17 dB over 50 ms speech frames, the planned music bed at -22 dB ducked by the side-chain,
  one effect "heavy door slam" at -12 dB, not ducked): the voice is 38-39 dB above the ducked bed in every shot and 16.5 dB above the effect in its shot; the 6 dB line never fires on the default plan.
  Final render of that episode: -14.0 LUFS, true peak -6.6 dBTP (the one-pass was already on target), no echo (all 6 windows tonal), channels in phase.
* A final render of the e2e test episode (3 shots, 1080x1920, fake providers, no music) lands within 0.8 LU of -14 at the page's default; the same episode with the page saved at -16 lands within 0.8 of -16 and
  goes back to -14 when the profile is changed (the target is part of the timeline hash).
