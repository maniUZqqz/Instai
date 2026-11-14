# Self-test: this PC (the machine under InstAI) - 0.14.0

`instai/ops/pcselftest.py`. Every feature of the owner's request has to work by itself once the GPU PC is on, and be tested by itself. The studio pipeline already tests itself
(`docs/selftests/studio-pipeline.md`); this is the same for the machine: small REAL actions, each judged on its own, kept in `data/selftest/pc.json`, shown on the System screen
(card "Automatic self-test of this PC") and as one line on the home screen. API: `GET/POST /api/system/selftest`. Job: `system.selftest` (resource `gpu` when a GPU check is in it, else `cpu`).

## The checks

| Key | Group | The real action | Pass | Waits (`pending`) while |
|---|---|---|---|---|
| `database` | pc | `PRAGMA journal_mode`, migration plan, job count | no migration pending, WAL | - |
| `disk` | pc | free space of the data and models drives | >= 20 GB ok, 3-20 warn, < 3 fail | - |
| `ffmpeg` | pc | encode a 1 s 320x180 pattern + sine with libx264/aac | file > 1.5 kB; warn when `ass`, `zoompan`, `xfade` are missing | - |
| `persian_text` | pc | draw a Persian sentence with the program's font (Vazirmatn) | the picture has more than 400 ink pixels; fail when the font did not load | - |
| `update_channel` | pc | read START.bat + scripts/self_update.py + data/logs/update.log, fetch GitHub's `VERSION` (raw) | START.bat calls the updater and the version equals GitHub's; WARN (with the one thing to do) for an old Download-ZIP folder, a newer GitHub, a working copy ahead of GitHub, or no internet | - |
| `autostart` | pc | `scripts/autostart.py` status | the Startup shortcut exists; `skip` off Windows or when the owner switched it off | - |
| `remotion_toolchain` | tools | `toolchain.status()`; starts the idempotent background setup when it is not running | Node.js + packages + browser present | it is installing (retried every 15 min) |
| `remotion_render` | tools | one still (frame 30) of `TitleCard`, size square, through `remotion/render.mjs` | png > 4 kB and the composition event | the toolchain is not ready |
| `gpu_card` | gpu | `nvidia-smi` | card found; warn under 11 GB | no NVIDIA card / driver (the GPU PC is off) |
| `nvenc` | gpu | encode a 1 s clip with `h264_nvenc` | encoded; warn when ffmpeg has no NVENC or the card refused | no card |
| `ollama_run` | gpu | `gpu_diag.probe_ollama()`: a few tokens from the owner's model, placement from Ollama's `/api/ps` | model fully on the GPU; warn when partly; fail when on the CPU | Ollama is not running / no model |
| `comfyui` | gpu | `launcher.ensure_running()` (the way a job starts it, shared with the NMarketing agent), `device_info`, workflow availability | runs on the GPU and at least one workflow ready; warn with none ready; fail on the CPU | no card, or ComfyUI not found / not started |

## When it runs by itself (`auto_queue`, called from the automation tick about every 5 minutes)

* the checks that load a model or an encoder (`nvenc`, `ollama_run`, `comfyui`) also wait until nobody works hard on the card (under 40 % GPU utilization), so they never push another model in front of the NMarketing agent's job; the button "Run now" ignores that;
* never ran, or still waiting: as soon as its OWN requirement is there (at once when it was not ready at its last attempt, otherwise not more often than every 15 minutes);
* a result of an older version: the cheap checks at once, the tool / GPU checks after 6 hours;
* a warning or a failure: again after an hour (the owner may have fixed it);
* a good result of this version: again after a day (cheap) or a week (tool / GPU).

`INSTAI_PC_SELFTEST_AUTO=0` (or the setting `pc_selftest_auto = false`) switches it off; the test suite never gets surprise jobs.

## The check on the owner's GPU PC (what must be seen)

1. After `START.bat` (or at the next Windows logon) the System screen shows the card within a few minutes; no button is needed.
2. `gpu_card` says "NVIDIA GeForce RTX 3060 ... 12 GB"; `nvenc` ok; `ollama_run` ok with "100 % on the GPU" for a model that fits (the owner's models are never changed); `comfyui` ok with "N of M workflows ready".
3. `remotion_toolchain` and `remotion_render` ok after the first background setup (data\logs\remotion-setup.log).
4. `update_channel` is ok: START.bat has the updater and the version equals GitHub's.

Job payload to run it by hand: `POST /api/system/selftest {}` (everything) or `{"only": ["ollama_run", "comfyui"]}`; pass = the job `succeeded` and `result.summary.fail == 0`.
