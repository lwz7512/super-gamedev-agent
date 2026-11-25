"""Generate site/assets/banner.svg: a pixel-art level where the workflow is the path.

Usage: python3 site/banner.py site/assets/banner.svg   (pure standard library)
"""
import sys

W, H = 1280, 440
FONT = "ui-sans-serif, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
out = []
a = out.append

def sprite(x, y, rows, palette, px=4, cls=""):
    """Pixel art from strings: each char a palette key, '.' transparent."""
    g = [f'<g transform="translate({x} {y})"{cls}>']
    for j, row in enumerate(rows):
        i = 0
        while i < len(row):
            c = row[i]
            if c == ".":
                i += 1
                continue
            k = i
            while k < len(row) and row[k] == c:
                k += 1
            g.append(f'<rect x="{i*px}" y="{j*px}" width="{(k-i)*px}" height="{px}" fill="{palette[c]}"/>')
            i = k
    g.append("</g>")
    return "".join(g)

a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d" shape-rendering="crispEdges">')
a('<title id="t">Super Gamedev Agent</title>')
a('<desc id="d">A pixel-art game level: a hero jumps from Idea to Brief, Build, Verify, Art and sound, Playtest and Ship, '
  'watched by a team of AI roles (designer, programmer, artist, QA, producer). Paths for first games, hobby ideas, '
  'your engine and studios.</desc>')
a('''<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#110f26"/><stop offset="0.6" stop-color="#1d1742"/><stop offset="1" stop-color="#2e1a45"/>
  </linearGradient>
  <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#ffb547"/><stop offset="1" stop-color="#ff6b8b"/>
  </linearGradient>
  <radialGradient id="glow" cx="0.72" cy="0.55" r="0.5">
    <stop offset="0" stop-color="#7c5cff" stop-opacity="0.30"/><stop offset="1" stop-color="#7c5cff" stop-opacity="0"/>
  </radialGradient>
</defs>''')
a(f'<rect width="{W}" height="{H}" fill="url(#sky)"/><rect width="{W}" height="{H}" fill="url(#glow)"/>')

# stars (deterministic)
import random
r = random.Random(7)
for _ in range(70):
    x, y = r.randint(0, W), r.randint(0, 300)
    s = r.choice([2, 2, 2, 3])
    a(f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="#ffffff" opacity="{r.choice([0.25, 0.4, 0.6, 0.8])}"/>')
# pixel moon
a(sprite(1176, 34, [
    "..oooo..",
    ".oooooo.",
    "oocooooo",
    "oooooco.".ljust(8, "o"),
    "oooooooo",
    "oocooooo",
    ".oooooo.",
    "..oooo..",
], {"o": "#ffe9b0", "c": "#e8cf8f"}, px=5))

# distant pixel hills
hill = "#241c4a"
a(f'<path d="M560 440 L560 380 L620 380 L620 360 L700 360 L700 372 L780 372 L780 350 L860 350 L860 366 L960 366 L960 344 L1060 344 L1060 360 L1160 360 L1160 340 L1280 340 L1280 440 Z" fill="{hill}"/>')

# ---- the level: platforms from Idea to Ship -----------------------------------
stages = [  # label, x, y(top), width, grass colour
    ("Idea",       600, 352, 84, "#ffb547"),
    ("Brief",      700, 318, 84, "#ff8a5c"),
    ("Build",      800, 284, 84, "#ff6b8b"),
    ("Verify",     900, 250, 84, "#5fd49c"),
    ("Art & sound", 1000, 216, 96, "#d99cf0"),
    ("Playtest",   1112, 182, 84, "#7cc0f2"),
]
for label, x, y, w, grass in stages:
    a(f'<rect x="{x}" y="{y}" width="{w}" height="10" fill="{grass}"/>')
    a(f'<rect x="{x}" y="{y+10}" width="{w}" height="22" fill="#4a3d86"/>')
    for bx in range(x, x + w, 12):                       # brick seams
        a(f'<rect x="{bx}" y="{y+20}" width="2" height="12" fill="#3a2f6e"/>')
    a(f'<rect x="{x}" y="{y+32}" width="{w}" height="4" fill="#2b2357"/>')
    a(f'<text x="{x + w/2}" y="{y+27}" text-anchor="middle" font-family="{MONO}" font-size="11" font-weight="700" fill="#ffffff" opacity="0.92" shape-rendering="auto">{label.replace("&", "&amp;")}</text>')

# goal: the Ship platform with a flag
gx, gy = 1206, 148
a(f'<rect x="{gx}" y="{gy}" width="64" height="10" fill="#ffd166"/><rect x="{gx}" y="{gy+10}" width="64" height="22" fill="#4a3d86"/>'
  f'<rect x="{gx}" y="{gy+32}" width="64" height="4" fill="#2b2357"/>')
a(f'<text x="{gx+32}" y="{gy+27}" text-anchor="middle" font-family="{MONO}" font-size="11" font-weight="700" fill="#ffffff" shape-rendering="auto">Ship</text>')
a(f'<rect x="{gx+42}" y="{gy-58}" width="4" height="58" fill="#e8e6ff"/>')
a(sprite(gx + 46, gy - 58, [
    "ggggggg",
    "gggggg.",
    "ggggg..",
    "gggggg.",
    "ggggggg",
], {"g": "#5fd49c"}, px=4))

# coins along the route
coin = [".yy.", "yYYy", "yYYy", ".yy."]
for cx, cy in [(735, 276), (835, 242), (935, 206), (1045, 172), (1150, 138)]:
    a(sprite(cx, cy, coin, {"y": "#ffb547", "Y": "#ffe08a"}, px=3))

# dotted jump arcs between platforms
for (l1, x1, y1, w1, _), (l2, x2, y2, w2, _) in zip(stages, stages[1:] + [("Ship", gx, gy, 64, "")]):
    sx, sy, ex, ey = x1 + w1 - 14, y1 - 4, x2 + 14, y2 - 4
    mx, my = (sx + ex) / 2, min(sy, ey) - 42
    a(f'<path d="M{sx} {sy} Q{mx} {my} {ex} {ey}" fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="2" stroke-dasharray="2 6" shape-rendering="auto"/>')

# the hero, mid-jump over Build -> Verify
hero = [
    "..oooo..",
    ".oooooo.",
    ".owoowo.",
    ".okookv.",
    ".oooooo.",
    "..pppp..",
    ".pp..pp.",
    ".b....b.",
]
a(sprite(876, 200, hero, {"o": "#ffb547", "w": "#ffffff", "k": "#1b1640", "v": "#ffffff", "p": "#ff6b8b", "b": "#2b2357"}, px=4))
a('<path d="M870 234 l-14 6 M870 224 l-18 0" stroke="#ffffff" stroke-opacity="0.5" stroke-width="2"/>')   # motion lines

# ---- the team: role avatars on a ledge above the level -------------------------
roles = [  # label, hair/hat, shirt, accessory key colour
    ("Designer",   "#ffb547", "#c0457a", "#ffffff"),
    ("Programmer", "#5fd49c", "#3466a8", "#5fd49c"),
    ("Artist",     "#d99cf0", "#7d4bb5", "#ff6b8b"),
    ("QA",         "#7cc0f2", "#2f7d6d", "#ffd166"),
    ("Producer",   "#ffd166", "#8a5a2a", "#e8e6ff"),
    ("You",        "#ffd166", "#ff6b8b", "#ffd166"),
]
face = "#f6d2b5"
ax0, ay = 612, 40
for i, (label, hat, shirt, acc) in enumerate(roles):
    x = ax0 + i * 88
    if label == "You":                        # the director: you decide, the team asks first
        rows = [
            "g.g..g.g",
            "gggggggg",
            ".hhhhhh.",
            ".fkffkf.",
            ".ffffff.",
            "..fmmf..",
            ".cccccc.",
            "ccccxccc",
            "cccccccc",
            ".c....c.",
        ]
        pal = {"g": "#ffd166", "h": "#8a5a2a", "f": face, "k": "#1b1640", "m": "#c0457a", "c": shirt, "x": acc}
    else:
        rows = [
            "..hhhh..",
            ".hhhhhh.",
            ".hffffh.",
            ".fkffkf.",
            ".ffffff.",
            "..ffff..",
            ".cccccc.",
            "ccccxccc",
            "cccccccc",
            ".c....c.",
        ]
        pal = {"h": hat, "f": face, "k": "#1b1640", "c": shirt, "x": acc}
    a(f'<rect x="{x - 12}" y="{ay - 8}" width="72" height="76" rx="8" fill="#ffffff" fill-opacity="0.06" stroke="{hat}" stroke-opacity="0.55" shape-rendering="auto"/>')
    a(sprite(x + 8, ay, rows, pal, px=4))
    a(f'<text x="{x + 24}" y="{ay + 60}" text-anchor="middle" font-family="{FONT}" font-size="10.5" font-weight="600" fill="#e8e6ff" shape-rendering="auto">{label}</text>')
a(f'<text x="{ax0 - 8}" y="{ay - 16}" font-family="{MONO}" font-size="11" letter-spacing="2" fill="#8f8bb8" shape-rendering="auto">YOUR AI STUDIO · 49 ROLE AGENTS · YOU DIRECT</text>')

# ---- title block and paths ----------------------------------------------------
a(f'<g font-family="{FONT}" shape-rendering="auto">')
a('<text x="64" y="92" fill="#ffb547" font-size="17" font-weight="700" letter-spacing="4">CLAUDE CODE · GAME DEVELOPMENT</text>')
a('<text x="62" y="160" fill="#ffffff" font-size="62" font-weight="800" letter-spacing="-1">Super Gamedev</text>')
a('<text x="62" y="224" fill="url(#accent)" font-size="62" font-weight="800" letter-spacing="-1">Agent</text>')
a('<text x="64" y="268" fill="#d6d3f0" font-size="21">Describe a game. Your AI studio helps you make it.</text>')
a('<text x="64" y="296" fill="#8f8bb8" font-size="15">From a first game in your browser to shipping with a team.</text>')
chips = [("First game", "#ffb547"), ("Hobby idea", "#ff6b8b"), ("Your engine", "#5fd49c"), ("Studio", "#7cc0f2")]
cx = 64
for label, col in chips:
    w = 22 + len(label) * 8.6
    a(f'<rect x="{cx}" y="326" width="{w:.0f}" height="30" rx="15" fill="{col}" fill-opacity="0.14" stroke="{col}" stroke-opacity="0.7"/>')
    a(f'<rect x="{cx + 12}" y="337" width="8" height="8" fill="{col}" shape-rendering="crispEdges"/>')
    a(f'<text x="{cx + 26}" y="346" fill="#ffffff" font-size="14" font-weight="600">{label}</text>')
    cx += w + 10
a('<text x="64" y="392" fill="#6f6a98" font-size="13">Godot · Unity · Unreal · Phaser · three.js · and 7 more engines</text>')
a('</g>')

# ground strip
a(f'<rect x="0" y="{H-14}" width="{W}" height="14" fill="#1a1436"/>')
for gx2 in range(0, W, 16):
    a(f'<rect x="{gx2}" y="{H-14}" width="8" height="4" fill="#2b2357"/>')
a('</svg>')
open(sys.argv[1], "w").write("\n".join(out) + "\n")
print("written", sys.argv[1])
