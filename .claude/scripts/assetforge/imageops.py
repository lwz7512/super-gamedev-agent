"""Images: background keying, fitting, palette lock, frame strips, measurements.

Generators rarely hand back a game-ready sprite: the background is baked in
(OpenArt documents no transparent output, so prompts ask for a flat key colour),
some fake transparency with a grey checkerboard, sizes are 1024 px, and
"pixel art" arrives as blurry blocks in 200 colours. These functions turn that
into the exact size, alpha and palette the style lock asks for.
"""

from __future__ import annotations

from collections import Counter, deque
from pathlib import Path

from PIL import Image

from common import hex_rgb


def load(path: Path) -> Image.Image:
    img = Image.open(path)
    img.load()
    return img.convert("RGBA")


def dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def has_real_alpha(img: Image.Image) -> bool:
    lo, hi = img.getchannel("A").getextrema()
    return lo < 250 and hi > 5


def border_pixels(img: Image.Image, step: int = 1):
    w, h = img.size
    px = img.load()
    for x in range(0, w, step):
        yield px[x, 0]
        yield px[x, h - 1]
    for y in range(0, h, step):
        yield px[0, y]
        yield px[w - 1, y]


def checker_colours(img: Image.Image) -> list[tuple] | None:
    """Two light greys alternating along the border: a baked 'transparency' checkerboard."""
    border = [p[:3] for p in border_pixels(img, step=max(1, img.size[0] // 256))]
    common = Counter((c[0] // 8, c[1] // 8, c[2] // 8) for c in border).most_common(2)
    if len(common) < 2 or common[0][1] + common[1][1] < 0.85 * len(border):
        return None
    cols = [tuple(v * 8 + 4 for v in c) for c, _ in common]
    grey = all(max(c) - min(c) < 16 and min(c) > 120 for c in cols)
    apart = 12 < dist(cols[0], cols[1]) < 110
    return cols if grey and apart and common[1][1] > 0.2 * len(border) else None


def background_colours(img: Image.Image, key_hex: str, tol: float) -> tuple[list[tuple], str]:
    checker = checker_colours(img)
    if checker:
        return checker, "checkerboard (fake transparency)"
    key = hex_rgb(key_hex)
    border = [p[:3] for p in border_pixels(img)]
    near_key = sum(1 for c in border if dist(c, key) <= tol * 2.5)
    if near_key > 0.5 * len(border):
        return [key], f"key colour {key_hex}"
    common, n = Counter((c[0] // 6, c[1] // 6, c[2] // 6) for c in border).most_common(1)[0]
    if n > 0.6 * len(border):
        return [tuple(v * 6 + 3 for v in common)], "flat border colour"
    return [], "no flat background found"


def key_background(img: Image.Image, key_hex: str, tol: float = 40.0, binary: bool = True) -> tuple[Image.Image, str]:
    """Flood-fill the background from the edges to transparent, then clean the fringe."""
    if has_real_alpha(img):
        return img, "kept the image's own alpha"
    bgs, how = background_colours(img, key_hex, tol)
    if not bgs:
        return img, how
    w, h = img.size
    px = img.load()
    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(h):
        q.append((0, y)); q.append((w - 1, y))
    is_bg = lambda c: min(dist(c, b) for b in bgs) <= tol
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        c = px[x, y]
        if not is_bg(c):
            continue
        px[x, y] = (0, 0, 0, 0)
        if x > 0: q.append((x - 1, y))
        if x < w - 1: q.append((x + 1, y))
        if y > 0: q.append((x, y - 1))
        if y < h - 1: q.append((x, y + 1))
    # Fringe: opaque pixels touching the keyed area that still lean toward the
    # background colour (anti-aliased edges against magenta turn pink). An
    # anti-aliased edge can be two or three pixels deep, so peel up to 3 rings.
    cleaned = 0
    fringe = []
    for _ in range(3):
        ring = []
        for y in range(h):
            for x in range(w):
                c = px[x, y]
                if c[3] == 0:
                    continue
                if any(0 <= x + dx < w and 0 <= y + dy < h and px[x + dx, y + dy][3] == 0
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    d = min(dist(c, b) for b in bgs)
                    if d <= tol * 2.0:
                        ring.append((x, y, d))
        if not ring:
            break
        for x, y, d in ring:
            c = px[x, y]
            if binary:
                px[x, y] = (0, 0, 0, 0)
            else:
                a = max(0.0, min(1.0, (d - tol) / tol))
                b = min(bgs, key=lambda bb: dist(c, bb))
                un = [int(max(0, min(255, (c[i] - (1 - a) * b[i]) / a))) if a > 0.05 else 0 for i in range(3)]
                px[x, y] = (*un, int(a * 255))
        cleaned += len(ring)
        if not binary:
            break                      # soft alpha: one ring, kept semi-transparent
    fringe = [None] * cleaned
    return img, f"{how}: removed, {len(fringe)} edge pixels cleaned"


def trim(img: Image.Image) -> Image.Image:
    box = img.getchannel("A").getbbox()
    return img.crop(box) if box else img


def fit(img: Image.Image, size: tuple[int, int], anchor: str, padding: int, pixel: bool) -> Image.Image:
    W, H = size
    if anchor == "fill":
        # Cover the frame and crop the overflow (backgrounds, tiles).
        s = max(W / img.width, H / img.height)
        nw, nh = max(1, round(img.width * s)), max(1, round(img.height * s))
        img = img.resize((nw, nh), _resample(pixel, s))
        l, t = (nw - W) // 2, (nh - H) // 2
        return img.crop((l, t, l + W, t + H))
    img = trim(img)
    aw, ah = max(1, W - 2 * padding), max(1, H - 2 * padding)
    s = min(aw / img.width, ah / img.height)
    nw, nh = max(1, round(img.width * s)), max(1, round(img.height * s))
    img = img.resize((nw, nh), _resample(pixel, s))
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = (W - nw) // 2
    y = H - padding - nh if anchor == "bottom-center" else (H - nh) // 2
    canvas.alpha_composite(img, (x, y))
    return canvas


def _resample(pixel: bool, scale: float):
    if pixel:
        return Image.Resampling.BOX if scale < 1 else Image.Resampling.NEAREST
    return Image.Resampling.LANCZOS


def lock_palette(img: Image.Image, palette: list[str], max_colors: int, binary_alpha: bool) -> Image.Image:
    alpha = img.getchannel("A")
    if binary_alpha:
        alpha = alpha.point(lambda a: 255 if a >= 128 else 0)
    rgb = img.convert("RGB")
    if palette:
        flat = [v for c in palette for v in hex_rgb(c)]
        pal = Image.new("P", (1, 1))
        pal.putpalette(flat + flat[:3] * (256 - len(palette)))
        q = rgb.quantize(palette=pal, dither=Image.Dither.NONE)
    else:
        # Count colours only where the sprite is visible, so the background
        # does not use up the budget.
        q = rgb.quantize(colors=max(2, max_colors), method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = q.convert("RGBA")
    out.putalpha(alpha)
    if binary_alpha:
        # Fully transparent pixels carry no colour, so files stay small and clean.
        px = out.load()
        for y in range(out.height):
            for x in range(out.width):
                if px[x, y][3] == 0:
                    px[x, y] = (0, 0, 0, 0)
    return out


def strip(frames: list[Image.Image]) -> Image.Image:
    w, h = frames[0].size
    sheet = Image.new("RGBA", (w * len(frames), h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.alpha_composite(f, (i * w, 0))
    return sheet


def measure(img: Image.Image, palette: list[str]) -> dict:
    a = img.getchannel("A")
    hist = a.histogram()
    total = img.width * img.height
    transparent = hist[0]
    semi = total - hist[0] - hist[255]
    opaque = [p[:3] for p in img.getdata() if p[3] > 0]
    colours = len(set(opaque))
    pal = {hex_rgb(c) for c in palette}
    on_pal = sum(1 for p in opaque if p in pal) if pal else None
    box = a.getbbox()
    return {
        "size": f"{img.width}x{img.height}",
        "transparent_ratio": round(transparent / total, 4),
        "semi_alpha_pixels": semi,
        "colours": colours,
        "palette_share": round(on_pal / len(opaque), 4) if pal and opaque else None,
        "touches_edge": bool(box) and (box[0] == 0 or box[1] == 0 or box[2] == img.width or box[3] == img.height),
        "baseline": box[3] if box else None,
        "empty": box is None,
        "checkerboard": checker_colours(img) is not None and not has_real_alpha(img),
    }
