# Self-test: real style sample pictures (GPU / ComfyUI on the owner's PC)

What needs the GPU in this feature: only the **real sample picture of each style** (job `styles.preview`). Everything else (the 116 styles, the
colour themes, the idea bank, picking a look once per project, the drawn swatches) works without it.

## It starts by itself

`WorkerRunner` calls `styles.previews.auto_queue()` on every automation tick (about every 5 minutes at most). It queues a `styles.preview` job
(12 styles per chunk, low priority, `payload.auto = true`) as soon as ALL of these hold: the image engine is not the demo `placeholder`, ComfyUI
answers and the image workflow (`flux_dev_fp8_t2i` by default) is ready on some PC, at least one style has no up-to-date sample and no such job is
already queued or running. Switch off with `INSTAI_STYLE_SAMPLES_AUTO=0` or the setting `style_samples_auto = false`. Nothing is left for the owner
to click; the library page shows "N of 116 samples made" and a button for a manual start.

## The check (automatic, real)

* Pass: after the first automatic chunk `GET /api/library/previews` reports `done >= 1`, the chunk job is `succeeded` with `result.made >= 1`, and
  `GET /api/library` lists the first style of the chunk with a `thumbnail_url` (the real sample; until then only the drawn `preview_url`) and that
  url serves a PNG larger than 10 kB.
* Pass (whole library): `pending == 0` after the last chunk (116 styles at about a minute each: roughly two hours of GPU in 12-style chunks).
* Same fixed neutral subject in every picture (`previews.SUBJECT`), so the pictures compare the looks, not the subjects.

## The same check by hand on the GPU PC

    pytest -m gpu -s tests/test_gpu_smoke.py::test_real_comfyui_makes_a_sample_image_of_a_style      (also part of Test-GPU.bat)

or queue the job directly: `POST /api/library/previews {"keys": ["pixel_art_16bit"]}` and poll `GET /api/jobs/<id>`; the payload the worker runs is
`{"keys": ["pixel_art_16bit"], "force": false}` and the pass condition is `result.made == 1`.

## Failure modes (all visible in the library page / processing queue, none need a click)

* ComfyUI off or workflow not ready: the job waits (`comfy_down`) and the next tick retries; finished pictures are kept.
* A style whose prompt changed has an out-of-date sample and is redone by the next automatic chunk.
* Demo mode (`image_engine = placeholder`): no real sample is attempted and the drawn swatch is shown.
