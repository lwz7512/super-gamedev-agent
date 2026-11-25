"""evals tests: run with `evals.sh selftest`.

The static checks are run against a copy of the repo and seen failing on
five kinds of breakage; the behaviour scorer is tested on canned transcripts,
so no Claude run (and no cost) is needed here.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import behavior  # noqa: E402

REPO = HERE.parents[3]


def stream(*events) -> str:
    return "\n".join(json.dumps(e) for e in events)


def tool(name, **inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


RESULT = {"type": "result", "subtype": "success", "result": "Here is the plan. May I write player.gd?",
          "total_cost_usd": 0.12, "num_turns": 5}


class Scoring(unittest.TestCase):
    def test_parse_finds_skills_commands_and_writes(self):
        run = behavior.parse_stream(stream(
            tool("Skill", skill="router"),
            tool("Read", file_path="/x/game/.claude/skills/godot-2d-movement/SKILL.md"),
            tool("Bash", command="cat .claude/library/skills/genres/platformer/SKILL.md"),
            tool("Bash", command="bash .claude/scripts/vault.sh search save"),
            tool("Write", file_path="/x/game/player.gd", content="..."),
            RESULT))
        self.assertEqual(run["skills"], ["godot-2d-movement", "platformer", "router"])
        self.assertEqual(len(run["writes"]), 1)
        self.assertEqual(run["cost"], 0.12)

    def test_each_expectation_passes_and_fails(self):
        case = {"expect": {"uses_any": {"skills": ["platformer"], "bash": ["godot-verify.sh"]},
                           "uses_none": {"bash": ["--yes"]}, "no_write": True, "asks": True, "says_any": ["write"]}}
        good = behavior.parse_stream(stream(tool("Skill", skill="platformer"), RESULT))
        status, rows = behavior.score(case, good)
        self.assertEqual(status, "pass", rows)
        bad = behavior.parse_stream(stream(
            tool("Bash", command="bash .claude/scripts/asset-forge.sh gen swing --yes"),
            tool("Edit", file_path="/x/player.gd", old_string="a", new_string="b"),
            {"type": "result", "subtype": "success", "result": "Done, I changed it.", "num_turns": 3}))
        status, rows = behavior.score(case, bad)
        self.assertEqual(status, "fail")
        failed = {r["expect"] for r in rows if r["status"] == "fail"}
        self.assertEqual(failed, {"uses one of", "avoids", "asks before writing", "ends with a question", "mentions"})

    def test_a_run_that_never_happened_is_not_assessed(self):
        run = behavior.parse_stream("")
        run["error"] = "claude exited 1: not logged in"
        status, rows = behavior.score({"expect": {"no_write": True}}, run)
        self.assertEqual(status, "not_assessed")       # never a pass for "no writes" when nothing ran

    def test_cases_are_well_formed(self):
        cases = behavior.load_cases()
        self.assertGreaterEqual(len(cases), 8)
        for c in cases:
            self.assertTrue(c["prompt"] and c["expect"], c["id"])
            self.assertIn(c.get("fixture", "none"), list(behavior.FIXTURES) + ["none"], c["id"])
            for s in c["expect"].get("uses_any", {}).get("skills", []):
                self.assertTrue((REPO / ".claude/skills" / s).exists() or list((REPO / ".claude/library").glob(f"**/{s}/SKILL.md")),
                                f"{c['id']} expects unknown skill {s}")


class StaticChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.copy = cls.tmp / "repo"
        shutil.copytree(REPO, cls.copy, ignore=shutil.ignore_patterns(".git", "production", "_site", "__pycache__"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)
        os.environ.pop("SGA_EVAL_ROOT", None)

    def statuses(self) -> dict:
        os.environ["SGA_EVAL_ROOT"] = str(self.copy)
        import static
        importlib.reload(static)
        return {r["check"]: r["status"] for r in static.run()}

    def test_clean_copy_passes_then_each_break_is_caught(self):
        s = self.statuses()
        self.assertTrue(all(v == "pass" for v in s.values()), s)
        c = self.copy
        agent = c / ".claude/agents/gameplay-programmer.md"
        agent.write_text(agent.read_text().replace("`physics-tuning`", "`physics-tunning`"))
        (c / ".claude/hooks/notify.sh").unlink()
        (c / ".claude/scripts/vault/store.py").write_text("def broken(:\n")
        mj = c / "vault/modules/godot/save-slots/module.json"
        m = json.loads(mj.read_text())
        m["external_refs"] = ["res://ui/hud.gd"]
        mj.write_text(json.dumps(m))
        doc = c / ".claude/docs/studio-vault.md"
        doc.write_text(doc.read_text() + "\nSee [the plan](no-such-file.md).\n")
        s = self.statuses()
        for check in ("agent skill references", "settings and hooks", "scripts parse", "vault integrity", "doc links"):
            self.assertEqual(s[check], "fail", f"{check} did not catch its break: {s}")


if __name__ == "__main__":
    unittest.main()
