"""vault: cross-game memory and reuse (run through vault.sh).

Modules (reusable systems):
  list [--tag T]                   what the vault holds
  search <words>                   by name, description, tags and README
  show <name>                      a module's README, files, autoloads, actions
  harvest <name> <path>... [opts]  copy a system out of this game into the vault
  add <name> [--dir res://...]     install a module into this game
  outdated                         installed modules with a newer vault version
  diff <name>                      files changed locally since the module was added
  update <name> [--force]          take the vault's newer version
  push <name> [--part P]           send this game's improvements back to the vault
  verify <name>|--all              install into an empty project, import, run its tests
Lessons (what games taught):
  lessons [--tag T] [--skill S] [--engine E] [--text W] [--all]
  lesson add --title ... --kind K --tags a,b --skills s1 --body-file F
  promote <lesson-id> --skill <skill>   addendum for a library skill / proposal for a studio skill
  addenda <skill>                  print the addenda for a library skill
Games:
  register [--name N]              add this game to the vault's registry
  games                            every registered game and its modules
  brief                            one-paragraph summary for session start
  selftest                         this tool's tests

Exit: 0 done/pass · 1 fail or refused · 3 not assessed or a problem to fix.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lessons as L  # noqa: E402
import modules as M  # noqa: E402
from store import Vault, VaultError, locate, newer, read_lock  # noqa: E402

MARK = {"pass": "ok  ", "fail": "FAIL", "not_assessed": "N/A "}


def say(s: str = "") -> None:
    print(s, flush=True)


def engine_of(game: Path) -> str:
    if (game / "project.godot").exists():
        return "godot"
    return "any"


def game_name(game: Path) -> str:
    pg = game / "project.godot"
    if pg.exists():
        m = re.search(r'(?m)^config/name="([^"]*)"', pg.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return game.name


def cmd_list(v: Vault, game: Path, a) -> int:
    mods = [m for m in v.modules() if not a.tag or a.tag in m.get("tags", [])]
    if not mods:
        say(f"no modules in {v.root}/modules" + (f" tagged {a.tag}" if a.tag else ""))
        return 0
    lock = read_lock(game)["modules"]
    for m in mods:
        here = lock.get(m["name"], {}).get("version")
        mark = f"  [installed {here}]" if here else ""
        say(f"{m['name']:<22} {m.get('version', '?'):<8} {m.get('engine', '?'):<6} {m.get('description', '')}{mark}")
    return 0


def cmd_search(v: Vault, game: Path, a) -> int:
    words = [w.lower() for w in a.words]
    hits = []
    for m in v.modules():
        hay = " ".join([m["name"], m.get("description", ""), " ".join(m.get("tags", []))]).lower()
        readme = Path(m["_dir"]) / "README.md"
        hay += " " + (readme.read_text().lower() if readme.exists() else "")
        score = sum(hay.count(w) for w in words)
        if all(w in hay for w in words):
            hits.append((score, m))
    for _, m in sorted(hits, key=lambda x: -x[0]):
        say(f"{m['name']:<22} {m.get('version', '?'):<8} {m.get('description', '')}")
    found = [l for l in L.all_lessons(v) if all(w in (l.get("title", "") + l["body"]).lower() for w in words)]
    for l in found[:5]:
        say(f"lesson: {l['id']}  {l.get('title', '')}")
    return 0 if hits or found else 3


def cmd_show(v: Vault, game: Path, a) -> int:
    m = v.module(a.name)
    say(f"{m['name']} {m.get('version')} ({m.get('engine')} {m.get('engine_min', '')}+) · installs to {m.get('install_dir')}")
    say(f"files: {', '.join(m.get('files', []))}")
    if m.get("autoloads"):
        say(f"autoloads: {', '.join(f'{k} -> {v_}' for k, v_ in m['autoloads'].items())}")
    if m.get("input_actions"):
        say(f"input actions: {', '.join(m['input_actions'])}")
    if m.get("external_refs"):
        say(f"WARNING not self-contained: {', '.join(m['external_refs'])}")
    o = m.get("origin", {})
    say(f"origin: {o.get('game', '?')} {o.get('commit', '')} {o.get('harvested', '')}")
    readme = Path(m["_dir"]) / "README.md"
    if readme.exists():
        say("\n" + readme.read_text())
    return 0


def cmd_harvest(v: Vault, game: Path, a) -> int:
    m = M.harvest(v, game, a.name, a.paths, a.description or "", [t for t in (a.tags or "").split(",") if t],
                  a.part, a.install_dir)
    say(f"harvested {a.name} {m['version']}: {len(m['files'])} file(s) -> {v.module_dir(a.name)}")
    if m["autoloads"]:
        say(f"  autoloads: {', '.join(m['autoloads'])}")
    if m["input_actions"]:
        say(f"  input actions: {', '.join(m['input_actions'])}")
    for w in m["_warnings"]:
        say(f"  WARNING {w}")
    say(f"next: write {v.module_dir(a.name)}/README.md, add a test scenario, then vault.sh verify {a.name}")
    return 1 if m["external_refs"] else 0


def cmd_add(v: Vault, game: Path, a) -> int:
    for line in M.add(v, game, a.name, a.dir, a.force):
        say(line)
    say(f"recorded in modules.lock.json; usage: vault.sh show {a.name}")
    return 0


def cmd_outdated(v: Vault, game: Path, a) -> int:
    lock = read_lock(game)["modules"]
    if not lock:
        say("no vault modules installed here")
        return 0
    stale = 0
    for name, e in sorted(lock.items()):
        try:
            latest = v.module(name)["version"]
        except VaultError:
            say(f"{name:<22} {e['version']:<8} (no longer in the vault)")
            continue
        changed = M.local_changes(game, name)
        flag = "newer in vault" if newer(latest, e["version"]) else "up to date"
        stale += flag != "up to date"
        say(f"{name:<22} {e['version']:<8} vault {latest:<8} {flag}" + (f" · {len(changed)} local edit(s)" if changed else ""))
    return 1 if stale else 0


def cmd_diff(v: Vault, game: Path, a) -> int:
    changed = M.local_changes(game, a.name)
    say("\n".join(changed) if changed else "no local changes")
    return 1 if changed else 0


def cmd_update(v: Vault, game: Path, a) -> int:
    for line in M.update(v, game, a.name, a.force):
        say(line)
    return 0


def cmd_push(v: Vault, game: Path, a) -> int:
    m = M.push(v, game, a.name, a.part)
    say(f"pushed {a.name} {m['version']} to the vault; run vault.sh verify {a.name}, then commit the template repo")
    return 0


def cmd_verify(v: Vault, game: Path, a) -> int:
    import verify
    names = [m["name"] for m in v.modules()] if a.all else [a.name]
    worst = "pass"
    for n in names:
        status, rows = verify.verify(v, n, a.keep)
        say(f"{MARK[status]} {n}")
        for r in rows:
            if r["status"] != "pass" or a.verbose:
                say(f"       {MARK[r['status']]} {r['check']}: {r['detail']}")
        worst = "fail" if "fail" in (worst, status) else "not_assessed" if "not_assessed" in (worst, status) else "pass"
    say(f"STATUS: {worst}")
    return {"pass": 0, "fail": 1}.get(worst, 3)


def cmd_lessons(v: Vault, game: Path, a) -> int:
    found = L.find(v, [t for t in (a.tag or "").split(",") if t], a.skill or "", a.engine or "", a.text or "", a.all)
    for l in found:
        first = next((ln for ln in l["body"].splitlines() if ln.strip()), "")
        say(f"{l['id']}  [{l.get('kind', '?')}{', ' + l['status'] if l['status'] != 'active' else ''}] {l.get('title', '')}")
        say(f"    {first[:160]}")
    if not found:
        say("no matching lessons")
    return 0


def cmd_lesson(v: Vault, game: Path, a) -> int:
    body = Path(a.body_file).read_text() if a.body_file else (a.body or "")
    p = L.add(v, a.title, body, a.kind, [t for t in (a.tags or "").split(",") if t],
              [s for s in (a.skills or "").split(",") if s], a.engine or engine_of(game), a.game or game_name(game))
    say(f"lesson saved: {p}")
    return 0


def cmd_promote(v: Vault, game: Path, a) -> int:
    kind, path = L.promote(v, a.lesson, a.skill)
    if kind == "addendum":
        say(f"added to {path}: read beside the library skill '{a.skill}' from now on")
    else:
        say(f"lesson marked promoted; apply it to the studio skill with: /skill-improve {a.skill} (finding: lesson {a.lesson})")
    return 0


def cmd_addenda(v: Vault, game: Path, a) -> int:
    text = L.addenda(v, a.skill)
    say(text if text else f"no addenda for {a.skill}")
    return 0


def cmd_register(v: Vault, game: Path, a) -> int:
    v.register_game(game.resolve(), a.name or game_name(game), engine_of(game))
    say(f"registered {a.name or game_name(game)} in {v.root / 'games.json'}")
    return 0


def cmd_games(v: Vault, game: Path, a) -> int:
    reg = v.games()["games"]
    if not reg:
        say("no games registered (bin/new-game.sh registers each new game)")
        return 0
    latest = {m["name"]: m["version"] for m in v.modules()}
    for g in reg:
        p = Path(g["path"])
        if not p.exists():
            say(f"{g['name']:<24} (moved or deleted: {p})")
            continue
        lock = read_lock(p)["modules"]
        mods = ", ".join(f"{n} {e['version']}" + (" (update)" if newer(latest.get(n, ""), e["version"]) else "")
                         for n, e in sorted(lock.items())) or "no modules"
        say(f"{g['name']:<24} {engine_of(p):<6} {mods}")        # engine read live: set up after registration
    return 0


def cmd_brief(v: Vault, game: Path, a) -> int:
    eng = engine_of(game)
    mods = [m for m in v.modules() if eng == "any" or m.get("engine") in (eng, "any")]
    les = L.find(v, engine="" if eng == "any" else eng)
    if not mods and not les:
        return 0
    parts = [f"Studio vault: {len(mods)} reusable module(s)"] + ([f"{len(les)} lesson(s)" + ("" if eng == "any" else f" for {eng}")] if les else [])
    say(" · ".join(parts) + ". Before building a system, try: bash .claude/scripts/vault.sh search <words>.")
    for l in les[:3]:
        say(f"  lesson: {l.get('title', l['id'])}")
    if (game / "modules.lock.json").exists():
        stale = [n for n, e in read_lock(game)["modules"].items()
                 if any(m["name"] == n and newer(m["version"], e["version"]) for m in mods)]
        if stale:
            say(f"  newer in the vault: {', '.join(stale)} (vault.sh outdated)")
    return 0


def cmd_selftest(v: Vault, game: Path, a) -> int:
    import unittest
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent / "tests"))
    return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="vault", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", help="game root (default: current folder)")
    p.add_argument("--vault", help="vault folder (default: the template's vault/)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list"); s.add_argument("--tag")
    s = sub.add_parser("search"); s.add_argument("words", nargs="+")
    s = sub.add_parser("show"); s.add_argument("name")
    s = sub.add_parser("harvest"); s.add_argument("name"); s.add_argument("paths", nargs="+")
    s.add_argument("--description"); s.add_argument("--tags"); s.add_argument("--install-dir", dest="install_dir")
    s.add_argument("--part", choices=["major", "minor", "patch"], default="minor")
    s = sub.add_parser("add"); s.add_argument("name"); s.add_argument("--dir"); s.add_argument("--force", action="store_true")
    sub.add_parser("outdated")
    s = sub.add_parser("diff"); s.add_argument("name")
    s = sub.add_parser("update"); s.add_argument("name"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("push"); s.add_argument("name"); s.add_argument("--part", choices=["major", "minor", "patch"], default="minor")
    s = sub.add_parser("verify"); s.add_argument("name", nargs="?"); s.add_argument("--all", action="store_true")
    s.add_argument("--keep", action="store_true"); s.add_argument("-v", "--verbose", action="store_true")
    s = sub.add_parser("lessons")
    for k in ("tag", "skill", "engine", "text"):
        s.add_argument(f"--{k}")
    s.add_argument("--all", action="store_true", help="include retired lessons")
    s = sub.add_parser("lesson"); s.add_argument("action", choices=["add"]); s.add_argument("--title", required=True)
    s.add_argument("--kind", choices=L.KINDS, default="pitfall"); s.add_argument("--tags"); s.add_argument("--skills")
    s.add_argument("--engine"); s.add_argument("--game"); s.add_argument("--body"); s.add_argument("--body-file", dest="body_file")
    s = sub.add_parser("promote"); s.add_argument("lesson"); s.add_argument("--skill", required=True)
    s = sub.add_parser("addenda"); s.add_argument("skill")
    s = sub.add_parser("register"); s.add_argument("--name")
    sub.add_parser("games")
    sub.add_parser("brief")
    sub.add_parser("selftest")
    a = p.parse_args(argv)
    game = Path(a.project).resolve() if a.project else Path.cwd()
    try:
        if a.cmd == "verify" and not (a.name or a.all):
            raise VaultError("verify needs a module name or --all")
        return globals()[f"cmd_{a.cmd}"](Vault(locate(game, a.vault)), game, a)
    except VaultError as e:
        say(f"NOT ASSESSED: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
