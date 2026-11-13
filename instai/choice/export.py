"""The posting package of a choice story: every picture in posting order, the captions with the real numbers filled in, the graph map, the schedule.
Nothing is posted: the owner uploads it by hand (the app never publishes by itself)."""
from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from instai.render import fa_text

from . import graph as G
from . import services

KIND_COL = {"start": (232, 162, 43), "story": (120, 130, 150), "choice": (47, 127, 209), "ending": (46, 158, 91)}
END_COL = {"good": (46, 158, 91), "bad": (217, 74, 61), "secret": (139, 79, 209), "neutral": (107, 114, 128)}


def map_image(story, out: Path) -> Path:
    """A picture of the whole graph (columns = depth), for the owner's own overview."""
    g = story.graph
    lay = G.layout(g)
    cw, rh, bw, bh, pad = 230, 130, 150, 80, 60
    W = pad * 2 + lay["columns"] * cw
    H = pad * 2 + max(lay["rows"], 1) * rh + 40
    im = Image.new("RGB", (max(W, 600), H), (244, 241, 234))
    d = ImageDraw.Draw(im)
    fnt, small = fa_text.font(30, True), fa_text.font(20)
    pos = {i: (pad + c * cw, pad + r * rh) for i, (c, r) in lay["positions"].items()}
    idx = G.by_id(g)
    fa = story.language == "fa"
    for a, b, _c in G.edges(g):
        if a in pos and b in pos:
            x0, y0 = pos[a][0] + bw, pos[a][1] + bh / 2
            x1, y1 = pos[b][0], pos[b][1] + bh / 2
            d.line([x0, y0, x1, y1], fill=(120, 126, 140), width=3)
            ang = math.atan2(y1 - y0, x1 - x0)
            d.polygon([(x1, y1), (x1 - 14 * math.cos(ang - 0.4), y1 - 14 * math.sin(ang - 0.4)), (x1 - 14 * math.cos(ang + 0.4), y1 - 14 * math.sin(ang + 0.4))],
                      fill=(120, 126, 140))
    for nid, (x, y) in pos.items():
        n = idx[nid]
        col = END_COL.get(n.get("ending") or "neutral") if n.get("kind") == "ending" else KIND_COL.get(n.get("kind"), (120, 130, 150))
        d.rounded_rectangle([x, y, x + bw, y + bh], radius=16, fill=col, outline=(31, 36, 48), width=3)
        fa_text.draw_text(d, (x + bw / 2, y + 26), fa_text.digits_fa(n.get("number")) if fa else str(n.get("number")), fnt, (255, 255, 255), anchor="mm")
        fa_text.draw_text(d, (x + bw / 2, y + 58), (n.get("title") or "")[:18], small, (255, 255, 255), anchor="mm")
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "PNG", optimize=True)
    return out


def captions_text(story) -> str:
    fa = story.language == "fa"
    g = story.graph
    parts = []
    for n in sorted(G.nodes_of(g), key=lambda n: n.get("number") or 0):
        num = fa_text.digits_fa(n["number"]) if fa else n["number"]
        head = f"=== {'پست' if fa else 'Post'} {num} ==="
        cap = G.resolve(n.get("caption") or G.default_caption(n, g, fa=fa), g, fa=fa)
        tags = " ".join(n.get("hashtags") or [])
        parts.append("\n".join(x for x in (head, cap, tags) if x))
    return "\n\n".join(parts) + "\n"


README_EN = ("Post the pictures in number order (001, 002, ...). Each caption already contains the right post numbers.\n"
             "Release them in order; do not change the order or the numbers, because the captions point to them.\n"
             "Never published automatically: upload by hand.\n")
README_FA = ("تصویرها را به ترتیب شماره (۰۰۱، ۰۰۲، …) منتشر کنید. شمارهٔ پست‌ها در متن هر کپشن از قبل درست نوشته شده است.\n"
             "ترتیب و شماره‌ها را عوض نکنید؛ کپشن‌ها به همین شماره‌ها اشاره می‌کنند. هیچ‌چیز خودکار منتشر نمی‌شود؛ خودتان بارگذاری کنید.\n")


def build(story, image_for: dict[str, Path], out_zip: Path, work: Path) -> Path:
    """Zip: NNN.png pictures, captions.txt, schedule.csv, graph.json, map.png, README.txt. `image_for` maps node id -> rendered PNG."""
    g = story.graph
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    mp = map_image(story, work / "map.png")
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["number", "id", "local_time", "utc_time"])
    for r in services.schedule(story):
        wr.writerow([r["number"], r["id"], r["local"], r["utc"]])
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for n in sorted(G.nodes_of(g), key=lambda n: n.get("number") or 0):
            p = image_for.get(n["id"])
            if p and Path(p).exists():
                z.write(p, f"{n['number']:03d}.png")
        z.writestr("captions.txt", captions_text(story))
        z.writestr("schedule.csv", buf.getvalue())
        z.writestr("graph.json", json.dumps({"title": story.title, "language": story.language, "graph": g}, ensure_ascii=False, indent=1))
        z.write(mp, "map.png")
        z.writestr("README.txt", README_FA if story.language == "fa" else README_EN)
    return out_zip
