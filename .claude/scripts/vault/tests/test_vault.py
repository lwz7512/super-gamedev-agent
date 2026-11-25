"""vault tests: run with `vault.sh selftest`.

Every test uses its own temporary vault and games; the real vault/ is only
read by the Godot verify test (SGA_TEST_GODOT=1), which also shows verify
failing on a module with a parse error.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import cli  # noqa: E402
import lessons as L  # noqa: E402
import modules as M  # noqa: E402
from store import STUDIO, TOKEN, Vault, VaultError, locate, read_lock  # noqa: E402

PROJECT = '''config_version=5

[application]

config/name="Combo Game"
config/features=PackedStringArray("4.7")

[autoload]

Combo="*res://systems/combo/combo.gd"

[input]

jump={"deadzone": 0.2, "events": []}
attack={"deadzone": 0.2, "events": []}
'''


def make_game(root: Path) -> Path:
    (root / "systems/combo").mkdir(parents=True)
    (root / "ui").mkdir()
    (root / "project.godot").write_text(PROJECT)
    (root / "systems/combo/combo.gd").write_text(
        'extends Node\nconst DATA := preload("res://systems/combo/combo_data.json")\n'
        'func _process(_d):\n\tif Input.is_action_just_pressed("attack"):\n\t\tpass\n'
        '\tvar x := Input.get_axis("move_left", "move_right")\n')
    (root / "systems/combo/combo_data.json").write_text('{"chain": 3}\n')
    (root / "systems/combo/combo.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n\n'
        '[ext_resource type="Script" uid="uid://b8x2k" path="res://systems/combo/combo.gd" id="1"]\n'
        '[ext_resource type="Script" path="res://ui/hud.gd" id="2"]\n\n[node name="Combo" type="Node"]\nscript = ExtResource("1")\n')
    (root / "systems/combo/combo.gd.uid").write_text("uid://b8x2k\n")
    (root / "ui/hud.gd").write_text("extends Control\n")
    return root


def empty_game(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.godot").write_text('config_version=5\n\n[application]\n\nconfig/name="Next Game"\n')
    return root


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.vault = Vault(self.tmp / "vault")
        self.game = make_game(self.tmp / "game1")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_cli(self, *argv, project=None):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--vault", str(self.vault.root), "--project", str(project or self.game), *argv])
        return code, buf.getvalue()


class Modules(Base):
    def test_harvest_makes_paths_relocatable(self):
        m = M.harvest(self.vault, self.game, "combo", ["systems/combo"], "Combo chains", ["combat"])
        self.assertEqual(sorted(m["files"]), ["combo.gd", "combo.tscn", "combo_data.json"])   # no .uid
        self.assertEqual(m["autoloads"], {"Combo": "combo.gd"})
        self.assertEqual(sorted(m["input_actions"]), ["attack"])
        self.assertEqual(m["external_refs"], ["res://ui/hud.gd"])
        self.assertIn("move_left", " ".join(m["_warnings"]))            # used but never defined
        gd = (self.vault.module_dir("combo") / "files/combo.gd").read_text()
        self.assertIn(f'preload("{TOKEN}/combo_data.json")', gd)
        tscn = (self.vault.module_dir("combo") / "files/combo.tscn").read_text()
        self.assertNotIn("uid=", tscn)
        self.assertIn(f'path="{TOKEN}/combo.gd"', tscn)
        self.assertIn('path="res://ui/hud.gd"', tscn)                     # external stays as it was
        code, out = self.run_cli("harvest", "combo", "systems/combo")
        self.assertEqual(code, 1, out)                                     # not self-contained: exit 1
        self.assertIn("WARNING references outside the module", out)

    def test_add_update_push_round_trip(self):
        M.harvest(self.vault, self.game, "combo", ["systems/combo/combo.gd", "systems/combo/combo_data.json"], "Combo", [])
        g2 = empty_game(self.tmp / "game2")
        code, out = self.run_cli("add", "combo", project=g2)
        self.assertEqual(code, 0, out)
        gd = (g2 / "modules/combo/combo.gd").read_text()
        self.assertIn('preload("res://modules/combo/combo_data.json")', gd)
        pg = (g2 / "project.godot").read_text()
        self.assertIn('Combo="*res://modules/combo/combo.gd"', pg)
        self.assertIn('attack={"deadzone": 0.2, "events": []}', pg)
        self.assertEqual(read_lock(g2)["modules"]["combo"]["version"], "1.0.0")
        # adding again over a folder the vault did not make is refused
        g3 = empty_game(self.tmp / "game3")
        (g3 / "modules/combo").mkdir(parents=True)
        (g3 / "modules/combo/mine.gd").write_text("extends Node\n")
        self.assertEqual(self.run_cli("add", "combo", project=g3)[0], 3)
        # a local improvement: diff sees it, update refuses, push takes it back
        with open(g2 / "modules/combo/combo.gd", "a") as f:
            f.write("# tuned in game2\n")
        self.assertEqual(self.run_cli("diff", "combo", project=g2)[0], 1)
        code, out = self.run_cli("update", "combo", project=g2)
        self.assertEqual(code, 3, out)
        self.assertIn("local edits", out)
        code, out = self.run_cli("push", "combo", project=g2)
        self.assertEqual(code, 0, out)
        vault_gd = (self.vault.module_dir("combo") / "files/combo.gd").read_text()
        self.assertIn("# tuned in game2", vault_gd)
        self.assertIn(TOKEN, vault_gd)                                     # paths made relocatable again
        self.assertNotIn("res://modules/combo", vault_gd)
        self.assertEqual(json.loads((self.vault.module_dir("combo") / "module.json").read_text())["version"], "1.1.0")
        # another game on the old version sees the update and takes it
        g4 = empty_game(self.tmp / "game4")
        self.run_cli("add", "combo", project=g4)
        lock = read_lock(g4)
        lock["modules"]["combo"]["version"] = "1.0.0"
        (g4 / "modules.lock.json").write_text(json.dumps(lock))
        code, out = self.run_cli("outdated", project=g4)
        self.assertEqual(code, 1, out)
        self.assertIn("newer in vault", out)
        self.assertEqual(self.run_cli("update", "combo", project=g4)[0], 0)
        self.assertEqual(self.run_cli("outdated", project=g4)[0], 0)

    def test_search_and_list(self):
        M.harvest(self.vault, self.game, "combo", ["systems/combo/combo.gd"], "Attack combo chains", ["combat"])
        self.assertEqual(self.run_cli("search", "combo", "chains")[0], 0)
        self.assertEqual(self.run_cli("search", "inventory")[0], 3)
        code, out = self.run_cli("list", "--tag", "combat")
        self.assertIn("combo", out)

    def test_locate_through_template_marker(self):
        tpl = self.tmp / "template"
        (tpl / "vault").mkdir(parents=True)
        g = empty_game(self.tmp / "gameX")
        (g / ".claude").mkdir()
        (g / ".claude/sga-template").write_text(str(tpl) + "\n")
        env = os.environ.pop("SGA_VAULT", None)
        try:
            self.assertEqual(locate(g), (tpl / "vault").resolve())
        finally:
            if env:
                os.environ["SGA_VAULT"] = env


class Lessons(Base):
    def test_add_find_promote(self):
        p = L.add(self.vault, "Coyote time needs 6 frames", "Players missed jumps at 3 frames.\n\nUse 6.", "technique",
                  ["platformer", "feel"], ["platformer", "play-verify"], "godot", "game1")
        self.assertTrue(p.exists())
        self.assertEqual(len(L.find(self.vault, tags=["feel"])), 1)
        self.assertEqual(len(L.find(self.vault, skill="platformer")), 1)
        self.assertEqual(len(L.find(self.vault, engine="unity")), 0)
        self.assertEqual(len(L.find(self.vault, text="missed jumps")), 1)
        kind, addendum = L.promote(self.vault, p.stem, "platformer")          # a library skill
        self.assertEqual(kind, "addendum")
        self.assertIn("Coyote time needs 6 frames", addendum.read_text())
        self.assertIn("status: promoted", p.read_text())
        code, out = self.run_cli("addenda", "platformer")
        self.assertIn("Use 6.", out)
        kind, _ = L.promote(self.vault, p.stem, "play-verify")                # a studio skill
        self.assertEqual(kind, "skill-improve")
        with self.assertRaises(VaultError):
            L.promote(self.vault, p.stem, "no-such-skill")
        with self.assertRaises(VaultError):
            L.add(self.vault, "x", "y", "rumour", [], [], "any", "g")

    def test_brief_and_registry(self):
        L.add(self.vault, "A lesson", "body", "pitfall", [], [], "godot", "g")
        code, out = self.run_cli("brief")
        self.assertIn("1 lesson(s) for godot", out)
        self.run_cli("register")
        code, out = self.run_cli("games")
        self.assertIn("Combo Game", out)


def _godot():
    sys.path.insert(0, str(STUDIO / ".claude/scripts/playtest"))
    from godot import PlaytestError, find_godot
    try:
        return find_godot(STUDIO)
    except PlaytestError:
        return None


@unittest.skipUnless(os.environ.get("SGA_TEST_GODOT") == "1" and _godot(), "set SGA_TEST_GODOT=1 with Godot installed")
class Verify(unittest.TestCase):
    def test_seed_module_passes_and_a_broken_copy_fails(self):
        import verify
        real = Vault(STUDIO / "vault")
        status, rows = verify.verify(real, "save-slots")
        self.assertEqual(status, "pass", rows)
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(STUDIO / "vault/modules", tmp / "vault/modules")
            broken = tmp / "vault/modules/godot/save-slots/files/save_slots.gd"
            broken.write_text(broken.read_text().replace("func has_slot(slot: int) -> bool:", "func has_slot(slot: int) -> bool"))
            status, rows = verify.verify(Vault(tmp / "vault"), "save-slots")
            self.assertEqual(status, "fail", rows)
            self.assertTrue(any("Parse Error" in r["detail"] or r["status"] == "fail" for r in rows))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
