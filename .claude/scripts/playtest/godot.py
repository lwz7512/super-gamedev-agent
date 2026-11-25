"""Godot side: install the telemetry addon, find the engine, run simulations."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[3]
ADDON = STUDIO / ".claude/engines/godot/telemetry/addons/sga_telemetry"
AUTOLOAD = 'Telemetry="*res://addons/sga_telemetry/telemetry.gd"'


class PlaytestError(Exception):
    pass


def find_godot(root: Path) -> str:
    cands = [os.environ.get("GODOT", ""), shutil.which("godot") or "", shutil.which("godot4") or "",
             "/Applications/Godot.app/Contents/MacOS/Godot", str(Path.home() / "Applications/Godot.app/Contents/MacOS/Godot")]
    helper = root / ".claude/hooks/yaml-helper.sh"
    if helper.exists():
        r = subprocess.run(["bash", str(helper), "get_effective_yaml_key", "engine.path"], cwd=root, capture_output=True, text=True)
        p = r.stdout.strip().strip('"')
        if p:
            cands[1:1] = [p, p + "/Contents/MacOS/Godot"]
    for c in cands:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    raise PlaytestError("Godot binary not found (set GODOT=/path/to/godot or engine.path in project.yaml)")


def _set_key(text: str, section: str, key: str, value: str) -> str:
    """Set key=value inside [section] of a project.godot, adding either if missing."""
    line = f"{key}={value}"
    m = re.search(rf"(?m)^\[{re.escape(section)}\]\s*$", text)
    if not m:
        return text.rstrip("\n") + f"\n\n[{section}]\n\n{line}\n"
    nxt = re.search(r"(?m)^\[", text[m.end():])
    body_end = m.end() + nxt.start() if nxt else len(text)
    body = text[m.end():body_end]
    if re.search(rf"(?m)^{re.escape(key)}=", body):
        return text[:m.end()] + re.sub(rf"(?m)^{re.escape(key)}=.*$", line, body) + text[body_end:]
    return text[:m.end()] + f"\n\n{line}\n" + text[m.end():].lstrip("\n")


def install(root: Path, playtest: bool | None, endpoint: str | None, token: str | None, consent: bool | None) -> list[str]:
    pg = root / "project.godot"
    if not pg.exists():
        raise PlaytestError(f"no project.godot in {root}")
    dest = root / "addons/sga_telemetry"
    dest.mkdir(parents=True, exist_ok=True)
    for f in ADDON.iterdir():
        if f.suffix in (".gd", ".md"):
            shutil.copyfile(f, dest / f.name)
    text = pg.read_text(encoding="utf-8")
    done = [f"copied the addon to {dest.relative_to(root)}/"]
    if AUTOLOAD not in text:
        # First in [autoload], so it is ready before the game's own singletons.
        m = re.search(r"(?m)^\[autoload\]\s*$", text)
        if m:
            text = text[:m.end()] + f"\n\n{AUTOLOAD}\n" + text[m.end():].lstrip("\n")
        else:
            text = text.rstrip("\n") + f"\n\n[autoload]\n\n{AUTOLOAD}\n"
        done.append("registered the Telemetry autoload (first in [autoload])")
    if playtest is not None:
        text = _set_key(text, "sga_telemetry", "playtest_build", "true" if playtest else "false")
        done.append(f"sga_telemetry/playtest_build={'true' if playtest else 'false'}")
    if endpoint is not None:
        text = _set_key(text, "sga_telemetry", "endpoint", f'"{endpoint}"')
        done.append(f"sga_telemetry/endpoint={endpoint or '(none)'}")
    if token is not None:
        text = _set_key(text, "sga_telemetry", "token", f'"{token}"')
        done.append("sga_telemetry/token set")
    if consent is not None:
        text = _set_key(text, "sga_telemetry", "require_consent", "true" if consent else "false")
        done.append(f"sga_telemetry/require_consent={'true' if consent else 'false'}")
    pg.write_text(text, encoding="utf-8")
    return done


def installed(root: Path) -> bool:
    pg = root / "project.godot"
    return (root / "addons/sga_telemetry/telemetry.gd").exists() and pg.exists() and AUTOLOAD in pg.read_text(encoding="utf-8")


def simulate(root: Path, out: Path, bot: str, runs: int, parallel: int, seed: int, frames: int, stall: int,
             watch: str, scene: str, timeout: int, extra: list[str]) -> list[dict]:
    godot = find_godot(root)
    r = subprocess.run([godot, "--headless", "--path", str(root), "--import"], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise PlaytestError(f"godot --import failed: {r.stderr[-300:]}")
    out.mkdir(parents=True, exist_ok=True)

    def one(i: int) -> dict:
        d = out / f"run-{i:04d}"
        d.mkdir(exist_ok=True)
        cmd = [godot, "--headless", "--path", str(root), "--fixed-fps", "60", *([scene] if scene else []), *extra, "--",
               f"--sga-sim={bot}", f"--sga-run={i}", f"--sga-seed={seed + i}", f"--sga-frames={frames}",
               f"--sga-stall={stall}", f"--sga-telemetry-dir={d}"] + ([f"--sga-watch={watch}"] if watch else [])
        t0 = time.time()
        log = open(d / "godot.log", "w")
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            (d / "killed").write_text(f"no exit within {timeout}s (hang or infinite loop)\n")
            code = None
        log.close()
        return {"run": i, "exit": code, "seconds": round(time.time() - t0, 2), "dir": str(d)}

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        return list(pool.map(one, range(runs)))
