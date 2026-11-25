"""Godot 4 import: settings, SpriteFrames, and an in-engine gallery.

- Runs `godot --headless --import`, then sets each managed file's [params]
  (audio loop flags; textures lossless, no mipmaps) and imports again.
  Param names checked against the .import files Godot 4.7.2 writes.
- Animations (frames > 1) get a SpriteFrames resource beside the strip.
- The gallery (tests/asset_gallery/) shows every image asset at whole-number
  zoom over the preview background and loads every sound; its scenario
  (tests/scenarios/asset-gallery.json) is played by godot-verify.sh, so the
  assets are judged inside the real engine, at the project's own filtering.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from common import FAIL, NA, PASS, ForgeError, Project, parse_size

GALLERY_GD = '''extends Node2D
## Asset gallery, written by asset-forge (.claude/scripts/asset-forge.sh godot).
## Shows every image asset and loads every sound so /play-verify can look at
## them in the running engine. Regenerated on each run: do not edit.

var loaded_count := 0
var sounds_loaded := 0
var failed: Array[String] = []


func _ready() -> void:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/asset_gallery/items.json"))
	RenderingServer.set_default_clear_color(Color(data.background))
	var view := get_viewport_rect().size
	var x := 12.0
	var y := 12.0
	var row_h := 0.0
	var sound_lines: Array[String] = []
	for it in data.items:
		var res = load(it.path)
		if res == null:
			failed.append(it.path)
			continue
		loaded_count += 1
		if res is AudioStream:
			sounds_loaded += 1
			sound_lines.append("%s  %.2fs%s" % [it.id, res.get_length(), "  (loops)" if it.get("loop", false) else ""])
			continue
		var node: Node2D
		var size: Vector2
		if res is SpriteFrames:
			var anim := AnimatedSprite2D.new()
			anim.sprite_frames = res
			anim.play(&"default")
			size = res.get_frame_texture(&"default", 0).get_size()
			node = anim
		else:
			var spr := Sprite2D.new()
			spr.texture = res
			size = res.get_size()
			node = spr
		var zoom: float = it.zoom
		var cell := size * zoom
		if x + cell.x > view.x - 12.0 and x > 12.0:
			x = 12.0
			y += row_h + 22.0
			row_h = 0.0
		node.scale = Vector2(zoom, zoom)
		node.position = Vector2(x, y) + cell / 2.0
		add_child(node)
		var label := Label.new()
		label.text = it.id
		label.position = Vector2(x, y + cell.y + 2.0)
		label.add_theme_font_size_override("font_size", 10)
		add_child(label)
		x += maxf(cell.x, 48.0) + 16.0
		row_h = maxf(row_h, cell.y)
	if not sound_lines.is_empty():
		var sounds := Label.new()
		sounds.text = "Sounds (loaded):\n" + "\n".join(sound_lines)
		sounds.position = Vector2(12.0, y + row_h + 28.0)
		sounds.add_theme_font_size_override("font_size", 12)
		add_child(sounds)
		row_h += 28.0 + 16.0 * (sound_lines.size() + 1)
	var total := y + row_h + 24.0
	if total > view.y:
		scale = Vector2.ONE * (view.y / total)
'''

GALLERY_TSCN = '''[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://tests/asset_gallery/gallery.gd" id="1"]

[node name="AssetGallery" type="Node2D"]
script = ExtResource("1")
'''


def find_godot(proj: Project) -> str:
    cands = [os.environ.get("GODOT", ""), shutil.which("godot") or "", shutil.which("godot4") or "",
             "/Applications/Godot.app/Contents/MacOS/Godot",
             str(Path.home() / "Applications/Godot.app/Contents/MacOS/Godot")]
    helper = proj.root / ".claude/hooks/yaml-helper.sh"
    if helper.exists():
        r = subprocess.run(["bash", str(helper), "get_effective_yaml_key", "engine.path"],
                           cwd=proj.root, capture_output=True, text=True)
        p = r.stdout.strip().strip('"')
        if p:
            cands.insert(1, p)
            cands.insert(2, p + "/Contents/MacOS/Godot")
    for c in cands:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    raise ForgeError("Godot binary not found (set GODOT=/path/to/godot or engine.path in project.yaml)")


def _import(godot: str, proj: Project) -> subprocess.CompletedProcess:
    return subprocess.run([godot, "--headless", "--path", str(proj.root), "--import"],
                          capture_output=True, text=True, timeout=600)


def params_for(a: dict) -> dict:
    ext = Path(a["path"]).suffix.lower()
    if a.get("kind", "image") == "image":
        return {"compress/mode": "0", "mipmaps/generate": "false", "process/fix_alpha_border": "true"}
    if ext == ".wav":
        return {"edit/loop_mode": "2" if a.get("loop") else "0", "edit/trim": "false"}
    if ext in (".ogg", ".mp3"):
        return {"loop": "true" if a.get("loop") else "false"}
    return {}


def patch_import(path: Path, params: dict) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    for k, v in params.items():
        pat = re.compile(rf"(?m)^{re.escape(k)}=.*$")
        if pat.search(text):
            new = pat.sub(f"{k}={v}", text)
        else:
            new = text.replace("[params]\n", f"[params]\n\n{k}={v}\n", 1)
        changed |= new != text
        text = new
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def sprite_frames(proj: Project, a: dict) -> Path:
    frames = int(a.get("frames", 1))
    w, h = parse_size(proj.category(a)["size"])
    res_path = "res://" + a["path"]
    out = proj.root / (str(Path(a["path"]).with_suffix("")) + ".frames.tres")
    subs = []
    refs = []
    for i in range(frames):
        subs.append(f'[sub_resource type="AtlasTexture" id="AtlasTexture_f{i}"]\natlas = ExtResource("1")\n'
                    f"region = Rect2({i * w}, 0, {w}, {h})\n")
        refs.append(f'{{\n"duration": 1.0,\n"texture": SubResource("AtlasTexture_f{i}")\n}}')
    body = (f'[gd_resource type="SpriteFrames" load_steps={frames + 2} format=3]\n\n'
            f'[ext_resource type="Texture2D" path="{res_path}" id="1"]\n\n' + "\n".join(subs) +
            '\n[resource]\nanimations = [{\n"frames": [' + ", ".join(refs) + '],\n'
            f'"loop": {"true" if a.get("loop", True) else "false"},\n"name": &"default",\n'
            f'"speed": {float(a.get("fps", 8))}\n}}]\n')
    out.write_text(body, encoding="utf-8")
    return out


def gallery(proj: Project, assets: list[dict]) -> Path:
    style = proj.style["art"]
    pixel = style["kind"] == "pixel"
    items = []
    animated = False
    for a in assets:
        if a.get("kind", "image") == "image":
            size = proj.category(a).get("size", "32x32")
            w, h = parse_size(size)
            zoom = max(1, int(96 // max(w, h))) if pixel else min(1.0, 160.0 / max(w, h))
            if int(a.get("frames", 1)) > 1:
                animated = True
                path = "res://" + str(Path(a["path"]).with_suffix("")) + ".frames.tres"
            else:
                path = "res://" + a["path"]
            items.append({"id": a["id"], "path": path, "zoom": zoom})
        else:
            items.append({"id": a["id"], "path": "res://" + a["path"], "zoom": 1, "loop": bool(a.get("loop"))})
    d = proj.root / "tests/asset_gallery"
    d.mkdir(parents=True, exist_ok=True)
    (d / "gallery.gd").write_text(GALLERY_GD, encoding="utf-8")
    (d / "gallery.tscn").write_text(GALLERY_TSCN, encoding="utf-8")
    (d / "items.json").write_text(json.dumps({"background": style["preview_background"], "items": items}, indent=2) + "\n")
    scn = {
        "name": "asset-gallery",
        "scene": "res://tests/asset_gallery/gallery.tscn",
        "steps": [
            {"at": 3, "expect": f"loaded_count == {len(items)}", "label": f"all {len(items)} assets load in Godot"},
            {"at": 3, "expect": "failed.is_empty()", "label": "no asset failed to load"},
            {"at": 20, "shot": "gallery"},
        ],
    }
    if animated:
        scn["filmstrip"] = {"from": 4, "every": 3, "count": 8}
    sp = proj.root / "tests/scenarios/asset-gallery.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(scn, indent=2) + "\n")
    return sp


def run(proj: Project, assets: list[dict], set_nearest: bool) -> tuple[str, list[dict]]:
    if not (proj.root / "project.godot").exists():
        raise ForgeError("no project.godot here: the godot step needs a Godot project")
    godot = find_godot(proj)
    rows = []
    if set_nearest:
        pg = proj.root / "project.godot"
        t = pg.read_text(encoding="utf-8")
        key = "textures/canvas_textures/default_texture_filter=0"
        if "default_texture_filter=" in t:
            t = re.sub(r"(?m)^textures/canvas_textures/default_texture_filter=.*$", key, t)
        elif "[rendering]" in t:
            t = t.replace("[rendering]\n", f"[rendering]\n\n{key}\n", 1)
        else:
            t = t.rstrip("\n") + f"\n\n[rendering]\n\n{key}\n"
        pg.write_text(t, encoding="utf-8")
        rows.append({"check": "project filter", "status": PASS, "detail": "default canvas texture filter set to Nearest"})
    for a in assets:
        if a.get("kind", "image") == "image" and int(a.get("frames", 1)) > 1:
            sprite_frames(proj, a)
    r = _import(godot, proj)
    if r.returncode != 0:
        raise ForgeError(f"godot --import failed ({r.returncode}): {r.stderr[-400:]}")
    patched = 0
    for a in assets:
        imp = proj.root / (a["path"] + ".import")
        if not imp.exists():
            rows.append({"check": a["id"], "status": FAIL, "detail": "Godot wrote no .import file (not under res://, or not an importable type)"})
            continue
        patched += patch_import(imp, params_for(a))
    if patched:
        r = _import(godot, proj)
        if r.returncode != 0:
            raise ForgeError(f"godot --import (after settings) failed: {r.stderr[-400:]}")
    for a in assets:
        imp = proj.root / (a["path"] + ".import")
        if not imp.exists():
            continue
        text = imp.read_text(encoding="utf-8")
        dest = re.search(r'(?m)^path="res://(.+?)"', text)
        ok = dest and (proj.root / dest.group(1)).exists()
        want = params_for(a)
        settings_ok = all(re.search(rf"(?m)^{re.escape(k)}={re.escape(v)}$", text) for k, v in want.items())
        rows.append({"check": a["id"], "status": PASS if ok and settings_ok else FAIL,
                     "detail": ("imported" if ok else "no imported resource") + ("" if settings_ok else "; import settings did not stick")})
    errors = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(("ERROR:", "SCRIPT ERROR:"))]
    if errors:
        rows.append({"check": "import log", "status": FAIL, "detail": "; ".join(errors[:3])})
    return (FAIL if any(x["status"] == FAIL for x in rows) else PASS if rows else NA), rows
