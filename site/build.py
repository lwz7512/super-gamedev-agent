#!/usr/bin/env python3
"""Build the GitHub Pages site from the documents in this repo.

Every page is generated from a committed file, so the site cannot drift from
the repo: guides from the Markdown docs, the agent catalog from
.claude/agents/*.md, the studio skill catalog from .claude/skills/*/SKILL.md,
and the knowledge library from .claude/library/skills/**/SKILL.md. Catalog
groups are derived from .claude/docs/agent-roster.md and skills-reference.md;
anything those files do not list lands in an "Other" group rather than being
dropped.

Usage:  python site/build.py [--out _site]
Needs:  the `markdown` package (pip install markdown)
"""

from __future__ import annotations

import argparse
import html
import json
import posixpath
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
REPO = "lwz7512/super-gamedev-agent"
SITE_URL = f"https://lwz7512.github.io/super-gamedev-agent"
GITHUB = f"https://github.com/{REPO}"
BLOB = f"{GITHUB}/blob/main"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"

# Guide pages: repo path -> (site path, nav title, one-line summary)
# Guide pages: repo path -> (site path, title, summary, group). Order is reading order.
GUIDE_GROUPS = [
    ("Getting started", "How the studio works, from an idea to a shipped game."),
    ("Layers", "The five layers this template adds, one reference each."),
    ("Reference", "Skill chains, the knowledge library, engine versions."),
]
GUIDES = {
    "docs/WORKFLOW-GUIDE.md": ("guide/workflow.html", "Workflow guide",
        "Zero to a shipped game: the seven phases, the default minimal path, every command, and where the added layers plug in.", "Getting started"),
    "docs/CCGS-README.md": ("guide/studio.html", "Studio layer tour",
        "The full Claude Code Game Studios feature tour: hooks, rules, rigor tiers and studio mode.", "Getting started"),
    "docs/COLLABORATIVE-DESIGN-PRINCIPLE.md": ("guide/collaboration.html", "Collaboration protocol",
        "Question, options, decision, draft, approval: how the agents work with you instead of for you.", "Getting started"),
    ".claude/docs/godot-verify.md": ("guide/godot-verify.html", "Run-and-verify (Godot)",
        "Scenarios that play the game: scripted input, live-node checks, errors, screenshots, filmstrips, determinism.", "Layers"),
    ".claude/docs/asset-forge.md": ("guide/asset-forge.html", "Asset production",
        "Generate, clean up, check, import and license game art and sound: OpenArt, ElevenLabs, sfxr, placeholders.", "Layers"),
    ".claude/docs/playtest-data.md": ("guide/playtest-data.html", "Playtest data",
        "Telemetry, in-game feedback, simulation bots and playtest reports: where players quit, die and get stuck.", "Layers"),
    ".claude/docs/studio-vault.md": ("guide/studio-vault.html", "Studio vault",
        "Memory across games: reusable modules with tests, lessons with evidence, and addenda to library skills.", "Layers"),
    ".claude/docs/evals.md": ("guide/evals.html", "Evals",
        "Static integrity checks, layer self-tests and behaviour evals of real Claude runs: is it still one system?", "Layers"),
    "docs/skill-flow-diagrams.md": ("guide/skill-flows.html", "Skill flow diagrams",
        "How the studio skills chain together, and which artifacts pass between them.", "Reference"),
    ".claude/library/README.md": ("guide/library.html", "Knowledge library tour",
        "The awesome-gamedev-agent-skills catalog: how the router picks skills and what each engine covers.", "Reference"),
    ".claude/library/docs/VERSION-SUPPORT.md": ("guide/engine-versions.html", "Engine versions",
        "The engine releases every library skill is checked against.", "Reference"),
}

LIBRARY_CATEGORIES = {
    "router": ("Router", "The entry point: detects the engine and names the 2-3 skills a request needs."),
    "godot": ("Godot 4.7", "GDScript and C#, scenes, TileMapLayer, physics, shaders, headless tests, export."),
    "unity": ("Unity 6.3 LTS", "Scripting, Input System, physics, animation, ScriptableObjects, builds."),
    "unreal": ("Unreal Engine 5.8", "Blueprints, C++ gameplay, Enhanced Input, Behavior Trees, Niagara, packaging."),
    "web-engines": ("Web engines", "Phaser, PixiJS and three.js."),
    "ebitengine": ("Ebitengine", "2D games in Go."),
    "other-engines": ("Other engines", "Bevy, pygame, LÖVE, Defold and Roblox."),
    "disciplines": ("Disciplines", "Engine-neutral technique: AI, saving, game feel, shaders, procedural generation and more."),
    "genres": ("Genres", "Design glue for platformers, roguelikes, RPGs, card games and more."),
    "workflows": ("Workflows", "Game jams, fast prototypes, design docs, and publishing on Steam and itch.io."),
}

ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Crect width='32' height='32' rx='7' fill='%231b1640'/%3E%3Crect x='7' y='8' width='18' height='6' rx='2' "
        "fill='%23ffb547'/%3E%3Crect x='7' y='18' width='18' height='6' rx='2' fill='%23ff6b8b'/%3E%3C/svg%3E")


# ---------------------------------------------------------------- parsing --

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML frontmatter: scalars, quoted strings, [lists], > and | blocks."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm: dict = {}
    lines = text[3:end].strip("\n").splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", lines[i])
        i += 1
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in (">", ">-", "|", "|-", ""):
            block = []
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            val = (" " if val.startswith(">") or val == "" else "\n").join(b for b in block if b)
        elif len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1].replace('\\"', '"')
        elif val.startswith("[") and val.endswith("]"):
            val = [v.strip().strip("\"'") for v in val[1:-1].split(",") if v.strip()]
        fm[key] = val
    return fm, text[end + 4:].lstrip("\n")


def reference_groups(path: Path) -> list[tuple[str, list[str]]]:
    """Section headings and the backticked names in their table rows."""
    groups: list[tuple[str, list[str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        h = re.match(r"^#{2,3}\s+(.*)", line)
        if h:
            title = re.sub(r"\s*--\s*", " — ", h.group(1)).strip()
            groups.append((title, []))
            continue
        row = re.match(r"^\|\s*`/?([a-z0-9-]+)`", line)
        if row and groups:
            groups[-1][1].append(row.group(1))
    return [(t, names) for t, names in groups if names]


@dataclass
class Doc:
    kind: str            # guide | agent | skill | library
    src: str             # repo-relative path
    out: str             # site-relative path
    name: str
    title: str
    summary: str
    meta: dict = field(default_factory=dict)
    body: str = ""
    group: str = ""


def collect() -> dict[str, list[Doc]]:
    docs: dict[str, list[Doc]] = {"guide": [], "agent": [], "skill": [], "library": []}
    for src, (out, title, summary, group) in GUIDES.items():
        p = ROOT / src
        if not p.exists():
            sys.exit(f"build: guide source missing: {src}")
        body = p.read_text(encoding="utf-8")
        if src == ".claude/library/README.md":
            body = re.sub(r"(?ms)^## Sponsors\n.*?(?=^## )", "", body)   # upstream ad slots
            body = re.sub(r"(?m)^.*\]\(#sponsors\).*\n", "", body)       # its badge and contents entry
        docs["guide"].append(Doc("guide", src, out, Path(out).stem, title, summary, body=body, group=group))

    for p in sorted((ROOT / ".claude/agents").glob("*.md")):
        fm, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        name = fm.get("name", p.stem)
        docs["agent"].append(Doc("agent", rel(p), f"agents/{name}.html", name, name,
                                 fm.get("description", ""), fm, body))

    for p in sorted((ROOT / ".claude/skills").glob("*/SKILL.md")):
        if (p.parent / ".library").exists():
            continue                      # a library copy: catalogued under library/
        fm, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        name = fm.get("name", p.parent.name)
        docs["skill"].append(Doc("skill", rel(p), f"skills/{name}.html", name, "/" + name,
                                 fm.get("description", ""), fm, body))

    lib = ROOT / ".claude/library"
    active = {d.name for d in (ROOT / ".claude/skills").iterdir() if (d / ".library").exists()}
    paths = [lib / "router/SKILL.md"] + sorted(lib.glob("skills/*/*/SKILL.md"))
    for p in paths:
        fm, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        name = fm.get("name", p.parent.name)
        cat = "router" if p.parent.name == "router" else p.parent.parent.name
        d = Doc("library", rel(p), f"library/{name}.html", name, name,
                fm.get("description", ""), fm, body, group=cat)
        d.meta["_active"] = name in active
        docs["library"].append(d)

    docs["vault"] = collect_vault()
    assign_groups(docs["agent"], ROOT / ".claude/docs/agent-roster.md")
    assign_groups(docs["skill"], ROOT / ".claude/docs/skills-reference.md")
    for d in docs["skill"]:
        if d.summary.startswith("Old name of "):      # kept so old commands still work
            d.group = "Old names"
            d.meta["_alias"] = True
    docs["skill"].sort(key=lambda d: d.group == "Old names")
    return docs


def collect_vault() -> list[Doc]:
    """Modules (README + module.json), lessons and addenda from vault/."""
    out = []
    v = ROOT / "vault"
    for mj in sorted(v.glob("modules/*/*/module.json")):
        m = json.loads(mj.read_text(encoding="utf-8"))
        readme = mj.parent / "README.md"
        out.append(Doc("vault", rel(readme if readme.exists() else mj), f"vault/module-{m['name']}.html", m["name"], m["name"],
                       m.get("description", ""), m, readme.read_text(encoding="utf-8") if readme.exists() else "", group="module"))
    for lp in sorted(v.glob("lessons/*.md"), reverse=True):
        fm, body = parse_frontmatter(lp.read_text(encoding="utf-8"))
        first = next((ln for ln in body.splitlines() if ln.strip()), "")
        out.append(Doc("vault", rel(lp), f"vault/lesson-{lp.stem}.html", lp.stem, fm.get("title", lp.stem), first, fm, body, group="lesson"))
    for ap in sorted(v.glob("addenda/*.md")):
        out.append(Doc("vault", rel(ap), f"vault/addenda-{ap.stem}.html", ap.stem, ap.stem,
                       f"Corrections from this studio's games to the library skill {ap.stem}.", {}, ap.read_text(encoding="utf-8"), group="addenda"))
    return out


def assign_groups(items: list[Doc], ref: Path) -> None:
    order = reference_groups(ref)
    where = {}
    for title, names in order:
        for n in names:
            where.setdefault(n, title)
    for d in items:
        d.group = where.get(d.name, "Other")
    titles = [t for t, _ in order] + ["Other"]
    items.sort(key=lambda d: (titles.index(d.group) if d.group in titles else 99, d.name))


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


# -------------------------------------------------------------- rendering --

def slugify(value: str, separator: str = "-") -> str:
    """GitHub-style heading ids, so in-page links written for github.com work."""
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
    return value.replace(" ", separator)


LIST_ITEM = re.compile(r"^( *)([-*+]|\d+[.)]) +")


def normalise_lists(text: str) -> str:
    """Re-indent nested lists to 4 spaces per level.

    The docs follow GitHub, which nests a list under any indent that reaches
    the parent's text (2 spaces under "- ", 3 under "1. "). Python-Markdown
    needs 4, and otherwise runs the nested items into the parent's line.
    Fenced code is left alone.
    """
    out, stack, fence = [], [], None
    for line in text.split("\n"):
        f = re.match(r"^\s*(```+|~~~+)", line)
        if fence:
            out.append(line)
            if f and f.group(1)[0] == fence[0] and len(f.group(1)) >= len(fence):
                fence = None
            continue
        if f:
            fence = f.group(1)
            out.append(line)
            continue
        m = LIST_ITEM.match(line)
        indent = len(line) - len(line.lstrip(" "))
        if m:
            while stack and stack[-1] >= indent and not (stack[-1] == indent):
                stack.pop()
            if not stack or indent > stack[-1]:
                stack.append(indent)
            level = stack.index(indent) if indent in stack else len(stack) - 1
            out.append("    " * level + line.lstrip(" "))
        elif stack and line.strip() and indent > 0:
            # continuation text of the innermost open item
            out.append("    " * len([i for i in stack if i < indent]) + line.lstrip(" "))
        else:
            if line.strip() and indent == 0:
                stack = []
            out.append(line)
    return "\n".join(out)


class Site:
    def __init__(self, docs: dict[str, list[Doc]], out: Path):
        self.docs, self.out = docs, out
        self.by_src = {d.src: d for kind in docs.values() for d in kind}
        # Library copies in .claude/skills point at the library pages.
        for d in docs["library"]:
            self.by_src.setdefault(f".claude/skills/{d.name}/SKILL.md", d)
        self.by_src["README.md"] = Doc("guide", "README.md", "index.html", "index", "Home", "")
        self.names = {d.name: d for d in docs["library"]}
        self.names.update({d.name: d for d in docs["skill"]})
        self.agents = {d.name: d for d in docs["agent"]}

    # -- links
    def resolve(self, src: str, href: str, here: str, image: bool = False) -> str:
        if re.match(r"^(?:[a-z]+:|//|#)", href) or not href:
            return href
        path, _, anchor = href.partition("#")
        target = posixpath.normpath(posixpath.join(posixpath.dirname(src), path))
        anchor = "#" + anchor if anchor else ""
        if target.startswith("site/assets/"):
            return self.url(here, "assets/" + target[len("site/assets/"):])
        if image:
            return f"{RAW}/{target}"
        for cand in (target, f"{target}/SKILL.md", f"{target}/README.md"):
            if cand in self.by_src:
                return self.url(here, self.by_src[cand].out) + anchor
        return f"{BLOB}/{target}{anchor}"

    @staticmethod
    def url(here: str, target: str) -> str:
        depth = here.count("/")
        return "../" * depth + target

    def render_md(self, doc: Doc, here: str) -> tuple[str, list]:
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "toc", "sane_lists", "md_in_html"],
            extension_configs={"toc": {"slugify": slugify, "toc_depth": "2-3"}})
        out = md.convert(normalise_lists(doc.body))
        out = re.sub(r'(<a\b[^>]*?\bhref=")([^"]*)(")',
                     lambda m: m.group(1) + html.escape(self.resolve(doc.src, html.unescape(m.group(2)), here), quote=True) + m.group(3), out)
        out = re.sub(r'(<img\b[^>]*?\bsrc=")([^"]*)(")',
                     lambda m: m.group(1) + html.escape(self.resolve(doc.src, html.unescape(m.group(2)), here, image=True), quote=True) + m.group(3), out)
        out = self.link_code(out, here)
        # Wide tables scroll inside their own box on narrow screens.
        out = out.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
        return out, md.toc_tokens

    def link_code(self, htm: str, here: str) -> str:
        """`skill-name`, `/skill` and `agent-name` in prose become links."""
        def sub(m: re.Match) -> str:
            raw = m.group(1)
            name = raw.lstrip("/")
            d = self.names.get(name) or self.agents.get(name)
            if not d or (raw.startswith("/") and d.kind != "skill"):
                return m.group(0)
            return f'<a class="code-link" href="{self.url(here, d.out)}"><code>{raw}</code></a>'
        parts = re.split(r"(<pre\b.*?</pre>|<a\b.*?</a>|<h[1-6]\b.*?</h[1-6]>)", htm, flags=re.S)
        for i in range(0, len(parts), 2):
            parts[i] = re.sub(r"<code>(/?[a-z0-9][a-z0-9-]+)</code>", sub, parts[i])
        return "".join(parts)

    # -- page shell
    def page(self, here: str, title: str, description: str, main: str, active: str, aside: str = "") -> None:
        u = lambda t: self.url(here, t)
        nav = [("index.html", "Home", "home"), ("guide/index.html", "Guides", "guide"),
               ("agents/index.html", "Agents", "agent"), ("skills/index.html", "Studio skills", "skill"),
               ("library/index.html", "Knowledge library", "library"), ("vault/index.html", "Vault", "vault")]
        current = ' aria-current="page"'
        nav_html = "".join(
            f'<a href="{u(h)}"{current if k == active else ""}>{t}</a>' for h, t, k in nav)
        full_title = title if title == "Super Gamedev Agent" else f"{title} · Super Gamedev Agent"
        layout = f'<div class="layout has-aside"><aside class="toc">{aside}</aside><main>{main}</main></div>' \
            if aside else f'<div class="layout"><main>{main}</main></div>'
        doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(description[:155], quote=True)}">
<link rel="canonical" href="{SITE_URL}/{'' if here == 'index.html' else here}">
<meta property="og:title" content="{html.escape(full_title, quote=True)}">
<meta property="og:description" content="{html.escape(description[:155], quote=True)}">
<link rel="icon" href="{ICON}">
<link rel="stylesheet" href="{u('assets/style.css')}">
</head>
<body>
<header class="site-header">
  <div class="bar">
    <a class="brand" href="{u('index.html')}"><span class="logo" aria-hidden="true"></span>Super Gamedev Agent</a>
    <nav class="nav">{nav_html}<a href="{GITHUB}" class="gh">GitHub</a></nav>
  </div>
</header>
{layout}
<footer class="site-footer">
  <p>Built from the documents in <a href="{GITHUB}">{REPO}</a>.
  Studio layer: <a href="https://github.com/Donchitos/Claude-Code-Game-Studios">Claude Code Game Studios</a> (MIT).
  Knowledge library: <a href="https://github.com/gamedev-skills/awesome-gamedev-agent-skills">awesome-gamedev-agent-skills</a> (Apache-2.0).</p>
</footer>
<script>
document.querySelectorAll('[data-filter]').forEach(function (input) {{
  var scope = document.getElementById(input.dataset.filter);
  var count = document.querySelector('[data-count="' + input.dataset.filter + '"]');
  input.addEventListener('input', function () {{
    var q = input.value.trim().toLowerCase(), shown = 0;
    scope.querySelectorAll('.card').forEach(function (c) {{
      var hit = !q || c.textContent.toLowerCase().indexOf(q) !== -1;
      c.hidden = !hit; if (hit) shown++;
    }});
    scope.querySelectorAll('.group').forEach(function (g) {{
      g.hidden = !g.querySelector('.card:not([hidden])');
    }});
    if (count) count.textContent = q ? shown + ' match' + (shown === 1 ? '' : 'es') : '';
  }});
}});
</script>
</body>
</html>
"""
        dest = self.out / here
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(doc, encoding="utf-8")

    # -- building blocks
    def card(self, here: str, d: Doc, badge: str = "") -> str:
        b = f'<span class="badge">{badge}</span>' if badge else ""
        return (f'<a class="card" href="{self.url(here, d.out)}"><span class="card-title">'
                f'<code>{html.escape(d.title)}</code>{b}</span>'
                f'<span class="card-text">{html.escape(trim(d.summary, 190))}</span></a>')

    def catalog(self, here: str, items: list[Doc], groups: list[tuple[str, str]], badge=lambda d: "") -> str:
        out = []
        for key, lead in groups:
            members = [d for d in items if d.group == key]
            if not members:
                continue
            heading = LIBRARY_CATEGORIES.get(key, (key, ""))[0]
            out.append(f'<section class="group"><h2 id="{slugify(heading)}">{html.escape(heading)} '
                       f'<span class="count">{len(members)}</span></h2>'
                       + (f'<p class="lead">{html.escape(lead)}</p>' if lead else "")
                       + '<div class="cards">' + "".join(self.card(here, d, badge(d)) for d in members)
                       + "</div></section>")
        return "".join(out)

    def search(self, scope: str, what: str) -> str:
        return (f'<div class="search"><input type="search" placeholder="Filter {what}…" '
                f'aria-label="Filter {what}" data-filter="{scope}"><span class="muted" data-count="{scope}"></span></div>')

    def toc(self, tokens: list) -> str:
        items = []
        for t in tokens:
            if t["level"] > 2:
                continue
            items.append(f'<li><a href="#{t["id"]}">{t["name"]}</a></li>')
            if len(items) > 40:
                break
        return '<p class="toc-title">On this page</p><ul>' + "".join(items) + "</ul>" if len(items) > 2 else ""

    # -- pages
    def build(self) -> int:
        if self.out.exists():
            shutil.rmtree(self.out)
        (self.out / "assets").mkdir(parents=True)
        for f in (ROOT / "site/assets").iterdir():
            shutil.copy(f, self.out / "assets" / f.name)
        (self.out / ".nojekyll").write_text("")
        n = 0
        n += self.home()
        n += self.guides()
        n += self.detail_pages()
        n += self.catalogs()
        n += self.vault_pages()
        self.sitemap()
        return n

    def home(self) -> int:
        here = "index.html"
        readme = Doc("guide", "README.md", here, "index", "Super Gamedev Agent", "",
                     body=(ROOT / "README.md").read_text(encoding="utf-8"))
        # The hero shows the banner and title; drop them from the rendered README.
        readme.body = re.sub(r"(?s)\A.*?^# [^\n]*\n", "", readme.body, flags=re.M)
        readme.body = re.sub(r"(?m)^<p align=\"center\">.*?</p>\s*$", "", readme.body, flags=re.S)
        # The hero and the layer grid already say what the README's opening and
        # layer table say: start the rendered README at the walkthrough.
        cut = readme.body.find("## How a game moves through it")
        if cut > 0:
            readme.body = readme.body[cut:]
        body, tokens = self.render_md(readme, here)
        n_agents, n_lib = len(self.docs["agent"]), len(self.docs["library"]) - 1
        n_skills = sum(1 for d in self.docs["skill"] if not d.meta.get("_alias"))
        # Engines = rows of the router's detection table, so the count follows the library.
        router = (ROOT / ".claude/library/router/SKILL.md").read_text(encoding="utf-8")
        engines = len(re.findall(r"(?m)^\| *\d+ *\| *[^|]+\| *`", router))
        vault = self.docs["vault"]
        n_mod = sum(1 for d in vault if d.group == "module")
        n_les = sum(1 for d in vault if d.group == "lesson")
        stats = "".join(f'<div class="stat"><strong>{v}</strong><span>{k}</span></div>' for v, k in (
            (n_agents, "role agents"), (n_skills, "studio skills"), (n_lib, "library skills"), (engines, "engines"),
            (n_mod, "vault modules"), (n_les, "lessons")))
        u = lambda t: self.url(here, t)
        layers = [
            ("studio", "Studio", f"{n_agents} agents · {n_skills} skills", "Directors, leads and specialists run the process: brief, prototype, stories, gates, release.", "agents/index.html"),
            ("knowledge", "Knowledge", f"{n_lib} skills · {engines} engines", "Version-pinned engine skills, disciplines and genres, picked per request by a router.", "library/index.html"),
            ("verify", "Run-and-verify", "/play-verify", "Agents play the Godot game from a scenario and look at what happened.", "guide/godot-verify.html"),
            ("assets", "Asset production", "/make-assets", "OpenArt, ElevenLabs and a synth, then cleanup, checks, import and a licence ledger.", "guide/asset-forge.html"),
            ("playtest", "Playtest data", "/playtest-data", "Telemetry, feedback and bots that find soft-locks; reports with charts.", "guide/playtest-data.html"),
            ("vault", "Studio vault", f"{n_mod} module(s) · {n_les} lessons", "What earlier games built and learned, offered to the next.", "vault/index.html"),
            ("evals", "Evals", "/studio-evals", "Integrity checks, every layer's tests, and scored runs of the agent itself.", "guide/evals.html"),
        ]
        grid = "".join(f'<a class="layer {k}" href="{u(href)}"><span class="eyebrow">{i + 1} · {name}</span>'
                       f'<strong>{html.escape(sub)}</strong><span>{html.escape(text)}</span></a>'
                       for i, (k, name, sub, text, href) in enumerate(layers))
        main = f"""
<section class="hero">
  <img class="banner" src="{u('assets/banner.svg')}" alt="Super Gamedev Agent: a Claude Code game studio in seven layers" width="1280" height="400">
  <p class="tagline">A Claude Code setup for making games, in seven layers: a studio of AI agents
  that runs the process, a library that knows your engine, and five layers that let the agents
  play the game, make its assets, learn from playtests, remember across games and check themselves.</p>
  <div class="stats">{stats}</div>
  <pre class="quickstart"><code>git clone git@github.com:{REPO}.git
super-gamedev-agent/bin/new-game.sh ~/games/my-game godot
cd ~/games/my-game &amp;&amp; claude      # then: "make me a game"</code></pre>
</section>
<h2 class="section-title">The seven layers</h2>
<section class="layers">{grid}</section>
<article class="prose">{body}</article>"""
        self.page(here, "Super Gamedev Agent",
                  "A Claude Code game studio in seven layers: role agents, an engine knowledge library, run-and-verify, asset production, playtest data, a cross-game vault and evals.",
                  main, "home")
        return 1

    def guides(self) -> int:
        here = "guide/index.html"
        sections = ""
        for group, lead in GUIDE_GROUPS:
            cards = "".join(
                f'<a class="card" href="{self.url(here, d.out)}"><span class="card-title">{html.escape(d.title)}</span>'
                f'<span class="card-text">{html.escape(d.summary)}</span></a>' for d in self.docs["guide"] if d.group == group)
            sections += f'<section class="group"><h2>{group}</h2><p class="lead">{lead}</p><div class="cards">{cards}</div></section>'
        self.page(here, "Guides", "Guides to the Super Gamedev Agent studio, its layers and the knowledge library.",
                  f'<h1>Guides</h1><p class="lead">Long-form documentation from the repo.</p>{sections}', "guide")
        for d in self.docs["guide"]:
            body, tokens = self.render_md(d, d.out)
            main = (f'<nav class="crumbs"><a href="{self.url(d.out, "guide/index.html")}">Guides</a> / {d.group}</nav>'
                    f'<p class="source"><a href="{BLOB}/{d.src}">{d.src}</a></p><article class="prose">{body}</article>')
            self.page(d.out, d.title, d.summary, main, "guide", aside=self.toc(tokens))
        return 1 + len(self.docs["guide"])

    def detail_pages(self) -> int:
        n = 0
        labels = {"agent": ("Agents", "agents/index.html"), "skill": ("Studio skills", "skills/index.html"),
                  "library": ("Knowledge library", "library/index.html")}
        for kind in ("agent", "skill", "library"):
            for d in self.docs[kind]:
                body, tokens = self.render_md(d, d.out)
                crumb_t, crumb_h = labels[kind]
                group = LIBRARY_CATEGORIES.get(d.group, (d.group,))[0]
                chips = [f'<span class="chip">{html.escape(group)}</span>']
                for key, label in (("model", "model"), ("argument-hint", "args")):
                    v = d.meta.get(key)
                    if v and v != "inherit":
                        chips.append(f'<span class="chip"><b>{label}</b> {html.escape(str(v))}</span>')
                if kind == "agent" and d.meta.get("tools"):
                    chips.append(f'<span class="chip"><b>tools</b> {html.escape(str(d.meta["tools"]))}</span>')
                if kind == "library":
                    chips.append('<span class="chip on">on by default</span>' if d.meta.get("_active")
                                 else f'<span class="chip">activate: <code>library.sh activate …</code></span>')
                heading = f"<code>{html.escape(d.title)}</code>"
                main = (f'<nav class="crumbs"><a href="{self.url(d.out, crumb_h)}">{crumb_t}</a> / {html.escape(group)}</nav>'
                        f'<h1 class="detail-title">{heading}</h1>'
                        f'<p class="lead">{html.escape(d.summary)}</p>'
                        f'<div class="chips">{"".join(chips)}</div>'
                        f'<p class="source"><a href="{BLOB}/{d.src}">View source: {d.src}</a></p>'
                        f'<article class="prose">{body}</article>')
                self.page(d.out, d.title, d.summary, main, kind, aside=self.toc(tokens))
                n += 1
        return n

    def catalogs(self) -> int:
        agents, skills, lib = self.docs["agent"], self.docs["skill"], self.docs["library"]

        def ordered_groups(items):
            seen = []
            for d in items:
                if d.group not in seen:
                    seen.append(d.group)
            return [(g, "") for g in seen]

        here = "agents/index.html"
        self.page(here, "Agents", f"The {len(agents)} studio agents, from directors to engine specialists.",
                  f'<h1>Agents</h1><p class="lead">{len(agents)} role agents, organised like a studio. Directors set vision, '
                  'leads own departments, specialists implement. Each specialist names the knowledge-library skills for its role.</p>'
                  + self.search("agent-list", "agents") + f'<div id="agent-list">{self.catalog(here, agents, ordered_groups(agents))}</div>',
                  "agent")

        here = "skills/index.html"
        real = sum(1 for d in skills if not d.meta.get("_alias"))
        self.page(here, "Studio skills", f"The {real} studio workflow skills (slash commands).",
                  f'<h1>Studio skills</h1><p class="lead">{real} slash commands that run the production process: '
                  'onboarding, design, architecture, stories, QA, release and team orchestration.</p>'
                  + self.search("skill-list", "skills") + f'<div id="skill-list">{self.catalog(here, skills, ordered_groups(skills))}</div>',
                  "skill")

        here = "library/index.html"
        on = sum(1 for d in lib if d.meta.get("_active"))
        groups = [(k, v[1]) for k, v in LIBRARY_CATEGORIES.items()]
        unknown = sorted({d.group for d in lib} - set(LIBRARY_CATEGORIES))
        groups += [(g, "") for g in unknown]
        self.page(here, "Knowledge library", f"{len(lib) - 1} engine, discipline, genre and workflow skills plus the router.",
                  f'<h1>Knowledge library</h1><p class="lead">{len(lib) - 1} skills and a router, from awesome-gamedev-agent-skills. '
                  f'{on} are on by default (the router, disciplines, genres and publishing). Turn on your engine with '
                  '<code>bash .claude/scripts/library.sh activate &lt;group&gt;</code>; the router can read the rest at any time.</p>'
                  + self.search("lib-list", "library skills")
                  + f'<div id="lib-list">{self.catalog(here, lib, groups, lambda d: "on" if d.meta.get("_active") else "")}</div>',
                  "library")
        return 3

    def vault_pages(self) -> int:
        items = self.docs["vault"]
        here = "vault/index.html"
        mods = [d for d in items if d.group == "module"]
        lessons = [d for d in items if d.group == "lesson"]
        addenda = [d for d in items if d.group == "addenda"]

        def card(d, badge=""):
            b = f'<span class="badge">{html.escape(badge)}</span>' if badge else ""
            return (f'<a class="card" href="{self.url(here, d.out)}"><span class="card-title">{html.escape(d.title)}{b}</span>'
                    f'<span class="card-text">{html.escape(trim(d.summary, 200))}</span></a>')
        kinds = {}
        for d in lessons:
            kinds.setdefault(str(d.meta.get("kind", "other")), []).append(d)
        heading = {"pitfall": "Pitfalls", "technique": "Techniques", "process": "Process", "tool": "Tools", "design": "Design"}
        lesson_html = "".join(f'<section class="group"><h3>{heading.get(k, k.capitalize())} <span class="count">{len(v)}</span></h3>'
                              f'<div class="cards">{"".join(card(d, "promoted" if d.meta.get("status") == "promoted" else "") for d in v)}</div></section>'
                              for k, v in sorted(kinds.items()))
        main = (f'<h1>Studio vault</h1><p class="lead">What this studio\'s games built and learned, offered to every new game: '
                f'{len(mods)} reusable module(s), {len(lessons)} lessons and {len(addenda)} addenda to library skills. '
                f'Use it through <code>/studio-vault</code> or <code>bash .claude/scripts/vault.sh</code> '
                f'(<a href="{self.url(here, "guide/studio-vault.html")}">guide</a>).</p>'
                + self.search("vault-list", "the vault")
                + f'<div id="vault-list"><section class="group"><h2>Modules <span class="count">{len(mods)}</span></h2>'
                f'<p class="lead">Systems with relocatable paths and tests; <code>vault.sh add &lt;name&gt;</code> installs one.</p>'
                f'<div class="cards">{"".join(card(d, d.meta.get("version", "")) for d in mods)}</div></section>'
                f'<section class="group"><h2>Lessons <span class="count">{len(lessons)}</span></h2>'
                f'<p class="lead">What happened, the evidence, and what to do next time. Session start shows them for the game\'s engine.</p>'
                f'{lesson_html}</section>'
                f'<section class="group"><h2>Addenda <span class="count">{len(addenda)}</span></h2>'
                f'<p class="lead">Promoted lessons, read beside a library skill; they win where they disagree.</p>'
                f'<div class="cards">{"".join(card(d) for d in addenda)}</div></section></div>')
        self.page(here, "Studio vault", "Reusable modules, lessons and library-skill addenda from this studio's games.", main, "vault")
        for d in items:
            body, tokens = self.render_md(d, d.out)
            chips = []
            if d.group == "module":
                m = d.meta
                chips = [f"v{m.get('version', '?')}", f"{m.get('engine', '?')} {m.get('engine_min', '')}+",
                         f"installs to {m.get('install_dir', '?')}"] + [f"autoload {k}" for k in m.get("autoloads", {})] + \
                        [f"tag {t}" for t in m.get("tags", [])]
                body = (f'<pre><code>bash .claude/scripts/vault.sh add {html.escape(d.name)}\n'
                        f'bash .claude/scripts/vault.sh verify {html.escape(d.name)}</code></pre>') + body
            elif d.group == "lesson":
                m = d.meta
                chips = [str(m.get("kind", "")), f"engine {m.get('engine', '?')}", f"from {m.get('game', '?')}", str(m.get("date", "")),
                         str(m.get("status", "active"))] + [f"tag {t}" for t in (m.get("tags") or [])]
                body += "".join(f'<p class="muted">Bears on: ' + ", ".join(f"<code>{html.escape(x)}</code>" for x in (m.get("skills") or [])) + "</p>") \
                    if m.get("skills") else ""
                body = self.link_code(body, d.out)
            kind = {"module": "Module", "lesson": "Lesson", "addenda": "Addenda"}[d.group]
            main = (f'<nav class="crumbs"><a href="{self.url(d.out, "vault/index.html")}">Vault</a> / {kind}</nav>'
                    f'<h1 class="detail-title">{html.escape(d.title)}</h1>'
                    + (f'<div class="chips">{"".join(f"<span class=chip>{html.escape(c)}</span>" for c in chips if c.strip())}</div>' if chips else "")
                    + f'<p class="source"><a href="{BLOB}/{d.src}">View source: {d.src}</a></p><article class="prose">{body}</article>')
            self.page(d.out, d.title, d.summary or d.title, main, "vault", aside=self.toc(tokens))
        return 1 + len(items)

    def sitemap(self) -> None:
        urls = sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*.html"))
        body = "".join(f"<url><loc>{SITE_URL}/{'' if u == 'index.html' else u}</loc></url>" for u in urls)
        (self.out / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n')


def trim(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "_site"))
    args = ap.parse_args()
    out = Path(args.out).resolve()
    # The build deletes its output first: only ever delete a folder it made.
    if out.exists() and any(out.iterdir()) and not (out / ".nojekyll").exists():
        sys.exit(f"build: {out} is not empty and was not made by this script; refusing to replace it")
    docs = collect()
    n = Site(docs, out).build()
    print(f"built {n} pages into {out}: {len(docs['guide'])} guides, {len(docs['agent'])} agents, "
          f"{len(docs['skill'])} studio skills, {len(docs['library'])} library pages")
    others = [d.name for k in ("agent", "skill") for d in docs[k] if d.group == "Other"]
    if others:
        print(f"note: not in the roster/skills reference, listed under Other: {', '.join(others)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
