# Self-test: word-by-word captions - 0.20.0

Row `captions` (group `pc`) of the PC self-test (`instai/ops/pcselftest.py`, `check_captions`; real action in `instai/render/captions_check.py`). CPU only: libass runs on the CPU, so it is
fully verifiable on any PC with the project's ffmpeg (no GPU PC needed).

## The real action

For each of the seven presets (`pop box karaoke clean neon typewriter lower`), in a vertical 360x640 and a landscape 640x360 frame (14 samples):

1. `captions.plan` makes the ASS for a one-second sample line (Persian, series-neutral look, platform instagram / youtube).
2. ffmpeg draws one frame of a flat dark clip with `ass=sub.ass:fontsdir=fonts` (the bundled Vazirmatn files).
3. The frame is judged: caption ink exists (> 40 pixels), every inked pixel lies inside the platform's safe zone (reels / youtube, 2 % tolerance), and the ASS has no unescaped brace.
4. `injection_ok()`: a caption with `{\an9\pos(1,1)}` and braces typed into it makes an ASS whose only tag blocks are the engine's and whose typed braces are escaped.

## Verdicts

| verdict | when |
|---|---|
| `ok` | all 14 samples drew inside the zone and the injection check passed |
| `fail` | a preset drew no ink / left the zone / has a stray brace (the reason names the preset and the frame shape), ffmpeg could not draw one, or the injection check failed |
| `skip` | this ffmpeg has no `ass` filter (the `ffmpeg` row already says so, with the fix); NOT a failure |

It runs with the other cheap checks (once per version, again every day), takes a few seconds, writes nothing to the owner's data and publishes nothing.

## Judging the output by eye

`GET /api/captions/previews?page=<id>` draws the eight presets as pictures with the page's series colours (cached in `media/captions/previews`); the Visual card of the page settings shows them.
A full render: produce a preview of an episode whose page picked a preset; the video has the captions burned in, `provenance.captions` says `estimated: true` (no engine reports word times yet),
and `episode.srt` sits next to it.
