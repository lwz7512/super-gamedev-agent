"""playtest: telemetry, simulation bots, collection and analysis (run through playtest.sh).

  init                         production/playtest/config.json (funnel, thresholds)
  install [opts]               add the sga_telemetry addon + Telemetry autoload to the Godot game
  simulate <bot> [opts]        headless bot runs in parallel: monkey, or res://tests/bots/<x>.gd
  collect [opts]               run the HTTP collector for playtest sessions (foreground)
  ingest <file|dir|zip>...     bring session files from testers into production/playtest/sessions/
  report [opts]                Markdown report + charts from everything collected
  check [opts]                 the threshold checks only (exit 0 pass / 1 fail / 3 not assessed)
  status                       what data there is
  selftest                     run this tool's own tests

Exit: 0 pass/done · 1 a check failed · 3 not assessed or a problem to fix.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze  # noqa: E402
import godot  # noqa: E402

PB = Path("production/playtest")
MARK = {"pass": "ok  ", "fail": "FAIL", "not_assessed": "N/A "}


def say(s: str = "") -> None:
    print(s, flush=True)


def root_of(args) -> Path:
    return Path(args.project).resolve() if args.project else Path.cwd()


def config(root: Path) -> dict:
    p = root / PB / "config.json"
    if not p.exists():
        return dict(analyze.DEFAULT_CONFIG)
    try:
        return {**analyze.DEFAULT_CONFIG, **json.loads(p.read_text())}
    except json.JSONDecodeError as e:
        raise godot.PlaytestError(f"{p} is not valid JSON: {e}") from None


def charts_ok() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def data_dirs(root: Path, only: str) -> list[Path]:
    people = [root / PB / "sessions", root / PB / "inbox"]
    sims = [root / PB / "sim"]
    return people if only == "players" else sims if only == "sims" else people + sims


def cmd_init(root: Path, args) -> int:
    p = root / PB / "config.json"
    if p.exists():
        say(f"kept {p.relative_to(root)}")
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = dict(analyze.DEFAULT_CONFIG)
    cfg["funnel"] = ["session_start", "level_start level=1", "level_end level=1"]
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    say(f"wrote {p.relative_to(root)}: set the funnel steps and thresholds for this game")
    return 0


def cmd_install(root: Path, args) -> int:
    for line in godot.install(root, args.playtest, args.endpoint, args.token,
                              None if args.consent is None else args.consent == "required"):
        say(line)
    say("In game code: Telemetry.event(\"level_start\", {\"level\": 1}), Telemetry.progress(\"checkpoint\"), "
        "Telemetry.event(\"death\", {\"pos\": player.global_position}), Telemetry.run_end(\"won\").")
    return 0


def cmd_simulate(root: Path, args) -> int:
    if not godot.installed(root):
        say("NOT ASSESSED: telemetry is not installed in this game (playtest.sh install)")
        return 3
    label = args.label or f"{Path(args.bot).stem}-{datetime.now():%Y%m%d-%H%M%S}"
    out = root / PB / "sim" / label
    n = 2
    while out.exists():                 # never mix a new batch into an old one
        out = root / PB / "sim" / f"{label}-{n}"
        n += 1
    say(f"simulating {args.runs} runs of {args.bot}, {args.parallel} at a time -> {out.relative_to(root)}/")
    res = godot.simulate(root, out, args.bot, args.runs, args.parallel, args.seed, args.frames, args.stall,
                         args.watch, args.scene, args.timeout, [])
    killed = sum(1 for r in res if r["exit"] is None)
    sessions, notes = analyze.load([out])
    cfg = config(root)
    result = analyze.analyse(sessions, cfg)
    for n in notes:
        say(f"note: {n}")
    for b in result["sim"]:
        say(f"{b['bot']}: {b['runs']} runs · {b['outcomes']} · win rate {b['win_rate']:.0%} · stall rate {b['stall_rate']:.0%}"
            + (f" · median {b['median_seconds_to_win']} s to win" if b["median_seconds_to_win"] is not None else ""))
        for s in b["stalls"][:5]:
            say(f"  stuck: run {s['run']} {s['outcome']} {s['state'] or ''}")
    for e in result["sim_errors"][:5]:
        say(f"  error in {e['sessions']} run(s): {e['message']} ({e['where']})")
    if killed:
        say(f"  {killed} run(s) killed after {args.timeout}s without exiting (a hang)")
    missing = sum(1 for r in res if not any(Path(r["dir"]).glob("*.jsonl")))
    if missing:
        say(f"  {missing} run(s) wrote no telemetry (see their godot.log)")
    from report import write
    rp = write(result, out, f"Simulation: {label}", cfg, charts_ok())
    say(f"report: {rp}")
    bot_checks = [c for c in result["checks"] if c["check"].startswith("bot ")]
    status = analyze.overall(bot_checks) if sessions else "not_assessed"
    if missing and status == "pass":
        status = "not_assessed"
    say(f"STATUS: {status}")
    return {"pass": 0, "fail": 1}.get(status, 3)


def cmd_collect(root: Path, args) -> int:
    import collector
    d = (root / PB / "inbox") if not args.dir else Path(args.dir).resolve()
    srv = collector.serve(d, args.host, args.port, args.token or os.environ.get("PLAYTEST_TOKEN", ""))
    try:
        lan = socket.gethostbyname(socket.gethostname())
    except OSError:
        lan = "<this machine's address>"
    say(f"collecting into {d}")
    say(f"game endpoint: http://{lan}:{args.port}/v1/events  (playtest.sh install --endpoint <that URL>)")
    say("Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_ingest(root: Path, args) -> int:
    dest = root / PB / "sessions"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in args.paths:
        p = Path(src).expanduser()
        if not p.exists():
            say(f"skip {src}: not found")
            continue
        if p.suffix == ".zip":
            with zipfile.ZipFile(p) as z:
                for name in z.namelist():
                    base = Path(name).name
                    if base.endswith((".jsonl", ".png")) and not base.startswith("."):
                        (dest / base).write_bytes(z.read(name))    # flattened: no paths from the archive
                        n += base.endswith(".jsonl")
        else:
            files = [p] if p.is_file() else list(p.rglob("*.jsonl")) + list(p.rglob("*-feedback-*.png"))
            for f in files:
                shutil.copyfile(f, dest / f.name)
                n += f.suffix == ".jsonl"
    say(f"ingested {n} session file(s) into {dest.relative_to(root)}/")
    return 0 if n else 3


def _analyse(root: Path, args) -> tuple[dict, dict, list[str]]:
    cfg = config(root)
    dirs = [Path(d).resolve() for d in args.dirs] if args.dirs else data_dirs(root, args.only)
    sessions, notes = analyze.load(dirs)
    return analyze.analyse(sessions, cfg), cfg, notes


def cmd_report(root: Path, args) -> int:
    result, cfg, notes = _analyse(root, args)
    label = args.label or f"{datetime.now():%Y-%m-%d}"
    from report import write
    p = write(result, root / PB / "reports" / label, args.title or f"Playtest report {label}", cfg, charts_ok())
    for n in notes:
        say(f"note: {n}")
    if not charts_ok():
        say("note: Pillow not found, so the report has no charts (bash .claude/scripts/asset-forge.sh setup)")
    return _print_checks(result, f"report: {p}")


def cmd_check(root: Path, args) -> int:
    result, _, notes = _analyse(root, args)
    for n in notes:
        say(f"note: {n}")
    return _print_checks(result, "")


def _print_checks(result: dict, tail: str) -> int:
    for c in result["checks"]:
        say(f"{MARK[c['status']]} {c['check']}: {c['detail']}")
    if tail:
        say(tail)
    status = analyze.overall(result["checks"])
    say(f"STATUS: {status}")
    return {"pass": 0, "fail": 1}.get(status, 3)


def cmd_status(root: Path, args) -> int:
    for name in ("sessions", "inbox", "sim"):
        d = root / PB / name
        n = len(list(d.rglob("*.jsonl"))) if d.exists() else 0
        say(f"{name:<9} {n} session file(s)  {d.relative_to(root)}/")
    say(f"telemetry installed: {'yes' if godot.installed(root) else 'no'}")
    return 0


def cmd_selftest(root: Path, args) -> int:
    import unittest
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent / "tests"))
    return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="playtest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", help="game root (default: current folder)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    s = sub.add_parser("install")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--playtest", dest="playtest", action="store_true", default=None, help="playtest build: record without asking, F8 feedback")
    g.add_argument("--no-playtest", dest="playtest", action="store_false")
    s.add_argument("--endpoint", help="collector URL, e.g. http://192.168.1.20:8787/v1/events ('' to clear)")
    s.add_argument("--token")
    s.add_argument("--consent", choices=["required", "not-required"], help="release builds: ask players first (default required)")
    s = sub.add_parser("simulate")
    s.add_argument("bot", help="monkey, or res://tests/bots/<name>.gd")
    s.add_argument("--runs", type=int, default=50)
    s.add_argument("--parallel", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--frames", type=int, default=3600, help="max frames per run (60 = 1 s of game time)")
    s.add_argument("--stall", type=int, default=900, help="frames without Telemetry.progress() before a run counts as stalled")
    s.add_argument("--watch", default="", help="state to record on stall/timeout, e.g. Player:position,Player:velocity")
    s.add_argument("--scene", default="", help="res:// scene to start in (default: the main scene)")
    s.add_argument("--timeout", type=int, default=120, help="seconds before a run that never exits is killed")
    s.add_argument("--label")
    s = sub.add_parser("collect")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8787)
    s.add_argument("--dir")
    s.add_argument("--token")
    s = sub.add_parser("ingest")
    s.add_argument("paths", nargs="+")
    for name in ("report", "check"):
        s = sub.add_parser(name)
        s.add_argument("--only", choices=["players", "sims", "all"], default="all")
        s.add_argument("--dirs", nargs="*")
        if name == "report":
            s.add_argument("--label")
            s.add_argument("--title")
    sub.add_parser("status")
    sub.add_parser("selftest")
    args = p.parse_args(argv)
    try:
        return globals()[f"cmd_{args.cmd}"](root_of(args), args)
    except godot.PlaytestError as e:
        say(f"NOT ASSESSED: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
