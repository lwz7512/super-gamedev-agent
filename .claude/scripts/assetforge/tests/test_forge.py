"""asset-forge tests: run with `asset-forge.sh selftest`.

Every check is shown failing on bad input as well as passing on good input.
The paid generators are tested against a local mock server that asserts the
request shape from the official docs; no network, no API key, no cost.
Godot integration runs when SGA_TEST_GODOT=1 and a Godot binary is found.
"""

from __future__ import annotations

import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from PIL import Image, ImageDraw  # noqa: E402

import audioops  # noqa: E402
import cli  # noqa: E402
import imageops  # noqa: E402
import ledger  # noqa: E402
import providers  # noqa: E402
import qa  # noqa: E402
import synth  # noqa: E402
from common import FAIL, NA, PASS, Project, save_json  # noqa: E402

STUDIO = HERE.parents[3]


def sprite_on(bg, size=512, scale=4) -> Image.Image:
    """An orange blob with a dark outline, anti-aliased against `bg` like a generator's output."""
    big = Image.new("RGB", (size * scale, size * scale), bg)
    d = ImageDraw.Draw(big)
    m = size * scale
    d.ellipse([m * 0.3, m * 0.2, m * 0.7, m * 0.85], fill=(255, 160, 60), outline=(60, 30, 20), width=6 * scale)
    return big.resize((size, size), Image.Resampling.LANCZOS)


def checker_bg(size=512, s=32):
    img = Image.new("RGB", (size, size), (204, 204, 204))
    d = ImageDraw.Draw(img)
    for y in range(0, size, s):
        for x in range((y // s) % 2 * s, size, 2 * s):
            d.rectangle([x, y, x + s - 1, y + s - 1], fill=(153, 153, 153))
    return img


def run_cli(root: Path, *argv) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(["--project", str(root), *argv])
    return code, buf.getvalue()


class Synth(unittest.TestCase):
    def test_presets_are_deterministic_and_audible(self):
        for name in synth.PRESETS:
            a = synth.render(synth.preset(name, 5), 5)
            b = synth.render(synth.preset(name, 5), 5)
            self.assertEqual(a, b, name)
            m = audioops.analyse(a, 44100)
            self.assertGreater(m["rms_dbfs"], -40, name)
            self.assertLess(m["seconds"], 4.01, name)
        self.assertNotEqual(synth.render(synth.preset("coin", 1), 1), synth.render(synth.preset("coin", 2), 2))

    def test_unknown_preset(self):
        with self.assertRaises(ValueError):
            synth.preset("kazoo", 1)


class Images(unittest.TestCase):
    def test_key_colour_background_and_fringe(self):
        img = sprite_on((255, 0, 255)).convert("RGBA")
        out, note = imageops.key_background(img, "#ff00ff", 40, binary=True)
        self.assertIn("key colour", note)
        px = out.load()
        self.assertEqual(px[0, 0][3], 0)
        self.assertEqual(px[256, 300][3], 255)
        pinkish = [p for p in out.getdata() if p[3] and p[0] > 200 and p[2] > 200 and p[1] < 80]
        self.assertEqual(pinkish, [], "magenta fringe left on the sprite edge")

    def test_fake_checkerboard_is_detected_and_removed(self):
        img = checker_bg()
        d = ImageDraw.Draw(img)
        d.ellipse([150, 120, 360, 420], fill=(255, 160, 60))
        rgba = img.convert("RGBA")
        self.assertTrue(imageops.measure(rgba, [])["checkerboard"])
        out, note = imageops.key_background(rgba, "#ff00ff", 30)
        self.assertIn("checkerboard", note)
        self.assertEqual(out.load()[5, 5][3], 0)
        self.assertFalse(imageops.measure(out, [])["checkerboard"])

    def test_real_alpha_is_kept(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle([10, 10, 50, 50], fill=(255, 0, 255, 255))
        out, note = imageops.key_background(img.copy(), "#ff00ff", 40)
        self.assertIn("own alpha", note)
        self.assertEqual(out.load()[30, 30], (255, 0, 255, 255))   # magenta content survives

    def test_fit_bottom_centre_and_palette(self):
        img, _ = imageops.key_background(sprite_on((255, 0, 255)).convert("RGBA"), "#ff00ff", 40)
        out = imageops.fit(img, (32, 32), "bottom-center", 1, pixel=True)
        self.assertEqual(out.size, (32, 32))
        self.assertEqual(imageops.measure(out, [])["baseline"], 31)        # bottom row 30 drawn: bbox end 31
        pal = ["#000000", "#3c1e14", "#ffa03c", "#ffffff"]
        locked = imageops.lock_palette(out, pal, 32, binary_alpha=True)
        m = imageops.measure(locked, pal)
        self.assertEqual(m["palette_share"], 1.0)
        self.assertEqual(m["semi_alpha_pixels"], 0)


class ImageQA(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.proj = Project(self.root)
        save_json(self.proj.style_path, {"art": {"palette": ["#000000", "#ffa03c"]}})

    def tearDown(self):
        shutil.rmtree(self.root)

    def check(self, img, **entry):
        p = self.root / "assets/x.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        img.save(p)
        a = {"id": "x", "kind": "image", "category": "character", "path": "assets/x.png", **entry}
        return {r["check"]: r["status"] for r in qa.check_image(self.proj, a)}

    def good(self, w=32, h=32):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle([8, 8, w - 9, h - 2], fill=(255, 160, 60, 255))
        return img

    def test_good_sprite_passes(self):
        res = self.check(self.good())
        self.assertTrue(all(v == PASS for v in res.values()), res)

    def test_each_defect_fails(self):
        self.assertEqual(self.check(self.good(40, 32))["size"], FAIL)
        opaque = Image.new("RGBA", (32, 32), (255, 160, 60, 255))
        self.assertEqual(self.check(opaque)["transparency"], FAIL)
        self.assertEqual(self.check(checker_bg(32, 4).convert("RGBA"))["no fake checkerboard"], FAIL)
        semi = self.good(); ImageDraw.Draw(semi).point((2, 2), fill=(0, 0, 0, 128))
        self.assertEqual(self.check(semi)["hard alpha edges"], FAIL)
        edge = Image.new("RGBA", (32, 32), (0, 0, 0, 0)); ImageDraw.Draw(edge).rectangle([0, 8, 20, 31], fill=(0, 0, 0, 255))
        self.assertEqual(self.check(edge)["inside padding"], FAIL)
        off = self.good(); ImageDraw.Draw(off).rectangle([10, 10, 12, 12], fill=(10, 200, 10, 255))
        self.assertEqual(self.check(off)["palette lock"], FAIL)
        self.assertEqual(self.check(Image.new("RGBA", (32, 32)))["not empty"], FAIL)

    def test_frame_baseline_drift(self):
        a, b = self.good(), Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        ImageDraw.Draw(b).rectangle([8, 4, 23, 20], fill=(255, 160, 60, 255))    # floats up
        self.assertEqual(self.check(imageops.strip([a, b]), frames=2)["frame baseline"], FAIL)
        self.assertEqual(self.check(imageops.strip([a, a]), frames=2)["frame baseline"], PASS)

    def test_missing_file_fails(self):
        a = {"id": "x", "kind": "image", "category": "character", "path": "assets/nope.png"}
        self.assertEqual(qa.check_image(self.proj, a)[0]["status"], FAIL)


class Audio(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.proj = Project(self.root)

    def tearDown(self):
        shutil.rmtree(self.root)

    def qa_of(self, samples, **entry):
        p = self.root / "assets/s.wav"
        audioops.write_wav(p, samples)
        a = {"id": "s", "kind": "sfx", "path": "assets/s.wav", **entry}
        return {r["check"]: r["status"] for r in qa.check_audio(self.proj, a)}

    def test_cleaned_synth_passes(self):
        raw = [0.0] * 8000 + synth.render(synth.preset("hit", 2), 2)
        clean = audioops.clean(raw, 44100, -1.0, 40, loop=False)
        res = self.qa_of(clean)
        self.assertTrue(all(v == PASS for v in res.values()), res)
        self.assertAlmostEqual(audioops.analyse(clean, 44100)["peak_dbfs"], -1.0, delta=0.1)

    def test_defects_fail(self):
        self.assertEqual(self.qa_of([0.0] * 4410)["not silent"], FAIL)
        self.assertEqual(self.qa_of([1.0, -1.0] * 4410)["headroom"], FAIL)
        self.assertEqual(self.qa_of([0.0] * 8000 + [0.5, -0.5] * 2000)["starts promptly"], FAIL)
        self.assertEqual(self.qa_of([0.3] * 1000 + [-0.3] * 1000, loop=True)["seamless loop"], FAIL)

    def test_loop_crossfade_closes_the_seam(self):
        import math
        tone = [0.5 * math.sin(i * 0.0371) for i in range(44100)]
        looped = audioops.clean(tone, 44100, -1.0, 40, loop=True)
        self.assertLess(audioops.analyse(looped, 44100)["loop_jump"], 0.05)

    @unittest.skipUnless(audioops.ffmpeg(), "ffmpeg not installed")
    def test_ogg_round_trip(self):
        p = self.root / "a.wav"
        audioops.write_wav(p, synth.render(synth.preset("blip", 1), 1))
        o = audioops.encode(p, self.root / "a.ogg")
        s, rate = audioops.read_wav(o)
        self.assertGreater(len(s), 1000)


class Ledger(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.proj = Project(self.root)
        (self.root / "assets/sprites").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def file(self, rel):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (4, 4)).save(p)

    def test_foreign_entries_and_header_survive(self):
        self.proj.ledger_path.write_text("# my header\n- path: assets/a.png\n  origin: you  # mine\n")
        r = ledger.upsert(self.proj, {"path": "assets/b.png", "origin": "code", "tool": "x", "ships": True})
        self.assertEqual(r, "added")
        self.assertEqual(ledger.upsert(self.proj, {"path": "assets/a.png", "origin": "ai"}), "kept")
        text = self.proj.ledger_path.read_text()
        self.assertTrue(text.startswith("# my header\n- path: assets/a.png\n  origin: you  # mine\n"))
        self.assertEqual(ledger.upsert(self.proj, {"path": "assets/b.png", "origin": "code", "tool": "y"}), "updated")
        self.assertEqual(self.proj.ledger_path.read_text().count("assets/b.png"), 1)

    def entry(self, plan, vendor="openart", **extra):
        self.file("assets/sprites/h.png")
        save_json(self.proj.style_path, {"providers": {vendor: {"plan": plan}}})
        rec = {"provider": vendor, "via": "mcp", "model": "m", **extra}
        ledger.upsert(self.proj, ledger.entry_for(self.proj, {"path": "assets/sprites/h.png"}, rec))
        return ledger.check(self.proj, release=False)[0]

    def test_plan_terms(self):
        self.assertEqual(self.entry("plus"), PASS)
        self.assertEqual(self.entry("starter"), FAIL)          # goal unset counts as commercial
        self.assertEqual(self.entry(""), NA)
        self.assertEqual(self.entry("starter", "elevenlabs"), PASS)
        self.assertEqual(self.entry("free", "elevenlabs"), FAIL)

    def test_missing_entry_and_placeholder(self):
        self.file("assets/sprites/x.png")
        self.assertEqual(ledger.check(self.proj, False)[0], FAIL)
        ledger.upsert(self.proj, ledger.entry_for(self.proj, {"path": "assets/sprites/x.png"}, {"provider": "placeholder"}))
        self.assertEqual(ledger.check(self.proj, False)[0], PASS)
        self.assertEqual(ledger.check(self.proj, True)[0], FAIL)      # placeholders block a release

    def test_empty_is_not_assessed(self):
        self.assertEqual(ledger.check(self.proj, False)[0], NA)


class MockElevenLabs(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        MockElevenLabs.seen.append({"path": self.path, "key": self.headers.get("xi-api-key"), "body": body})
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.end_headers()
        self.wfile.write(b"ID3" + b"\x00" * 200)

    def do_GET(self):
        buf = io.BytesIO()
        sprite_on((255, 0, 255), 256).save(buf, "PNG")
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(buf.getvalue())

    def log_message(self, *a):
        pass


class Providers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), MockElevenLabs)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.env = dict(os.environ)
        os.environ["ELEVENLABS_BASE_URL"] = self.base
        os.environ["ELEVENLABS_API_KEY"] = "test-key"
        MockElevenLabs.seen.clear()
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        shutil.rmtree(self.dir)

    def test_paid_call_needs_approval(self):
        with self.assertRaises(providers.NeedsApproval):
            providers.elevenlabs_sfx("whoosh", self.dir, {}, 1.0, False, None, 1, approved=False)
        self.assertEqual(MockElevenLabs.seen, [])

    def test_sfx_request_shape(self):
        cfg = {"sfx_model": "eleven_text_to_sound_v2", "output_format": "mp3_44100_128"}
        files = providers.elevenlabs_sfx("sword swing", self.dir, cfg, 1.5, True, 0.4, 2, approved=True)
        self.assertEqual(len(files), 2)
        req = MockElevenLabs.seen[0]
        self.assertEqual(req["path"], "/v1/sound-generation?output_format=mp3_44100_128")
        self.assertEqual(req["key"], "test-key")
        self.assertEqual(req["body"], {"text": "sword swing", "model_id": "eleven_text_to_sound_v2",
                                       "loop": True, "duration_seconds": 1.5, "prompt_influence": 0.4})

    def test_voice_request_shape(self):
        cfg = {"tts_model": "eleven_multilingual_v2", "output_format": "mp3_44100_128"}
        providers.elevenlabs_voice("Halt!", self.dir, cfg, "VOICE123", 1, approved=True)
        req = MockElevenLabs.seen[0]
        self.assertEqual(req["path"], "/v1/text-to-speech/VOICE123?output_format=mp3_44100_128")
        self.assertEqual(req["body"], {"text": "Halt!", "model_id": "eleven_multilingual_v2"})

    def test_duration_range(self):
        from common import ForgeError
        with self.assertRaises(ForgeError):
            providers.elevenlabs_sfx("x", self.dir, {}, 45.0, False, None, 1, approved=True)

    def test_download_refuses_plain_http_remote(self):
        from common import ForgeError
        with self.assertRaises(ForgeError):
            providers.download("http://example.com/a.png", self.dir)

    def test_openart_mcp_result_through_the_pipeline(self):
        root = self.dir / "game"
        root.mkdir()
        self.assertEqual(run_cli(root, "init")[0], 0)
        save_json(root / "assets/style.json", {"providers": {"openart": {"plan": "plus"}}})
        run_cli(root, "add", "slime", "--kind", "image", "--category", "enemy", "--prompt", "a green slime")
        code, out = run_cli(root, "prompt", "slime")
        self.assertIn("#ff00ff background", out)
        code, out = run_cli(root, "ingest", f"{self.base}/result.png", "--id", "slime", "--provider", "openart",
                            "--model", "nano-banana-2")
        self.assertEqual(code, 0, out)
        code, out = run_cli(root, "normalize", "slime")
        self.assertEqual(code, 0, out)
        self.assertIn("key colour", out)
        code, out = run_cli(root, "qa", "slime")
        self.assertEqual(code, 0, out)
        code, out = run_cli(root, "ledger", "check")
        self.assertEqual(code, 0, out)
        text = (root / "assets/provenance.yaml").read_text()
        self.assertIn("origin: ai", text)
        self.assertIn("plan: plus", text)
        rec = json.loads((root / "assets/_raw/slime/record.json").read_text())
        self.assertEqual(rec["takes"][0]["via"], "mcp")
        self.assertTrue((root / "assets/_raw/.gdignore").exists())

    def test_elevenlabs_through_the_pipeline_needs_yes(self):
        root = self.dir / "game2"
        root.mkdir()
        run_cli(root, "init")
        run_cli(root, "add", "swing", "--kind", "sfx", "--provider", "elevenlabs", "--prompt", "sword swing", "--duration", "1")
        code, out = run_cli(root, "gen", "swing")
        self.assertEqual(code, 4, out)
        self.assertIn("NEEDS APPROVAL", out)
        self.assertEqual(MockElevenLabs.seen, [])
        code, out = run_cli(root, "gen", "swing", "--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(MockElevenLabs.seen), 1)


@unittest.skipUnless(audioops.ffmpeg(), "ffmpeg not installed")
class LossyHeadroom(unittest.TestCase):
    """Regression: lossy encoders overshoot on square waves. CI's libvorbis took a
    -1 dBFS sfxr jump to 0 dBFS with clipped samples; LAME does the same here."""

    def test_normalized_lossy_sfx_keeps_its_headroom(self):
        root = Path(tempfile.mkdtemp())
        try:
            run_cli(root, "init")
            save_json(root / "assets/style.json", {"audio": {"format": "mp3"}})
            for preset in ("jump", "laser"):
                run_cli(root, "add", preset, "--kind", "sfx", "--preset", preset, "--seed", "3")
                run_cli(root, "gen", preset)
                self.assertEqual(run_cli(root, "normalize", preset)[0], 0)
            code, out = run_cli(root, "qa", "-v")
            self.assertEqual(code, 0, out)
            self.assertNotIn("FAIL headroom", out)
        finally:
            shutil.rmtree(root)


class LocalFlow(unittest.TestCase):
    def test_synth_and_placeholder_end_to_end(self):
        root = Path(tempfile.mkdtemp())
        try:
            run_cli(root, "init")
            run_cli(root, "add", "jump", "--kind", "sfx", "--preset", "jump", "--seed", "3")
            run_cli(root, "add", "hero", "--kind", "image", "--category", "character", "--provider", "placeholder", "--frames", "2")
            for i in ("jump", "hero"):
                self.assertEqual(run_cli(root, "gen", i)[0], 0)
                code, out = run_cli(root, "normalize", i)
                self.assertEqual(code, 0, out)
            code, out = run_cli(root, "qa")
            if audioops.ffmpeg() or True:
                self.assertEqual(code, 0, out)
            code, out = run_cli(root, "ledger", "check", "--release")
            self.assertEqual(code, 1, out)                 # the placeholder blocks a release
            self.assertIn("placeholder", out)
            run_cli(root, "sheet")
            self.assertTrue((root / "production/qa/assets/sheet.png").exists())
        finally:
            shutil.rmtree(root)


def _godot():
    for c in (os.environ.get("GODOT", ""), shutil.which("godot") or "", "/Applications/Godot.app/Contents/MacOS/Godot"):
        if c and Path(c).exists():
            return c
    return None


@unittest.skipUnless(os.environ.get("SGA_TEST_GODOT") == "1" and _godot(), "set SGA_TEST_GODOT=1 with Godot installed")
class GodotImport(unittest.TestCase):
    def test_import_frames_gallery_and_play_verify(self):
        root = Path(tempfile.mkdtemp())
        try:
            (root / "project.godot").write_text('config_version=5\n\n[application]\n\nconfig/name="forge-test"\n'
                                                 'config/features=PackedStringArray("4.7")\n')
            run_cli(root, "init")
            run_cli(root, "add", "hero", "--kind", "image", "--category", "character", "--provider", "placeholder", "--frames", "2", "--fps", "6")
            run_cli(root, "add", "coin", "--kind", "sfx", "--preset", "coin", "--seed", "4")
            run_cli(root, "add", "hum", "--kind", "sfx", "--preset", "powerup", "--seed", "9", "--loop")
            for i in ("hero", "coin", "hum"):
                run_cli(root, "gen", i)
                self.assertEqual(run_cli(root, "normalize", i)[0], 0)
            run_cli(root, "qa")
            code, out = run_cli(root, "godot", "--set-nearest")
            self.assertEqual(code, 0, out)
            self.assertIn("default_texture_filter=0", (root / "project.godot").read_text())
            self.assertTrue((root / "assets/characters/hero_ph.frames.tres").exists())
            hum = (root / "assets/sfx/hum.ogg.import").read_text() if (root / "assets/sfx/hum.ogg.import").exists() \
                else (root / "assets/sfx/hum.wav.import").read_text()
            self.assertRegex(hum, r"(?m)^(loop=true|edit/loop_mode=2)$")
            gv = STUDIO / ".claude/scripts/godot-verify.sh"
            subprocess.run(["bash", str(gv), "install", "--project", str(root)], check=True, capture_output=True)
            r = subprocess.run(["bash", str(gv), "run", "tests/scenarios/asset-gallery.json", "--project", str(root),
                                "--out", str(root / "out")], cwd=root, capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((root / "out/shots/gallery.png").exists())
            print(f"\n[godot gallery: {root / 'out'}]", file=sys.stderr)
        finally:
            if os.environ.get("SGA_KEEP") != "1":
                shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
