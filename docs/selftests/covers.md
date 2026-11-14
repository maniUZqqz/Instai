# Self-test: the cover maker (0.16.0)

Two rows of the PC self-test (`instai/ops/pcselftest.py` `CHECKS`; code in `instai/covers/selftest.py`). Same rules as `docs/selftests/instai-pc-selftest.md`: a check is one small REAL action, judged on its own,
`pending` = it waits for something and runs by itself the moment it can, a failing check is a result and never a crashed job.

| Key | Group | The real action | Pass | Waits (`pending`) / skips |
|---|---|---|---|---|
| `covers` | tools (cheap, no GPU; runs by itself on every new version, then weekly) | render a synthetic Chagher-style series (made-up, no price / statistic): **every format at its exact full size** with `episode_card` (the JPEG of a format with a cap stays under it), then **every layout (16) in every format (9) at scale 0.18** (Persian) | every picture has exactly the format's size, is not blank (grey-level spread > 18), has a title drawn, every text is inside the canvas, the title is inside the safe area (+5 % for shadows) and overlaps no avoid zone by 12 % or more | - |
| `covers_bg` | gpu (runs by itself once ComfyUI is up and the card is quiet; `ready` = `_comfy_ready`) | `background.probe`: **one 512x512** background through the real path (`compute.require_workflow` + `compute.run_task("comfy.graph")`, the page's image workflow), then composited under `episode_card` | the picture is 512x512 and not flat, and the cover with it passes the same judgement as above; the sample is kept as `data/selftest/covers-bg-sample.png` | ComfyUI or the image model is not there yet (`ProviderError(wait=...)`): `pending`; demo mode (`image_engine = placeholder`): `skip` |

## Pass checks written as the acceptance of the item

1. A cover for episode 1 of a synthetic series is produced offline in every format (`tests/test_covers_engine.py::test_every_format_is_rendered_at_its_exact_size_in_full`, and the `covers` row) and
   Persian is shaped the same with libraqm and with `fa_text` (`tests/test_covers_text.py`; on a PC without libraqm only the built-in path exists and it is checked on its own).
2. The publishing package contains `cover.png` (and `cover.jpg`) from the new maker (`tests/test_covers_api.py::test_a_cover_is_made_with_six_versions_...`).
3. `tests/test_i18n.py`, `tests/test_ui_words.py` pass; `tests/test_platform_version.py` passes once the lead rebuilds the UI (its built-UI hash test fails on `main` itself until then).
4. No NMarketing import: `grep -rn "apps\.\|services\.\|photoedit" instai/covers` finds none (a `SOURCE:` note names the NMarketing file, it is text only).

## Manual proof on the GPU PC (once it is on)

`python -m pytest -m gpu tests/test_gpu_smoke.py` is unchanged; the `covers_bg` row of the self-test is the automatic proof. To look at the result: System screen -> «آزمون خودکار این رایانه» -> row «پس‌زمینهٔ هوش مصنوعیِ کاور».
