#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerates manifests/curated.json: the curated, VERIFIED model library for an RTX 3060 12 GB (the Downloads page lists it).

Run it on any PC with internet (Python 3.10+, standard library only):   python scripts/gen_curated_manifest.py [--out manifests/curated.json]

Nothing in the output is typed by hand except titles/explanations: for every file the script asks the Hugging Face API (tree of the repo
at the repo's current commit) and writes the exact repo + commit + path, the size and the sha256 of the LFS object; the licence comes from
the model card's `license` field (read the same day). For the custom-node zips it pins the GitHub commit and measures size + sha256 of the
codeload archive. The script FAILS (writes nothing) when a file is missing, gated or has no sha256, so a manifest line is never a guess.

Policy (docs/MODELS.md): `commercial` is "yes" only for a plainly permissive licence line (apache-2.0, mit, bsd, openrail++ ...);
"conditional" for use-restricted licences; "no" for non-commercial ones (cc-by-nc ..., InsightFace); "unknown" when the card says `other`.
Anything that is not "yes" has `default: false` and the UI asks for an explicit confirmation before the download starts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

UA = {"User-Agent": "InstAI-manifest-generator/1.0"}
TODAY = time.strftime("%Y-%m-%d")
HF_API = "https://huggingface.co/api/models/"


def get_json(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


_REPOS: dict[str, dict] = {}


def repo(repo_id: str) -> dict:
    """{id, sha, license, files: {path: {size, sha256}}} of a Hugging Face model repo (cached). `files` is filled directory by directory
    (see file_info): the tree of a big repo (piper-voices) is paginated, one folder never is."""
    if repo_id not in _REPOS:
        info = get_json(HF_API + repo_id)
        if info.get("gated"):
            raise SystemExit(f"{repo_id} is gated (needs a login) - not usable for an automatic download")
        card = info.get("cardData") or {}
        _REPOS[repo_id] = {"id": info["id"], "sha": info["sha"], "license": card.get("license") or "", "files": {}, "dirs": set()}
    return _REPOS[repo_id]


def file_info(repo_id: str, path: str) -> dict | None:
    r = repo(repo_id)
    folder = path.rsplit("/", 1)[0] if "/" in path else ""
    if folder not in r["dirs"]:
        url = f"{HF_API}{r['id']}/tree/{r['sha']}" + (f"/{folder}" if folder else "")
        for f in get_json(url):
            if f.get("type") == "file":
                r["files"][f["path"]] = {"size": f.get("size"), "sha256": (f.get("lfs") or {}).get("oid")}
        r["dirs"].add(folder)
    return r["files"].get(path)


def hf_item(pkg: str, iid: str, repo_id: str, path: str, dest: str, title: str, aliases: list[str] | None = None) -> dict:
    r = repo(repo_id)
    f = file_info(repo_id, path)
    if not f or not f["size"]:
        raise SystemExit(f"{repo_id}/{path} not found")
    if not f["sha256"] or set(f["sha256"]) == {"*"}:
        raise SystemExit(f"{repo_id}/{path} has no readable sha256")
    it = {"id": f"{pkg}:{iid}", "package": pkg, "kind": "file", "title": title,
          "urls": [f"{{HF}}/{r['id']}/resolve/{r['sha']}/{path}"], "dest": dest, "size": f["size"], "sha256": f["sha256"],
          "hf": {"repo": r["id"], "revision": r["sha"], "path": path, "license": r["license"]},
          "source": f"Hugging Face API read {TODAY} (pinned commit {r['sha'][:7]}; size and sha256 of the LFS object)"}
    if aliases:
        it["aliases"] = aliases
    return it


def github_zip(pkg: str, iid: str, gh: str, dest_dir: str, marker: str, title: str) -> dict:
    out = subprocess.run(["git", "ls-remote", f"https://github.com/{gh}", "HEAD"], capture_output=True, text=True, timeout=60, check=True).stdout
    commit = out.split()[0]
    url = f"https://codeload.github.com/{gh}/zip/{commit}"
    h, n = hashlib.sha256(), 0
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return {"id": f"{pkg}:{iid}", "package": pkg, "kind": "zip", "strip": True, "title": f"{title} (commit {commit[:7]})",
            "urls": [url, f"https://github.com/{gh}/archive/{commit}.zip"], "dest": dest_dir, "marker": marker, "size": n, "sha256": h.hexdigest(),
            "source": f"GitHub archive of the pinned commit, size and sha256 measured {TODAY}"}


CK = "{COMFYUI}\\models\\checkpoints\\"
TE = "{COMFYUI}\\models\\text_encoders\\"
VAE = "{COMFYUI}\\models\\vae\\"
DM = "{COMFYUI}\\models\\diffusion_models\\"
CN = "{COMFYUI}\\models\\controlnet\\"
UP = "{COMFYUI}\\models\\upscale_models\\"
CV = "{COMFYUI}\\models\\clip_vision\\"
IPA = "{COMFYUI}\\models\\ipadapter\\"
PUL = "{COMFYUI}\\models\\pulid\\"
CLIP = "{COMFYUI}\\models\\clip\\"
FI = "{COMFYUI}\\models\\frame_interpolation\\"
INS = "{COMFYUI}\\models\\insightface\\models\\antelopev2\\"
NODES = "{COMFYUI}\\custom_nodes\\"


def fa_en(fa: str, en: str) -> dict:
    return {"fa": fa, "en": en}


def build() -> dict:
    packages: dict[str, dict] = {}
    items: list[dict] = []

    def pkg(pid: str, title: str, group: str, licence: str, commercial: str, why: dict, vram: str, note: dict | None = None, licence_url: str = "",
            order: int = 50, needs: list[str] | None = None) -> None:
        packages[pid] = {"title": title, "default": False, "licence": licence, "licence_verified": True,
                         "curated": {"group": group, "commercial": commercial, "vram": vram, "why": why, "note": note or {},
                                     "licence_url": licence_url, "checked": TODAY, "order": order, "needs": needs or []}}

    # ---------------------------------------------------------------- images: FLUX
    pkg("flux-schnell", "FLUX.1 [schnell] FP8, all-in-one checkpoint (fast, 4 steps)", "image", "Apache-2.0 (model card license field)", "yes",
        fa_en("نسخهٔ سریع و آزاد FLUX: با ۴ گام تصویر با کیفیت می‌سازد و مجوزش (Apache-2.0) استفادهٔ تجاری را آزاد می‌گذارد. یک فایل همه‌چیز را دارد (مدل + رمزگذار متن + VAE) و روی ۱۲ گیگابایت با بارگذاری خودکار ComfyUI کار می‌کند.",
              "The fast, freely licensed FLUX: good images in 4 steps, Apache-2.0 so commercial use is allowed. One file holds everything (model + text encoders + VAE); runs on 12 GB with ComfyUI's automatic offloading."),
        "12 GB (fp8; ComfyUI offloads what does not fit)", licence_url="https://huggingface.co/black-forest-labs/FLUX.1-schnell/blob/main/LICENSE.md", order=10)
    items.append(hf_item("flux-schnell", "fp8-checkpoint", "Comfy-Org/flux1-schnell", "flux1-schnell-fp8.safetensors", CK + "flux1-schnell-fp8.safetensors",
                         "FLUX.1 [schnell] FP8 checkpoint (Comfy-Org repack)", aliases=["FLUX.1 [schnell] FP8.safetensors"]))
    pkg("flux-parts", "FLUX text encoders + VAE (t5xxl fp8, clip_l, ae) for the split FLUX loaders", "image", "Apache-2.0 (encoders: model card; VAE: Lumina repack card)", "yes",
        fa_en("برای وقتی که FLUX را با بارگذارهای جدا (UNET + رمزگذار متن + VAE) یا با مدل‌های GGUF اجرا می‌کنید: رمزگذار T5 (fp8)، CLIP-L و VAE. اگر معادلش از قبل روی ComfyUI هست دوباره دانلود نمی‌شود.",
              "For running FLUX with the split loaders (UNET + text encoders + VAE) or with GGUF models: T5 (fp8), CLIP-L and the VAE. An equivalent file ComfyUI already has is not downloaded again."),
        "T5 fp8 about 5 GB in RAM / VRAM while encoding", order=11)
    items.append(hf_item("flux-parts", "t5xxl-fp8", "comfyanonymous/flux_text_encoders", "t5xxl_fp8_e4m3fn.safetensors", TE + "t5xxl_fp8_e4m3fn.safetensors",
                         "T5-XXL text encoder, fp8 (e4m3fn)", aliases=["t5xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp16.safetensors"]))
    items.append(hf_item("flux-parts", "clip-l", "comfyanonymous/flux_text_encoders", "clip_l.safetensors", TE + "clip_l.safetensors", "CLIP-L text encoder"))
    items.append(hf_item("flux-parts", "ae", "Comfy-Org/Lumina_Image_2.0_Repackaged", "split_files/vae/ae.safetensors", VAE + "ae.safetensors",
                         "FLUX VAE (ae.safetensors, ungated repack)", aliases=["flux_vae.safetensors", "ae.sft"]))
    # FLUX.1 [dev] is the existing package "flux" in manifests/image.json (non-commercial); its facts are printed by main() and pasted there.

    # ---------------------------------------------------------------- images: SDXL
    pkg("sdxl-base", "Stable Diffusion XL base 1.0 (the reference SDXL checkpoint)", "image", "CreativeML Open RAIL++-M (model card license field: openrail++)", "yes",
        fa_en("پایهٔ استاندارد SDXL؛ برای ControlNet، IP-Adapter و لورا‌های SDXL لازم است. مجوز Open RAIL++-M استفادهٔ تجاری را با محدودیت‌های رفتاری مجاز می‌داند.",
              "The standard SDXL base; the foundation for SDXL ControlNet, IP-Adapter and LoRAs. Open RAIL++-M allows commercial use with use-based restrictions."),
        "SDXL size (about 7 to 9 GB with the VAE)", licence_url="https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md", order=20)
    items.append(hf_item("sdxl-base", "base-1.0", "stabilityai/stable-diffusion-xl-base-1.0", "sd_xl_base_1.0.safetensors", CK + "sd_xl_base_1.0.safetensors", "SDXL base 1.0 checkpoint"))
    pkg("sdxl-realvis", "RealVisXL V4.0 (photoreal SDXL checkpoint, permissive licence)", "image", "CreativeML Open RAIL++-M (model card license field: openrail++)", "yes",
        fa_en("چک‌پوینت SDXL فوتورئال با مجوز آزاد (Open RAIL++-M)؛ برای آدم و محصول واقع‌نما، سریع‌تر و سبک‌تر از FLUX روی ۱۲ گیگابایت.",
              "A photoreal SDXL checkpoint under a permissive licence (Open RAIL++-M); realistic people and products, lighter and faster than FLUX on 12 GB."),
        "SDXL size (about 7 GB)", order=21)
    items.append(hf_item("sdxl-realvis", "v4.0", "SG161222/RealVisXL_V4.0", "RealVisXL_V4.0.safetensors", CK + "RealVisXL_V4.0.safetensors", "RealVisXL V4.0 checkpoint"))

    # ---------------------------------------------------------------- consistent characters / control
    pkg("controlnet-union-sdxl", "ControlNet Union SDXL (promax): pose, depth, canny, lines ... in one model", "control", "Apache-2.0 (model card license field)", "yes",
        fa_en("یک مدل ControlNet برای SDXL که همه‌کاره است: ژست، عمق، لبه، خط و ... . برای نگه داشتن ژست و ترکیب‌بندی شخصیت‌ها بین شات‌ها.",
              "One ControlNet for SDXL that does everything: pose, depth, edges, lines ... Keeps a character's pose and composition across shots."),
        "about 2.5 GB", order=30)
    items.append(hf_item("controlnet-union-sdxl", "promax", "xinsir/controlnet-union-sdxl-1.0", "diffusion_pytorch_model_promax.safetensors",
                         CN + "controlnet-union-sdxl-1.0-promax.safetensors", "ControlNet Union SDXL promax"))
    pkg("ipadapter-sdxl", "IP-Adapter Plus + Plus-Face (SDXL, ViT-H) + CLIP-ViT-H image encoder + the ComfyUI_IPAdapter_plus node", "control", "Apache-2.0 (IP-Adapter model card); node: GPL-3.0 (GitHub licence field)", "yes",
        fa_en("برای «همان شخصیت در همهٔ شات‌ها»: چهره و سبک از یک تصویر مرجع گرفته می‌شود. چهار فایل: دو مدل IP-Adapter، رمزگذار تصویر CLIP-ViT-H و گرهٔ ComfyUI_IPAdapter_plus. بعد از نصب، ComfyUI را یک بار ببندید و باز کنید.",
              "For \"the same character in every shot\": face and style are taken from one reference picture. Four parts: two IP-Adapter models, the CLIP-ViT-H image encoder and the ComfyUI_IPAdapter_plus node. Restart ComfyUI once afterwards."),
        "about 4.3 GB in total", note=fa_en("گرهٔ ComfyUI_IPAdapter_plus مجوز GPL-3.0 دارد؛ فقط کنار ComfyUI اجرا می‌شود و با InstAI پیوند نمی‌خورد.",
                                           "The ComfyUI_IPAdapter_plus node is GPL-3.0; it only runs inside ComfyUI and is not linked into InstAI."), order=31)
    items.append(hf_item("ipadapter-sdxl", "plus-sdxl", "h94/IP-Adapter", "sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors", IPA + "ip-adapter-plus_sdxl_vit-h.safetensors", "IP-Adapter Plus SDXL (ViT-H)"))
    items.append(hf_item("ipadapter-sdxl", "plus-face-sdxl", "h94/IP-Adapter", "sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors", IPA + "ip-adapter-plus-face_sdxl_vit-h.safetensors", "IP-Adapter Plus Face SDXL (ViT-H)"))
    items.append(hf_item("ipadapter-sdxl", "clip-vit-h", "h94/IP-Adapter", "models/image_encoder/model.safetensors", CV + "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
                         "CLIP-ViT-H-14 image encoder (laion2B), named as the IPAdapter node expects", aliases=["CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors", "clip_vision_vit_h.safetensors"]))
    items.append(github_zip("ipadapter-sdxl", "node", "cubiq/ComfyUI_IPAdapter_plus", NODES + "ComfyUI_IPAdapter_plus", "IPAdapterPlus.py", "ComfyUI_IPAdapter_plus custom node (cubiq)"))
    pkg("pulid-flux", "PuLID for FLUX (identity-preserving portraits) + node + EVA-CLIP + InsightFace antelopev2", "control", "PuLID weights Apache-2.0; InsightFace antelopev2 is NON-COMMERCIAL research use", "no",
        fa_en("حفظ هویت چهره با FLUX (شبیه IP-Adapter ولی دقیق‌تر). ⚠ وزن‌های InsightFace (تشخیص چهره) فقط برای پژوهش و غیرتجاری‌اند، پس این بسته پیش‌فرض خاموش است و دانلودش تأیید جداگانه می‌خواهد. همچنین بستهٔ پایتونِ insightface باید داخل ComfyUI نصب شود (خودکار نصب نمی‌شود).",
              "Identity-preserving faces with FLUX (like IP-Adapter, but sharper). WARNING: the InsightFace face-detection weights are research / non-commercial only, so this package is off by default and needs its own confirmation. The insightface Python package must also be installed inside ComfyUI (not done automatically)."),
        "FLUX fp8 plus about 3 GB of face models", note=fa_en("فقط برای استفادهٔ غیرتجاری. گرهٔ ComfyUI-PuLID-Flux مجوز Apache-2.0 دارد.", "Non-commercial use only. The ComfyUI-PuLID-Flux node is Apache-2.0."),
        licence_url="https://github.com/deepinsight/insightface#license", order=32)
    items.append(hf_item("pulid-flux", "pulid-v0.9.1", "guozinan/PuLID", "pulid_flux_v0.9.1.safetensors", PUL + "pulid_flux_v0.9.1.safetensors", "PuLID-FLUX v0.9.1"))
    items.append(hf_item("pulid-flux", "eva02-clip-l-336", "QuanSun/EVA-CLIP", "EVA02_CLIP_L_336_psz14_s6B.pt", CLIP + "EVA02_CLIP_L_336_psz14_s6B.pt", "EVA02-CLIP-L-336 (PuLID's image encoder)"))
    for fname in ("1k3d68.onnx", "2d106det.onnx", "genderage.onnx", "glintr100.onnx", "scrfd_10g_bnkps.onnx"):
        items.append(hf_item("pulid-flux", "antelopev2-" + fname.split(".")[0], "DIAMONIK7777/antelopev2", fname, INS + fname, "InsightFace antelopev2: " + fname))
    items.append(github_zip("pulid-flux", "node", "balazik/ComfyUI-PuLID-Flux", NODES + "ComfyUI-PuLID-Flux", "pulidflux.py", "ComfyUI-PuLID-Flux custom node (balazik)"))

    # ---------------------------------------------------------------- upscalers
    pkg("upscale-realesrgan", "Real-ESRGAN x4plus (upscaler, BSD-3-Clause)", "upscale", "BSD-3-Clause (Comfy-Org repack card)", "yes",
        fa_en("بزرگ‌نمایی ۴ برابری عکس و فریم با حفظ جزئیات؛ سبک و سریع روی GPU. مجوز BSD-3.", "4x upscaling of pictures and frames with detail; light and fast on the GPU. BSD-3 licence."),
        "under 2 GB", order=40)
    items.append(hf_item("upscale-realesrgan", "x4plus", "Comfy-Org/Real-ESRGAN_repackaged", "RealESRGAN_x4plus.safetensors", UP + "RealESRGAN_x4plus.safetensors",
                         "Real-ESRGAN x4plus", aliases=["RealESRGAN_x4plus.pth", "RealESRGAN_x4.pth"]))
    pkg("upscale-ultrasharp", "4x-UltraSharp (sharp upscaler; NON-COMMERCIAL licence)", "upscale", "CC-BY-NC-SA-4.0 (model card license field) - NON-COMMERCIAL", "no",
        fa_en("یکی از محبوب‌ترین بزرگ‌نماها برای جزئیات تیز. ⚠ مجوزش CC-BY-NC-SA 4.0 است (غیرتجاری)، پس پیش‌فرض خاموش است و دانلودش تأیید جداگانه می‌خواهد.",
              "A very popular sharp upscaler. WARNING: its licence is CC-BY-NC-SA 4.0 (non-commercial), so it is off by default and needs its own confirmation."),
        "under 2 GB", licence_url="https://creativecommons.org/licenses/by-nc-sa/4.0/", order=41)
    items.append(hf_item("upscale-ultrasharp", "4x", "Kim2091/UltraSharp", "4x-UltraSharp.pth", UP + "4x-UltraSharp.pth", "4x-UltraSharp"))

    # ---------------------------------------------------------------- video
    pkg("wan22-ti2v-5b", "Wan 2.2 TI2V-5B (text+image to video, light: fits 12 GB comfortably)", "video", "Apache-2.0 (Comfy-Org repack card)", "yes",
        fa_en("نسخهٔ سبک Wan 2.2 (۵ میلیارد پارامتر): متن‌به‌ویدئو و تصویر‌به‌ویدئو در یک مدل، با VAE تازهٔ Wan 2.2؛ برای ۱۲ گیگابایت بسیار راحت‌تر از مدل ۱۴ میلیاردی است. رمزگذار متن umt5 با بستهٔ Wan 2.2 مشترک است و اگر دارید دوباره دانلود نمی‌شود.",
              "The light Wan 2.2 (5B parameters): text-to-video and image-to-video in one model with the new Wan 2.2 VAE; far easier on 12 GB than the 14B pair. The umt5 text encoder is shared with the Wan 2.2 package and not downloaded twice."),
        "about 10 GB (fp16) plus encoder and VAE; comfortable on 12 GB", order=50)
    items.append(hf_item("wan22-ti2v-5b", "ti2v-5b-fp16", "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors", DM + "wan2.2_ti2v_5B_fp16.safetensors", "Wan 2.2 TI2V 5B (fp16)"))
    items.append(hf_item("wan22-ti2v-5b", "vae", "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/vae/wan2.2_vae.safetensors", VAE + "wan2.2_vae.safetensors", "Wan 2.2 VAE"))
    items.append(hf_item("wan22-ti2v-5b", "umt5-xxl-fp8", "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", TE + "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "umT5-XXL text encoder (fp8 scaled)"))
    pkg("ltx-distilled", "LTX-Video 2B 0.9.8 distilled FP8 (very fast video; licence 'other')", "video", "LTX-Video licence (model card license field: other) - read it before commercial use", "unknown",
        fa_en("مدل ویدئوی بسیار سریع (چند گام)، مناسب پیش‌نمایش و شات‌های کوتاه. مجوز در کارت مدل «other» است و در این‌جا بررسی نشده؛ پیش از انتشار تجاری متن مجوز را بخوانید، پس پیش‌فرض خاموش است.",
              "A very fast few-step video model, good for previews and short shots. Its licence is 'other' on the model card and was not audited here; read it before commercial use, so it is off by default."),
        "about 4.5 GB + T5 encoder", licence_url="https://huggingface.co/Lightricks/LTX-Video", order=51)
    items.append(hf_item("ltx-distilled", "2b-distilled-fp8", "Lightricks/LTX-Video", "ltxv-2b-0.9.8-distilled-fp8.safetensors", CK + "ltxv-2b-0.9.8-distilled-fp8.safetensors", "LTX-Video 2B 0.9.8 distilled (fp8)"))
    items.append(hf_item("ltx-distilled", "t5xxl-fp8-scaled", "comfyanonymous/flux_text_encoders", "t5xxl_fp8_e4m3fn_scaled.safetensors", TE + "t5xxl_fp8_e4m3fn_scaled.safetensors",
                         "T5-XXL text encoder, fp8 scaled", aliases=["t5xxl_fp16.safetensors", "t5xxl_fp8_e4m3fn.safetensors"]))
    pkg("rife", "RIFE v4.25 frame interpolation (smoother video: 2x frames)", "video", "MIT + Apache-2.0 (Comfy-Org repack card: mit-and-apache-2.0)", "yes",
        fa_en("فریم‌های میانی می‌سازد تا ویدئوی ۲۴ فریمی نرم‌تر شود (دو برابر). فایل کوچک است. به نسخه‌ای از ComfyUI نیاز دارد که گره‌های «درون‌یابی فریم» را دارد.",
              "Creates in-between frames so 24 fps video becomes smoother (2x). A small file. Needs a ComfyUI version that has the frame-interpolation nodes."),
        "under 1 GB", order=52)
    items.append(hf_item("rife", "v4.25", "Comfy-Org/Frame-Interpolation", "frame_interpolation/rife_v4.25.safetensors", FI + "rife_v4.25.safetensors", "RIFE v4.25 (ComfyUI repack)"))

    # ---------------------------------------------------------------- voices
    pkg("piper-fa-voices", "Four more Persian Piper voices (amir, ganji, ganji_adabi, reza_ibrahim; CPU, offline)", "voice", "CC0 dataset licence stated on each voice's MODEL_CARD", "yes",
        fa_en("چهار صدای فارسی دیگر برای Piper (روی CPU و بدون اینترنت): «امیر»، «گنجی»، «گنجی ادبی» و «رضا ابراهیم». دادهٔ آموزش هر چهار CC0 است. بعد از دانلود در انتخاب صدا دیده می‌شوند.",
              "Four more Persian voices for Piper (CPU, offline): amir, ganji, ganji_adabi and reza_ibrahim. The training data of all four is CC0. They appear in the voice picker after the download."),
        "CPU, about 64 MB each", order=60)
    for v in ("amir", "ganji", "ganji_adabi", "reza_ibrahim"):
        base = f"fa/fa_IR/{v}/medium/fa_IR-{v}-medium.onnx"
        items.append(hf_item("piper-fa-voices", v, "rhasspy/piper-voices", base, "{MODELS}\\piper\\" + f"fa_IR-{v}-medium.onnx", f"Piper voice fa_IR-{v}-medium"))
        # the .onnx.json files are small, not LFS: the tree gives no sha256 for them, so they are fetched through a second pass below
        items.append({"id": f"piper-fa-voices:{v}.json", "package": "piper-fa-voices", "kind": "file", "title": f"Piper voice fa_IR-{v}-medium (settings)",
                      "urls": [f"{{HF}}/{repo('rhasspy/piper-voices')['id']}/resolve/{repo('rhasspy/piper-voices')['sha']}/{base}.json"],
                      "dest": "{MODELS}\\piper\\" + f"fa_IR-{v}-medium.onnx.json", "size": file_info("rhasspy/piper-voices", base + ".json")["size"], "sha256": None,
                      "source": f"Hugging Face API read {TODAY} (pinned commit; small text file, size from the tree, no LFS hash: verified by size and recorded on first download)"})
    return {"group": "curated", "title": "Curated model library for an RTX 3060 12 GB (Hugging Face / GitHub; every file pinned with size + sha256)",
            "licence_note": "Read on " + TODAY + " from each repository's model-card licence field (not the full legal text). Packages whose licence is not plainly permissive are off by default and need a separate confirmation.",
            "generated_by": "scripts/gen_curated_manifest.py", "generated_at": TODAY, "packages": packages, "items": items}


def flux_dev_facts() -> dict:
    """The facts for the existing FLUX.1 [dev] FP8 item of manifests/image.json (its sha256 was null = unverified); printed, then pasted by hand."""
    r = repo("Comfy-Org/flux1-dev")
    f = file_info("Comfy-Org/flux1-dev", "flux1-dev-fp8.safetensors")
    return {"size": f["size"], "sha256": f["sha256"], "commit": r["sha"], "license": r["license"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifests", "curated.json"))
    args = ap.parse_args()
    m = build()
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(m, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print("flux:flux1-dev-fp8 (manifests/image.json):", json.dumps(flux_dev_facts()))
    total = sum(i.get("size") or 0 for i in m["items"])
    print(f"wrote {args.out}: {len(m['packages'])} packages, {len(m['items'])} items, {total / 1e9:.1f} GB in total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
