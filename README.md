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
instai/agents/                 role functions with JSON schemas, validate/repair/retry (runner.py)
instai/production/pipeline.py  what is missing -> next job (hash-based, resumable, partial regeneration)
instai/render/                 ffmpeg helpers, 2.5D camera filters, ASS subtitles, assembly, QC, placeholders
instai/gpu/arbiter.py          one heavy GPU job at a time, unload/wait logic
frontend/                      React + TS + Vite (build: python scripts/build_ui.py --force -> instai/static/app, committed)
docs/                          BRIEF, DECISIONS, MODELS (licences), BENCHMARKS
tests/                         pytest: unit, adapters vs fake servers, queue/arbiter, story flow, e2e render (needs ffmpeg), GPU smoke, UI (Playwright)
```

Dev setup: `START.bat` once (creates `.venv`), then `.venv\Scripts\python -m pip install -r requirements-test.txt` and `.venv\Scripts\python -m pytest -q`.
Demo mode (no GPU needed): Settings -> "Demo mode" (fake LLM, fake voice, placeholder images, fake research sources).
API: everything under `/api/` (see `instai/*/api.py`); errors are `{"error": {"code", "message" (Persian), "details"}}`.

Python 3.10-3.13. No secrets, models or user data in git (`.env`, `data/`, `models/`, `tools/` are ignored). Font: Vazirmatn (SIL OFL, `instai/render/fonts/OFL.txt`).
