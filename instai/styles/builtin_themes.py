"""Built-in themes: colour palette (background, primary, secondary, accent, shadow, highlight), lighting, mood and title/subtitle typography."""
from __future__ import annotations

from .schema import normalize_theme


def _th(key, names, descs, pal, light, mood, frag, neg, typo, tags) -> tuple[str, dict]:
    return key, normalize_theme({"name_fa": names[0], "name_en": names[1], "description_fa": descs[0], "description_en": descs[1], "palette": pal,
                                 "lighting": light, "mood": mood, "prompt_fragment": frag, "negative_fragment": neg, "typography": typo, "tags": tags})


def _ty(weight="bold", case="normal", anim="fade", color="#FFFFFF", outline="#000000", pos="bottom", box=0.0, size=64) -> dict:
    return {"title_weight": weight, "title_case": case, "title_animation": anim, "subtitle_color": color, "subtitle_outline": outline,
            "subtitle_position": pos, "subtitle_box_opacity": box, "subtitle_size": size}


BUILTIN_THEMES: dict[str, dict] = dict([
    _th("warm_sunset", ("غروب گرم", "Warm sunset"), ("نارنجی و طلایی با سایه‌های بنفش ملایم.", "Orange and gold with soft violet shadows."),
        ["#2B1B2D", "#E4572E", "#F3A712", "#FFD166", "#3D2645", "#FFF1D6"], "low golden-hour sun, long soft shadows", "warm, hopeful",
        "warm golden hour palette, orange and amber highlights, soft violet shadows", "cold blue cast, harsh midday light",
        _ty(anim="pop", outline="#3D2645"), ["warm"]),
    _th("cool_midnight", ("نیمه‌شبِ سرد", "Cool midnight"), ("آبی و بنفشِ شب با روشنایی‌های کوچک و گرم.", "Night blues and violets with small warm lights."),
        ["#0B1026", "#26408B", "#6C5CE7", "#FFB86B", "#04060F", "#DDE6FF"], "moonlight with small warm practical lights", "quiet, introspective",
        "cool midnight palette, deep blue and violet, small warm window lights, moonlit rim light", "overexposed, harsh daylight",
        _ty(anim="fade", color="#EAF0FF", outline="#04060F"), ["cool", "night"]),
    _th("pastel_dream", ("رؤیای پاستلی", "Pastel dream"), ("صورتی، نعنایی و بنفش روشن با درخشش نرم.", "Pink, mint and light lavender with a soft glow."),
        ["#FFF7FB", "#F7A8C4", "#A8E6CF", "#C3B1E1", "#8C7AA9", "#FFFFFF"], "soft diffused bloom", "gentle, dreamy",
        "soft pastel palette, pink mint and lavender, airy bloom, low contrast", "harsh contrast, dark murky colours",
        _ty(anim="fade", color="#FFFFFF", outline="#8C7AA9", box=0.0), ["pastel", "soft"]),
    _th("earthy_natural", ("خاکی و طبیعی", "Earthy natural"), ("قهوه‌ای، سبز زیتونی و کرم؛ حس دست‌ساز و طبیعی.", "Browns, olive greens and cream; natural and handmade."),
        ["#F2E8D5", "#6B8E4E", "#A47148", "#D9A441", "#3E2F23", "#FFFDF6"], "soft natural daylight", "grounded, organic",
        "earthy natural palette, olive green, clay brown and cream, natural materials", "neon colours, synthetic gloss",
        _ty(weight="regular", anim="fade", color="#FFFDF6", outline="#3E2F23"), ["earth", "natural"]),
    _th("mono_noir", ("تک‌رنگ نوآر", "Mono noir"), ("سیاه، خاکستری و سفید با یک رنگ برجسته‌ی کوچک.", "Black, grey and white with one small accent colour."),
        ["#0A0A0B", "#3A3A40", "#8B8B93", "#C0392B", "#000000", "#F5F5F5"], "hard single-source light, deep shadows", "tense, austere",
        "monochrome palette, deep blacks and bright whites, one small red accent", "colourful, pastel, low contrast",
        _ty(weight="black", case="upper", anim="slide", outline="#000000", pos="bottom", box=0.45), ["bw", "contrast"]),
    _th("retro_sepia", ("سپیای قدیمی", "Retro sepia"), ("کاغذ کهنه، قهوه‌ای و رنگ‌های کمرنگ‌شده.", "Aged paper, browns and faded colours."),
        ["#EBDDC1", "#7A5C3E", "#B5483A", "#D9B44A", "#2E2118", "#FFF8E8"], "flat vintage light with slight halation", "nostalgic, warm",
        "faded vintage palette, sepia browns, aged paper tone, slight film grain", "modern neon, pure white, clean digital",
        _ty(weight="bold", anim="typewriter", color="#FFF8E8", outline="#2E2118"), ["vintage"]),
    _th("vivid_pop", ("پاپِ پرانرژی", "Vivid pop"), ("رنگ‌های اشباع و شاد با کنتراست بالا.", "Saturated cheerful colours with high contrast."),
        ["#FFF4D6", "#E63946", "#1D7DEA", "#FFD60A", "#1B1B3A", "#FFFFFF"], "bright high-contrast light", "energetic, bold",
        "vivid saturated palette, primary colours, high contrast, bold shapes", "muted, desaturated, grey",
        _ty(weight="black", anim="pop", outline="#1B1B3A", size=68), ["pop", "bold"]),
    _th("cyber_teal_magenta", ("سبزآبی و سرخابیِ آینده", "Cyber teal & magenta"), ("نئون‌های سبزآبی و سرخابی روی شب تیره.", "Teal and magenta neons on a dark night."),
        ["#0A0F1F", "#12E2D5", "#FF2E97", "#FFD23F", "#05060F", "#E6F9FF"], "neon rim light with haze", "electric, futuristic",
        "teal and magenta neon palette, dark blue night, glowing rim light, haze", "daylight, pastel, natural green",
        _ty(weight="black", case="upper", anim="slide", color="#E6F9FF", outline="#FF2E97", box=0.0), ["neon", "scifi"]),
    _th("forest_mist", ("مه‌ی جنگل", "Forest mist"), ("سبزهای نرم و مه‌آلود با نور سرد صبح.", "Soft misty greens with cool morning light."),
        ["#E4EFE7", "#3F7D58", "#8FB9A8", "#F2C879", "#1F3B2C", "#FFFFFF"], "cool morning light through mist", "serene, fresh",
        "misty forest palette, soft greens and teal, cool morning light, gentle haze", "dry desert, harsh sunlight, red tones",
        _ty(weight="regular", anim="fade", outline="#1F3B2C"), ["nature", "calm"]),
    _th("candy_bright", ("آب‌نباتی شاد", "Candy bright"), ("رنگ‌های میوه‌ای و شاد برای محتوای کودکانه.", "Fruity cheerful colours for kid-friendly content."),
        ["#FFFBE6", "#FF6F61", "#4DD0E1", "#FFEB3B", "#5D4037", "#FFFFFF"], "bright flat light", "joyful, playful",
        "candy bright palette, strawberry red, sky cyan and lemon yellow, clean and cheerful", "dark, gritty, desaturated",
        _ty(weight="black", anim="pop", outline="#5D4037", size=70), ["kids", "bright"]),
    _th("royal_gold", ("طلایی سلطنتی", "Royal gold"), ("آبی سرمه‌ای، قرمز یاقوتی و طلا؛ حس شکوه.", "Navy, ruby red and gold; a sense of grandeur."),
        ["#101B3D", "#8E1B2B", "#C9A227", "#E9D8A6", "#070C1F", "#FFF8E1"], "warm candlelit glow with gold accents", "regal, dramatic",
        "royal palette, deep navy, ruby red and metallic gold accents, ornate", "neon, pastel, flat plastic",
        _ty(weight="bold", anim="fade", color="#FFF3C4", outline="#101B3D"), ["gold", "classic"]),
    _th("ocean_calm", ("آرامش اقیانوسی", "Ocean calm"), ("آبی، فیروزه‌ای و سفید با حس تمیز و خنک.", "Blue, aqua and white with a clean cool feel."),
        ["#F2FAFF", "#1E88E5", "#26C6DA", "#FFB74D", "#0D3B66", "#FFFFFF"], "clean bright daylight", "clean, trustworthy",
        "ocean palette, clean blues and aqua, white highlights, small warm orange accent", "muddy, brown, dark red",
        _ty(weight="bold", anim="slide", outline="#0D3B66"), ["blue", "clean"]),
    _th("winter_frost", ("یخبندانِ زمستانی", "Winter frost"), ("آبی یخی، خاکستریِ نقره‌ای و درخشش سرد.", "Icy blue, silver grey and a cold glimmer."),
        ["#EAF3F9", "#7FB3D5", "#B8C6DB", "#F7D794", "#34495E", "#FFFFFF"], "cold overcast light with sparkle", "crisp, still",
        "winter frost palette, icy blue and silver grey, cold glimmer, soft snow light", "warm sunset, tropical colours",
        _ty(weight="regular", anim="fade", outline="#34495E"), ["cold", "winter"]),
    _th("persian_turquoise", ("فیروزه و لاجورد ایرانی", "Persian turquoise & lapis"), ("فیروزه‌ای، لاجوردی، زعفرانی و طلایی با الهام از کاشی‌کاری.", "Turquoise, lapis, saffron and gold inspired by tile work."),
        ["#F6EBD3", "#16808D", "#1E3A8A", "#E3A008", "#0F2A3A", "#FFF8E1"], "even warm light like a sunlit courtyard", "poetic, ornate",
        "turquoise and lapis lazuli palette with saffron and gold accents, tile-work inspired colours", "neon, grey, muddy",
        _ty(weight="bold", anim="fade", color="#FFF8E1", outline="#0F2A3A"), ["persian", "ornate"]),
    _th("desert_dusk", ("غروبِ کویر", "Desert dusk"), ("نارنجی سوخته، صورتیِ خاکی و آسمان بنفش.", "Burnt orange, dusty pink and a purple sky."),
        ["#3B2F4A", "#D1603D", "#E8A87C", "#F6D55C", "#241B2F", "#FFF1E0"], "low sun with long warm shadows", "vast, calm",
        "desert dusk palette, burnt orange, dusty pink and violet sky, long warm shadows", "green lush, cold blue",
        _ty(weight="bold", anim="fade", outline="#241B2F"), ["warm", "desert"]),
    _th("sakura_spring", ("بهارِ شکوفه", "Sakura spring"), ("صورتی کم‌رنگ، سبز تازه و آبی آسمانی.", "Pale pink, fresh green and sky blue."),
        ["#FFF5F7", "#F4A6C0", "#8CCB9B", "#8ECAE6", "#6B5B95", "#FFFFFF"], "bright airy spring light", "fresh, tender",
        "spring palette, pale pink blossoms, fresh green and sky blue, airy light", "dark, autumn browns",
        _ty(weight="regular", anim="fade", outline="#6B5B95"), ["spring", "soft"]),
])
