"""Behavioural evals: run Claude Code headless on a throwaway game and check
what it actually did, not what it says.

Each case (.claude/evals/cases/*.json) is a prompt plus expectations:

  {"id": "...", "prompt": "...", "fixture": "platformer|corridor|none", "library": ["godot"],
   "setup": ["bash .claude/scripts/godot-verify.sh install"], "max_turns": 12,
   "expect": {"uses_any": {"skills": [...], "bash": [...]},   # loaded one of these skills, or ran one of these
              "uses_none": {"skills": [...], "bash": [...]},
              "no_write": true,          # never attempted Write/Edit/NotebookEdit (ask before writing)
              "asks": true,              # the final answer asks the person something
              "says_any": ["..."]}}      # the final answer mentions one of these

A run is made in a fresh game from bin/new-game.sh, with only this project's
settings (no user plugins or MCP servers), the run's model, a turn cap and a
dollar cap. Write and Edit are not pre-approved, so an attempt is visible in
the transcript and denied. Runs are not deterministic: use --n to repeat.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

PASS, FAIL, NA = "pass", "fail", "not_assessed"
ROOT = Path(__file__).resolve().parents[3]
FIXTURES = {
    "platformer": ROOT / ".claude/engines/godot/verify/fixture",
    "corridor": ROOT / ".claude/engines/godot/telemetry/fixture",
}
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}


def load_cases(only: list[str] | None = None) -> list[dict]:
    cases = []
    for p in sorted((ROOT / ".claude/evals/cases").glob("*.json")):
        c = json.loads(p.read_text())
        c["_file"] = p.name
        if not only or c["id"] in only:
            cases.append(c)
    return cases


def parse_stream(text: str) -> dict:
    """Tool calls, loaded skills, the final answer and the cost from stream-json output."""
    tools, final, cost, turns, error = [], "", None, None, None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for block in (ev.get("message") or {}).get("content", []) or []:
                if block.get("type") == "tool_use":
                    tools.append({"name": block.get("name", ""), "input": block.get("input") or {}})
        elif ev.get("type") == "result":
            final = ev.get("result") or ""
            cost = ev.get("total_cost_usd")
            turns = ev.get("num_turns")
            if ev.get("is_error") or ev.get("subtype", "success") != "success":
                error = ev.get("subtype") or "error"
    return {"tools": tools, "skills": loaded_skills(tools), "bash": [t["input"].get("command", "") for t in tools if t["name"] == "Bash"],
            "writes": [t for t in tools if t["name"] in WRITE_TOOLS], "final": final, "cost": cost, "turns": turns, "error": error}


def loaded_skills(tools: list[dict]) -> list[str]:
    names = []
    for t in tools:
        i = t["input"]
        if t["name"] == "Skill" and i.get("skill"):
            names.append(str(i["skill"]).split(":")[-1].lstrip("/"))
        paths = [i.get("file_path", "")] if t["name"] == "Read" else ([i.get("command", "")] if t["name"] == "Bash" else [])
        for p in paths:
            for part in p.split():
                if part.endswith("SKILL.md"):
                    seg = Path(part).parts
                    names.append(seg[-2] if len(seg) >= 2 else part)
    return sorted(set(names))


def score(case: dict, run: dict) -> tuple[str, list[dict]]:
    if run.get("error") and not run["tools"] and not run["final"]:
        return NA, [{"expect": "run", "status": NA, "detail": f"the run did not complete: {run['error']}"}]
    e = case.get("expect", {})
    rows = []

    def add(name, ok, detail):
        rows.append({"expect": name, "status": PASS if ok else FAIL, "detail": detail})

    if "uses_any" in e:
        want_s, want_b = e["uses_any"].get("skills", []), e["uses_any"].get("bash", [])
        hit_s = [s for s in run["skills"] if s in want_s]
        hit_b = [b for b in run["bash"] if any(w in b for w in want_b)]
        add("uses one of", bool(hit_s or hit_b),
            f"loaded {hit_s or '-'}; ran {[h[:60] for h in hit_b] or '-'} (wanted skills {want_s} or commands {want_b})")
    if "uses_none" in e:
        bad_s = [s for s in run["skills"] if s in e["uses_none"].get("skills", [])]
        bad_b = [b for b in run["bash"] if any(w in b for w in e["uses_none"].get("bash", []))]
        add("avoids", not (bad_s or bad_b), f"loaded {bad_s or '-'}; ran {[b[:80] for b in bad_b] or '-'}")
    if e.get("no_write"):
        add("asks before writing", not run["writes"],
            "no write attempted" if not run["writes"] else f"attempted {[w['name'] + ' ' + str(w['input'].get('file_path', ''))[-50:] for w in run['writes']]}")
    if e.get("asks"):
        add("ends with a question", "?" in run["final"][-600:], "asks the person" if "?" in run["final"][-600:] else "no question in the final answer")
    if e.get("says_any"):
        hits = [w for w in e["says_any"] if w.lower() in run["final"].lower()]
        add("mentions", bool(hits), f"said {hits}" if hits else f"none of {e['says_any']}")
    status = FAIL if any(r["status"] == FAIL for r in rows) else PASS if rows else NA
    return status, rows


def make_game(case: dict, base: Path) -> Path:
    game = base / "game"
    r = subprocess.run(["bash", str(ROOT / "bin/new-game.sh"), str(game), *case.get("library", [])], capture_output=True, text=True,
                       env={**__import__("os").environ, "SGA_NO_REGISTER": "1"})
    if r.returncode != 0:
        raise RuntimeError(f"new-game.sh failed: {r.stdout[-300:]}{r.stderr[-300:]}")
    fx = FIXTURES.get(case.get("fixture", "none"))
    if fx:
        shutil.copytree(fx, game, dirs_exist_ok=True)
    for cmd in case.get("setup", []):
        subprocess.run(["bash", "-c", cmd], cwd=game, capture_output=True, timeout=300)
    subprocess.run(["git", "-C", str(game), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(game), "-c", "user.name=eval", "-c", "user.email=eval@example.invalid",
                    "commit", "-qm", "eval fixture"], capture_output=True)
    return game


def run_case(case: dict, model: str, budget: float, keep: bool) -> dict:
    base = Path(tempfile.mkdtemp(prefix=f"sga-eval-{case['id']}-"))
    t0 = time.time()
    try:
        game = make_game(case, base)
        cmd = ["claude", "-p", case["prompt"], "--output-format", "stream-json", "--verbose",
               "--max-turns", str(case.get("max_turns", 12)), "--model", model, "--max-budget-usd", f"{budget:.2f}",
               "--setting-sources", "project,local", "--strict-mcp-config", "--permission-mode", "default",
               "--no-session-persistence"]
        p = subprocess.run(cmd, cwd=game, capture_output=True, text=True, timeout=900)
        (base / "stream.jsonl").write_text(p.stdout)
        run = parse_stream(p.stdout)
        if not run["final"] and p.returncode != 0:
            run["error"] = run["error"] or f"claude exited {p.returncode}: {p.stderr.strip()[-200:]}"
    except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        run = {"tools": [], "skills": [], "bash": [], "writes": [], "final": "", "cost": None, "turns": None, "error": str(e)}
    status, rows = score(case, run)
    out = {"id": case["id"], "status": status, "checks": rows, "skills": run["skills"],
           "bash": [b[:160] for b in run["bash"]], "writes": len(run["writes"]), "cost_usd": run["cost"],
           "turns": run["turns"], "seconds": round(time.time() - t0, 1), "final": run["final"][-1200:],
           "error": run.get("error"), "workdir": str(base) if keep else None}
    if not keep:
        shutil.rmtree(base, ignore_errors=True)
    return out
