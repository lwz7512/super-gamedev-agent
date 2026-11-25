"""Lessons: what a game taught, kept where the next game will see it.

A lesson is a Markdown file with a small header:

    ---
    title: Headless Godot never fires frame_post_draw
    date: 2026-11-25
    game: super-gamedev-agent
    engine: godot
    kind: pitfall            # pitfall | technique | process | tool | design
    tags: [headless, screenshots, testing]
    skills: [godot-gdscript-headless-testing, play-verify]
    status: active           # active | promoted | retired
    ---
    What happened, the evidence, and what to do next time.

Promotion turns a lesson into lasting guidance: for a vendored library skill
it becomes an addendum (vault/addenda/<skill>.md, read beside the skill, so the
library itself stays unmodified); for a studio skill it becomes a proposal for
/skill-improve.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from store import Vault, VaultError

KINDS = ("pitfall", "technique", "process", "tool", "design")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "lesson"


def parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            for line in text[3:end].strip().splitlines():
                k, _, v = line.partition(":")
                v = v.split("#")[0].strip()
                if v.startswith("[") and v.endswith("]"):
                    v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
                meta[k.strip()] = v
            body = text[end + 4:].strip()
    meta["id"] = path.stem
    meta["path"] = str(path)
    meta["body"] = body
    for k in ("tags", "skills"):
        if isinstance(meta.get(k), str):
            meta[k] = [meta[k]] if meta[k] else []
        meta.setdefault(k, [])
    meta.setdefault("status", "active")
    return meta


def all_lessons(vault: Vault) -> list[dict]:
    d = vault.root / "lessons"
    return [parse(p) for p in sorted(d.glob("*.md"))] if d.exists() else []


def find(vault: Vault, tags=(), skill: str = "", engine: str = "", text: str = "", include_retired: bool = False) -> list[dict]:
    out = []
    for l in all_lessons(vault):
        if l["status"] == "retired" and not include_retired:
            continue
        if tags and not set(tags) & set(l["tags"]):
            continue
        if skill and skill not in l["skills"]:
            continue
        if engine and l.get("engine") not in (engine, "any", ""):
            continue
        if text and text.lower() not in (l.get("title", "") + " " + l["body"]).lower():
            continue
        out.append(l)
    return sorted(out, key=lambda l: l.get("date", ""), reverse=True)


def add(vault: Vault, title: str, body: str, kind: str, tags: list[str], skills: list[str], engine: str, game: str) -> Path:
    if kind not in KINDS:
        raise VaultError(f"kind must be one of {', '.join(KINDS)}")
    if not title.strip() or not body.strip():
        raise VaultError("a lesson needs a title and a body (what happened, the evidence, what to do next time)")
    d = vault.root / "lessons"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{date.today().isoformat()}-{_slug(title)}.md"
    n = 2
    while p.exists():
        p = d / f"{date.today().isoformat()}-{_slug(title)}-{n}.md"
        n += 1
    p.write_text("---\n" f"title: {title}\n" f"date: {date.today().isoformat()}\n" f"game: {game}\n" f"engine: {engine}\n"
                 f"kind: {kind}\n" f"tags: [{', '.join(tags)}]\n" f"skills: [{', '.join(skills)}]\n" "status: active\n---\n\n"
                 f"{body.strip()}\n", encoding="utf-8")
    return p


def set_status(path: Path, status: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^status:.*$", f"status: {status}", text, count=1)
    path.write_text(text, encoding="utf-8")


def library_skills() -> set[str]:
    from store import STUDIO
    lib = STUDIO / ".claude/library"
    names = {p.parent.name for p in lib.glob("skills/*/*/SKILL.md")}
    return names | ({"router"} if (lib / "router/SKILL.md").exists() else set())


def promote(vault: Vault, lesson_id: str, skill: str) -> tuple[str, Path | None]:
    hits = [l for l in all_lessons(vault) if l["id"] == lesson_id]
    if not hits:
        raise VaultError(f"no lesson '{lesson_id}' (vault.sh lessons)")
    l = hits[0]
    if skill in library_skills():
        a = vault.root / "addenda" / f"{skill}.md"
        a.parent.mkdir(parents=True, exist_ok=True)
        head = a.read_text() if a.exists() else (
            f"# Addenda for the library skill `{skill}`\n\n"
            "Read with the skill. These come from this studio's own games and take precedence over the skill "
            "where they disagree; the library itself is left unmodified so upstream updates still apply.\n\n")
        a.write_text(head + f"## {l.get('title', l['id'])}\n\n_From lesson `{l['id']}` ({l.get('game', '?')}, {l.get('date', '?')})._\n\n{l['body']}\n\n")
        set_status(Path(l["path"]), "promoted")
        return "addendum", a
    from store import STUDIO
    if (STUDIO / ".claude/skills" / skill / "SKILL.md").exists():
        set_status(Path(l["path"]), "promoted")
        return "skill-improve", None
    raise VaultError(f"no skill named '{skill}' in the studio or the library")


def addenda(vault: Vault, skill: str) -> str:
    a = vault.root / "addenda" / f"{skill}.md"
    return a.read_text(encoding="utf-8") if a.exists() else ""
