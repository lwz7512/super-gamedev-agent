"""playtest tests: run with `playtest.sh selftest`.

Each check is seen failing on data that should fail it, passing on data that
should pass it, and not assessed when there is nothing to judge. The Godot
integration (SGA_TEST_GODOT=1) plays the telemetry fixture with real bots,
sends a session through the collector, detects a crash and submits in-game
feedback through the run-and-verify harness.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import analyze  # noqa: E402
import cli  # noqa: E402
import collector  # noqa: E402
import godot  # noqa: E402
from analyze import FAIL, NA, PASS  # noqa: E402

STUDIO = HERE.parents[3]


def row(sid, ev, t=0, f=0, p=None, scene="res://level.tscn", run=None):
    r = {"sid": sid, "ev": ev, "t": t, "f": f, "scene": scene}
    if p is not None:
        r["p"] = p
    if run is not None:
        r["run"] = run
    return r


def session(d: Path, sid: str, rows: list, end=True, bot="", iid="i1") -> Path:
    start = row(sid, "session_start", p={"bot": bot, "iid": iid, "viewport": [640, 360], "version": "0.1", "platform": "macOS"})
    rows = [start] + rows + ([row(sid, "session_end", t=rows[-1]["t"] + 1000 if rows else 1000, p={"seconds": 120})] if end else [])
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{sid}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def checks_of(sessions, cfg=None):
    r = analyze.analyse(sessions, cfg or {})
    return {c["check"]: c["status"] for c in r["checks"]}, r


class Analysis(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def load(self):
        return analyze.load([self.d])[0]

    def test_nothing_is_not_assessed(self):
        c, _ = checks_of([])
        self.assertTrue(all(v == NA for v in c.values()), c)
        self.assertEqual(analyze.overall([]), NA)

    def test_crash_rate(self):
        for i in range(10):
            session(self.d, f"s{i}", [row(f"s{i}", "scene", 5)], end=i != 0)
        c, r = checks_of(self.load(), {"thresholds": {"crash_rate": 0.2}})
        self.assertEqual(c["crash rate"], PASS)
        self.assertEqual(r["overview"]["crashed_sessions"], 1)
        c, _ = checks_of(self.load(), {"thresholds": {"crash_rate": 0.05}})
        self.assertEqual(c["crash rate"], FAIL)

    def test_errors_grouped_and_checked(self):
        err = {"type": "script", "message": "Invalid call", "where": "res://p.gd:4"}
        session(self.d, "a", [row("a", "error", 10, p=err), row("a", "error", 20, p=err)])
        session(self.d, "b", [row("b", "scene", 10)])
        c, r = checks_of(self.load())
        self.assertEqual(r["errors"][0]["events"], 2)
        self.assertEqual(r["errors"][0]["sessions"], 1)
        self.assertEqual(c["errors"], FAIL)              # 1 of 2 sessions > 5%
        warn = {"type": "warning", "message": "w", "where": "x"}
        shutil.rmtree(self.d)
        session(self.d, "c", [row("c", "error", 10, p=warn)])
        _, r = checks_of(self.load())
        self.assertEqual(r["errors"], [])               # warnings are not errors

    def test_funnel_order_and_dropoff(self):
        steps = ["session_start", "level_start level=1", "level_end level=1"]
        for i in range(4):
            rows = [row(f"s{i}", "level_start", 1, p={"level": 1})]
            if i < 1:
                rows.append(row(f"s{i}", "level_end", 2, p={"level": 1}))
            session(self.d, f"s{i}", rows)
        # level_end before level_start must not count
        session(self.d, "x", [row("x", "level_end", 1, p={"level": 1}), row("x", "level_start", 2, p={"level": 1})])
        c, r = checks_of(self.load(), {"funnel": steps})
        self.assertEqual([f["sessions"] for f in r["funnel"]], [5, 5, 1])
        self.assertEqual(c["funnel"], FAIL)
        c, _ = checks_of(self.load(), {"funnel": steps, "thresholds": {"funnel_step_dropoff": 0.9}})
        self.assertEqual(c["funnel"], PASS)

    def test_levels_deaths_and_completion(self):
        for i in range(3):
            rows = [row(f"s{i}", "level_start", 1000, p={"level": 2}),
                    row(f"s{i}", "death", 3000, p={"pos": [100, 200]})]
            if i == 0:
                rows.append(row(f"s{i}", "level_end", 31000, p={"level": 2}))
            session(self.d, f"s{i}", rows)
        c, r = checks_of(self.load())
        lv = r["levels"][0]
        self.assertEqual((lv["level"], lv["starts"], lv["completions"], lv["deaths"]), ("2", 3, 1, 3))
        self.assertEqual(lv["median_seconds"], 30.0)
        self.assertEqual(c["level completion"], FAIL)
        self.assertEqual(len(r["positions"]["res://level.tscn"]), 3)

    def test_perf_threshold(self):
        session(self.d, "p", [row("p", "perf", 5000, p={"ft_avg": 16.7, "ft_p95": 41.0, "ft_max": 80, "mem_mb": 120})])
        c, r = checks_of(self.load())
        self.assertEqual(c["frame time"], FAIL)
        self.assertEqual(r["perf"][0]["frame_ms_p95"], 41.0)
        c, _ = checks_of(self.load(), {"thresholds": {"frame_p95_ms": 50}})
        self.assertEqual(c["frame time"], PASS)

    def test_feedback(self):
        session(self.d, "f", [row("f", "feedback", 9000, p={"rating": 2, "text": "lost", "screenshot": "f-shot.png", "recent": ["death"]})])
        c, r = checks_of(self.load())
        self.assertEqual(c["feedback"], FAIL)
        self.assertTrue(r["feedback"][0]["screenshot"].endswith("f-shot.png"))

    def test_bots_kept_apart_and_judged(self):
        for i in range(10):
            sid = f"b{i}"
            out = "won" if i < 9 else "stalled"
            state = {"Player:position": [100, 99999]} if out == "stalled" else {}
            session(self.d, sid, [row(sid, "run_end", 50, f=600, p={"outcome": out, "frames": 600, "state": state}, run=str(i))], bot="monkey")
        c, r = checks_of(self.load())
        self.assertEqual(r["overview"]["player_sessions"], 0)
        b = r["sim"][0]
        self.assertEqual((b["runs"], b["win_rate"], b["stall_rate"], b["left_level"]), (10, 0.9, 0.1, 1))
        self.assertEqual(c["bot monkey"], FAIL)                    # 10% > 5%
        c, _ = checks_of(self.load(), {"thresholds": {"sim_stall_rate": 0.2}})
        self.assertEqual(c["bot monkey"], PASS)

    def test_torn_last_line_is_tolerated(self):
        p = session(self.d, "t", [row("t", "scene", 5)], end=False)
        with open(p, "a") as f:
            f.write('{"sid": "t", "ev": "sce')                  # a crash mid-write
        sessions, notes = analyze.load([self.d])
        self.assertEqual(len(sessions), 1)
        self.assertTrue(any("unreadable" in n for n in notes))


class Collector(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.srv = collector.serve(self.d / "inbox", "127.0.0.1", 0, token="sekret")
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        shutil.rmtree(self.d)

    def post(self, body, token="sekret"):
        req = urllib.request.Request(self.url + "/v1/events", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Playtest-Token": token})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_store_and_reject(self):
        self.assertEqual(self.post([row("abc-1", "scene"), row("abc-1", "death")]), 200)
        self.assertEqual(len((self.d / "inbox/abc-1.jsonl").read_text().splitlines()), 2)
        self.assertEqual(self.post([row("abc-1", "x")], token="wrong"), 401)
        self.assertEqual(self.post({"not": "a list"}), 400)
        self.post([row("../../evil", "x"), row("a/b", "x")])        # file names come from sids
        self.assertEqual(sorted(p.name for p in (self.d / "inbox").iterdir()), ["abc-1.jsonl"])
        self.assertFalse((self.d / "evil.jsonl").exists())


class Cli(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--project", str(self.root), *argv])
        return code, buf.getvalue()

    def test_ingest_zip_is_flattened(self):
        z = self.root / "tester.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("telemetry/s1.jsonl", json.dumps(row("s1", "session_start")) + "\n")
            f.writestr("../../escape.jsonl", "{}\n")
        code, out = self.run_cli("ingest", str(z))
        self.assertEqual(code, 0, out)
        names = sorted(p.name for p in (self.root / "production/playtest/sessions").iterdir())
        self.assertEqual(names, ["escape.jsonl", "s1.jsonl"])        # written inside, never outside
        self.assertFalse((self.root.parent / "escape.jsonl").exists())

    def test_report_writes_markdown_and_charts(self):
        d = self.root / "production/playtest/sessions"
        for i in range(3):
            session(d, f"s{i}", [row(f"s{i}", "level_start", 1, p={"level": 1}),
                                 row(f"s{i}", "death", 2, p={"pos": [320, 200]}),
                                 row(f"s{i}", "level_end", 3, p={"level": 1})])
        self.run_cli("init")
        code, out = self.run_cli("report", "--label", "t")
        rep = self.root / "production/playtest/reports/t"
        self.assertTrue((rep / "report.md").exists(), out)
        try:
            import PIL  # noqa: F401
            self.assertTrue((rep / "levels.png").exists())
            self.assertTrue(any(p.name.startswith("heatmap-players") for p in rep.iterdir()))
        except ImportError:
            pass
        self.assertIn("STATUS:", out)

    def test_install_edits_project_godot(self):
        (self.root / "project.godot").write_text('config_version=5\n\n[application]\n\nconfig/name="x"\n\n'
                                                 '[autoload]\n\nGame="*res://game.gd"\n')
        code, out = self.run_cli("install", "--playtest", "--endpoint", "http://127.0.0.1:8787/v1/events")
        self.assertEqual(code, 0, out)
        t = (self.root / "project.godot").read_text()
        self.assertLess(t.index("Telemetry="), t.index("Game="))     # first autoload
        self.assertIn("playtest_build=true", t)
        self.assertIn('endpoint="http://127.0.0.1:8787/v1/events"', t)
        self.run_cli("install", "--no-playtest")
        t = (self.root / "project.godot").read_text()
        self.assertEqual(t.count("Telemetry="), 1)
        self.assertIn("playtest_build=false", t)
        self.assertNotIn("playtest_build=true", t)
        self.assertTrue(godot.installed(self.root))


def _godot():
    try:
        return godot.find_godot(STUDIO)
    except godot.PlaytestError:
        return None


@unittest.skipUnless(os.environ.get("SGA_TEST_GODOT") == "1" and _godot(), "set SGA_TEST_GODOT=1 with Godot installed")
class GodotTelemetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        shutil.copytree(STUDIO / ".claude/engines/godot/telemetry/fixture", cls.root, dirs_exist_ok=True)
        godot.install(cls.root, None, None, None, None)
        cls.g = _godot()
        subprocess.run([cls.g, "--headless", "--path", str(cls.root), "--import"], capture_output=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        if os.environ.get("SGA_KEEP") != "1":
            shutil.rmtree(cls.root)

    def sim(self, bot, runs, label):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--project", str(self.root), "simulate", bot, "--runs", str(runs), "--parallel", "4",
                             "--frames", "1200", "--stall", "300", "--watch", "Player:position", "--label", label])
        return code, buf.getvalue()

    def test_bots(self):
        code, out = self.sim("res://tests/bots/runner.gd", 4, "runner")
        self.assertEqual(code, 0, out)
        self.assertIn("{'won': 4}", out)
        code, out = self.sim("res://tests/bots/lazy.gd", 3, "lazy")
        self.assertEqual(code, 1, out)                                 # the soft-lock is found
        self.assertIn("stalled", out)
        self.assertIn("[363.9", out)                                   # ...at the pit bottom
        code, out = self.sim("monkey", 8, "monkey")
        self.assertIn("monkey: 8 runs", out)
        self.assertNotIn("wrote no telemetry", out)

    def test_collector_crash_and_session_end(self):
        inbox = self.root / "production/playtest/inbox"
        srv = collector.serve(inbox, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/v1/events"
        local = self.root / "tel-local"
        base = [self.g, "--headless", "--path", str(self.root), "--fixed-fps", "60", "--", "--playtest",
                f"--sga-endpoint={url}", f"--sga-telemetry-dir={local}"]
        try:
            # 1) a session that is killed: no session_end anywhere
            p = subprocess.Popen(base, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2.5)
            p.send_signal(signal.SIGKILL)
            p.wait()
            # 2) a clean session: quits by itself after 90 frames; must report 1) as crashed
            subprocess.run([self.g, "--headless", "--path", str(self.root), "--fixed-fps", "60", "--quit-after", "90",
                            "--", "--playtest", f"--sga-endpoint={url}", f"--sga-telemetry-dir={local}"],
                           capture_output=True, timeout=120)
        finally:
            srv.shutdown()
        files = sorted(local.glob("*.jsonl"))
        self.assertEqual(len(files), 2)
        first, second = [f.read_text() for f in files]
        self.assertNotIn('"session_end"', first)
        self.assertIn('"previous_session_crashed"', second)
        self.assertIn(files[0].stem, second)
        got = (inbox / files[1].name).read_text()
        self.assertIn('"session_end"', got)                     # the blocking final post arrived
        self.assertEqual(len(got.splitlines()), len(second.strip().splitlines()))

    def test_feedback_form_through_play_verify(self):
        gv = STUDIO / ".claude/scripts/godot-verify.sh"
        subprocess.run(["bash", str(gv), "install", "--project", str(self.root)], check=True, capture_output=True)
        tel = self.root / "tel-feedback"
        scn = self.root / "tests/scenarios/feedback.json"
        scn.parent.mkdir(parents=True, exist_ok=True)
        scn.write_text(json.dumps({"name": "feedback", "steps": [
            {"at": 20, "key": "F8"},
            {"at": 40, "expect": "panel.visible", "node": "/root/Telemetry/Feedback", "label": "F8 opens the form"},
            {"at": 45, "do": "submit(4, \"jump felt floaty\")", "node": "/root/Telemetry/Feedback"},
            {"at": 50, "expect": "not panel.visible and not tree.paused", "node": "/root/Telemetry/Feedback",
             "label": "sending closes the form and unpauses"},
            {"at": 55, "shot": "after"}]}))
        # --playtest and the telemetry dir ride along after the harness's own arguments
        r = subprocess.run(["bash", str(gv), "run", str(scn), "--project", str(self.root), "--out", str(self.root / "out-fb")],
                           cwd=self.root, capture_output=True, text=True, timeout=300,
                           env={**os.environ, "SGA_USER_ARGS": f"--playtest --sga-telemetry-dir={tel}"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = [json.loads(l) for f in tel.glob("*.jsonl") for l in f.read_text().splitlines()]
        fb = [x for x in rows if x["ev"] == "feedback"]
        self.assertEqual(len(fb), 1)
        self.assertEqual((fb[0]["p"]["rating"], fb[0]["p"]["text"]), (4, "jump felt floaty"))
        self.assertTrue((tel / fb[0]["p"]["screenshot"]).exists())


if __name__ == "__main__":
    unittest.main()
