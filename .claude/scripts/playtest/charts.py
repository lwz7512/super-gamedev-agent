"""Charts for the playtest report, drawn with Pillow so they are plain PNGs
Claude can Read and a Markdown viewer can show."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

BG = (20, 18, 36)
FG = (235, 233, 250)
MUTED = (150, 146, 190)
BAR = (255, 181, 71)
BAD = (255, 107, 139)
GOOD = (102, 214, 150)


def bars(path: Path, title: str, items: list[tuple[str, float, str]], unit: str = "", width: int = 720) -> Path:
    """Horizontal bars: (label, value 0..1 or absolute, colour key 'ok'|'bad'|'')."""
    row = 26
    h = 48 + row * max(1, len(items)) + 12
    img = Image.new("RGB", (width, h), BG)
    d = ImageDraw.Draw(img)
    d.text((14, 12), title, fill=FG)
    top = max([v for _, v, _ in items] + [1e-9])
    label_w = 220
    for i, (label, v, tone) in enumerate(items):
        y = 44 + i * row
        d.text((14, y + 5), label[:34], fill=MUTED)
        w = int((width - label_w - 90) * (v / top if top else 0))
        colour = BAD if tone == "bad" else GOOD if tone == "ok" else BAR
        d.rectangle([label_w, y + 4, label_w + max(2, w), y + row - 6], fill=colour)
        shown = f"{v:.0%}" if unit == "%" else f"{v:g}{unit}"
        d.text((label_w + max(2, w) + 8, y + 5), shown, fill=FG)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def heatmap(path: Path, title: str, points: list[tuple], viewport: tuple[int, int], background: str | None = None) -> Path:
    """Event positions as a density glow. The canvas covers the screen area
    (outlined; the screenshot goes there when given) plus wherever events
    happened, since levels are usually bigger than one screen. Points far
    outside (a body falling forever) are counted in the title, not drawn."""
    vw, vh = viewport
    near = [p for p in points if -3 * vw <= p[0] <= 4 * vw and -3 * vh <= p[1] <= 4 * vh]
    far = len(points) - len(near)
    x0, y0, x1, y1 = 0.0, 0.0, float(vw), float(vh)
    if near:
        x0, y0 = min(x0, min(p[0] for p in near) - 24), min(y0, min(p[1] for p in near) - 24)
        x1, y1 = max(x1, max(p[0] for p in near) + 24), max(y1, max(p[1] for p in near) + 24)
    s = min(1.5, 1000 / (x1 - x0), 640 / (y1 - y0))
    W, H, top = int((x1 - x0) * s), int((y1 - y0) * s), 24
    to = lambda x, y: ((x - x0) * s, (y - y0) * s + top)
    out = Image.new("RGB", (W, H + top), BG)
    sx, sy = to(0, 0)
    if background and Path(background).exists():
        shot = Image.open(background).convert("RGB").resize((int(vw * s), int(vh * s)))
        out.paste(Image.blend(shot, Image.new("RGB", shot.size, (0, 0, 0)), 0.35), (int(sx), int(sy)))
    d = ImageDraw.Draw(out)
    d.rectangle([sx, sy, sx + vw * s, sy + vh * s], outline=MUTED)
    d.text((sx + 4, sy + 3), "screen", fill=MUTED)
    # Each point adds to the layer, so places where many events land glow brighter.
    acc = Image.new("L", out.size, 0)
    r = max(5, int(min(vw, vh) * s / 40))
    for x, y, *_ in near:
        px, py = to(x, y)
        dot = Image.new("L", out.size, 0)
        ImageDraw.Draw(dot).ellipse([px - r, py - r, px + r, py + r], fill=110)
        acc = ImageChops.add(acc, dot)
    acc = acc.filter(ImageFilter.GaussianBlur(r / 2))
    out = Image.composite(Image.new("RGB", out.size, BAD), out, acc)
    d = ImageDraw.Draw(out)
    for x, y, *_ in near:
        d.point(to(x, y), fill=FG)
    d.rectangle([0, 0, W, top - 1], fill=BG)
    d.text((8, 6), f"{title}  ({len(near)} points" + (f", {far} far outside the level, not drawn" if far else "") + ")", fill=FG)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path)
    return path
