"""Regenerate docs/MODELS.md from the licence registry (instai/core/licences.py is the single source of truth).
Usage:  .venv\\Scripts\\python scripts\\gen_docs.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instai.settings")
os.environ.setdefault("INSTAI_TESTING", "1")

import django  # noqa: E402

django.setup()
from instai.core import licences  # noqa: E402

HEAD = """# Models, tools and licences

Generated from `instai/core/licences.py` by `scripts/gen_docs.py` - edit the registry, not this file.
The Settings page shows the same table as badges.

**How to read "Verified".** "model card read on 2026-10-28" means the licence line on the model's public Hugging Face card was read on that
day; the full licence text was **not** audited and nothing here is legal advice. "brief" means the owner's brief states it. "NOT verified"
means nobody has checked yet. Territorial and sanctions clauses (relevant from Iran) must be read in the full texts before a model is
adopted for published, commercial content.

**Open owner decisions**
1. **FLUX.1 [dev]** - weights are under a non-commercial licence. The model card says generated outputs may be used commercially "as described in
   the licence"; the licence text itself is gated and could not be read here. Until the owner (or a lawyer) accepts it, InstAI is built so that
   the image model is swappable: Qwen-Image and Z-Image are Apache-2.0 per their cards and must be benchmarked against FLUX with the same seeds.
2. **Anime video model** (Index-AniSora V3.2, AnimeGen I2V, Wan 2.2 + anime LoRA) - Phase 3 comparison; each licence (including the extra repo
   terms of AniSora) must be read first. No character/IP LoRAs.
3. **Voices** - the licence of each Piper voice (e.g. `fa_IR-gyro-medium`) must be checked on its model card before publishing commercially.

**Measured numbers** (VRAM at the chosen quantisation, seconds per step, quality notes) are only entered in `docs/BENCHMARKS.md` after the
benchmark has run on the real machine; this table never contains invented numbers (the VRAM column says "to measure" where unknown).

"""

if __name__ == "__main__":
    path = os.path.join(ROOT, "docs", "MODELS.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEAD + licences.markdown())
    print("wrote", path)
