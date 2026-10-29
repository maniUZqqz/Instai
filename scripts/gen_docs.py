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

**Finding what is already installed.** InstAI does not ask where the models are: `instai/core/discovery.py` searches the PC (ComfyUI
installs with their launcher, every models folder incl. `extra_model_paths.yaml`, NMarketing's voice engines, Piper, Ollama) and the
**Models** page shows what was found, where, what is missing and which feature each missing file blocks. Model files are matched by file
name in any sub-folder and letter case, plus known aliases (e.g. `FLUX.1 [dev] FP8.safetensors` = `flux1-dev-fp8.safetensors`).

"""

OFFERS_HEAD = """
## Optional downloads (offered on the Models page, downloaded only after the owner confirms)

The list lives in `manifests/*.json` (packages with an `offer` block). Before anything is fetched the page shows the name, the size still
to download, the licence (with a link) and why it is better; the API refuses a download without `confirm: true`. Files the ComfyUI InstAI
uses can already see are never downloaded again; downloads resume and every file has a pinned sha256. Quality and speed on the RTX 3060
are NOT measured yet; the anime video candidates are judged in Production lab > Compare on the same stills and seeds as plain Wan 2.2.

| Candidate | For | Size (all files) | Needs | Licence | Commercial use |
|---|---|---|---|---|---|
"""


def offers_markdown() -> str:
    from instai.core import model_status

    packages, items = model_status.manifests()
    rows = []
    for pid, p in packages.items():
        o = p.get("offer")
        if not o:
            continue
        size = sum(i.get("size") or 0 for i in items if i.get("package") == pid)
        needs = ", ".join(o.get("needs", []) + [i.split(":")[-1] for i in o.get("needs_items", [])]) or "-"
        rows.append(f"| {o['name']} (`{pid}`, workflow `{o.get('workflow')}`) | {o.get('group', '').replace('_', ' ')} | {size / 1e9:.1f} GB | {needs} | "
                    f"{p.get('licence')} | {o.get('commercial')} |")
    return OFFERS_HEAD + "\n".join(rows) + "\n"


if __name__ == "__main__":
    path = os.path.join(ROOT, "docs", "MODELS.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEAD + licences.markdown() + offers_markdown())
    print("wrote", path)
