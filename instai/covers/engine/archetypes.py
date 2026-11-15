"""The "mood board": common layout patterns of clickable video covers, film posters and series art, as a short description for each layout.

The list is HAND-WRITTEN and descriptive: for each layout it says what it looks like, where it works and what not to do. Nothing was scraped from any site and no
poster or picture was copied; the preview of each layout is drawn by the cover maker itself with a made-up sample. Every pattern is tied to a layout of ``styles.STYLES``
so one click starts a cover.

SOURCE: ported from NMarketing:backend/apps/thumbs/archetypes.py @ v3.02 (c23f861), adapted for series/episode covers
(product_hero and pinterest_collage dropped; the three studio layouts added; every text in Persian and English).
"""
from __future__ import annotations

ORIGINS = {"video": ("کاورِ ویدیو", "Video covers"), "poster": ("پوستر", "Posters"), "series": ("سریال و قسمت", "Series and episodes"), "social": ("پست و استوری", "Posts and stories")}

#: style key -> the notes (the layout's own title and pattern come from ``styles.STYLES``)
NOTES: dict[str, dict] = {
    "character_face": {"origin": "video",
        "why": ("در اندازهٔ کوچکِ فهرستِ ویدیوها، چهره و کنتراست زودتر از هر چیز دیده می‌شود.", "At the small size of a video list a face and contrast are seen before anything else."),
        "dos": (["چهره را بزرگ و نزدیک بگیرید", "فقط یک کلمه را رنگی کنید", "لبهٔ سفیدِ باریک دورِ شخصیت"], ["Keep the face big and close", "Colour only one word", "A thin white edge round the character"]),
        "donts": (["جمله‌های بلند", "بیش از دو رنگِ تأکید"], ["Long sentences", "More than two accent colours"]),
        "text_rule": ("حداکثر ۴ کلمه", "At most 4 words")},
    "split_ba": {"origin": "series",
        "why": ("تغییرِ دنیای داستان را بدونِ خواندنِ متن نشان می‌دهد و کنجکاوی می‌سازد.", "It shows the change of the story world without reading and builds curiosity."),
        "dos": (["هر دو تصویر را با یک زاویه و نور بگیرید", "برچسب‌ها را کوتاه کنید"], ["Use the same angle and light for both pictures", "Keep the labels short"]),
        "donts": (["مقایسهٔ بی‌ربط"], ["An unrelated comparison"]), "text_rule": ("حداکثر ۳ کلمه به‌علاوهٔ دو برچسب", "At most 3 words plus two labels")},
    "number_list": {"origin": "series",
        "why": ("عدد جای قسمت را در سریال می‌گوید و بیننده را به دیدنِ بقیه می‌کشاند.", "The number tells where the episode sits in the series and pulls the viewer to the others."),
        "dos": (["عدد را با شمارهٔ واقعیِ قسمت یکی کنید", "عنوان را کوتاه نگه دارید"], ["Use the real episode number", "Keep the title short"]),
        "donts": (["بیش از یک عدد"], ["More than one number"]), "text_rule": ("یک عدد + ۳ تا ۵ کلمه", "One number + 3 to 5 words")},
    "question_hook": {"origin": "video",
        "why": ("مغز ناتمام‌ها را دوست ندارد؛ جوابِ سؤال فقط با دیدنِ قسمت پیدا می‌شود.", "The brain dislikes unfinished things; the answer comes only by watching the episode."),
        "dos": (["سؤالی بپرسید که قسمت واقعاً جوابش را می‌دهد"], ["Ask a question the episode really answers"]),
        "donts": (["تیترِ فریبنده که قسمت آن را برآورده نمی‌کند"], ["A misleading title the episode does not deliver"]), "text_rule": ("یک پرسشِ کوتاه", "One short question")},
    "minimal_luxury": {"origin": "series",
        "why": ("کم‌گویی نشانهٔ کیفیت است؛ برای سریال‌های آرام و هنری.", "Saying little signals quality; for calm, artistic series."),
        "dos": (["متنِ بسیار کم", "فقط یک رنگِ تأکید"], ["Very little text", "Only one accent colour"]), "donts": (["شلوغ‌کردن", "رنگ‌های جیغ"], ["Clutter", "Screaming colours"]),
        "text_rule": ("حداکثر ۵ کلمه", "At most 5 words")},
    "cinema_poster": {"origin": "poster",
        "why": ("قالبی که مخاطب با «فیلم» و «اتفاقِ مهم» پیوند می‌دهد.", "A format the viewer links with \"a film\" and \"something important\"."),
        "dos": (["عنوان کوتاه", "بلوکِ اعتبار را با نام‌های واقعی پر کنید"], ["A short title", "Fill the credits block with real names"]),
        "donts": (["تقلیدِ پوستر یا لوگوی یک فیلمِ مشخص"], ["Imitating the poster or logo of one specific film"]), "text_rule": ("عنوان ۱–۳ کلمه + جملهٔ کوتاه", "A title of 1-3 words + a short line")},
    "sticker_outline": {"origin": "social",
        "why": ("پرانرژی و دوستانه؛ در فیدِ شلوغ دیده می‌شود.", "Energetic and friendly; it stands out in a busy feed."),
        "dos": (["رنگ‌های گرم و اشباع"], ["Warm, saturated colours"]), "donts": (["برای مخاطبِ رسمی"], ["For a formal audience"]), "text_rule": ("حداکثر ۴ کلمه", "At most 4 words")},
    "neon": {"origin": "social",
        "why": ("حالِ علمی‌تخیلی، بازی و رازِ شبانه را می‌رساند.", "It carries a sci-fi, game or night-mystery mood."),
        "dos": (["حداکثر دو رنگِ نئون"], ["At most two neon colours"]), "donts": (["متنِ ریز (درخشش خوانایی را می‌خورد)"], ["Small text (the glow eats legibility)"]), "text_rule": ("حداکثر ۴ کلمه", "At most 4 words")},
    "news_bold": {"origin": "video",
        "why": ("قابِ آشنای رسانه‌ای؛ جدی و فوری به نظر می‌رسد.", "A familiar media frame; it looks serious and urgent."),
        "dos": (["تیتر را کوتاه و دقیق بنویسید"], ["Write the headline short and exact"]), "donts": (["برچسبِ «فوری» برای چیزِ غیرفوری"], ["An \"urgent\" label on something that is not"]),
        "text_rule": ("تیتر ≤ ۸ کلمه", "Headline of at most 8 words")},
    "versus": {"origin": "video",
        "why": ("مقایسه همیشه جذاب است و هر دو طرفدار کلیک می‌کنند.", "A comparison is always attractive and both fans click."),
        "dos": (["دو شخصیت با اندازهٔ برابر"], ["Two characters of the same size"]), "donts": (["جانب‌داریِ بصریِ آشکار"], ["Obvious visual bias"]), "text_rule": ("دو نام + «VS»", "Two names + \"VS\"")},
    "magazine_cover": {"origin": "poster",
        "why": ("قابِ آشنای «شمارهٔ ویژه»؛ عمق می‌سازد و موضوع را مهم نشان می‌دهد.", "The familiar \"special issue\" frame; it adds depth and makes the subject look important."),
        "dos": (["سرلوحه کوتاه", "تیترِ اصلی با یک کلمهٔ رنگی"], ["A short masthead", "A main headline with one coloured word"]),
        "donts": (["شلوغ‌کردنِ کاور با تیترهای زیاد", "تقلیدِ سرلوحهٔ یک مجلهٔ مشخص"], ["Too many headlines", "Imitating the masthead of one specific magazine"]),
        "text_rule": ("سرلوحه ≤ ۳ کلمه + دو تیتر", "Masthead of at most 3 words + two headlines")},
    "retro_poster": {"origin": "poster",
        "why": ("نوستالژی و حسِ دست‌ساز؛ در میانِ طراحی‌های دیجیتالیِ براق متمایز است.", "Nostalgia and a handmade feel; it stands out among glossy digital designs."),
        "dos": (["حداکثر ۳ رنگ", "عنوانِ کوتاه روی نوار"], ["At most 3 colours", "A short title on the ribbon"]), "donts": (["افکت‌های مدرنِ براق", "متنِ ریزِ زیاد"], ["Glossy modern effects", "Lots of small text"]),
        "text_rule": ("عنوان ≤ ۴ کلمه", "Title of at most 4 words")},
    "quote_card": {"origin": "social",
        "why": ("ساده و قابلِ ذخیره؛ جمله‌های کوتاه بیشتر به اشتراک گذاشته می‌شوند.", "Simple and easy to save; short lines get shared more."),
        "dos": (["دیالوگی که واقعاً در قسمت هست", "فضای خالیِ فراوان"], ["A line that is really in the episode", "Lots of empty space"]),
        "donts": (["نقل‌قولِ ساختگی به نامِ یک آدمِ واقعی", "متنِ بسیار بلند"], ["A made-up quote under a real person's name", "Very long text"]), "text_rule": ("جمله ≤ ۱۵ کلمه", "Line of at most 15 words")},
    "episode_card": {"origin": "series",
        "why": ("همهٔ قسمت‌ها یک شکل می‌شوند؛ بیننده شمارهٔ قسمت و نامِ سریال را در یک نگاه می‌خواند.", "Every episode looks the same; the viewer reads the episode number and the series name at a glance."),
        "dos": (["همیشه همان شخصیت و همان رنگ‌ها", "جملهٔ قلاب را از فیلم‌نامه بردارید"], ["Always the same character and colours", "Take the hook line from the script"]),
        "donts": (["شمارهٔ اشتباه", "عنوانِ بلندتر از سه خط"], ["A wrong number", "A title longer than three lines"]), "text_rule": ("نامِ سریال + عدد + عنوان ≤ ۶ کلمه", "Series name + number + title of at most 6 words")},
    "cliffhanger": {"origin": "series",
        "why": ("جمله‌ای که وسطش قطع می‌شود، بیننده را به دیدنِ قسمت (یا قسمتِ بعد) می‌کشاند.", "A line cut in the middle pulls the viewer to the episode (or the next one)."),
        "dos": (["جمله را در اوجِ کنجکاوی تمام کنید", "تاریکی و نورِ یک‌طرفه"], ["Stop the line at the peak of curiosity", "Darkness and one-sided light"]),
        "donts": (["جملهٔ فریبنده که قسمت جوابش را نمی‌دهد"], ["A teaser line the episode never answers"]), "text_rule": ("یک جملهٔ نیمه‌تمام ≤ ۸ کلمه", "One unfinished line of at most 8 words")},
    "choice_split": {"origin": "series",
        "why": ("بیننده انتخاب را می‌بیند و می‌خواهد جوابِ خودش را در نظرها بنویسد یا قسمتِ بعد را ببیند.", "The viewer sees the choice and wants to answer in the comments or watch the next part."),
        "dos": (["دو گزینهٔ هم‌وزن", "هر گزینه ۲ تا ۵ کلمه"], ["Two options of equal weight", "2-5 words per option"]), "donts": (["گزینه‌ای که آشکارا درست است"], ["An option that is obviously right"]),
        "text_rule": ("پرسش + دو گزینه", "A question + two options")},
}


def public(styles) -> list[dict]:
    """-> the notes of every layout for the API (``styles`` is ``styles.STYLES``)."""
    out = []
    for key, n in NOTES.items():
        sd = styles.get(key)
        if sd is None:
            continue
        o_fa, o_en = ORIGINS.get(n["origin"], ("", ""))
        out.append({"style": key, "origin": n["origin"], "origin_fa": o_fa, "origin_en": o_en, "why_fa": n["why"][0], "why_en": n["why"][1],
                    "dos_fa": n["dos"][0], "dos_en": n["dos"][1], "donts_fa": n["donts"][0], "donts_en": n["donts"][1],
                    "text_rule_fa": n["text_rule"][0], "text_rule_en": n["text_rule"][1], "pattern_fa": sd.pattern_fa, "pattern_en": sd.pattern_en,
                    "formats": sd.formats})
    return out
