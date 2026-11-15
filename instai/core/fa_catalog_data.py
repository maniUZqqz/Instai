"""Persian twins of the English catalogue texts (models, licences, packages, workflows, installer items, provider messages).

The owner reads Persian only (audit 2026-11-14: «MOSS-TTS is not installed (Download-Models.bat --only moss-tts)» on a Persian page). The
catalogue sources (manifests/*.json, core/licences.py, the ComfyUI workflow table, the providers) stay English: they are technical records
with sources and licences. `core/fa_catalog.py` swaps these exact texts for the Persian ones in the API answers of a Persian page; the English
original is kept beside it (`<field>_en`) for the «اطلاعات فنی» view. `tests/test_core_audit_catalog.py` fails when a source text has no twin
here, so a new package or model cannot ship in English only.

Product names (FLUX, Wan, Piper ...) and licence identifiers (Apache-2.0, MIT ...) stay in Latin letters on purpose; everything around them is Persian.
Numbers are written with Persian digits.
"""
from __future__ import annotations

# ------------------------------------------------------------------ licences (the exact English text -> Persian)
LICENCE: dict[str, str] = {
    "FLUX.1 [dev] Non-Commercial License": "مجوز غیرتجاریِ FLUX.1 [dev]",
    "Apache-2.0 + additional restrictions (repo LICENSE) when retraining / making derivatives": "Apache-2.0 با محدودیت‌های بیشتر (در متن مجوزِ مخزن) برای آموزشِ دوباره یا ساختنِ مدل مشتق",
    "Apache-2.0 (card tag: commercial-use)": "Apache-2.0 (روی صفحهٔ مدل برچسبِ «استفادهٔ تجاری» دارد)",
    "Apache-2.0 (card tag commercial-use)": "Apache-2.0 (روی صفحهٔ مدل برچسبِ «استفادهٔ تجاری» دارد)",
    "Apache-2.0 (per Qasem manifest); verify - docs/MODELS.md": "Apache-2.0 (طبق مانیفستِ NMarketing؛ باید بررسی شود)",
    "MIT (engine); each voice has its own licence - see docs/MODELS.md": "MIT (موتور)؛ هر صدا مجوزِ خودش را دارد",
    "unofficial online endpoint - not licensed for commercial use": "سرویسِ آنلاینِ غیررسمی — مجوزِ استفادهٔ تجاری ندارد",
    "Apache-2.0 (node); MIT (gguf)": "Apache-2.0 (گره)؛ MIT (بستهٔ gguf)",
    "varies per LoRA": "برای هر LoRA فرق می‌کند",
    "requires a not-sanctioned-country representation": "اقرار می‌خواهد که کاربر در کشورِ تحریم‌شده نیست",
    "territorial / trade-law clauses": "بندهای محدودیتِ سرزمینی و قوانینِ تجارت",
    "API only (no open weights)": "فقط از راه API؛ وزن‌ها باز نیست",
    "Apache-2.0 (per Qasem notes)": "Apache-2.0 (طبق یادداشت‌های NMarketing)",
    "MIT (per Qasem notes)": "MIT (طبق یادداشت‌های NMarketing)",
    "engine MIT; each voice has its own licence": "موتور: MIT؛ هر صدا مجوزِ خودش را دارد",
    "Apache-2.0 (per brief)": "Apache-2.0 (طبق شرحِ پروژه)",
    "CC-BY-NC-4.0 - NON-COMMERCIAL": "CC-BY-NC-4.0 — غیرتجاری",
    "unofficial endpoint, not for commercial use": "سرویسِ غیررسمی؛ برای استفادهٔ تجاری نیست",
    "MIT (per repo)": "MIT (طبق مخزن)",
    "MIT (per BiRefNet repo; unverified)": "MIT (طبق مخزنِ BiRefNet؛ بررسی‌نشده)",
    "non-commercial": "غیرتجاری",
    "GPL-3.0 build (run as a separate program, not linked)": "ساخت GPL-3.0 (برنامهٔ جداگانه اجرا می‌شود و به کدِ InstAI پیوند نمی‌خورد)",
    "GPL-3.0 build; InstAI only runs it as a separate program": "ساخت GPL-3.0؛ InstAI فقط آن را به‌صورتِ برنامهٔ جداگانه اجرا می‌کند",
    "SIL Open Font License 1.1": "مجوزِ فونتِ باز SIL نسخهٔ ۱٫۱",
    "Apache-2.0 (encoder cards; the VAE is an ungated repack)": "Apache-2.0 (طبق صفحهٔ رمزگذارها؛ VAE بازبسته‌بندیِ آزاد است)",
    "Apache-2.0 (models); GPL-3.0 (the ComfyUI node)": "Apache-2.0 (مدل‌ها)؛ GPL-3.0 (گرهٔ ComfyUI)",
    "PuLID Apache-2.0; InsightFace antelopev2 NON-COMMERCIAL": "PuLID: Apache-2.0؛ InsightFace antelopev2: غیرتجاری",
    "CC-BY-NC-SA-4.0 - NON-COMMERCIAL": "CC-BY-NC-SA-4.0 — غیرتجاری",
    "LTX-Video licence (card says 'other')": "مجوزِ ویژهٔ LTX-Video (روی صفحهٔ مدل «other» نوشته شده)",
    "CC0 training data (each voice's MODEL_CARD)": "داده‌های آموزشیِ CC0 (در MODEL_CARD هر صدا)",
    "Remotion License: free for an individual, a for-profit organisation with up to 3 employees, a non-profit, or evaluation; a Company License for larger companies":
        "مجوزِ Remotion: برای یک فرد، شرکتِ انتفاعیِ تا ۳ کارمند، سازمانِ غیرانتفاعی یا ارزیابی رایگان است؛ شرکت‌های بزرگ‌تر باید «مجوز شرکتی» بخرند",
    "Apache-2.0 (per model cards; verify the exact tag)": "Apache-2.0 (طبق صفحهٔ مدل‌ها؛ برچسبِ دقیقِ مدل را بررسی کنید)",
    "Gemma Terms of Use (custom)": "شرایطِ استفادهٔ Gemma (مجوزِ اختصاصی)",
    "Apache-2.0 (per brief list)": "Apache-2.0 (طبق فهرستِ شرحِ پروژه)",
    "Llama 3 community licence (derivative)": "مجوزِ جامعهٔ Llama 3 (مدل مشتق)",
    # workflows
    "FLUX.1 [dev] Non-Commercial License (weights); output use: see docs/MODELS.md": "مجوزِ غیرتجاریِ FLUX.1 [dev] (برای وزن‌ها)؛ شرایطِ استفاده از خروجی در پروندهٔ «مدل‌ها و مجوزها»ی پروژه",
    "FLUX.1 [dev] Non-Commercial License (weights)": "مجوزِ غیرتجاریِ FLUX.1 [dev] (برای وزن‌ها)",
    "Apache-2.0 (Wan 2.2, umT5, VAE, lightx2v) - per Qasem manifest notes; re-verify": "Apache-2.0 (Wan 2.2، umT5، VAE، lightx2v) — طبق یادداشت‌های NMarketing؛ باید دوباره بررسی شود",
    "Apache-2.0 (Wan 2.2) - per Qasem manifest notes; re-verify": "Apache-2.0 (Wan 2.2) — طبق یادداشت‌های NMarketing؛ باید دوباره بررسی شود",
    "Apache-2.0 + extra restrictions for retraining/derivatives (bilibili/Index-anisora LICENSE); community GGUF conversion":
        "Apache-2.0 با محدودیت‌های بیشتر برای آموزشِ دوباره و مدل مشتق (متن مجوزِ Index-anisora)؛ تبدیلِ GGUF را جامعهٔ کاربران ساخته",
    "Apache-2.0 (AIdeaLab; card tag commercial-use; Wan 2.2 base); community GGUF conversion":
        "Apache-2.0 (AIdeaLab؛ برچسبِ «استفادهٔ تجاری» روی صفحهٔ مدل؛ پایه: Wan 2.2)؛ تبدیلِ GGUF را جامعهٔ کاربران ساخته",
    "CreativeML Open RAIL++-M (model card: commercial use allowed, use-based restrictions)": "CreativeML Open RAIL++-M (طبق صفحهٔ مدل: استفادهٔ تجاری آزاد است، با محدودیت‌هایی در نوعِ استفاده)",
    # packages
    "Apache-2.0 (model card license field)": "Apache-2.0 (طبق صفحهٔ مدل)",
    "Apache-2.0 (encoders: model card; VAE: Lumina repack card)": "Apache-2.0 (رمزگذارها: طبق صفحهٔ مدل؛ VAE: طبق صفحهٔ بازبسته‌بندیِ Lumina)",
    "CreativeML Open RAIL++-M (model card license field: openrail++)": "CreativeML Open RAIL++-M (طبق صفحهٔ مدل)",
    "Apache-2.0 (IP-Adapter model card); node: GPL-3.0 (GitHub licence field)": "Apache-2.0 (طبق صفحهٔ IP-Adapter)؛ گره: GPL-3.0 (طبق صفحهٔ گیت‌هاب)",
    "PuLID weights Apache-2.0; InsightFace antelopev2 is NON-COMMERCIAL research use": "وزن‌های PuLID: Apache-2.0؛ InsightFace antelopev2: فقط پژوهشی و غیرتجاری",
    "BSD-3-Clause (Comfy-Org repack card)": "BSD-3-Clause (طبق صفحهٔ بازبسته‌بندیِ Comfy-Org)",
    "CC-BY-NC-SA-4.0 (model card license field) - NON-COMMERCIAL": "CC-BY-NC-SA-4.0 (طبق صفحهٔ مدل) — غیرتجاری",
    "Apache-2.0 (Comfy-Org repack card)": "Apache-2.0 (طبق صفحهٔ بازبسته‌بندیِ Comfy-Org)",
    "LTX-Video licence (model card license field: other) - read it before commercial use": "مجوزِ ویژهٔ LTX-Video (روی صفحهٔ مدل «other» نوشته شده) — پیش از استفادهٔ تجاری متنش را بخوانید",
    "MIT + Apache-2.0 (Comfy-Org repack card: mit-and-apache-2.0)": "MIT + Apache-2.0 (طبق صفحهٔ بازبسته‌بندیِ Comfy-Org)",
    "CC0 dataset licence stated on each voice's MODEL_CARD": "مجوزِ دادگان: CC0 (در MODEL_CARD هر صدا نوشته شده)",
    "CreativeML Open RAIL++-M (model card read 2026-10-29: commercial use allowed, use-based restrictions)":
        "CreativeML Open RAIL++-M (صفحهٔ مدل در ۷ آبان ۱۴۰۵ خوانده شد: استفادهٔ تجاری آزاد است، با محدودیت‌هایی در نوعِ استفاده)",
    "Apache-2.0 (Qwen-Image-Edit-2509, Qwen2.5-VL text encoder, Qwen-Image VAE, Lightning LoRA)": "Apache-2.0 (Qwen-Image-Edit-2509، رمزگذارِ متنِ Qwen2.5-VL، VAEِ Qwen-Image، LoRAِ Lightning)",
    "Piper MIT; voice licence unverified": "Piper: MIT؛ مجوزِ صدا بررسی نشده",
    "Apache-2.0 (node, GitHub licence field read 2026-10-29); gguf package MIT (PyPI classifier read 2026-10-29)": "Apache-2.0 (گره؛ طبق صفحهٔ گیت‌هاب)؛ بستهٔ gguf: MIT (طبق PyPI)",
    "Apache-2.0 + extra restrictions for retraining/derivatives (bilibili Index-anisora LICENSE)": "Apache-2.0 با محدودیت‌های بیشتر برای آموزشِ دوباره و مدل مشتق (متن مجوزِ Index-anisora)",
    "PSF License": "مجوزِ PSF (بنیاد نرم‌افزار Python)",
}

# ------------------------------------------------------------------ how the licence was checked (core/licences.py `verified`)
VERIFIED: dict[str, str] = {
    "GitHub licence field + PyPI classifier read on 2026-10-29": "فیلد مجوزِ گیت‌هاب و دسته‌بندیِ PyPI در ۷ آبان ۱۴۰۵ خوانده شد",
    "HF card + GitHub LICENSE read on 2026-10-28 (not audited)": "صفحهٔ مدل و متن مجوزِ گیت‌هاب در ۶ آبان ۱۴۰۵ خوانده شد (حقوقی بررسی نشده)",
    "HF card + LICENSE read on 2026-10-28 (licence line only)": "صفحهٔ مدل و متن مجوز در ۶ آبان ۱۴۰۵ خوانده شد (فقط سطرِ مجوز)",
    "LICENSE.md of remotion-dev/remotion read on 2026-11-13 (not legal advice)": "متن مجوزِ Remotion در ۲۲ آبان ۱۴۰۵ خوانده شد (مشاورهٔ حقوقی نیست)",
    "OFL.txt shipped with the package": "متنِ مجوز همراه بسته آمده است",
    "brief": "طبق شرحِ پروژه",
    "model card licence field + repository read on 2026-11-13 (not audited)": "فیلد مجوزِ صفحهٔ مدل و مخزن در ۲۲ آبان ۱۴۰۵ خوانده شد (حقوقی بررسی نشده)",
    "model card read on 2026-10-28 (licence line only)": "صفحهٔ مدل در ۶ آبان ۱۴۰۵ خوانده شد (فقط سطرِ مجوز)",
    "model card read on 2026-10-29 (licence section: commercial use permitted, use-based restrictions)": "صفحهٔ مدل در ۷ آبان ۱۴۰۵ خوانده شد (بخش مجوز: استفادهٔ تجاری آزاد، با محدودیت در نوعِ استفاده)",
    "nodejs.org (checksum pinned in setup_remotion.py)": "nodejs.org (هشِ فایل در برنامه ثابت شده است)",
}

# ------------------------------------------------------------------ what a model is for (`role`)
ROLE: dict[str, str] = {
    "image": "تصویر", "image + edit": "تصویر و ویرایشِ تصویر", "anime image": "تصویرِ انیمه", "video": "ویدئو", "anime video": "ویدئوی انیمه",
    "loads GGUF models in ComfyUI": "بارگذاریِ مدل‌های GGUF در ComfyUI", "speech, voice cloning": "گویندگی و شبیه‌سازیِ صدا", "ambience / SFX": "صدای محیط و جلوه‌های صوتی",
    "music": "موسیقی", "speech (CPU fallback)": "گویندگی (پشتیبانِ CPU)", "speech recognition": "تشخیصِ گفتار", "speech": "گویندگی", "mouth shapes": "حالتِ دهانِ عروسک",
    "diagrams for explainers": "نمودار برای ویدئوهای توضیحی", "upscale": "بزرگ‌نمایی", "background removal (parallax layers)": "حذفِ پس‌زمینه (لایه‌های پارالاکس)",
    "talking-head dependency": "وابستگیِ ویدئوی گویا", "assembly": "مونتاژ", "font": "فونت", "image (fast, 4 steps)": "تصویر (سریع، ۴ گام)",
    "image (split loaders)": "تصویر (بارگذارهای جدا)", "photoreal image": "تصویرِ واقع‌گرا", "pose / depth / edges control": "کنترلِ ژست، عمق و لبه",
    "consistent characters": "شخصیتِ هم‌شکل در همهٔ شات‌ها", "consistent faces": "چهرهٔ هم‌شکل", "video (text + image to video)": "ویدئو (از متن و تصویر)",
    "fast video": "ویدئوی سریع", "smoother video": "ویدئوی نرم‌تر", "speech (CPU)": "گویندگی (روی CPU)",
    "video built with code (titles, kinetic text, explainers)": "ویدئوی ساخته‌شده با کد (تیتر، متنِ متحرک، توضیحی)", "runs Remotion": "اجراکنندهٔ Remotion", "text": "متن",
}

# ------------------------------------------------------------------ VRAM / size remarks
VRAM: dict[str, str] = {
    "12 GB (fp8)": "۱۲ گیگابایت (fp8)", "to measure": "هنوز اندازه‌گیری نشده", "to measure (SDXL)": "هنوز اندازه‌گیری نشده (اندازهٔ SDXL)",
    "12 GB with fp8 + 8-step LoRA": "۱۲ گیگابایت با fp8 و LoRA هشت‌گامی", "GGUF Q4_0 ~9 GB per expert": "GGUF Q4_0 — حدود ۹ گیگابایت برای هر بخش",
    "GGUF Q4_K_M ~9.7 GB per expert": "GGUF Q4_K_M — حدود ۹٫۷ گیگابایت برای هر بخش", "-": "—", ">= 14 GB": "حداقل ۱۴ گیگابایت", "none (CPU)": "هیچ (روی CPU)",
    "CPU": "CPU", "small": "کم", "T5 fp8 about 5 GB while encoding": "T5 با fp8 هنگامِ رمزگذاری حدود ۵ گیگابایت", "7-9 GB": "۷ تا ۹ گیگابایت", "about 7 GB": "حدود ۷ گیگابایت",
    "about 2.5 GB": "حدود ۲٫۵ گیگابایت", "about 4.3 GB": "حدود ۴٫۳ گیگابایت", "FLUX fp8 + about 3 GB": "FLUX با fp8 و حدود ۳ گیگابایت", "comfortable on 12 GB": "روی ۱۲ گیگابایت راحت جا می‌شود",
    "about 4.5 GB + T5": "حدود ۴٫۵ گیگابایت + رمزگذارِ T5", "under 1 GB": "کمتر از ۱ گیگابایت", "8-9B fit 12 GB": "مدل‌های ۸ تا ۹ میلیاردی در ۱۲ گیگابایت جا می‌شوند",
    "12B fits": "مدلِ ۱۲ میلیاردی جا می‌شود", "20B offloads to RAM": "مدلِ ۲۰ میلیاردی بخشی از کار را به RAM می‌برد", "8B Q4": "مدلِ ۸ میلیاردیِ Q4",
    "12 GB (fp8; ComfyUI offloads what does not fit)": "۱۲ گیگابایت (fp8؛ آنچه جا نشود ComfyUI به حافظهٔ رایانه می‌برد)",
    "T5 fp8 about 5 GB in RAM / VRAM while encoding": "T5 با fp8 هنگامِ رمزگذاری حدود ۵ گیگابایت از حافظهٔ رایانه یا کارت می‌گیرد",
    "SDXL size (about 7 to 9 GB with the VAE)": "اندازهٔ SDXL (با VAE حدود ۷ تا ۹ گیگابایت)", "SDXL size (about 7 GB)": "اندازهٔ SDXL (حدود ۷ گیگابایت)",
    "about 4.3 GB in total": "روی هم حدود ۴٫۳ گیگابایت", "FLUX fp8 plus about 3 GB of face models": "FLUX با fp8 و حدود ۳ گیگابایت مدلِ چهره", "under 2 GB": "کمتر از ۲ گیگابایت",
    "about 10 GB (fp16) plus encoder and VAE; comfortable on 12 GB": "حدود ۱۰ گیگابایت (fp16) به‌اضافهٔ رمزگذار و VAE؛ روی ۱۲ گیگابایت راحت است",
    "about 4.5 GB + T5 encoder": "حدود ۴٫۵ گیگابایت + رمزگذارِ T5", "CPU, about 64 MB each": "روی CPU؛ هر صدا حدود ۶۴ مگابایت",
    "12 GB card: the 20 GB FP8 file is partly kept in RAM by ComfyUI; speed not measured on the RTX 3060": "روی کارتِ ۱۲ گیگابایتی: فایلِ ۲۰ گیگابایتیِ FP8 بخشی در حافظهٔ رایانه نگه داشته می‌شود (کارِ ComfyUI)؛ سرعت روی RTX 3060 اندازه‌گیری نشده",
    "~9 GB per expert (Q4_0); the high and low experts load one after the other": "حدود ۹ گیگابایت برای هر بخش (Q4_0)؛ بخشِ نویزِ بالا و پایین یکی‌یکی بارگذاری می‌شوند",
    "~9.7 GB per expert (Q4_K_M); the high and low experts load one after the other": "حدود ۹٫۷ گیگابایت برای هر بخش (Q4_K_M)؛ بخشِ نویزِ بالا و پایین یکی‌یکی بارگذاری می‌شوند",
    "SDXL size; to measure on the RTX 3060": "اندازهٔ SDXL؛ روی RTX 3060 باید اندازه‌گیری شود",
}

# ------------------------------------------------------------------ model names that contain English words (product names stay Latin)
NAME: dict[str, str] = {
    "FLUX text encoders + VAE (t5xxl fp8, clip_l, ae)": "رمزگذارهای متن و VAE برای FLUX (t5xxl fp8، clip_l، ae)",
    "Piper (engine) + voice fa_IR-gyro-medium": "موتور Piper + صدای فارسی fa_IR-gyro-medium",
    "Piper voices fa_IR amir / ganji / ganji_adabi / reza_ibrahim": "صداهای فارسیِ Piper (amir، ganji، ganji_adabi، reza_ibrahim)",
    "Vazirmatn font (UI + subtitles)": "فونت Vazirmatn (رابط و زیرنویس)", "Edge TTS (unofficial online endpoint)": "Edge TTS (سرویسِ آنلاینِ غیررسمی)",
    "Pocket-TTS (voice kit)": "Pocket-TTS (جعبه‌ابزارِ صدا)", "ComfyUI-GGUF custom node + gguf package": "گرهٔ ComfyUI-GGUF + بستهٔ gguf",
    "Wan 2.2 + anime style LoRA": "Wan 2.2 + LoRAِ سبکِ انیمه", "InsightFace detector weights": "وزن‌های آشکارسازِ InsightFace",
    "Wan 2.2 I2V A14B (fp8, high/low noise)": "Wan 2.2 I2V A14B (fp8، بخشِ نویزِ بالا و پایین)", "ControlNet Union SDXL (promax)": "ControlNet Union SDXL (promax)",
    "IP-Adapter Plus / Plus-Face (SDXL) + CLIP-ViT-H + ComfyUI_IPAdapter_plus": "IP-Adapter Plus و Plus-Face (SDXL) + CLIP-ViT-H + ComfyUI_IPAdapter_plus",
    "Wan 2.2 TI2V-5B (fp16) + Wan 2.2 VAE + umT5 encoder": "Wan 2.2 TI2V-5B (fp16) + Wan 2.2 VAE + رمزگذارِ umT5",
    "Remotion 4 (code-to-video: remotion, bundler, renderer, player)": "Remotion 4 (ساختِ ویدئو با کد: remotion، bundler، renderer، player)",
    "Node.js 24 LTS (portable zip)": "Node.js 24 LTS (نسخهٔ قابل‌حمل)", "Dorna / partai dorna-llama3 (Persian)": "Dorna / partai dorna-llama3 (فارسی)",
    "Wan 2.5 and later": "Wan 2.5 و نسخه‌های بعدی",
    "Animagine XL 4.0 Opt (anime images)": "Animagine XL 4.0 Opt (تصویرِ انیمه)",
    "Qwen-Image-Edit (consistent characters from the model sheets)": "Qwen-Image-Edit (شخصیتِ هم‌شکل از روی شیت‌های شخصیت)",
    "Gemma 3 / TranslateGemma (Ollama)": "Gemma 3 / TranslateGemma (Ollama)",
    "Stable Diffusion XL base 1.0": "Stable Diffusion XL پایه ۱٫۰",
    "FFmpeg 7.1.1 essentials build": "FFmpeg 7.1.1 (نسخهٔ essentials)", "FLUX.1 [schnell] FP8 (all-in-one checkpoint)": "FLUX.1 [schnell] FP8 (چک‌پوینتِ یک‌فایلی)",
    "LTX-Video 2B 0.9.8 distilled (FP8)": "LTX-Video 2B 0.9.8 فشرده (FP8)", "RIFE v4.25 (frame interpolation)": "RIFE v4.25 (میان‌فریم)",
    "Rhubarb Lip Sync 1.13": "Rhubarb Lip Sync 1.13", "Manim (Community)": "Manim (نسخهٔ جامعه)", "Vosk (ASR)": "Vosk (تشخیصِ گفتار)",
}

# ------------------------------------------------------------------ notes of a model / package
NOTE: dict[str, str] = {
    "Weights are non-commercial. The model card says generated outputs may be used commercially 'as described in the licence'; the full text (gated on Hugging Face) was not readable here. Owner/lawyer must read it. Fallback: Qwen-Image / Z-Image (Apache-2.0), to be benchmarked.":
        "وزن‌ها غیرتجاری است. صفحهٔ مدل می‌گوید خروجی را می‌شود «طبق متن مجوز» تجاری استفاده کرد، ولی متنِ کاملِ مجوز (پشتِ ورودِ Hugging Face) خوانده نشد؛ باید خودِ شما یا وکیلتان بخوانید. جایگزین: Qwen-Image یا Z-Image (Apache-2.0) که هنوز اندازه‌گیری نشده‌اند.",
    "Supported by the installed ComfyUI. Candidate to replace FLUX; also pose/expression editing from references.": "ComfyUIِ نصب‌شده پشتیبانی‌اش می‌کند. نامزدِ جایگزینیِ FLUX است؛ ژست و حالتِ چهره را هم از روی نمونه ویرایش می‌کند.",
    "Candidate image model; fast.": "نامزدِ مدلِ تصویر؛ سریع است.",
    "Optional download offered on the Models page (asks first, 6.9 GB). Workflow sdxl_anime_t2i (core nodes only). Anime keyframes instead of the general FLUX model; also a way around the FLUX dev weights licence question.":
        "دانلودِ اختیاری در صفحهٔ «مدل‌ها» (اول می‌پرسد؛ ۶٫۹ گیگابایت). فقط گره‌های اصلیِ ComfyUI لازم است. کلیدفریم‌های انیمه را به‌جای مدلِ عمومیِ FLUX می‌سازد و مشکلِ مجوزِ FLUX dev را هم دور می‌زند.",
    "Card: authors claim no rights over generated content; users remain responsible for lawful use. Planning estimate 8-10 GPU min per 5 s 480p shot - NOT measured.":
        "طبق صفحهٔ مدل، سازندگان بر محتوای ساخته‌شده ادعای حقی ندارند و مسئولیتِ استفادهٔ قانونی با کاربر است. برآوردِ برنامه‌ریزی: ۸ تا ۱۰ دقیقه کارتِ گرافیک برای هر شات ۵ ثانیه‌ای با کیفیت ۴۸۰ — اندازه‌گیری نشده.",
    "Use of the community GGUF conversion for generation is not retraining, but the extra clauses (legal compliance of outputs, indemnity, downstream binding) must be read by the owner. Needs the ComfyUI-GGUF custom node. Compared against plain Wan 2.2 on the same stills and seeds in Production lab > Compare. Optional download on the Models page (asks first; ~18.1 GB + the node; sha256 pinned).":
        "ساختنِ ویدئو با نسخهٔ GGUF آموزشِ دوباره حساب نمی‌شود، ولی بندهای اضافه (رعایتِ قانون در خروجی، جبرانِ خسارت، تعهدِ پایین‌دست) را باید خودِ شما بخوانید. به گرهٔ ComfyUI-GGUF نیاز دارد. در «آزمایشگاه تولید ← مقایسه» با Wan 2.2 ساده روی همان تصویرها مقایسه می‌شود. دانلودِ اختیاری در صفحهٔ «مدل‌ها» (اول می‌پرسد؛ حدود ۱۸٫۱ گیگابایت و گره؛ هشِ فایل‌ها ثابت است).",
    "Wan 2.2 I2V A14B fine-tune by AIdeaLab. The card recommends an RTX 4090 for the original weights; the community GGUF needs the ComfyUI-GGUF custom node. Comparison candidate. Optional download on the Models page (asks first; ~19.3 GB + the node; sha256 pinned).":
        "نسخهٔ تنظیم‌شدهٔ Wan 2.2 I2V A14B از AIdeaLab. صفحهٔ مدل برای وزن‌های اصلی کارتِ RTX 4090 را پیشنهاد می‌کند؛ نسخهٔ GGUF به گرهٔ ComfyUI-GGUF نیاز دارد. نامزدِ مقایسه. دانلودِ اختیاری در صفحهٔ «مدل‌ها» (اول می‌پرسد؛ حدود ۱۹٫۳ گیگابایت و گره؛ هشِ فایل‌ها ثابت است).",
    "Installed only together with an anime GGUF model, after the owner confirms. Pinned commit 6ea2651; ComfyUI must be restarted afterwards.": "فقط همراهِ یک مدلِ انیمهٔ GGUF و پس از تأییدِ شما نصب می‌شود. بعد از نصب باید ComfyUI را دوباره روشن کنید.",
    "Only if that specific LoRA's licence allows selling output. Many popular ones do not. No character/IP LoRAs.": "فقط اگر مجوزِ همان LoRA فروشِ خروجی را اجازه بدهد. بسیاری از پرطرفدارها اجازه نمی‌دهند. LoRAِ شخصیت یا مالکیتِ فکریِ دیگران استفاده نمی‌شود.",
    "EXCLUDED: the owner cannot make that representation from Iran.": "کنار گذاشته شد: شما از ایران نمی‌توانید آن اقرار را بدهید.",
    "EXCLUDED: territorial clauses and needs more VRAM than the RTX 3060.": "کنار گذاشته شد: بندهای سرزمینی دارد و حافظهٔ کارتِ بیشتری از RTX 3060 می‌خواهد.",
    "Not planned: nothing to run locally.": "برنامه‌ای برایش نیست: چیزی برای اجرا روی رایانه وجود ندارد.",
    "Best Persian narration; needs its own server (GPU).": "بهترین گویندگیِ فارسی؛ سرورِ جدای خودش را می‌خواهد (روی کارتِ گرافیک).",
    "Phase 3.": "برای ساختِ حرفه‌ای‌ترِ ویدئو.",
    "The voice licence must be checked on its model card before publishing commercially.": "پیش از انتشارِ تجاری، مجوزِ صدا را روی صفحهٔ مدلِ همان صدا بررسی کنید.",
    "Used later for subtitle timing checks.": "بعداً برای سنجشِ زمان‌بندیِ زیرنویس به کار می‌رود.",
    "AVAILABLE ON REQUEST of the owner, with a visible warning wherever it is chosen and in the QC report. Never selected automatically; do not use it for content you publish commercially.":
        "به درخواستِ شما در دسترس است و هر جا انتخاب شود (و در گزارشِ بررسیِ کیفیت) هشدارِ آشکار نشان می‌دهد. هرگز خودکار انتخاب نمی‌شود؛ برای محتوایی که تجاری منتشر می‌کنید از آن استفاده نکنید.",
    "AVAILABLE ON REQUEST of the owner, with a visible warning (needs internet; not a licensed service). Never selected automatically.": "به درخواستِ شما در دسترس است، با هشدارِ آشکار (اینترنت می‌خواهد و سرویسِ دارای مجوز نیست). هرگز خودکار انتخاب نمی‌شود.",
    "Drives puppet-2D mouths. MEASURED (dev PC): English via PocketSphinx 4.3 s for 7.1 s of speech; Persian via the phonetic recogniser 1.3 s for 6.2 s; pauses are masked by loudness because phonetic labels pauses as speech.":
        "دهانِ عروسکِ دوبعدی را حرکت می‌دهد. اندازه‌گیری‌شده (روی رایانهٔ سازنده): انگلیسی با PocketSphinx برای ۷٫۱ ثانیه گفتار ۴٫۳ ثانیه؛ فارسی با شناساگرِ آوایی برای ۶٫۲ ثانیه ۱٫۳ ثانیه؛ مکث‌ها از روی بلندیِ صدا جدا می‌شوند چون شناساگرِ آوایی مکث را گفتار می‌شمارد.",
    "Phase 3 candidate for code-rendered motion graphics (alternative: SVG/Canvas to video).": "نامزدِ ساختِ گرافیکِ متحرک با کد (جایگزین: SVG یا Canvas).",
    "Already used by NMarketing.": "NMarketing هم از آن استفاده می‌کند.",
    "EXCLUDED: check every dependency of talking-head tools.": "کنار گذاشته شد: وابستگی‌های ابزارهای ویدئوی گویا را باید یکی‌یکی بررسی کرد.",
    "Video produced with FFmpeg is not encumbered by the GPL.": "ویدئویی که با FFmpeg ساخته می‌شود زیرِ بارِ مجوزِ GPL نمی‌رود.",
    "Bundled in the repo with its licence text.": "همراهِ متنِ مجوزش در پروژه آمده است.",
    "The commercially usable FLUX; take it when the work is published.": "نسخهٔ FLUX که استفادهٔ تجاری‌اش آزاد است؛ برای کارهایی که منتشر می‌شوند همین را بردارید.",
    "For the split FLUX loaders and GGUF models.": "برای بارگذارهای جدای FLUX و مدل‌های GGUF.",
    "Commercial use allowed with use-based restrictions; the base of SDXL ControlNet / IP-Adapter.": "استفادهٔ تجاری با محدودیت در نوعِ استفاده آزاد است؛ پایهٔ ControlNet و IP-Adapterِ SDXL.",
    "A permissive photoreal SDXL checkpoint.": "یک چک‌پوینتِ واقع‌گرای SDXL با مجوزِ آزاد.",
    "Keeps a character's pose and composition across shots.": "ژست و ترکیب‌بندیِ شخصیت را در شات‌ها حفظ می‌کند.",
    "The node only runs inside ComfyUI; it is not linked into InstAI.": "گره فقط داخلِ ComfyUI اجرا می‌شود و به InstAI پیوند نمی‌خورد.",
    "Off by default; its download needs a separate confirmation because of the InsightFace weights.": "پیش‌فرض خاموش است؛ به‌خاطرِ وزن‌های InsightFace دانلودش تأییدِ جداگانه می‌خواهد.",
    "Comfy-Org repack.": "بازبسته‌بندیِ Comfy-Org.",
    "Off by default; its download needs a separate confirmation.": "پیش‌فرض خاموش است؛ دانلودش تأییدِ جداگانه می‌خواهد.",
    "The light Wan 2.2; shares the umT5 encoder with the 14B package.": "نسخهٔ سبکِ Wan 2.2؛ رمزگذارِ umT5 را با بستهٔ ۱۴ میلیاردی شریک است.",
    "Read the licence text before commercial use; off by default (needs a separate confirmation).": "پیش از استفادهٔ تجاری متنِ مجوز را بخوانید؛ پیش‌فرض خاموش است (تأییدِ جداگانه می‌خواهد).",
    "Needs a ComfyUI with the frame-interpolation nodes.": "ComfyUI باید گره‌های میان‌فریم را داشته باشد.",
    "Read each voice's card before publishing commercially.": "پیش از انتشارِ تجاری، صفحهٔ هر صدا را بخوانید.",
    "Installed from npm on the owner's PC (scripts/setup_remotion.py); nothing of Remotion is copied into this repository. OWNER: confirm that the organisation using InstAI is within the free tier, otherwise buy the Company License.":
        "روی رایانهٔ شما از مخزنِ بسته‌های جاوااسکریپت نصب می‌شود؛ چیزی از Remotion در پروژه کپی نمی‌شود. تصمیم با شماست: مطمئن شوید سازمانی که از InstAI استفاده می‌کند در بخشِ رایگانِ مجوز می‌گنجد، وگرنه «مجوز شرکتی» بخرید.",
    "Used from the PC when it is already installed, else the portable zip is unpacked into tools/node (nothing system-wide).": "اگر روی رایانه نصب باشد همان به کار می‌رود، وگرنه نسخهٔ قابل‌حمل در پوشهٔ ابزارهای پروژه باز می‌شود (چیزی در کلِ ویندوز نصب نمی‌شود).",
    "Preferred default for Persian script drafts; measure with the benchmark.": "پیش‌فرضِ ترجیحی برای پیش‌نویسِ فیلم‌نامهٔ فارسی؛ با آزمونِ سنجش اندازه‌گیری شود.",
    "Custom terms with use restrictions; read before commercial use.": "شرایطِ اختصاصی با محدودیت در نوعِ استفاده دارد؛ پیش از استفادهٔ تجاری بخوانید.",
    "Slow on 12 GB.": "روی ۱۲ گیگابایت کند است.",
    "Persian-specialised; check the licence of the exact build.": "مخصوصِ فارسی است؛ مجوزِ همان نسخه‌ای که برمی‌دارید را بررسی کنید.",
    "Adds one folder to ComfyUI\\custom_nodes and one small package to ComfyUI's Python. ComfyUI must be restarted afterwards.":
        "یک پوشه به custom_nodes برنامهٔ ComfyUI و یک بستهٔ کوچک به Python خودِ آن اضافه می‌کند. بعد از نصب باید ComfyUI را دوباره روشن کنید.",
    "Model files only. InstAI uses NMarketing's copy (models, engine code, Python environment) when model discovery finds it; see the Models page.":
        "فقط فایل‌های مدل. اگر NMarketing روی این رایانه باشد، InstAI از نسخهٔ آن (مدل‌ها، کدِ موتور و محیطِ Python) استفاده می‌کند؛ جزئیات در صفحهٔ «مدل‌ها».",
    # workflows
    "Graph from the owner's NMarketing node. If the licence is not acceptable, test Qwen-Image / Z-Image (Apache-2.0) - add a template here and compare with the same seed.":
        "گراف از گرهٔ NMarketing خودِ شما گرفته شده. اگر مجوز را نمی‌پذیرید، Qwen-Image یا Z-Image (Apache-2.0) را آزمایش کنید و با همان seed مقایسه کنید.",
    "Planning estimate from the brief: 8-10 min per 5 s shot on RTX 3060 12 GB. Measure with the benchmark.": "برآوردِ شرحِ پروژه: ۸ تا ۱۰ دقیقه برای هر شات ۵ ثانیه‌ای روی RTX 3060 با ۱۲ گیگابایت؛ با آزمونِ سنجش اندازه‌گیری شود.",
    "Same models as the I2V workflow, with ComfyUI's WanFirstLastFrameToVideo node (as the NMarketing regen tool). Estimate only.": "همان مدل‌های گردش‌کارِ I2V، با گرهٔ WanFirstLastFrameToVideoِ ComfyUI (مثلِ ابزارِ بازسازیِ NMarketing). فقط برآورد.",
    "Needs the ComfyUI-GGUF custom node. Same sampler and lightx2v LoRA as plain Wan so the comparison is like for like. UNVERIFIED graph: never run on a real ComfyUI.":
        "به گرهٔ ComfyUI-GGUF نیاز دارد. نمونه‌بردار و LoRAِ lightx2v همان Wan ساده است تا مقایسه منصفانه باشد. گرافِ آزموده‌نشده: هرگز روی ComfyUIِ واقعی اجرا نشده.",
    "Needs the ComfyUI-GGUF custom node. The model card recommends an RTX 4090 for the original weights; Q4_K_M is ~9.7 GB per expert. UNVERIFIED graph.":
        "به گرهٔ ComfyUI-GGUF نیاز دارد. صفحهٔ مدل برای وزن‌های اصلی RTX 4090 را پیشنهاد می‌کند؛ Q4_K_M برای هر بخش حدود ۹٫۷ گیگابایت است. گرافِ آزموده‌نشده.",
    "Core nodes only. The sheet is encoded and partly re-noised (denoise ~0.6) so the new keyframe keeps the character's look. Mid-confidence graph (standard img2img).":
        "فقط گره‌های اصلی. شیتِ شخصیت رمزگذاری و کمی نویزدار می‌شود تا کلیدفریمِ تازه ظاهرِ شخصیت را نگه دارد. اطمینانِ متوسط (img2imgِ استاندارد).",
    "UNVERIFIED graph written from ComfyUI's template documentation; the owner's ComfyUI has the Qwen-Image-Edit nodes but the model files must be downloaded.":
        "گرافِ آزموده‌نشده که از مستنداتِ الگوهای ComfyUI نوشته شده؛ ComfyUIِ شما گره‌های Qwen-Image-Edit را دارد ولی فایل‌های مدل باید دانلود شوند.",
    "The LoRA file name is chosen at run time (a trained character LoRA); it is not part of availability.": "نامِ فایلِ LoRA هنگامِ اجرا انتخاب می‌شود (LoRAِ آموزش‌دیدهٔ شخصیت)؛ جزوِ سنجشِ آماده‌بودن نیست.",
    "UNVERIFIED: written from ComfyUI's training-node documentation and never run. Training a 12B model on a 12 GB card may run out of memory; the job reports that plainly and the before/after numbers decide whether a LoRA helps at all.":
        "آزموده‌نشده: از مستنداتِ گرهٔ آموزشِ ComfyUI نوشته شده و هرگز اجرا نشده. آموزشِ مدلِ ۱۲ میلیاردی روی کارتِ ۱۲ گیگابایتی ممکن است حافظه کم بیاورد؛ کار همین را ساده گزارش می‌دهد و عددهای پیش و پس تصمیم می‌گیرند LoRA اصلاً کمک می‌کند یا نه.",
    "Optional download (asks first). Core ComfyUI nodes only; sampler and quality tags as the model card recommends (Euler a, CFG 5, 28 steps). Anime keyframes; NOT measured on the RTX 3060 yet.":
        "دانلودِ اختیاری (اول می‌پرسد). فقط گره‌های اصلیِ ComfyUI؛ نمونه‌بردار و برچسب‌های کیفیت طبقِ پیشنهادِ صفحهٔ مدل (Euler a، CFG 5، ۲۸ گام). کلیدفریمِ انیمه؛ هنوز روی RTX 3060 اندازه‌گیری نشده.",
    "Same models as qwen_image_edit_ref. UNVERIFIED graph (never run on a real ComfyUI): written from ComfyUI's Qwen-Image-Edit-2509 template; the text-encode node takes up to three reference images, the latent is an empty 9:16 canvas so the picture is a NEW scene with the characters of the sheets. This is the open (Apache-2.0) counterpart of IP-Adapter / PuLID-style conditioning.":
        "همان مدل‌های qwen_image_edit_ref. گرافِ آزموده‌نشده (هرگز روی ComfyUIِ واقعی اجرا نشده): از الگوی Qwen-Image-Edit-2509 نوشته شده؛ گرهٔ رمزگذارِ متن تا سه تصویرِ نمونه می‌گیرد و بوم ۹:۱۶ خالی است، پس تصویر یک صحنهٔ تازه با شخصیت‌های شیت‌هاست. جایگزینِ آزاد (Apache-2.0) برای روشِ IP-Adapter و PuLID.",
}

# ------------------------------------------------------------------ titles of packages, workflows and installer items
TITLE: dict[str, str] = {
    # packages
    "FLUX.1 [schnell] FP8, all-in-one checkpoint (fast, 4 steps)": "FLUX.1 [schnell] نسخهٔ FP8، یک‌فایلی و سریع (۴ گام)",
    "FLUX text encoders + VAE (t5xxl fp8, clip_l, ae) for the split FLUX loaders": "رمزگذارهای متن و VAE برای FLUX (t5xxl fp8، clip_l، ae) — برای بارگذارهای جدا",
    "Stable Diffusion XL base 1.0 (the reference SDXL checkpoint)": "Stable Diffusion XL پایه ۱٫۰ (چک‌پوینتِ مرجعِ SDXL)",
    "RealVisXL V4.0 (photoreal SDXL checkpoint, permissive licence)": "RealVisXL V4.0 (چک‌پوینتِ واقع‌گرای SDXL با مجوزِ آزاد)",
    "ControlNet Union SDXL (promax): pose, depth, canny, lines ... in one model": "ControlNet Union SDXL (promax): کنترلِ ژست، عمق، لبه و خط در یک مدل",
    "IP-Adapter Plus + Plus-Face (SDXL, ViT-H) + CLIP-ViT-H image encoder + the ComfyUI_IPAdapter_plus node": "IP-Adapter Plus و Plus-Face (SDXL، ViT-H) + رمزگذارِ تصویرِ CLIP-ViT-H + گرهٔ ComfyUI_IPAdapter_plus",
    "PuLID for FLUX (identity-preserving portraits) + node + EVA-CLIP + InsightFace antelopev2": "PuLID برای FLUX (حفظِ چهرهٔ شخصیت) + گره + EVA-CLIP + InsightFace antelopev2",
    "Real-ESRGAN x4plus (upscaler, BSD-3-Clause)": "Real-ESRGAN x4plus (بزرگ‌نمایی تصویر)",
    "4x-UltraSharp (sharp upscaler; NON-COMMERCIAL licence)": "4x-UltraSharp (بزرگ‌نماییِ تیزتر؛ مجوزِ غیرتجاری)",
    "Wan 2.2 TI2V-5B (text+image to video, light: fits 12 GB comfortably)": "Wan 2.2 TI2V-5B (ویدئو از متن و تصویر؛ سبک و مناسبِ ۱۲ گیگابایت)",
    "LTX-Video 2B 0.9.8 distilled FP8 (very fast video; licence 'other')": "LTX-Video 2B 0.9.8 فشرده FP8 (ویدئوی بسیار سریع؛ مجوزِ ویژه)",
    "RIFE v4.25 frame interpolation (smoother video: 2x frames)": "RIFE v4.25 (میان‌فریم برای ویدئوی نرم‌تر: دو برابر فریم)",
    "Four more Persian Piper voices (amir, ganji, ganji_adabi, reza_ibrahim; CPU, offline)": "چهار صدای فارسیِ دیگر برای Piper (amir، ganji، ganji_adabi، reza_ibrahim؛ روی CPU و بدونِ اینترنت)",
    "FLUX.1 [dev] FP8 checkpoint (~12 GB; the owner's ComfyUI usually has it already)": "FLUX.1 [dev] FP8 (حدود ۱۲ گیگابایت؛ معمولاً روی ComfyUIِ شما هست)",
    "BiRefNet-lite background removal (parallax layers, Phase 3)": "BiRefNet-lite (حذفِ پس‌زمینه برای لایه‌های پارالاکس)",
    "Animagine XL 4.0 Opt (SDXL anime still-image model, ~6.9 GB; core ComfyUI nodes only)": "Animagine XL 4.0 Opt (مدلِ تصویرِ انیمه روی SDXL، حدود ۶٫۹ گیگابایت؛ فقط با گره‌های اصلیِ ComfyUI)",
    "Qwen-Image-Edit 2509 (FP8) + Lightning 4-step: a new picture from the character model sheets (~31 GB)": "Qwen-Image-Edit 2509 (FP8) + Lightning چهارگامی: ساختِ تصویر از روی شیت‌های شخصیت (حدود ۳۱ گیگابایت)",
    "FFmpeg 7.1 static build (libass, libx264, zoompan, xfade, loudnorm); PyPI wheel first, GitHub zip as fallback": "FFmpeg 7.1 (مونتاژِ ویدئو؛ نسخهٔ ثابت با libass و libx264) — اول از PyPI، اگر نشد از گیت‌هاب",
    "Python 3.12.10 per-user installer (used only when no Python 3.10-3.13 exists)": "Python 3.12.10 (فقط وقتی هیچ Pythonِ مناسبی روی رایانه نیست؛ برای همین کاربر نصب می‌شود)",
    "Rhubarb Lip Sync 1.13.0 (mouth shapes for puppet 2D animation, Phase 3)": "Rhubarb Lip Sync 1.13.0 (حالتِ دهان برای عروسکِ دوبعدی)",
    "Wan 2.2 I2V A14B fp8 + 8-step LoRA (~36 GB; usually already on the owner's ComfyUI)": "Wan 2.2 I2V A14B (fp8) + LoRAِ هشت‌گامی (حدود ۳۶ گیگابایت؛ معمولاً روی ComfyUIِ شما هست)",
    "ComfyUI-GGUF custom node (city96, pinned commit) + the gguf Python package for ComfyUI's own Python (needed to load GGUF models)": "گرهٔ ComfyUI-GGUF + بستهٔ gguf برای Pythonِ خودِ ComfyUI (لازم برای بارگذاریِ مدل‌های GGUF)",
    "Index-AniSora V3.2 GGUF Q4_0 high+low (anime I2V candidate, ~18 GB; needs the ComfyUI-GGUF custom node)": "Index-AniSora V3.2 (GGUF Q4_0، بخشِ بالا و پایین؛ نامزدِ ویدئوی انیمه، حدود ۱۸ گیگابایت؛ به گرهٔ ComfyUI-GGUF نیاز دارد)",
    "AnimeGen I2V GGUF Q4_K_M high+low (anime I2V candidate, ~19 GB; needs the ComfyUI-GGUF custom node)": "AnimeGen I2V (GGUF Q4_K_M، بخشِ بالا و پایین؛ نامزدِ ویدئوی انیمه، حدود ۱۹ گیگابایت؛ به گرهٔ ComfyUI-GGUF نیاز دارد)",
    "Piper engine + Persian voice fa_IR-gyro-medium (CPU, offline narration fallback)": "موتورِ Piper + صدای فارسیِ fa_IR-gyro-medium (روی CPU و بدونِ اینترنت؛ گویندگیِ پشتیبان)",
    "MOSS-TTS-Realtime 1.7B + Persian LoRA + audio tokenizer (best Persian narration, ~12 GB)": "MOSS-TTS-Realtime 1.7B + LoRAِ فارسی + توکنایزرِ صدا (بهترین گویندگیِ فارسی، حدود ۱۲ گیگابایت)",
    "MOSS-SoundEffect v2.0 (ambience / SFX)": "MOSS-SoundEffect v2.0 (صدای محیط و جلوه‌های صوتی)",
    "ACE-Step 1.5 turbo (music)": "ACE-Step 1.5 turbo (موسیقیِ پس‌زمینه)",
    # workflows
    "FLUX.1 [dev] FP8 - text to image (9:16)": "FLUX.1 [dev] FP8 — تصویر از متن (۹:۱۶)",
    "Wan 2.2 I2V A14B fp8 + lightx2v 8-step (480p, <=81 frames)": "Wan 2.2 I2V A14B fp8 + lightx2v هشت‌گامی (۴۸۰p، حداکثر ۸۱ فریم)",
    "Wan 2.2 first/last frame (A14B fp8 + lightx2v 8-step): transitions and retakes": "Wan 2.2 فریمِ اول و آخر (A14B fp8 + lightx2v هشت‌گامی): گذار و بازسازیِ شات",
    "Index-AniSora V3.2 (GGUF Q4_0 high/low) - anime I2V candidate": "Index-AniSora V3.2 (GGUF Q4_0، بخشِ بالا و پایین) — نامزدِ ویدئوی انیمه",
    "AnimeGen I2V (AIdeaLab, GGUF Q4_K_M high/low) - anime I2V candidate": "AnimeGen I2V (AIdeaLab، GGUF Q4_K_M، بخشِ بالا و پایین) — نامزدِ ویدئوی انیمه",
    "FLUX.1 [dev] FP8 - keyframe from the character sheet (img2img, reference conditioning)": "FLUX.1 [dev] FP8 — کلیدفریم از روی شیتِ شخصیت (img2img با تصویرِ نمونه)",
    "Qwen-Image-Edit 2509 (4-step Lightning) - keyframe edited from the character sheet": "Qwen-Image-Edit 2509 (Lightning چهارگامی) — کلیدفریمِ ویرایش‌شده از شیتِ شخصیت",
    "FLUX.1 [dev] FP8 + a character LoRA (text to image)": "FLUX.1 [dev] FP8 + LoRAِ شخصیت (تصویر از متن)",
    "Train a character LoRA with ComfyUI's TrainLoraNode (UNVERIFIED, may not fit 12 GB)": "آموزشِ LoRAِ شخصیت با TrainLoraNodeِ ComfyUI (آزموده‌نشده؛ شاید در ۱۲ گیگابایت جا نشود)",
    "Animagine XL 4.0 Opt (SDXL anime) - text to image (9:16 close: 768x1344)": "Animagine XL 4.0 Opt (انیمهٔ SDXL) — تصویر از متن (۹:۱۶ نزدیک: ۷۶۸×۱۳۴۴)",
    "Qwen-Image-Edit 2509 (4-step Lightning) - a new picture from up to three character model sheets": "Qwen-Image-Edit 2509 (Lightning چهارگامی) — تصویرِ تازه از روی حداکثر سه شیتِ شخصیت",
    # installer items (files inside a package)
    "FLUX.1 [schnell] FP8 checkpoint (Comfy-Org repack)": "چک‌پوینتِ FLUX.1 [schnell] FP8 (بازبسته‌بندیِ Comfy-Org)", "T5-XXL text encoder, fp8 (e4m3fn)": "رمزگذارِ متنِ T5-XXL (fp8)",
    "CLIP-L text encoder": "رمزگذارِ متنِ CLIP-L", "FLUX VAE (ae.safetensors, ungated repack)": "VAEِ FLUX (ae.safetensors؛ بازبسته‌بندیِ آزاد)", "SDXL base 1.0 checkpoint": "چک‌پوینتِ SDXL پایه ۱٫۰",
    "RealVisXL V4.0 checkpoint": "چک‌پوینتِ RealVisXL V4.0", "IP-Adapter Plus SDXL (ViT-H)": "IP-Adapter Plus برای SDXL (ViT-H)", "IP-Adapter Plus Face SDXL (ViT-H)": "IP-Adapter Plus Face برای SDXL (ViT-H)",
    "CLIP-ViT-H-14 image encoder (laion2B), named as the IPAdapter node expects": "رمزگذارِ تصویرِ CLIP-ViT-H-14 (laion2B) با همان نامی که گرهٔ IPAdapter انتظار دارد",
    "ComfyUI_IPAdapter_plus custom node (cubiq) (commit a0f451a)": "گرهٔ ComfyUI_IPAdapter_plus (cubiq)", "PuLID-FLUX v0.9.1": "PuLID-FLUX v0.9.1",
    "EVA02-CLIP-L-336 (PuLID's image encoder)": "EVA02-CLIP-L-336 (رمزگذارِ تصویرِ PuLID)", "ComfyUI-PuLID-Flux custom node (balazik) (commit a80912f)": "گرهٔ ComfyUI-PuLID-Flux (balazik)",
    "Wan 2.2 TI2V 5B (fp16)": "Wan 2.2 TI2V 5B (fp16)", "Wan 2.2 VAE": "Wan 2.2 VAE", "umT5-XXL text encoder (fp8 scaled)": "رمزگذارِ متنِ umT5-XXL (fp8)",
    "LTX-Video 2B 0.9.8 distilled (fp8)": "LTX-Video 2B 0.9.8 فشرده (fp8)", "T5-XXL text encoder, fp8 scaled": "رمزگذارِ متنِ T5-XXL (fp8)", "RIFE v4.25 (ComfyUI repack)": "RIFE v4.25 (بازبسته‌بندیِ ComfyUI)",
    "FLUX.1 [dev] FP8 (Comfy-Org repack)": "FLUX.1 [dev] FP8 (بازبسته‌بندیِ Comfy-Org)", "BiRefNet-lite (AI background removal for «ادیتور عکس»)": "BiRefNet-lite (حذفِ پس‌زمینه با هوش مصنوعی برای «ادیتور عکس»)",
    "Animagine XL 4.0 Opt checkpoint (cagliostrolab)": "چک‌پوینتِ Animagine XL 4.0 Opt (cagliostrolab)", "Qwen-Image-Edit-2509 FP8 diffusion model (Comfy-Org)": "مدلِ Qwen-Image-Edit-2509 FP8 (Comfy-Org)",
    "Qwen2.5-VL 7B FP8 text encoder (Comfy-Org)": "رمزگذارِ متنِ Qwen2.5-VL 7B FP8 (Comfy-Org)", "Qwen-Image VAE (Comfy-Org)": "VAEِ Qwen-Image (Comfy-Org)",
    "Qwen-Image-Edit-2509 Lightning 4-step LoRA bf16 (lightx2v)": "LoRAِ Lightning چهارگامیِ Qwen-Image-Edit-2509 (lightx2v)",
    "FFmpeg 7.1 essentials build (Gyan, static; libass, harfbuzz, libx264) taken from the imageio-ffmpeg 0.6.0 wheel on PyPI (about 31 MB; no ffprobe)": "FFmpeg 7.1 (ساختِ ثابتِ Gyan با libass، harfbuzz و libx264) از بستهٔ imageio-ffmpeg 0.6.0 در PyPI (حدود ۳۱ مگابایت؛ بدونِ ffprobe)",
    "FFmpeg 7.1.1 essentials from GitHub (fallback; slow from Iran; ffmpeg.exe + ffprobe.exe) ": "FFmpeg 7.1.1 از گیت‌هاب (راهِ پشتیبان؛ از ایران کند است؛ شاملِ ffmpeg و ffprobe)",
    "FFmpeg 7.1.1 essentials from GitHub (fallback; slow from Iran; ffmpeg.exe + ffprobe.exe)": "FFmpeg 7.1.1 از گیت‌هاب (راهِ پشتیبان؛ از ایران کند است؛ شاملِ ffmpeg و ffprobe)",
    "Python 3.12.10 (only installed when no Python 3.12 is found; per-user, into {NM_HOME}\\python312)": "Python 3.12.10 (فقط وقتی Python 3.12 پیدا نشود؛ برای همین کاربر نصب می‌شود)",
    "Rhubarb Lip Sync 1.13.0 (Windows)": "Rhubarb Lip Sync 1.13.0 (ویندوز)",
    "Wan 2.2 I2V A14B high-noise expert, fp8_scaled (Apache-2.0)": "Wan 2.2 I2V A14B — بخشِ نویزِ بالا (fp8، Apache-2.0)",
    "Wan 2.2 I2V A14B low-noise expert, fp8_scaled (Apache-2.0)": "Wan 2.2 I2V A14B — بخشِ نویزِ پایین (fp8، Apache-2.0)",
    "umT5-XXL text encoder fp8 (shared by every Wan model, Apache-2.0)": "رمزگذارِ متنِ umT5-XXL (fp8؛ مشترکِ همهٔ مدل‌های Wan، Apache-2.0)",
    "Wan 2.1 VAE (used by Wan 2.2 A14B and Fun-InP 1.3B, Apache-2.0)": "Wan 2.1 VAE (برای Wan 2.2 A14B و Fun-InP 1.3B، Apache-2.0)",
    "lightx2v I2V 14B 480p step-distill LoRA rank64 (Kijai repack; original lightx2v, Apache-2.0)": "LoRAِ lightx2v برای I2V 14B با کیفیت ۴۸۰ (بازبسته‌بندیِ Kijai، Apache-2.0)",
    "ComfyUI-GGUF custom node (city96), commit 6ea2651 of 2026-01-12": "گرهٔ ComfyUI-GGUF (city96)", "gguf 0.19.0 (Python package the node needs), installed into ComfyUI's own Python with --no-deps": "gguf 0.19.0 (بستهٔ Pythonِ موردِ نیازِ گره، در Pythonِ خودِ ComfyUI نصب می‌شود)",
    "AniSora V3.2 high-noise expert, GGUF Q4_0": "AniSora V3.2 — بخشِ نویزِ بالا (GGUF Q4_0)", "AniSora V3.2 low-noise expert, GGUF Q4_0": "AniSora V3.2 — بخشِ نویزِ پایین (GGUF Q4_0)",
    "AnimeGen I2V high-noise expert, GGUF Q4_K_M": "AnimeGen I2V — بخشِ نویزِ بالا (GGUF Q4_K_M)", "AnimeGen I2V low-noise expert, GGUF Q4_K_M": "AnimeGen I2V — بخشِ نویزِ پایین (GGUF Q4_K_M)",
    "Piper engine (Windows x64)": "موتورِ Piper (ویندوز ۶۴ بیتی)", "Persian voice gyro (medium)": "صدای فارسیِ gyro (متوسط)", "Persian voice gyro config": "تنظیماتِ صدای فارسیِ gyro",
    "Piper voice fa_IR-amir-medium": "صدای Piper: fa_IR-amir-medium", "Piper voice fa_IR-amir-medium (settings)": "تنظیماتِ صدای Piper: fa_IR-amir-medium",
    "Piper voice fa_IR-ganji-medium": "صدای Piper: fa_IR-ganji-medium", "Piper voice fa_IR-ganji-medium (settings)": "تنظیماتِ صدای Piper: fa_IR-ganji-medium",
    "Piper voice fa_IR-ganji_adabi-medium": "صدای Piper: fa_IR-ganji_adabi-medium", "Piper voice fa_IR-ganji_adabi-medium (settings)": "تنظیماتِ صدای Piper: fa_IR-ganji_adabi-medium",
    "Piper voice fa_IR-reza_ibrahim-medium": "صدای Piper: fa_IR-reza_ibrahim-medium", "Piper voice fa_IR-reza_ibrahim-medium (settings)": "تنظیماتِ صدای Piper: fa_IR-reza_ibrahim-medium",
    "MOSS-TTS-Realtime 1.7B (speech + zero-shot cloning, Apache-2.0)": "MOSS-TTS-Realtime 1.7B (گویندگی و شبیه‌سازیِ صدا، Apache-2.0)",
    "Persian LoRA for MOSS-TTS-Realtime (Apache-2.0)": "LoRAِ فارسی برای MOSS-TTS-Realtime (Apache-2.0)", "MOSS-Audio-Tokenizer (codec for MOSS-TTS, Apache-2.0)": "MOSS-Audio-Tokenizer (کدکِ صدا برای MOSS-TTS، Apache-2.0)",
    "MOSS-SoundEffect v2.0 (ambience / sound effects, Apache-2.0)": "MOSS-SoundEffect v2.0 (صدای محیط و جلوه‌های صوتی، Apache-2.0)",
    "ACE-Step 1.5 turbo DiT + VAE + text encoder (background music, MIT; the 5Hz LM is not needed)": "ACE-Step 1.5 turbo (مدل، VAE و رمزگذارِ متن؛ موسیقیِ پس‌زمینه، MIT؛ مدلِ زبانیِ ۵ هرتزی لازم نیست)",
}

# ------------------------------------------------------------------ the services / tools the system and models pages list, provider messages and licence badges
SERVICE: dict[str, str] = {
    "NMarketing voice gateway": "دروازهٔ صدای NMarketing", "MOSS-TTS voice server": "سرورِ صدای MOSS-TTS", "ACE-Step music server": "سرورِ موسیقیِ ACE-Step",
    "MOSS-SoundEffect server": "سرورِ جلوه‌های صوتیِ MOSS-SoundEffect", "Piper (CPU)": "Piper (روی CPU)",
    # speech engines (providers/tts) and audio servers (providers/audio): the short state line
    "status=ready": "آماده است", "installed; started on demand": "نصب است؛ هنگامِ نیاز روشن می‌شود", "server ready": "سرور آماده است", "test tone": "صدای آزمایشی",
    "synthetic audio for tests": "صدای آزمایشی (فقط برای آزمون)", "edge-tts installed (needs internet)": "نصب است (اینترنت لازم دارد)",
    "MOSS-TTS is not installed (Download-Models.bat --only moss-tts) and no server URL is set": "MOSS-TTS نصب نیست و نشانیِ سرورش هم داده نشده است",
    "piper.exe not found (tools\\piper)": "Piper نصب نیست", "the edge-tts package is not installed (pip install edge-tts)": "بستهٔ edge-tts نصب نیست",
    "Pocket-TTS gateway URL not set (Settings)": "نشانیِ دروازهٔ Pocket-TTS در «تنظیمات» وارد نشده است",
    "MOSS-SoundEffect is not installed (Download-Models.bat --only moss-sfx)": "MOSS-SoundEffect نصب نیست", "ACE-Step is not installed (Download-Models.bat --only acestep)": "ACE-Step نصب نیست",
    "MIT engine; voice licence varies": "موتور: MIT؛ مجوزِ هر صدا جداست", "NON-COMMERCIAL (CC-BY-NC-4.0)": "غیرتجاری (CC-BY-NC-4.0)", "UNOFFICIAL ONLINE ENDPOINT": "سرویسِ آنلاینِ غیررسمی",
    "test audio": "صدای آزمایشی", "Apache-2.0": "Apache-2.0",
    "Persian LoRA default voice": "صدای پیش‌فرضِ فارسی (LoRA)",
    "auto = MOSS when ready, else Piper; Pocket and Edge are never chosen automatically": "خودکار = MOSS وقتی آماده است، وگرنه Piper؛ Pocket و Edge هرگز خودکار انتخاب نمی‌شوند",
}

# the anime comparison candidates (production/anime.CANDIDATES; /lab/compare)
LICENCE.update({
    "Apache-2.0 + extra restrictions that apply when retraining / making derivatives (read before commercial use)":
        "Apache-2.0 به‌علاوهٔ محدودیت‌های بیشتر برای آموزش دوباره و ساختن نسخهٔ مشتق (پیش از استفادهٔ تجاری بخوانید)",
    "Apache-2.0 (model card tag: commercial-use)": "Apache-2.0 (در کارتِ مدل «استفادهٔ تجاری» نوشته شده است)",
})
NAME.update({
    "Wan 2.2 I2V A14B (fp8 + lightx2v) - current": "Wan 2.2 I2V A14B (fp8 + lightx2v) - مدل فعلی",
    "Index-AniSora V3.2 (community GGUF Q4_0)": "Index-AniSora V3.2 (GGUF Q4_0 از جامعهٔ کاربران)",
    "AnimeGen I2V (AIdeaLab, community GGUF Q4_K_M)": "AnimeGen I2V (از AIdeaLab، GGUF Q4_K_M از جامعهٔ کاربران)",
})
NOTE.update({
    "The model the owner already uses in NMarketing.": "همان مدلی که همین حالا در NMarketing به کار می‌برید.",
    "Bilibili's anime fine-tune of Wan 2.2. Needs the ComfyUI-GGUF custom node. ~9 GB per expert.":
        "نسخهٔ انیمهٔ Wan 2.2 که شرکت Bilibili آموزش داده است. به افزونهٔ ComfyUI-GGUF نیاز دارد؛ حدود ۹ گیگابایت برای هر بخشِ مدل.",
    "Wan 2.2 I2V fine-tune for Japanese anime. Needs the ComfyUI-GGUF custom node. ~9.7 GB per expert; the card recommends an RTX 4090 for the full weights.":
        "نسخهٔ Wan 2.2 (از تصویر به ویدئو) برای انیمهٔ ژاپنی. به افزونهٔ ComfyUI-GGUF نیاز دارد؛ حدود ۹٫۷ گیگابایت برای هر بخشِ مدل؛ کارتِ مدل برای وزن‌های کامل RTX 4090 را پیشنهاد می‌کند.",
})

# one table for the walker: every text the Persian pages may show in English
ALL: dict[str, str] = {**LICENCE, **VERIFIED, **ROLE, **VRAM, **NAME, **NOTE, **TITLE, **SERVICE}
