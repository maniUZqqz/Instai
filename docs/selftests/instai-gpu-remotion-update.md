# Acceptance run for 0.10.0 (built as 0.8.0) on the owner's GPU PC (what to run, what must be seen)

Everything below is automatic after `START.bat` (it updates, prepares Remotion in the background and starts the program); these are the checks that prove it.

| Check | How | Pass |
|---|---|---|
| Automatic update | `python scripts\self_update.py --check` (or look at `data\logs\update.log` after START.bat) | "InstAI v0.10.0 is up to date" or "updated InstAI vX -> vY"; never a traceback |
| Remotion toolchain | open the "Video with code (Remotion)" page | Node.js, packages and browser all "Present" (first start: they appear within a few minutes; `data\logs\remotion-setup.log`) |
| Real render | `set INSTAI_REMOTION_REAL=1` then `python -m pytest tests\test_remotion.py -k real_render -q` | 1 passed (4 stills and one mp4 rendered through the real toolchain) |
| Remotion in the browser | `python -m pytest tests_ui\test_qa_sweep.py -k remotion -q` | every composition x every style plays; a render request is queued and succeeds |
| Whole app sweep | `python -m pytest tests_ui\test_qa_sweep.py -q` | every screen clean in Persian / English, desktop / phone |
| Curated models | Downloads page: pick `rife` (21 MB), schedule it "now" | job succeeds; `ComfyUI\models\frame_interpolation\rife_v4.25.safetensors` exists; picking it again says "complete" |
| De-duplication | pick a package whose file ComfyUI already has under another name | the file table says "already here (no download)" or the job finishes without downloading |
| Ollama on the GPU | Models page -> GPU panel while a text job runs | the model shows 100 % on the GPU; the job's live line shows the context size |
| Coexistence | Models page -> "Living next to NMarketing" card with the NM agent running | the card says the agent runs; ports 8188 / 11434 are "open (in use)"; no second ComfyUI window appears |
| GPU check | `Test-GPU.bat` | `VERDICT: GPU USED = YES` |

Fixtures for a quick manual job (Remotion): composition `TitleCard`, props `{"title": "چغر", "subtitle": "مربی ورزشی همراه شما"}`, style `cinematic_realistic`, size `landscape`;
pass = an mp4 of 150 frames at 30 fps (1920x1080) in the "Rendered videos" tab.
