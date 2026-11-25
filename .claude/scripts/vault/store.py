"""The studio vault: where it lives, what is in it, and what each game installed.

    <vault>/modules/<engine>/<name>/module.json   a reusable system
    <vault>/modules/<engine>/<name>/files/...     its files; internal paths use res://__module__/
    <vault>/modules/<engine>/<name>/tests/*.json  run-and-verify scenarios
    <vault>/lessons/<date>-<slug>.md              what a game taught
    <vault>/addenda/<skill>.md                    corrections and additions to a library skill
    <vault>/games.json                            the games made from this template

The vault is the template repo's vault/ folder, so it is versioned with git and
shared by every game made from the template. A game finds it through
.claude/sga-template (written by bin/new-game.sh); SGA_VAULT overrides.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[3]
TOKEN = "res://__module__"
TEXT_EXT = {".gd", ".tscn", ".tres", ".gdshader", ".cfg", ".json", ".md", ".txt", ".csv", ".gdshaderinc"}
SKIP_EXT = {".import", ".uid"}
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class VaultError(Exception):
    pass


def locate(project: Path, explicit: str | None = None) -> Path:
    if explicit or os.environ.get("SGA_VAULT"):
        return Path(explicit or os.environ["SGA_VAULT"]).expanduser().resolve()
    marker = project / ".claude/sga-template"
    if marker.exists():
        tpl = Path(marker.read_text().strip()).expanduser()
        if (tpl / "vault").is_dir():
            return (tpl / "vault").resolve()
    if (STUDIO / "vault").is_dir():
        return (STUDIO / "vault").resolve()
    home = Path.home() / ".sga/vault"
    home.mkdir(parents=True, exist_ok=True)
    return home


def load_json(p: Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise VaultError(f"{p} is not valid JSON: {e}") from None


def save_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def bump(version: str, part: str = "patch") -> str:
    m = SEMVER.match(version or "0.0.0")
    major, minor, patch = (int(x) for x in m.groups()) if m else (0, 0, 0)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def newer(a: str, b: str) -> bool:
    pa, pb = SEMVER.match(a or ""), SEMVER.match(b or "")
    if not pa or not pb:
        return a != b
    return tuple(map(int, pa.groups())) > tuple(map(int, pb.groups()))


class Vault:
    def __init__(self, root: Path):
        self.root = root

    def module_dir(self, name: str, engine: str = "godot") -> Path:
        return self.root / "modules" / engine / name

    def modules(self) -> list[dict]:
        out = []
        for mj in sorted((self.root / "modules").glob("*/*/module.json")):
            m = load_json(mj, {})
            m["_dir"] = str(mj.parent)
            out.append(m)
        return out

    def module(self, name: str) -> dict:
        hits = [m for m in self.modules() if m.get("name") == name]
        if not hits:
            raise VaultError(f"no module '{name}' in {self.root}/modules (vault.sh list)")
        return hits[0]

    def games(self) -> dict:
        return load_json(self.root / "games.json", {"games": []})

    def register_game(self, path: Path, name: str, engine: str) -> None:
        reg = self.games()
        reg["games"] = [g for g in reg["games"] if Path(g["path"]) != path]
        reg["games"].append({"name": name, "path": str(path), "engine": engine})
        save_json(self.root / "games.json", reg)


def lockfile(project: Path) -> Path:
    return project / "modules.lock.json"


def read_lock(project: Path) -> dict:
    return load_json(lockfile(project), {"modules": {}})


def write_lock(project: Path, lock: dict) -> None:
    save_json(lockfile(project), lock)
