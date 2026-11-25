"""evals: does the combined studio still work as one system? (run through evals.sh)

  static                      integrity checks: free, deterministic, run in CI
  selftests [--godot]         every layer's own test suite, summarised
  behavior [--case ID]... [--n N] [--model M] [--budget USD] [--yes]
                              real Claude Code runs on throwaway games, scored on
                              what the agent did (skills loaded, commands run,
                              writes attempted, questions asked). Costs money:
                              without --yes it prints the plan and exits 4.
  cases                       list the behaviour cases
  library-triggers            the vendored library's own offline trigger-eval check
  all                         static + selftests
  selftest                    this tool's tests

Exit: 0 pass · 1 fail · 3 not assessed · 4 a paid run is waiting for the person's yes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import behavior  # noqa: E402
import static  # noqa: E402

PASS, FAIL, NA = "pass", "fail", "not_assessed"
MARK = {PASS: "ok  ", FAIL: "FAIL", NA: "N/A "}
ROOT = Path(__file__).resolve().parents[3]


def say(s: str = "") -> None:
    print(s, flush=True)


def overall(statuses: list[str]) -> str:
    return FAIL if FAIL in statuses else NA if (NA in statuses or not statuses) else PASS


def code_of(status: str) -> int:
    return {PASS: 0, FAIL: 1}.get(status, 3)


def cmd_static(a) -> int:
    rows = static.run()
    for r in rows:
        say(f"{MARK[r['status']]} {r['check']}: {r['detail']}")
        for i in r["items"][:10]:
            say(f"       - {i}")
    s = overall([r["status"] for r in rows])
    say(f"STATUS: {s}")
    return code_of(s)


SUITES = [
    ("run-and-verify (layer 1)", ["bash", ".claude/scripts/godot-verify.sh", "selftest", "--timeout", "90"], True),
    ("asset production (layer 2)", ["bash", ".claude/scripts/asset-forge.sh", "selftest"], False),
    ("playtest data (layer 3)", ["bash", ".claude/scripts/playtest.sh", "selftest"], False),
    ("studio vault (layer 4)", ["bash", ".claude/scripts/vault.sh", "selftest"], False),
    ("evals (layer 5)", ["bash", ".claude/scripts/evals.sh", "selftest"], False),
]


def cmd_selftests(a) -> int:
    env = dict(os.environ)
    if a.godot:
        env["SGA_TEST_GODOT"] = "1"
    statuses = []
    for name, cmd, needs_godot in SUITES:
        if needs_godot and not a.godot:
            if getattr(a, "without_godot", False):
                say(f"skip {name}: left out on request (--without-godot); its own CI workflow runs it with Godot")
            else:
                say(f"N/A  {name}: needs Godot (add --godot)")
                statuses.append(NA)
            continue
        p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=1800)
        out = (p.stdout + p.stderr).strip().splitlines()
        tail = next((l for l in reversed(out) if l.startswith(("OK", "FAILED", "SELFTEST", "NOT ASSESSED"))), out[-1] if out else "")
        skipped = "skipped" in tail
        status = PASS if p.returncode == 0 else (NA if p.returncode == 3 else FAIL)
        statuses.append(status)
        say(f"{MARK[status]} {name}: {tail}" + ("  (some tests skipped: add --godot)" if skipped and not a.godot else ""))
    s = overall(statuses)
    say(f"STATUS: {s}")
    return code_of(s)


def cmd_cases(a) -> int:
    for c in behavior.load_cases():
        say(f"{c['id']:<26} {c.get('about', '')}")
    return 0


def cmd_behavior(a) -> int:
    if not shutil.which("claude"):
        say("NOT ASSESSED: the claude CLI is not on PATH")
        return 3
    cases = behavior.load_cases(a.case or None)
    if not cases:
        say("NOT ASSESSED: no matching cases (evals.sh cases)")
        return 3
    runs = len(cases) * a.n
    plan = f"{runs} Claude Code run(s) ({len(cases)} case(s) x {a.n}) on model {a.model}, at most ${a.budget:.2f} each, ${runs * a.budget:.2f} in all"
    if not a.yes:
        say(f"NEEDS APPROVAL: {plan}")
        say("Ask the person; on yes, run again with --yes.")
        return 4
    say(plan)
    label = a.label or f"{datetime.now():%Y%m%d-%H%M%S}"
    out = ROOT / "production/evals" / label
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for c in cases:
        for i in range(a.n):
            r = behavior.run_case(c, a.model, a.budget, a.keep)
            r["repeat"] = i + 1
            results.append(r)
            cost = f"${r['cost_usd']:.3f}" if isinstance(r["cost_usd"], (int, float)) else "$?"
            say(f"{MARK[r['status']]} {c['id']} #{i + 1}  ({r['turns']} turns, {cost}, {r['seconds']}s)")
            for ch in r["checks"]:
                if ch["status"] != PASS or a.verbose:
                    say(f"       {MARK[ch['status']]} {ch['expect']}: {ch['detail']}")
            if r.get("error"):
                say(f"       note: {r['error']}")
    by_case = {}
    for r in results:
        by_case.setdefault(r["id"], []).append(r["status"])
    summary = [{"id": k, "passed": v.count(PASS), "runs": len(v), "status": overall(v)} for k, v in by_case.items()]
    total = sum(r["cost_usd"] or 0 for r in results)
    (out / "results.json").write_text(json.dumps({"model": a.model, "results": results, "summary": summary,
                                                  "cost_usd": round(total, 4)}, indent=2))
    md = [f"# Behaviour evals {label}\n", f"Model `{a.model}` · {runs} run(s) · ${total:.2f}\n",
          "| Case | Passed | Status |", "|---|---|---|"]
    md += [f"| {s['id']} | {s['passed']}/{s['runs']} | {s['status']} |" for s in summary]
    md += ["", "## Runs", ""]
    for r in results:
        md.append(f"### {r['id']} #{r['repeat']}: {r['status']}\n")
        md += [f"- {ch['status']}: {ch['expect']}: {ch['detail']}" for ch in r["checks"]]
        md.append(f"- skills loaded: {', '.join(r['skills']) or '-'}")
        md.append(f"- commands: {'; '.join(b[:80] for b in r['bash'][:8]) or '-'}\n")
    (out / "report.md").write_text("\n".join(md) + "\n")
    s = overall([x["status"] for x in summary])
    say(f"cost ${total:.2f} · report {out / 'report.md'}")
    say(f"STATUS: {s}")
    return code_of(s)


def cmd_library_triggers(a) -> int:
    lib = ROOT / ".claude/library"
    p = subprocess.run(["python3", "-I", "scripts/run-trigger-evals.py", "--check"], cwd=lib, capture_output=True, text=True)
    say((p.stdout + p.stderr).strip())
    return 0 if p.returncode == 0 else 1


def cmd_all(a) -> int:
    s1 = cmd_static(a)
    say("")
    s2 = cmd_selftests(a)
    return max(s1, s2) if 1 in (s1, s2) else (3 if 3 in (s1, s2) else 0)


def cmd_selftest(a) -> int:
    import unittest
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent / "tests"))
    return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="evals", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("static")
    for name in ("selftests", "all"):
        s = sub.add_parser(name)
        s.add_argument("--godot", action="store_true", help="include the tests that run Godot")
        s.add_argument("--without-godot", dest="without_godot", action="store_true",
                       help="leave the Godot-only suite out (stated, not counted), e.g. in CI where another workflow runs it")
    sub.add_parser("cases")
    s = sub.add_parser("behavior")
    s.add_argument("--case", action="append")
    s.add_argument("--n", type=int, default=1)
    s.add_argument("--model", default="sonnet")
    s.add_argument("--budget", type=float, default=0.75, help="dollar cap per run")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--keep", action="store_true", help="keep each run's game folder and transcript")
    s.add_argument("--label")
    s.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("library-triggers")
    sub.add_parser("selftest")
    a = p.parse_args(argv)
    return globals()[f"cmd_{a.cmd.replace('-', '_')}"](a)


if __name__ == "__main__":
    sys.exit(main())
