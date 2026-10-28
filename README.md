# InstAI

A local, single-user production system for **animated video series for a content page** (Instagram first): plan the strategy, series, episodes,
script and storyboard with an LLM, render 9:16 episodes (stills with 2.5D camera motion + Persian narration + burned-in Persian subtitles today;
Wan video, puppet 2D and lip-sync in Phase 3), review and approve everything, export a package for manual upload.
Separate product from NMarketing (`Qasem`); it never runs on a server. Full brief: [`docs/BRIEF.md`](docs/BRIEF.md). Working rules: [`CLAUDE.md`](CLAUDE.md).

Status: **Phase 0 and Phase 1 complete, Phase 2 foundation built** (job queue, GPU arbiter, ComfyUI/TTS adapters, FFmpeg assembly). Everything is tested
with fake providers; real GPU behaviour is measured by the benchmark on the owner's machine (see [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)).

---

## راه‌اندازی و آزمایش روی رایانهٔ GPUدار (فارسی)

> این بخش را فقط یک‌بار دنبال کنید. به هیچ دستور خط فرمانی نیاز نیست.

**۱. گرفتن برنامه**
- با گیت: `git clone https://github.com/maniUZqqz/Instai` (مخزن خصوصی است؛ با حساب گیت‌هاب وارد شوید)، یا در صفحهٔ گیت‌هاب «Code ← Download ZIP» و بعد از حالت فشرده خارج کنید.
- پوشه را هر جا خواستید بگذارید (حتی اگر در نامش فاصله یا پرانتز باشد).

**۲. اجرا: روی `START.bat` دو بار کلیک کنید**
- بار اول چند دقیقه طول می‌کشد (اینترنت لازم است): اگر پایتون مناسب نباشد خودش نسخهٔ ۳٫۱۲ را فقط برای همین کاربر نصب می‌کند، محیط مجزا می‌سازد، بسته‌ها را نصب می‌کند، ابزار ffmpeg را (حدود ۳۰ مگابایت) می‌گیرد، پایگاه داده را آماده می‌کند، یک **چک‌لیست** کوتاه چاپ می‌کند و مرورگر را باز می‌کند.
- چک‌لیست نشان می‌دهد چه چیزی پیدا شد: کارت گرافیک، Ollama، ComfyUI، ffmpeg، موتورهای صدا. «[--]» یعنی پیدا نشد (خطا نیست؛ فقط آن بخش کار نمی‌کند).
- دفعه‌های بعد چند ثانیه طول می‌کشد. برای خاموش کردن: `STOP.bat`.
- اگر پرسید «Run the benchmark now» (فقط بار اول روی رایانهٔ GPUدار): **Y** را بزنید تا زمان واقعیِ ساخت تصویر، ویدئو، صدا و فیلم‌نامه روی همین رایانه اندازه‌گیری شود (حدود ۳۰ دقیقه). بعداً هم از صفحهٔ «سیستم» ممکن است.

**۳. پیش از آزمایش: Ollama و ComfyUI را روشن کنید** (همان‌هایی که برای NMarketing دارید). بعد در برنامه:
1. صفحهٔ **تنظیمات**: «حالت آزمایشی» باید **خاموش** باشد (در حالت آزمایشی خروجی ساختگی است). مدل Ollama را انتخاب کنید و «آزمون اتصال» را بزنید. اگر می‌خواهید از API (مثل MetisAI) استفاده کنید نشانی، مدل و کلید را همان‌جا بدهید؛ کلید فقط در فایل `.env` می‌ماند و جایی نمایش داده نمی‌شود.
2. صفحهٔ **سیستم**: آنچه پیدا شده را ببینید (GPU، مدل‌ها، گردش‌کارهای ComfyUI که آماده‌اند).
3. اگر مدل‌های Wan/FLUX در ComfyUI شما نیستند: در تنظیمات «بسته‌های اختیاری» یا `Download-Models.bat` (فایل‌های موجود در ComfyUI دوباره دانلود نمی‌شوند؛ مسیر ComfyUI را در تنظیمات بدهید).

**۴. آزمایش گام‌به‌گام**
1. «صفحهٔ جدید» ← قالب (انیمه «اگر…» / شخصیت کارتونی / توضیح مفاهیم) ← مراحل ← «پیشنهاد استراتژی» را بزنید، ویرایش و ساخت صفحه.
2. در «سازندهٔ مجموعه»: «ساخت طرح با هوش مصنوعی» ← طرح ۵ قسمتی را ویرایش و اعمال کنید.
3. در «ویرایشگر قسمت»: فیلم‌نامه ← تأیید ← استوری‌بورد (هر شات تکنیک و زمان GPUِ برآوردی دارد) ← «ساخت پیش‌نمایش» (ارزان و سریع) ← تماشا ← «ساخت نسخهٔ نهایی».
4. «پایش تولید»: صف، پیشرفت، گزارش و دکمهٔ لغو/تلاش دوباره؛ اگر برنامهٔ دیگری GPU را گرفته باشد «GPU مشغول» می‌بینید و کار منتظر می‌ماند.
5. «انتشار»: بستهٔ خروجی (ویدئو، کاور، کپشن، هشتگ) برای بارگذاری دستی. هیچ‌چیز خودکار منتشر نمی‌شود.

**۴ب. مسیر استودیویی (نسخهٔ جدید): از ایده تا قسمت، مثل یک استودیوی واقعی**

> هوش مصنوعی خدمهٔ ماست و شما کارگردانید: هر مرحله پیشنهاد می‌دهد، شما ویرایش می‌کنید و تأیید می‌زنید. هیچ‌چیز خودکار منتشر نمی‌شود. شرح کاملِ این روند و منبع‌های آن: [`docs/STUDIO_PIPELINE.md`](docs/STUDIO_PIPELINE.md).

1. **کتابخانه** (منوی کنار): بیش از ۴۰ سبک آماده (واقعی، شبیه انیمه، انیمهٔ تلویزیونی و دههٔ نود، شونن، آبرنگ، کارتون غربی، سه‌بعدی، خمیری، مینیاتور ایرانی…) و ۱۶ تم (رنگ، نور، حال‌وهوا، تایپوگرافی). از هر کدام «کپی» بگیرید و ویرایشش کنید، سبک تازه بسازید، صادر یا وارد کنید. «قالب‌ها» مسیر توسعهٔ مجموعه را تعیین می‌کنند (سه قالب اولیه + قالب‌های خودتان).
2. **صفحهٔ جدید:** قالب ← زبان‌ها (فارسی، انگلیسی یا هر دو) ← ظاهر (سطح واقع‌نمایی، سبک و تم) ← سطح خودکارسازی و «قفل پیش‌تولید». زبان رابط (فارسی/EN) از دکمهٔ بالای صفحه عوض می‌شود و به یاد می‌ماند.
3. **مجموعه ← اتاق توسعه** (برای «چه می‌شد اگر…»):
   - **سریال منبع:** نام سریال را بنویسید و «جست‌وجو» را بزنید (AniList و ویکی‌پدیا)؛ یکی را انتخاب کنید. اگر اینترنت کند یا بسته بود، «ورود دستی» همیشه هست.
   - **پژوهش کانن:** شخصیت‌ها، کمان‌ها، رویدادها و قواعد جهان از روی متنِ منبع، هرکدام با شمارهٔ منبع.
   - **ایده‌پردازی نقطهٔ انشعاب:** هوش مصنوعی ایده می‌دهد و شما هم اضافه می‌کنید؛ هر ایده را ویرایش، امتیازدهی، ادغام، رد یا تأیید کنید و «بیشتر شبیه این» بخواهید.
   - **نقشهٔ پیامدها و خط زمانی جایگزین** ← **کتاب سریال** (ویرایش و تأیید؛ شخصیت‌ها به صفحه اضافه می‌شوند) ← **ساختار قسمت‌ها** ← **تأیید نهایی توسعه**.
   - برای «شخصیت تکرارشونده» و «توضیح مفاهیم» مرحله‌های خودشان را دارند (یادداشت طراحی شخصیت، سناریو و شوخی؛ ایده‌پردازی موضوع، پژوهش با منبع، قیاس و راستی‌آزمایی).
4. **قسمت ← تب «پیش‌تولید»:** فیلم‌نامه ← استوری‌بورد ← **انیماتیک** (ویدئوی سریع با زمان‌بندی و گفتار آزمایشی) ← **برگه‌های طراحی** (شیت شخصیت، حالت‌های چهره، پس‌زمینه، اسکریپت رنگ) ← **انتخاب صدا** ← **تأیید نهایی**؛ بعد تولید شروع می‌شود. شاتِ ایراددار را با «درخواست بازسازی» (یادداشت کارگردان) فقط همان یکی را دوباره بسازید. «ترجمهٔ قسمت» متن را به زبان دیگر می‌برد.
5. **مدل متنی هر صفحه:** تنظیمات صفحه ← تولید ← «مدل متنی»: برای هر دسته کار (ایده‌پردازی، پژوهش، کتاب سریال، فیلم‌نامه، ترجمه) سرویس و مدل جدا بدهید (مثلاً ایده‌پردازی با API و فیلم‌نامه با Ollama) و یک مدل جایگزین.
6. **سطح خودکارسازی** (در تنظیمات صفحه) تعیین می‌کند کدام تأییدها با شماست: «دستی» همه، «نیمه‌خودکار» کتاب سریال، ساختار قسمت‌ها، استوری‌بورد و تأییدهای نهایی، «خودکار» فقط تأییدهای نهایی. انتشار در هر سطح دستی می‌ماند.

**۵. آزمون GPU (اختیاری):** روی `Test-GPU.bat` دو بار کلیک کنید؛ می‌گوید GPU دیده شد، مدل محلی فیلم‌نامهٔ فارسیِ معتبر نوشت، یک تصویر ساخته شد، یک جمله خوانده شد و حافظهٔ GPU آزاد شد. هر سرویسی که روشن نباشد «skipped» می‌شود.

**۶. اگر مشکلی بود:** به ما بگویید چه دیدید و این‌ها را بفرستید: متن چک‌لیست START.bat، فایل `data\logs\instai.log`، و گزارش بنچمارک (صفحهٔ «سیستم» ← دانلود گزارش). چیزی پاک نمی‌شود؛ پایگاه داده و رسانه‌ها در پوشهٔ `data` هستند.

**چه چیزی هنوز ساختگی/ناتمام است:** در «حالت آزمایشی» همه‌چیز ساختگی است. در حالت واقعی: تصویرِ کلیدی با ComfyUI و صدا با MOSS/Piper واقعی‌اند ولی روی GPU شما هنوز اندازه‌گیری نشده‌اند (تا بنچمارک اجرا نشود، زمان‌ها «برآورد» نامیده می‌شوند). انیمیشن پاپت دوبعدی، همگام‌سازی لب، پارالکس واقعی، ویدئوی Wan با ثبات شخصیت و QC پیشرفته فاز ۳ هستند؛ شات‌هایی با این تکنیک‌ها فعلاً با حرکت دوربین روی تصویر ساخته می‌شوند و در گزارش کیفیت همین ذکر می‌شود.

---

## For developers (English)

```
START.bat / STOP.bat           start/stop server + worker (self-checking; English console)
Download-Models.bat            manifest downloader (manifests/*.json; default set = ffmpeg + Piper)
Test-GPU.bat                   GPU smoke test (pytest -m gpu) - skips what is not running
instai/                        Django project: core (settings, hardware, benchmark), pages, story, assets, jobs, publishing
instai/providers/              Ollama, OpenAI-compatible, fake text providers; ComfyUI client + versioned graph templates; TTS adapters
instai/agents/                 role functions with JSON schemas, validate/repair/retry (runner.py); studio_roles.py (development + pre-production roles),
                               llm.py (text model per page and task group, with fallback)
instai/styles/                 style & theme library: 44 built-in styles, 16 themes, user copies, export/import, prompt composition
instai/studio/                 development room (templates, brainstorm boards, canon research, series bible, gates), pre-production
                               (animatic, design sheets, casting, retakes, translation) and their jobs
instai/research_series.py      real-series lookup: AniList / Wikipedia / Fandom (/ Jikan, off by default), manual entry always possible
instai/production/pipeline.py  what is missing -> next job (hash-based, resumable, partial regeneration)
instai/render/                 ffmpeg helpers, 2.5D camera filters, ASS subtitles, assembly, QC, placeholders
instai/gpu/arbiter.py          one heavy GPU job at a time, unload/wait logic
frontend/                      React + TS + Vite (build: python scripts/build_ui.py --force -> instai/static/app, committed)
                               texts: src/i18n/fa.ts + en.ts + src/i18n/packs/*.ts (a workstream adds its own pack file; tests/test_i18n.py checks both languages)
docs/                          BRIEF, DECISIONS, MODELS (licences), BENCHMARKS, STUDIO_PIPELINE (how real studios work -> InstAI stages)
tests/                         pytest: unit, adapters vs fake servers, queue/arbiter, story flow, e2e render (needs ffmpeg), GPU smoke, UI (Playwright)
```

Dev setup: `START.bat` once (creates `.venv`), then `.venv\Scripts\python -m pip install -r requirements-test.txt` and `.venv\Scripts\python -m pytest -q`.
Demo mode (no GPU needed): Settings -> "Demo mode" (fake LLM, fake voice, placeholder images, fake research sources).
API: everything under `/api/` (see `instai/*/api.py`); errors are `{"error": {"code", "message", "details"}}` - Persian, or English when the request has `X-Lang: en` (the UI sends it).
Local checks of the render path on a PC without START.bat's ffmpeg: install `imageio-ffmpeg` in the venv and set `INSTAI_FFMPEG_EXE` to its binary (absolute path); UI tests find an already installed chromium (or `INSTAI_UI_CHROMIUM`).

Python 3.10-3.13. No secrets, models or user data in git (`.env`, `data/`, `models/`, `tools/` are ignored). Font: Vazirmatn (SIL OFL, `instai/render/fonts/OFL.txt`).
