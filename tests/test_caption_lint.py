"""Caption lint and hashtag repair (0.16), ported from NMarketing's caption_guard / hashtags tests and adapted: arithmetic rules only, warnings only, never a rewrite; the shop's
«never say» list and the price reminders are gone; the platform limits are notes labelled approximate; every warning has Persian AND English text."""
from __future__ import annotations

import re

from instai.publishing import caption_lint, fatext, hashtags
from instai.publishing.caption_lint import check

FA = re.compile(r"[؀-ۿ]")


def codes(caption="", tags=None, **kw):
    return [w["code"] for w in check(caption, tags, **kw)]


# ------------------------------------------------------------------------------------------------------------------------------ the rules

def test_a_clean_caption_has_no_warnings():
    assert check("قسمت دوم: اگر ایران یک روز زودتر انیمیشن می‌ساخت چه می‌شد؟ پایان باز، فردا ادامه دارد.", ["انیمیشن", "#سریال_کوتاه"]) == []


def test_a_number_that_lost_its_zeros_is_flagged():
    assert "broken_number" in codes("۵۰ سکه = ۶۰۰٬۰۰ تومان")
    assert "broken_number" in codes("50 coins = 600,00 toman")
    assert "broken_number" not in codes("۵۰ سکه = ۶۰۰٬۰۰۰ تومان")
    assert "broken_number" not in codes("ساعت ۱۹:۳۰ و نسخهٔ ۲.۵")


def test_the_same_line_twice_is_flagged_next_to_each_other_or_apart():
    assert "repeated" in codes("قسمت بعد را ببین. لینک در بایو. لینک در بایو")
    assert "repeated" in codes("لینک قسمت بعد در بایو است.\nامروز داستان تازه‌ای داریم که ادامه می‌دهیم.\nلینک قسمت بعد در بایو است.")
    assert "repeated" not in codes("قسمت بعد را ببین. لینک در بایو. نظرتان را بنویسید")
    assert "repeated" not in codes("بله. بله. بله")                                  # a connective is not a copy-paste


def test_an_instruction_for_the_image_model_is_flagged():
    assert "image_prompt" in codes("یک دختر زیر باران، vertical 9:16, clean composition")
    assert "image_prompt" in codes("a hero at dawn, highly detailed, masterpiece")
    assert "image_prompt" in codes("پرامپت: بدون آدم، فقط فضای شهر")
    assert "image_prompt" in codes("نمای کلوز از چهرهٔ قهرمان")
    assert "image_prompt" not in codes("قهرمان ما در شهر ۹ تا ۱۶ ساله‌ها زندگی می‌کند")


def test_emoji_count_and_an_unfinished_sentence_are_flagged():
    assert "emoji" in codes("😀" * 8) and "emoji" not in codes("😀" * 6)
    long_open = "این یک متن بلند است که برای آزمایش نوشته شده و باید به‌اندازهٔ کافی طولانی باشد تا بررسی ناتمام‌بودن روی آن اجرا شود و در میانهٔ یک جمله"
    assert len(long_open) > 120 and "truncated" in codes(long_open) and "truncated" not in codes(long_open + ".") and "truncated" not in codes(long_open + " 🎬")
    assert "truncated" not in codes("کوتاه و ناتمام")                                  # short texts are not judged


def test_every_warning_is_reported_once_and_has_both_languages():
    out = check("۶۰۰٬۰۰ تومان. ۶۰۰٬۰۰ تومان", ["سریالکوتاه", "سریالکوتاه"])
    assert [w["code"] for w in out].count("broken_number") == 1
    for w in out:
        assert w["level"] in ("warn", "note") and w["message"] and w["message_en"] and FA.search(w["message"])
    assert not FA.search(check("x" * 10 + " 600,00", [])[0]["message_en"])


def test_the_caption_is_never_rewritten():
    text = "۶۰۰٬۰۰ تومان!!  و  دوباره ۶۰۰٬۰۰ تومان"
    tags = ["سریالکوتاه", "#بله"]
    before = (text, list(tags))
    out = check(text, tags)
    assert (text, tags) == before and isinstance(out, list) and all(set(w) == {"code", "level", "message", "message_en"} for w in out)


# ------------------------------------------------------------------------------------------------------------------------------ hashtags

def test_glued_hashtags_are_repaired_with_everyday_words_and_the_pages_own_words():
    assert hashtags.repair("سریالکوتاه") == "سریال_کوتاه"
    assert hashtags.repair("#انیمیشنایرانی") == "#انیمیشن_ایرانی"
    assert hashtags.repair("PDFآموزشی") == "PDF_آموزشی"
    assert hashtags.repair("ماجراجویی") == "ماجراجویی" and hashtags.repair("هوش_مصنوعی") == "هوش_مصنوعی" and hashtags.repair("مرغابی") == "مرغابی"
    assert hashtags.repair("خرسکوچولو") == "خرسکوچولو"                                # «خرس» is not an everyday word of the list: left as written
    vocab = hashtags.words_of("خرس کوچولوی ما", "#پلنگ_صورتی")
    assert hashtags.repair("خرسکوچولوی", vocab) == "خرس_کوچولوی" and "پلنگ" in vocab


def test_the_fitness_words_of_the_store_product_are_not_in_this_list():
    """NMarketing's list was written for a coaching app; here «برنامه + ورزشی» is not split because «ورزشی» is not an everyday word of an animation channel."""
    assert hashtags.repair("برنامهورزشی") == "برنامهورزشی"


def test_parse_clean_and_the_long_unexplained_tag():
    assert hashtags.parse(["a", " b ", "", 3]) == ["a", "b"] and hashtags.parse("#یک #دو،سه") == ["#یک", "#دو"] and hashtags.parse("سریال کوتاه, انیمیشن") == ["سریال کوتاه", "انیمیشن"]
    assert hashtags.clean("# هوش  مصنوعی") == "هوش_مصنوعی"
    assert hashtags.repair_all("#سریالکوتاه #ماجراجویی") == ["#سریال_کوتاه", "#ماجراجویی"]
    assert hashtags.is_glued("کلمهیناشناختهبسیاربلند") is True and hashtags.is_glued("هوش_مصنوعی") is False and hashtags.is_glued("ماجراجویی") is False


def test_the_lint_reports_glued_and_duplicate_tags_with_the_repaired_form():
    out = check("متن", ["سریالکوتاه", "کلمهیناشناختهبسیاربلند", "بله", "#بله"])
    glued = [w for w in out if w["code"] == "glued_hashtag"]
    assert len(glued) == 2 and "سریال_کوتاه" in glued[0]["message"] and "سریال_کوتاه" in glued[0]["message_en"] and "«_»" in glued[1]["message"]
    assert "duplicate_hashtag" in [w["code"] for w in out]
    assert "glued_hashtag" not in codes("متن", ["هوش_مصنوعی", "سریال_کوتاه"])


# ------------------------------------------------------------------------------------------------------------------------------ approximate limits

def test_instagram_limits_are_notes_labelled_approximate():
    long_caption = "متن. " * 500
    out = {w["code"]: w for w in check(long_caption, [f"t{i}" for i in range(35)], networks=["ig_reel"])}
    assert out["ig_caption_long"]["level"] == "note" and out["ig_tags_many"]["level"] == "note"
    assert "تقریبی" in out["ig_caption_long"]["message"] and "approximate" in out["ig_caption_long"]["message_en"] and "2200" not in out["ig_tags_many"]["message_en"]
    assert "30" in out["ig_tags_many"]["message_en"] and "2200" in out["ig_caption_long"]["message_en"]
    assert "ig_caption_long" not in codes(long_caption, [], networks=["telegram", "yt_wide"])           # the limit applies to Instagram's family only


def test_youtube_limits_title_description_and_tags():
    out = {w["code"]: w for w in check("د" * 5200, ["a" * 40] * 15, networks=["yt_wide"], title="ع" * 120)}
    assert {"yt_title_long", "yt_description_long", "yt_tags_long"} <= set(out) and all(w["level"] == "note" for w in out.values() if w["code"].startswith("yt_"))
    assert "100" in out["yt_title_long"]["message_en"] and "5000" in out["yt_description_long"]["message_en"] and "500" in out["yt_tags_long"]["message_en"]
    assert not [c for c in codes("کوتاه", ["الف"], networks=["yt_shorts"], title="عنوان") if c.startswith("yt_")]
    assert not [c for c in codes("د" * 5200, [], networks=["ig_reel"]) if c.startswith("yt_")]


def test_text_helpers_are_the_comparison_form_only():
    assert fatext.en_digits("۱۲۳٤") == "1234" and fatext.fa_digits("12") == "۱۲"
    assert fatext.normalize("جايگزينِ  مربي ٪ ٩٨") == fatext.normalize("جایگزین مربی ٪ ۹۸") and caption_lint.LIMITS["instagram"] == {"caption": 2200, "tags": 30}
