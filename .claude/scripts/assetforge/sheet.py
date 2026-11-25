"""Contact sheet: every asset at a glance, for Claude (and people) to look at.

Images are drawn twice, over a checkerboard (shows the alpha) and over the
game's preview background (shows how it reads in play), at a whole-number zoom
so pixel art stays sharp. Sounds are drawn as waveforms.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import audioops
import imageops
from common import ForgeError, Project, hex_rgb

CELL = 200


def _checker(w: int, h: int, s: int = 8) -> Image.Image:
    img = Image.new("RGBA", (w, h), (205, 205, 205, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, h, s):
        for x in range((y // s) % 2 * s, w, 2 * s):
            d.rectangle([x, y, x + s - 1, y + s - 1], fill=(160, 160, 160, 255))
    return img


def build(proj: Project, assets: list[dict], out: Path) -> Path:
    bg = (*hex_rgb(proj.style["art"]["preview_background"]), 255)
    pixel = proj.style["art"]["kind"] == "pixel"
    cols = 3 if len(assets) > 4 else max(1, len(assets))
    rows = (len(assets) + cols - 1) // cols or 1
    sheet = Image.new("RGBA", (cols * (2 * CELL + 12) + 12, rows * (CELL + 34) + 12), (14, 13, 26, 255))
    d = ImageDraw.Draw(sheet)
    for i, a in enumerate(assets):
        x0 = 12 + (i % cols) * (2 * CELL + 12)
        y0 = 12 + (i // cols) * (CELL + 34)
        path = proj.root / a["path"]
        label = f"{a['id']}"
        if not path.exists():
            d.rectangle([x0, y0, x0 + 2 * CELL, y0 + CELL], outline=(255, 107, 139, 255))
            d.text((x0 + 8, y0 + 8), "not produced", fill=(255, 107, 139, 255))
        elif a.get("kind", "image") == "image":
            img = imageops.load(path)
            s = min(CELL / img.width, CELL / img.height)
            if pixel and s >= 1:
                s = int(s)
            tw, th = max(1, int(img.width * s)), max(1, int(img.height * s))
            big = img.resize((tw, th), Image.Resampling.NEAREST if pixel else Image.Resampling.LANCZOS)
            for j, back in enumerate((_checker(CELL, CELL), Image.new("RGBA", (CELL, CELL), bg))):
                back.alpha_composite(big, ((CELL - tw) // 2, (CELL - th) // 2))
                sheet.alpha_composite(back, (x0 + j * CELL, y0))
            label += f"  {img.width}x{img.height}"
        else:
            try:
                samples, rate = audioops.read_wav(path)
                wf = audioops.waveform_png(samples, rate, out.parent / f".wave-{a['id']}.png", a["id"], (2 * CELL, CELL))
                (out.parent / f".wave-{a['id']}.png").unlink(missing_ok=True)
                sheet.alpha_composite(wf.convert("RGBA"), (x0, y0))
            except ForgeError as e:
                d.text((x0 + 8, y0 + 8), f"cannot read: {e}"[:60], fill=(255, 181, 71, 255))
        d.text((x0, y0 + CELL + 6), f"{label}  [{a.get('status', 'planned')}]", fill=(235, 233, 250, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
