"""Draw a PNG preview of a map folder (map.json + theme.json) to check it against the reference image.

Usage: python tools/map_preview.py maps/europa
Needs Pillow (pip install pillow). Not used by the game itself.
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 14  # hex radius in pixels


def neighbours(c, r):
    if c % 2:  # odd columns are raised half a field
        return [(c, r - 1), (c, r + 1), (c - 1, r - 1), (c - 1, r), (c + 1, r - 1), (c + 1, r)]
    return [(c, r - 1), (c, r + 1), (c - 1, r), (c - 1, r + 1), (c + 1, r), (c + 1, r + 1)]


def centre(c, r):
    return c * 1.5 * SIZE + SIZE, (r + (0 if c % 2 else 0.5)) * math.sqrt(3) * SIZE + SIZE


def main(folder):
    folder = Path(folder)
    m = json.loads((folder / "map.json").read_text(encoding="utf-8"))
    theme = json.loads((folder / "theme.json").read_text(encoding="utf-8"))
    cells = {}
    for r, line in enumerate(m["grid"]):
        for c, tok in enumerate(line.split()):
            if tok != "..":
                cells[(c, r)] = tok
    provs = m["provinces"]
    width = max(c for c, _ in cells) + 2
    height = max(r for _, r in cells) + 2
    img = Image.new("RGB", (int(width * 1.5 * SIZE + SIZE), int(height * math.sqrt(3) * SIZE)), theme["background"])
    draw = ImageDraw.Draw(img)
    for (c, r), tok in cells.items():
        if tok in provs:
            fill = theme["nation_colors"].get(provs[tok]["owner"], theme["neutral_color"])
        else:
            fill = theme["terrain"][tok]["fill"]
        x, y = centre(c, r)
        pts = [(x + SIZE * math.cos(math.radians(60 * i)), y + SIZE * math.sin(math.radians(60 * i))) for i in range(6)]
        draw.polygon(pts, fill=fill, outline=theme["hex_outline"])
    for (c, r), tok in cells.items():
        if tok not in provs:
            continue
        x0, y0 = centre(c, r)
        for n in neighbours(c, r):
            other = cells.get(n)
            if other in provs and other != tok:
                x1, y1 = centre(*n)
                mx, my, dx, dy = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
                length = math.hypot(dx, dy)
                px, py = -dy / length * SIZE / 2, dx / length * SIZE / 2
                draw.line([(mx + px, my + py), (mx - px, my - py)], fill=theme["province_border"], width=2)
    for p in provs.values():
        x, y = centre(*p["capital"])
        draw.text((x - 3, y - 6), theme["capital_icon"], fill="white")
    out = folder / "preview.png"
    img.save(out)
    print(f"{len(provs)} provinces, {len(cells)} fields -> {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "maps/europa")
