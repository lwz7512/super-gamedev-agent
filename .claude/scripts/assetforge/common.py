"""Shared paths, config and result vocabulary for asset-forge.

Project files (all under the game's root):
  assets/style.json      the art and audio lock: sizes, palette, key colour, providers
  assets/manifest.json   every asset: id, kind, target path, prompt, provider, status
  assets/provenance.yaml where each shipped file came from (the studio's format)
  assets/_raw/<id>/      generator output before cleanup (Godot skips it: .gdignore)
  assets/_inbox/         files dropped in by hand, waiting for `ingest`
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

PASS, FAIL, NA = "pass", "fail", "not_assessed"
RANK = {PASS: 0, NA: 1, FAIL: 2}          # not_assessed outranks pass, never hides a fail

STUDIO = Path(__file__).resolve().parents[3]

DEFAULT_STYLE = {
    "schema": 1,
    "art": {
        "kind": "pixel",
        "palette": [],
        "max_colors": 32,
        "alpha": "binary",
        "key_color": "#ff00ff",
        "preview_background": "#1c1a33",
        "style_prompt": "",
        "avoid": "text, letters, watermark, signature, frame, border, drop shadow, ground, scenery, multiple objects",
        "categories": {
            "character": {"size": "32x32", "anchor": "bottom-center", "padding": 1},
            "enemy": {"size": "32x32", "anchor": "bottom-center", "padding": 1},
            "item": {"size": "16x16", "anchor": "center", "padding": 1},
            "tile": {"size": "16x16", "anchor": "fill", "padding": 0},
            "ui": {"size": "32x32", "anchor": "center", "padding": 0},
            "background": {"size": "640x360", "anchor": "fill", "padding": 0, "alpha": "none"},
        },
    },
    "audio": {
        "format": "ogg",
        "sample_rate": 44100,
        "peak_dbfs": -1.0,
        "sfx_max_seconds": 4.0,
        "lead_silence_ms": 40,
    },
    "providers": {
        "openart": {"via": "mcp", "plan": "", "model": ""},
        "elevenlabs": {
            "plan": "",
            "sfx_model": "eleven_text_to_sound_v2",
            "tts_model": "eleven_multilingual_v2",
            "voice_id": "",
            "output_format": "mp3_44100_128",
        },
    },
}

STATUSES = ["planned", "generated", "normalized", "qa-pass", "qa-fail", "imported", "approved"]


class ForgeError(Exception):
    """A problem the user must fix (bad config, missing file); exit 3 = not assessed."""


def project_root(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit).resolve()
        if not p.is_dir():
            raise ForgeError(f"no such project folder: {p}")
        return p
    cwd = Path.cwd()
    for marker in ("assets/manifest.json", "project.godot", "project.yaml", "package.json"):
        if (cwd / marker).exists():
            return cwd
    return cwd


def load_json(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise ForgeError(f"missing {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ForgeError(f"{path} is not valid JSON: {e}") from None


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


class Project:
    def __init__(self, root: Path):
        self.root = root
        self.assets = root / "assets"
        self.style_path = self.assets / "style.json"
        self.manifest_path = self.assets / "manifest.json"
        self.ledger_path = self.assets / "provenance.yaml"
        self.raw = self.assets / "_raw"
        self.inbox = self.assets / "_inbox"
        self.out = root / "production" / "qa" / "assets"

    @property
    def style(self) -> dict:
        return merge(DEFAULT_STYLE, load_json(self.style_path, {}))

    def manifest(self) -> dict:
        m = load_json(self.manifest_path, {"schema": 1, "assets": []})
        ids = [a.get("id") for a in m["assets"]]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ForgeError(f"manifest has duplicate ids: {', '.join(sorted(dupes))}")
        return m

    def save_manifest(self, m: dict) -> None:
        save_json(self.manifest_path, m)

    def entry(self, m: dict, asset_id: str) -> dict:
        for a in m["assets"]:
            if a.get("id") == asset_id:
                return a
        raise ForgeError(f"no asset '{asset_id}' in {self.manifest_path.relative_to(self.root)}")

    def category(self, a: dict) -> dict:
        cats = self.style["art"]["categories"]
        cat = dict(cats.get(a.get("category", ""), {}))
        for k in ("size", "anchor", "padding", "alpha"):
            if k in a:
                cat[k] = a[k]
        return cat

    def ensure_dirs(self) -> None:
        for d in (self.raw, self.inbox):
            d.mkdir(parents=True, exist_ok=True)
            # Godot would import every candidate image; keep raw output out of res://
            (d / ".gdignore").touch()

    def rel(self, p: Path) -> str:
        try:
            return p.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(p)


def parse_size(s: str) -> tuple[int, int]:
    try:
        w, h = s.lower().split("x")
        return int(w), int(h)
    except Exception:
        raise ForgeError(f"bad size '{s}', expected WIDTHxHEIGHT") from None


def hex_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) != 6:
        raise ForgeError(f"bad colour '{s}', expected #rrggbb")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def today() -> str:
    return date.today().isoformat()


def worst(statuses) -> str:
    statuses = list(statuses)
    return max(statuses, key=lambda s: RANK.get(s, 1)) if statuses else NA


def say(msg: str = "") -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
