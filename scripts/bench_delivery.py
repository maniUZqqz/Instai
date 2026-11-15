"""Developer tool for docs/BENCHMARKS.md: measures what the delivery work claims, on synthetic mixes, and prints Markdown. Nothing is changed or kept.

  python scripts/bench_delivery.py                 loudness before/after on three synthetic mixes, echo strengths of clean and doubled speech
  python scripts/bench_delivery.py --real DIR      also measures every .wav in DIR (real narration you have; only the numbers are printed, never the files)

Needs numpy and ffmpeg (the app's own: `instai.core.runtime`). English / ASCII output."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instai.settings")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("INSTAI_DATA_DIR", tempfile.mkdtemp(prefix="bench-data-"))


def main() -> int:
    import django

    django.setup()
    import numpy as np

    from instai.render import audiofixtures as fx
    from instai.render import audioqc, ffmpeg, loudness

    ff = ffmpeg.binaries()[0]
    sr = fx.SR
    work = Path(tempfile.mkdtemp(prefix="bench-delivery-"))
    try:
        def pauses():
            parts = []
            for i, (db, pause) in enumerate([(-18, 0.2), (-30, 2.5), (-24, 0.2), (-14, 3.0), (-27, 0.2)]):
                parts += [fx.speechlike(2.2, seed=10 + i, level_db=db, pause_every=0), np.zeros(int(pause * sr), dtype=np.float32)]
            return np.concatenate(parts)

        def with_music():
            v = fx.speechlike(14.0, seed=41, level_db=-24.0)
            env = np.ones_like(v)
            env[np.abs(v) > 0.01] = 0.25                                  # a crude ducking: the bed drops while the voice speaks
            return v + fx.pulse_music(14.0, level_db=-26.0) * env

        def with_effects():
            x = fx.speechlike(14.0, seed=31, level_db=-26.0)
            rng = np.random.default_rng(5)
            for t0 in (3.0, 7.5, 11.0):
                n, i = int(0.4 * sr), int(t0 * sr)
                x[i:i + n] += np.float32(0.5) * rng.standard_normal(n).astype(np.float32) * np.hanning(n).astype(np.float32)
            return x

        mixes = [("A: five sentences at -14..-30 dBFS, 2.5 s and 3 s pauses", pauses()), ("B: narration over a ducked music bed", with_music()),
                 ("C: narration with three loud effect bursts", with_effects())]
        print("### Loudness: the render's one-pass loudnorm against the settled file (ffmpeg %s)\n" % (ffmpeg.binaries()[0],))
        print("| Mix | Target | One-pass LUFS / dBTP | Settled LUFS / dBTP | Rounds | Gain dB | Within 0.8 LU, TP <= -1 |")
        print("|---|---|---|---|---|---|---|")
        for name, x in mixes:
            wav = fx.write_wav(work / "m.wav", x)
            for target in (-14.0, -16.0):
                mp4 = fx.synthetic_video(work / f"m{int(-target)}.mp4", wav, ffmpeg_exe=ff, seconds=round(len(x) / sr, 2), loudnorm_to=target)
                before = loudness.measure(mp4)
                rep = loudness.settle(mp4, target=target)
                after = loudness.measure(mp4)
                ok = abs(after["lufs"] - target) <= 0.8 and after["tp"] <= -0.95
                print(f"| {name} | {target:.0f} | {before['lufs']} / {before['tp']} | {after['lufs']} / {after['tp']} | {rep.get('rounds')} | {rep.get('gain_db')} | {'yes' if ok else 'NO'} |")
        print("\n### Echo test: normalised auto-correlation at the echo lag (line = %.2f; per shot = %.2f)\n" % (audioqc.ECHO_R, audioqc.SHOT_ECHO_R))
        clean = [audioqc.echo_report(fx.speechlike(5.0, seed=s))["strength"] for s in range(1, 31)]
        print(f"- noise-excited synthetic speech, 30 seeds, 5 s windows: highest {max(clean):.3f}, median {float(np.median(clean)):.3f}")
        x = fx.speechlike(5.0, seed=3)
        print("- the same speech plus its own copy 150 ms later:")
        for g in (0.15, 0.25, 0.5, 1.0):
            r = audioqc.echo_report(fx.delayed_copy(x, 0.15, g))
            print(f"  - copy at {20 * np.log10(g):+.0f} dB: strength {r['strength']:.3f}, lag {r['lag_s']}, doubled {r['doubled']}")
        if "--real" in sys.argv:
            folder = Path(sys.argv[sys.argv.index("--real") + 1])
            print(f"\n- real narration files in the folder you gave ({len(list(folder.glob('*.wav')))} wav files; strengths per 5 s window, hop 0.5 s):")
            seen = set()
            for f in sorted(folder.glob("*.wav")):
                sig = audioqc.decode_mono(f)
                if len(sig) in seen or len(sig) < 4 * sr:
                    continue
                seen.add(len(sig))
                vals = [audioqc.echo_report(sig[a:a + 5 * sr])["strength"] for a in range(0, len(sig) - 3 * sr, sr // 2)]
                dbl = [audioqc.echo_report(fx.delayed_copy(sig[a:a + 5 * sr], 0.15, 0.5))["strength"] for a in range(0, len(sig) - 3 * sr, sr * 2)]
                print(f"  - {len(sig) / sr:.1f} s: clean max {max(vals):.3f}, p90 {sorted(vals)[int(len(vals) * 0.9)]:.3f}; with a -6 dB copy at 150 ms: min {min(dbl):.3f}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
