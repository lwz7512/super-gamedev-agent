"""Harvest a system out of one game, add it to another, update it, push it back.

Paths: inside the vault every res:// path that points into the module is
written as res://__module__/...; installing replaces that with the game's
folder for the module (res://modules/<name> by default). References to files
outside the harvested set are listed as external: the module is then not
self-contained, and `verify` will show what breaks.
Godot's uid="..." attributes and .uid/.import files are dropped: uids are
per project, and Godot regenerates them on import.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from store import SKIP_EXT, TEXT_EXT, TOKEN, Vault, VaultError, bump, load_json, read_lock, save_json, sha, write_lock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "playtest"))
from godot import _set_key  # noqa: E402  (shared project.godot editor)

RES = re.compile(r'res://[^"\'\s\)\]>,]+')
UID_ATTR = re.compile(r'\s+uid="uid://[a-z0-9]+"')
ACTION_USE = re.compile(r'(?:is_action(?:_just)?_(?:pressed|released)|get_action_strength|action_press|action_release|'
                        r'get_axis|get_vector|is_action)\(\s*([^)]*)\)')
QUOTED = re.compile(r'["\']([A-Za-z0-9_\-]+)["\']')


def _project_section(text: str, section: str) -> dict[str, str]:
    m = re.search(rf"(?m)^\[{re.escape(section)}\]\s*$", text)
    if not m:
        return {}
    body = text[m.end():]
    nxt = re.search(r"(?m)^\[", body)
    body = body[:nxt.start()] if nxt else body
    out, key = {}, None
    for line in body.splitlines():
        km = re.match(r"^([A-Za-z0-9_/\-\.]+)=(.*)$", line)
        if km:
            key = km.group(1)
            out[key] = km.group(2)
        elif key and line.strip():
            out[key] += "\n" + line       # multi-line values (input events)
    return out


def _collect(game: Path, paths: list[str]) -> tuple[Path, list[Path]]:
    files = []
    for p in paths:
        src = (game / p.replace("res://", "")).resolve()
        if not src.exists():
            raise VaultError(f"no such file or folder in the game: {p}")
        if game.resolve() not in src.parents and src != game.resolve():
            raise VaultError(f"{p} is outside the game folder")
        files += [f for f in (src.rglob("*") if src.is_dir() else [src]) if f.is_file() and f.suffix not in SKIP_EXT]
    if not files:
        raise VaultError("nothing to harvest")
    base = Path(os.path.commonpath([str(f.parent) for f in files]))   # the folder holding everything harvested
    return base, sorted(set(files))


def harvest(vault: Vault, game: Path, name: str, paths: list[str], description: str, tags: list[str],
            part: str = "minor", install_dir: str | None = None) -> dict:
    base, files = _collect(game, paths)
    res_base = "res://" + base.relative_to(game.resolve()).as_posix() if base != game.resolve() else "res://"
    res_base = res_base.rstrip("/")
    inside = {"res://" + f.relative_to(game.resolve()).as_posix(): f for f in files}
    pg = (game / "project.godot").read_text(encoding="utf-8") if (game / "project.godot").exists() else ""
    dest = vault.module_dir(name)
    old = load_json(dest / "module.json", {})
    if (dest / "files").exists():
        shutil.rmtree(dest / "files")
    external, actions = set(), set()
    rel_files = []
    for f in files:
        rel = f.relative_to(base).as_posix()
        out = dest / "files" / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix in TEXT_EXT:
            text = f.read_text(encoding="utf-8", errors="replace")
            text = UID_ATTR.sub("", text)

            def swap(m):
                ref = m.group(0)
                if ref in inside:
                    return TOKEN + ref[len(res_base):] if res_base != "res://" else TOKEN + "/" + ref[len("res://"):]
                if not ref.startswith(TOKEN):
                    external.add(ref)
                return ref
            text = RES.sub(swap, text)
            if f.suffix == ".gd":
                for call in ACTION_USE.findall(text):
                    actions.update(QUOTED.findall(call))
            out.write_text(text, encoding="utf-8")
        else:
            shutil.copyfile(f, out)
        rel_files.append(rel)
    autoloads = {}
    for k, v in _project_section(pg, "autoload").items():
        target = v.strip('"').lstrip("*")
        if target in inside:
            autoloads[k] = inside[target].relative_to(base).as_posix()
    defined = _project_section(pg, "input")
    input_actions = {a: defined[a] for a in sorted(actions) if a in defined}
    builtin_missing = sorted(a for a in actions if a not in defined and not a.startswith("ui_"))
    commit = ""
    try:
        commit = subprocess.run(["git", "-C", str(game), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    m = re.search(r'(?m)^config/name="([^"]*)"', pg)
    module = {
        "name": name,
        "version": bump(old.get("version", "0.0.0"), part) if old else "1.0.0",
        "engine": "godot",
        "engine_min": old.get("engine_min", _feature_version(pg)),
        "description": description or old.get("description", ""),
        "tags": sorted(set(tags or old.get("tags", []))),
        "install_dir": install_dir or old.get("install_dir", f"res://modules/{name.replace('-', '_')}"),
        "files": rel_files,
        "autoloads": autoloads,
        "input_actions": input_actions,
        "requires": old.get("requires", []),
        "tests": old.get("tests", []),
        "external_refs": sorted(external),
        "origin": {"game": m.group(1) if m else game.name, "path": str(game), "commit": commit,
                   "paths": paths, "harvested": date.today().isoformat()},
        "license": old.get("license", "own"),
    }
    save_json(dest / "module.json", module)
    if not (dest / "README.md").exists():
        (dest / "README.md").write_text(f"# {name}\n\n{description}\n\nHarvested from {module['origin']['game']}. "
                                        "Describe how to use it here: the vault skill shows this file before adding the module.\n")
    log = dest / "CHANGELOG.md"
    entry = f"- {module['version']} ({module['origin']['harvested']}): harvested from {module['origin']['game']}" \
            + (f" @ {commit}" if commit else "") + "\n"
    log.write_text((log.read_text() if log.exists() else "# Changelog\n\n") + entry)
    module["_warnings"] = ([f"references outside the module: {', '.join(sorted(external))}"] if external else []) + \
                          ([f"input actions used but not defined in project.godot: {', '.join(builtin_missing)}"] if builtin_missing else [])
    return module


def _feature_version(pg: str) -> str:
    m = re.search(r'config/features=PackedStringArray\("(\d+\.\d+)', pg)
    return m.group(1) if m else ""


def add(vault: Vault, game: Path, name: str, install_dir: str | None = None, force: bool = False) -> list[str]:
    m = vault.module(name)
    src = Path(m["_dir"]) / "files"
    target_res = (install_dir or m["install_dir"]).rstrip("/")
    target = game / target_res.replace("res://", "")
    lock = read_lock(game)
    if target.exists() and any(target.iterdir()) and name not in lock["modules"] and not force:
        raise VaultError(f"{target_res} already exists and was not installed by the vault (pass --force to overwrite)")
    for r in m.get("requires", []):
        if r not in lock["modules"]:
            raise VaultError(f"'{name}' needs '{r}' first: vault.sh add {r}")
    hashes = {}
    for rel in m["files"]:
        s, d = src / rel, target / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.suffix in TEXT_EXT:
            d.write_text(s.read_text(encoding="utf-8").replace(TOKEN, target_res), encoding="utf-8")
        else:
            shutil.copyfile(s, d)
        hashes[rel] = sha(d)
    done = [f"copied {len(m['files'])} file(s) to {target_res}/"]
    pg = game / "project.godot"
    if pg.exists():
        text = pg.read_text(encoding="utf-8")
        for k, rel in m.get("autoloads", {}).items():
            if not re.search(rf"(?m)^{re.escape(k)}=", text):
                text = _set_key(text, "autoload", k, f'"*{target_res}/{rel}"')
                done.append(f"autoload {k}")
        for a, val in m.get("input_actions", {}).items():
            if not re.search(rf"(?m)^{re.escape(a)}=", text):
                text = _set_key(text, "input", a, val)
                done.append(f"input action {a}")
        pg.write_text(text, encoding="utf-8")
    lock["modules"][name] = {"version": m["version"], "dir": target_res, "files": hashes}
    write_lock(game, lock)
    return done


def local_changes(game: Path, name: str) -> list[str]:
    entry = read_lock(game)["modules"].get(name)
    if not entry:
        raise VaultError(f"'{name}' is not installed here (vault.sh add {name})")
    base = game / entry["dir"].replace("res://", "")
    return [rel for rel, h in entry["files"].items() if not (base / rel).exists() or sha(base / rel) != h]


def update(vault: Vault, game: Path, name: str, force: bool) -> list[str]:
    entry = read_lock(game)["modules"].get(name)
    if not entry:
        raise VaultError(f"'{name}' is not installed here")
    changed = local_changes(game, name)
    if changed and not force:
        raise VaultError(f"local edits in {', '.join(changed)}: push them first (vault.sh push {name}) "
                         f"or overwrite with --force (copies are kept as .orig)")
    base = game / entry["dir"].replace("res://", "")
    for rel in changed:
        p = base / rel
        if p.exists():
            shutil.copyfile(p, p.with_name(p.name + ".orig"))
    return add(vault, game, name, entry["dir"], force=True)


def push(vault: Vault, game: Path, name: str, part: str = "minor") -> dict:
    """Take the game's improved copy back into the vault as a new version."""
    entry = read_lock(game)["modules"].get(name)
    if not entry:
        raise VaultError(f"'{name}' is not installed here")
    m = vault.module(name)
    base = game / entry["dir"].replace("res://", "")
    dest = Path(m["_dir"]) / "files"
    files = []
    for f in sorted(base.rglob("*")):
        if f.is_file() and f.suffix not in SKIP_EXT and not f.name.endswith(".orig"):
            rel = f.relative_to(base).as_posix()
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if f.suffix in TEXT_EXT:
                out.write_text(UID_ATTR.sub("", f.read_text(encoding="utf-8")).replace(entry["dir"], TOKEN), encoding="utf-8")
            else:
                shutil.copyfile(f, out)
            files.append(rel)
    meta = load_json(Path(m["_dir"]) / "module.json", {})
    meta["files"] = files
    meta["version"] = bump(meta.get("version", "1.0.0"), part)
    save_json(Path(m["_dir"]) / "module.json", meta)
    log = Path(m["_dir"]) / "CHANGELOG.md"
    log.write_text((log.read_text() if log.exists() else "# Changelog\n\n") +
                   f"- {meta['version']} ({date.today().isoformat()}): pushed back from {game.name}\n")
    lock = read_lock(game)
    lock["modules"][name] = {"version": meta["version"], "dir": entry["dir"], "files": {r: sha(base / r) for r in files}}
    write_lock(game, lock)
    return meta
