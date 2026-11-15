"""Three cover layouts written for this studio, through exactly the same ``StyleDef`` / ``Ctx`` API as the ported ones (so they can be copied back to NMarketing later):

* ``episode_card``  - the series name, a big episode-number badge and the hook line (the everyday cover of an episode);
* ``cliffhanger``   - a dark scene, a spot-lit character and a headline that is cut off at its end ("to be continued");
* ``choice_split``  - an A / B choice poster for ``instai.choice`` stories: the question on top, two halves, a letter disc and a choice plate on each.

Every function only takes a ``Ctx``. The shared helpers of ``styles`` are imported inside the functions (``styles`` imports this module last).
"""
from __future__ import annotations

from PIL import Image, ImageChops

from . import palette as pm
from . import primitives as P
from . import shapes as S
from . import typo
from .render import Ctx
from .typo import TextStyle


def _st():
    from . import styles

    return styles


def _fade_end(c: Ctx, frac: float = 0.5):
    """A ``post`` function for ``Ctx.text``: the LAST line of the block dissolves over the last ``frac`` of its width, towards the end of the reading
    direction (left in Persian, right in English) - a headline that is cut off in the dark."""
    def post(img: Image.Image, blk) -> Image.Image:
        import numpy as np

        w, h = img.size
        n = max(1, blk.lines)
        y0 = max(0, int(blk.origin[1] + blk.nominal[1] * (n - 1) / n - blk.nominal[1] * 0.04))
        alpha = img.getchannel("A")
        ink = alpha.crop((0, y0, w, h)).point(lambda v: 255 if v > 10 else 0).getbbox()
        if not ink:
            return img
        bx0, bx1 = ink[0], ink[2]
        span = max(1.0, (bx1 - bx0) * frac)
        xs = np.arange(w, dtype=np.float32)
        t = np.clip((xs - bx0) / span, 0.0, 1.0) if c.rtl else np.clip((bx1 - xs) / span, 0.0, 1.0)
        t = t * t * (3.0 - 2.0 * t)
        ramp = np.ones((h, w), dtype=np.float32)
        ramp[y0:, :] = t[None, :]
        a = (np.asarray(alpha, dtype=np.float32) * ramp).clip(0, 255).astype("uint8")
        out = img.copy()
        out.putalpha(Image.fromarray(a))
        return out
    return post


# ───────────────────────────── 1. episode card

def episode_card(c: Ctx) -> None:
    st = _st()
    p = c.pal
    W, H = c.W, c.H
    wide = c.orient == "wide"
    z = c.zones(sub_frac=0.42, text_h=0.62, overlap=0.04)
    tr, sr, side = z["text"], z["subject"], z["side"]
    cx, cy = (sr[0] + sr[2]) / 2, sr[1] + (sr[3] - sr[1]) * 0.52
    if c.bg_wants_photo():
        c.bg_photo(darken=0.38, saturate=1.15, vign=0.4)
        c.scrim(tr, 0.52)
    else:
        c.bg_gradient(62, [(0.0, p.bg1), (1.0, p.bg2)])
        band = P.polygon_mask(c.size, [(0, H * 0.60), (W, H * 0.44), (W, H * 0.56), (0, H * 0.72)] if not wide else [(W * 0.50, 0), (W * 0.62, 0), (W * 0.44, H), (W * 0.32, H)])
        c.add("slanted band", "fx", P.solid(c.size, p.accent2, band, 0.30))
        c.texture("halftone", color="#ffffff", alpha=0.13, spacing=24, direction=45)
    c.add("subject glow", "fx", P.glow_blob(c.size, (cx, cy), max(sr[2] - sr[0], sr[3] - sr[1]) * 0.62, p.accent2, 0.55))
    img, cut = c.subject_rgba()
    if img is None:
        st._fallback_hero(c, sr)
    elif cut:
        c.put_cutout("subject", img, sr, valign="bottom", scale=0.97, outline="#ffffff" if c.spec["subject"]["outline"] else None, ow=c.u(11),
                     glow=(p.accent, c.u(22), 0.45))
        st._arrow_accent(c, sr, side)
    else:
        c.put_photo("subject photo", img, sr, fade=st._fade_side(c, side), extent=0.4, focus=(0.5, 0.3))
    has_num = c.has("number") or c.has("badge")
    th_ = max(1.0, tr[3] - tr[1])
    rad = min(c.W * (0.105 if wide else 0.14), (tr[2] - tr[0]) * 0.24, th_ * 0.34)
    k_f = min(0.16, 0.06 * c.W / th_) if c.has("kicker") else 0.0
    d_f = (2.25 * rad / th_) if has_num else 0.0
    rest = max(0.3, 1.0 - k_f - d_f)
    items = c.stack(tr, [("kicker", k_f), ("_disc", d_f), ("title", rest * 0.68), ("subtitle", rest * 0.32)])
    al = st._text_align(c)
    if "kicker" in items:
        st._kicker(c, items["kicker"], align=al, px=0.034)
    if "_disc" in items and has_num:
        r = items["_disc"]
        start_x = (r[2] - rad) if c.rtl else (r[0] + rad)
        if c.orient != "wide":
            start_x = (r[0] + r[2]) / 2.0
        center = c.clear_of_avoid((start_x, (r[1] + r[3]) / 2.0), rad)
        c.center_add("episode badge", "badge", S.circle(rad, fill=p.accent, ring=p.ink, ring_w=c.u(8), shadow=True), center)
        c.center_add("badge ring", "shape", S.ring(rad * 0.88, c.u(3), pm.on(p.accent), 0.5, dash=True), center)
        word = c.word("episode") if c.has("number") else ""
        num = c.content.get("number") or c.content.get("badge")
        ink = pm.on(p.accent)
        shift = rad * 0.16 if word else 0.0
        c.text("number", num, (center[0] - rad * 0.9, center[1] - rad * 0.95 + shift, center[0] + rad * 0.9, center[1] + rad * 0.95 + shift),
               TextStyle(fill=ink, font_key="lalezar", weight=400, align="center", line_gap=1.0), max_lines=1, min_f=0.03, max_f=0.3, avoid=False, ink_center=True)
        if word:
            c.text("badge word", word, (center[0] - rad * 0.62, center[1] - rad * 0.80, center[0] + rad * 0.62, center[1] - rad * 0.42),
                   TextStyle(fill=ink, font_key="sahel", weight=800, align="center"), max_lines=1, min_f=0.012, max_f=0.04, avoid=False, ink_center=True)
        # a rule from the disc to the end of the row
        rule_w = max(0.0, (r[2] - r[0]) - rad * 2.5)
        if rule_w > c.u(30) and c.orient == "wide":
            rx = (center[0] - rad * 1.25 - rule_w) if c.rtl else (center[0] + rad * 1.25)
            c.add("rule", "accent", P.solid((int(rule_w), max(3, int(c.u(5)))), p.accent), (rx, center[1] - c.u(2)))
    if "title" in items:
        c.text("title", c.content["title"], items["title"], st._title_style(c, align=al), max_lines=3, max_f=0.15 if wide else 0.13, ax=al, ay="middle")
    if "subtitle" in items:
        c.text("subtitle", c.content["subtitle"], items["subtitle"], st._sub_style(c, align=al), max_lines=2, max_f=0.055, ax=al, ay="top")
    c.finish(vign=0.28)


# ───────────────────────────── 2. cliffhanger

def cliffhanger(c: Ctx) -> None:
    st = _st()
    p = c.pal
    W, H = c.W, c.H
    wide = c.orient == "wide"
    z = c.zones(sub_frac=0.5, text_h=0.40, overlap=0.0)
    tr, sr, side = z["text"], z["subject"], z["side"]
    if not wide:                                  # tall / square: the character in the upper part (its chest sinks into the dark), the headline below it
        sh_ = c.safe[3] - c.safe[1]
        sr = (0.0, c.safe[1], float(W), c.safe[1] + sh_ * 0.68)
    cx = (sr[0] + sr[2]) / 2
    cy = sr[1] + (sr[3] - sr[1]) * 0.42
    deep = P.lerp_hex(p.bg1, "#000000", 0.55)
    if c.bg_wants_photo():
        c.bg_photo(darken=0.62, saturate=0.85, vign=0.7)
        c.scrim(tr, 0.45)
    else:
        c.add("background", "background", P.radial(c.size, (cx, cy), max(W, H) * 0.85, [(0.0, P.lerp_hex(p.bg2, "#000000", 0.30)), (1.0, deep)]))
    # a cone of light falls from above on the character
    cone_w = (sr[2] - sr[0]) * 0.42
    cone = P.polygon_mask(c.size, [(cx - c.u(34), 0), (cx + c.u(34), 0), (cx + cone_w, sr[3]), (cx - cone_w, sr[3])])
    c.add("light cone", "fx", P.solid(c.size, "#ffffff", P.blur_alpha(cone, c.u(26)), 0.15))
    c.add("spot light", "fx", P.glow_blob(c.size, (cx, cy), max(sr[2] - sr[0], sr[3] - sr[1]) * 0.55, "#ffffff", 0.22))
    c.add("fog", "fx", P.glow_blob(c.size, (cx, sr[3] * 0.97), max(W, H) * 0.5, p.accent2, 0.30))
    img, cut = c.subject_rgba()
    if img is None:
        st._fallback_hero(c, sr, accent=p.accent2, alt=p.accent)
    elif cut:
        c.put_cutout("subject", img, sr, valign="bottom", scale=0.95, outline=None, ow=0, shadow=False, glow=(p.accent2, c.u(28), 0.40), rim=p.accent)
    else:
        c.put_photo("subject photo", img, sr, fade=st._fade_side(c, side), extent=0.4, focus=(0.5, 0.3))
    # the lower part sinks into darkness so the headline reads
    c.add("bottom shade", "fx", P.solid(c.size, "#000000", P.edge_ramp(c.size, "bottom", 0.55 if not wide else 0.35, 0.0, 1.0), 0.88))
    if not wide:
        tr = (c.safe[0], c.safe[1] + (c.safe[3] - c.safe[1]) * 0.60, c.safe[2], c.safe[3])
    items = c.stack(tr, [("kicker", 0.12), ("title", 1.0), ("subtitle", 0.34)])
    al = st._text_align(c)
    if "kicker" in items:
        st._kicker(c, items["kicker"], bg=p.accent2, fg=pm.on(p.accent2), align=al, px=0.032, slant=0.2)
    title = c.content.get("title", "")
    if typo.plain(title) and not typo.plain(title).rstrip().endswith(("…", "...", "؟", "?")):
        title = title.rstrip(" .،,") + "…"
    if "title" in items:
        c.text("title", title, items["title"], st._title_style(c, align=al, stroke_w=0.07, line_gap=1.02), max_lines=3, max_f=0.15 if wide else 0.125,
               ax=al, ay="middle", post=_fade_end(c, 0.5))
    tbc = c.content.get("subtitle") or c.word("tbc")
    lab = typo.label(tbc, int(c.W * 0.036), font_key="sahel", weight=800, fill=pm.on(p.accent), bg=p.accent, slant=0.18)
    if lab is not None:
        r = items.get("subtitle") or (tr[0], tr[3] - lab.height - c.u(8), tr[2], tr[3])
        x = (r[2] - lab.width) if al == "right" else ((r[0] + r[2]) / 2 - lab.width / 2 if al == "center" else r[0])
        c.add("to be continued", "badge", lab, (x, r[3] - lab.height))
    c.finish(grain_amount=0.02, vign=0.5)


# ───────────────────────────── 3. A / B choice

def choice_split(c: Ctx) -> None:
    st = _st()
    p = c.pal
    W, H = c.W, c.H
    x0, y0, x1, y1 = c.safe
    wide = c.orient == "wide"
    ia, ca = c.subject_rgba(1)
    ib, cb = c.subject_rgba(2)
    col_a = P.lerp_hex(p.accent2, p.bg1, 0.30)
    col_b = P.lerp_hex(p.accent, p.bg1, 0.55)
    slant = int((W if wide else H) * 0.035)
    th = (y1 - y0) * (0.34 if wide else 0.2)                         # the question band
    if wide:
        mask_a = P.polygon_mask(c.size, [(0, 0), (W / 2 + slant, 0), (W / 2 - slant, H), (0, H)])
        rect_a, rect_b = (x0, y0 + th, W / 2 - slant * 1.4, y1), (W / 2 + slant * 1.4, y0 + th, x1, y1)
    else:
        mask_a = P.polygon_mask(c.size, [(0, 0), (W, 0), (W, H / 2 - slant), (0, H / 2 + slant)])
        rect_a, rect_b = (x0, y0 + th, x1, H / 2 - slant * 1.2), (x0, H / 2 + slant * 1.2, x1, y1)
    if c.rtl and wide:                                               # in Persian "A" (الف) is on the right, where reading starts
        mask_a = mask_a.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        rect_a, rect_b = (W - rect_b[2], rect_b[1], W - rect_b[0], rect_b[3]), (W - rect_a[2], rect_a[1], W - rect_a[0], rect_a[3])
    base = P.gradient(c.size, [(0.0, P.lerp_hex(col_b, p.bg1, 0.25)), (1.0, col_b)], 50).convert("RGBA")
    base.paste(P.gradient(c.size, [(0.0, col_a), (1.0, P.lerp_hex(col_a, p.bg1, 0.4))], 50).convert("RGBA"), (0, 0), mask_a)
    c.add("split background", "background", base)
    c.texture("rays", color="#ffffff", alpha=0.07, center=(W / 2, H / 2), n=20)
    # the divider and the OR disc
    line = ([(W / 2 + slant, 0), (W / 2 - slant, H)] if wide else [(0, H / 2 + slant), (W, H / 2 - slant)])
    if c.rtl and wide:
        line = [(W - line[0][0], line[0][1]), (W - line[1][0], line[1][1])]
    m = P.aa_mask(c.size, lambda d, k: d.line([(x * k, y * k) for x, y in line], fill=255, width=int(c.u(10) * k)))
    div, off = P.stylized(m, "#ffffff", glow=(p.accent, c.u(14), 0.8))
    c.add("divider", "accent", div, (-off[0], -off[1]))
    for key, rect, col, img, cut, letter in (("a", rect_a, col_a, ia, ca, c.word("letter_a")), ("b", rect_b, col_b, ib, cb, c.word("letter_b"))):
        rw, rh = rect[2] - rect[0], rect[3] - rect[1]
        disc_r = min(rw, rh) * 0.15
        plate_h = rh * 0.26
        corner_left = rect[0] < W / 2 if wide else True            # the disc sits in an outer top corner so the character keeps the height
        center = ((rect[0] + disc_r * 1.3) if corner_left else (rect[2] - disc_r * 1.3), rect[1] + disc_r * 1.3)
        subj_rect = (rect[0], rect[1] + disc_r * 0.6, rect[2], rect[3] - plate_h * 0.7)
        if img is not None and cut:
            c.put_cutout(f"subject {key}", img, subj_rect, valign="bottom", scale=0.96, outline="#ffffff", ow=c.u(9), glow=(col, c.u(22), 0.55))
        elif img is not None:
            c.put_photo(f"subject photo {key}", img, (subj_rect[0] + c.u(14), subj_rect[1], subj_rect[2] - c.u(14), subj_rect[3]), radius=c.u(24), border="#ffffff", bw=c.u(7), shadow=True)
        else:
            st._fallback_hero(c, subj_rect, accent=col if key == "b" else "#ffffff", alt="#ffffff" if key == "b" else p.accent)
        c.center_add(f"letter disc {key}", "badge", S.circle(disc_r, fill="#ffffff", ring=p.ink, ring_w=c.u(6), shadow=True), center)
        c.text(f"letter {key}", letter, (center[0] - disc_r * 0.7, center[1] - disc_r * 0.62, center[0] + disc_r * 0.7, center[1] + disc_r * 0.62),
               TextStyle(fill=p.ink if col is col_a else P.lerp_hex(p.ink, col_b, 0.2), font_key="lalezar", weight=400, align="center"), max_lines=1, min_f=0.02, max_f=0.14, avoid=False)
        label = c.content.get(f"label_{key}")
        if typo.plain(label or ""):
            plate = (rect[0] + rw * 0.04, rect[3] - plate_h, rect[2] - rw * 0.04, rect[3] - plate_h * 0.05)
            c.text(f"choice {key}", label, plate, TextStyle(fill="#ffffff", hl=p.accent, auto_hl=False, font_key="sahel", weight=800, align="center", line_gap=1.12,
                                                            plate=("#05070d", 0.22, 0.28), shadow=(0.0, 0.03, 0.03, "#000000", 0.35)), max_lines=2, max_f=0.06, ay="middle")
    mid = (W / 2, H / 2)
    c.center_add("or disc", "accent", S.circle(c.u(48), fill=p.accent, ring="#ffffff", ring_w=c.u(6), shadow=True), mid)
    c.text("or", c.word("or"), (mid[0] - c.u(38), mid[1] - c.u(26), mid[0] + c.u(38), mid[1] + c.u(26)),
           TextStyle(fill=pm.on(p.accent), font_key="lalezar", weight=400, align="center"), max_lines=1, min_f=0.02, max_f=0.07, avoid=False)
    # the question band
    bh = int(th + y0)
    grad = Image.new("RGBA", (W, bh), (5, 7, 13, 255))
    grad.putalpha(P.edge_ramp((W, bh), "top", 1.0, 0.0, 0.9).point(lambda v: int(v * 0.85)))
    c.add("title scrim", "fx", grad, (0, 0))
    items = c.stack((x0, y0, x1, y0 + th), [("kicker", 0.3), ("title", 1.0), ("subtitle", 0.34)])
    if "kicker" in items:
        c.text("top label", c.content["kicker"], items["kicker"], TextStyle(fill=p.accent, font_key="sahel", weight=800, align="center"), max_lines=1, min_f=0.02, max_f=0.036, ay="bottom")
    if "title" in items:
        c.text("title", c.content["title"], items["title"], st._title_style(c, align="center", auto_hl=True), max_lines=2, max_f=0.11, ay="middle")
    if "subtitle" in items:
        c.text("subtitle", c.content["subtitle"], items["subtitle"], st._sub_style(c, align="center"), max_lines=1, max_f=0.045, ay="top")
    c.finish(vign=0.25)


def build(StyleDef) -> list:
    """The three StyleDef rows (the class is passed in because ``styles`` imports this module while it is being defined)."""
    return [
        StyleDef("episode_card", "کارتِ قسمت", "Episode card", "نامِ سریال، شمارهٔ بزرگِ قسمت و جملهٔ قلاب", "Series name, a big episode number and the hook line",
                 "کاورِ هر قسمت: نامِ سریال بالا، یک نشانِ گردِ بزرگ با شمارهٔ قسمت، عنوانِ درشتِ قسمت و جملهٔ قلابِ فیلم‌نامه زیرش؛ شخصیتِ ثابتِ سریال کنارِ متن. با همین قالب همهٔ قسمت‌ها یکدست می‌شوند.",
                 "The everyday cover of an episode: the series name on top, a big round badge with the episode number, a bold episode title and the script's hook line below; the series' fixed character next to the text. The same layout keeps every episode consistent.",
                 episode_card, "vivid", "lalezar", "series", "recommended",
                 [("kicker", "نامِ سریال", "Series name"), ("number", "شمارهٔ قسمت", "Episode number"), ("title", "عنوانِ قسمت", "Episode title"),
                  ("subtitle", "جملهٔ قلاب (از فیلم‌نامه)", "Hook line (from the script)"), ("badge", "نشانِ جایگزین (اگر شماره ندارید)", "Badge text (when there is no number)")],
                 ["youtube", "aparat", "telegram", "story", "ig_portrait", "ig_square", "poster", "season_card"],
                 tips=[("نامِ سریال را در برچسبِ بالا و جملهٔ قلاب را در زیرعنوان بگذارید.", "Put the series name in the top label and the hook line in the subtitle.")], origin="instai"),
        StyleDef("cliffhanger", "پایانِ معلق", "Cliffhanger", "صحنهٔ تاریک، شخصیتِ نورافکن‌خورده، عنوانِ نیمه‌تمام", "A dark scene, a spot-lit character, a cut-off headline",
                 "برای قسمتی که با یک پرسشِ بی‌پاسخ تمام می‌شود: زمینهٔ تقریباً سیاه، مخروطِ نور از بالا روی شخصیت، و عنوانی که آخرِ خطش در تاریکی محو می‌شود، با برچسبِ «ادامه دارد…».",
                 "For an episode that ends on an unanswered question: an almost black scene, a cone of light from above on the character and a headline whose last line fades into the dark, with a \"to be continued...\" label.",
                 cliffhanger, "dark", "lalezar", "series", "recommended",
                 [("kicker", "نامِ سریال / شمارهٔ قسمت", "Series name / episode number"), ("title", "جملهٔ معلق (نیمه‌تمام)", "The hanging line (unfinished)"),
                  ("subtitle", "برچسبِ پایین (پیش‌فرض: ادامه دارد…)", "Bottom label (default: TO BE CONTINUED...)")],
                 ["youtube", "aparat", "telegram", "story", "ig_portrait", "ig_square", "poster", "season_card"],
                 tips=[("جمله را همان‌جا که کنجکاوی اوج می‌گیرد تمام نکنید؛ نقطه‌چین خودکار می‌آید.", "Stop the line where curiosity peaks; the dots come by themselves.")], origin="instai"),
        StyleDef("choice_split", "پوستر انتخاب A / B", "A / B choice poster", "پرسش بالا، دو نیمه، حرفِ هر گزینه", "The question on top, two halves, a letter for each option",
                 "برای داستانِ انتخابی (instai.choice): پرسش در بالا، دو نیمه با دو رنگِ متضاد، دیسکِ حرفِ «الف / ب» و برچسبِ هر گزینه، و دیسکِ «یا» در مرکز؛ هر دو شخصیتِ گزینه‌ها می‌توانند بیایند.",
                 "For a choice story (instai.choice): the question on top, two halves in two contrasting colours, a letter disc and a plate for each option and an \"OR\" disc in the middle; the characters of both options may appear.",
                 choice_split, "vivid", "lalezar", "series", "optional",
                 [("kicker", "برچسبِ بالا (پیش‌فرض: خالی)", "Top label (default: empty)"), ("title", "پرسش", "The question"), ("subtitle", "نامِ داستان", "Story name"),
                  ("label_a", "گزینهٔ الف", "Option A"), ("label_b", "گزینهٔ ب", "Option B")],
                 ["youtube", "ig_square", "ig_portrait", "story", "telegram", "aparat", "season_card"], True,
                 tips=[("گزینه‌ها کوتاه باشند (۲ تا ۵ کلمه) تا روی برچسب جا شوند.", "Keep the options short (2-5 words) so they fit on the plates.")], origin="instai"),
    ]
