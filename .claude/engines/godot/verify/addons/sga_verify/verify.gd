extends Node
## Run-and-verify harness for Godot 4.5+ (Super Gamedev Agent).
##
## Plays a scenario file against the running game: scripted input at exact
## frames, expressions checked against live nodes, screenshots, a filmstrip and
## a state trace, then writes report.json and quits with 0 (pass), 1 (fail) or
## 3 (not assessed).
##
## Inert unless the game is started with `-- --sga-scenario=<abs path>`.
## .claude/scripts/godot-verify.sh adds it as an autoload through a temporary
## override.cfg, so project.godot never lists it and exports never run it.
## Scenario format: .claude/docs/godot-verify.md.

const VERSION := "sga_verify 1"
const EXIT_PASS := 0
const EXIT_FAIL := 1
const EXIT_NOT_ASSESSED := 3

var _scn: Dictionary = {}
var _out := ""
var _scenario_path := ""
var _update_baselines := false
var _headless := false
var _logger: Object = null

var _started := false
var _frame := -1
var _end_frame := 0
var _max_frames := 600
var _finishing := false
var _inflight := 0

var _steps: Array = []
var _releases: Array = []            # [frame, InputEvent]
var _windows: Array = []             # open expect/always checks
var _checks: Array = []              # finished check results
var _shots: Array = []
var _film: Array = []                # [frame, Image]
var _film_cfg: Dictionary = {}
var _trace_cfg: Dictionary = {}
var _trace: FileAccess = null
var _notes: Array = []


func _ready() -> void:
	var args := _user_args()
	if not args.has("sga-scenario"):
		set_process(false)
		return
	process_mode = Node.PROCESS_MODE_ALWAYS
	process_priority = -1000          # before the game's own _process each frame
	_headless = DisplayServer.get_name() == "headless"
	_scenario_path = args["sga-scenario"]
	_out = args.get("sga-out", ProjectSettings.globalize_path("user://sga_verify"))
	_update_baselines = args.has("sga-update-baselines")
	DirAccess.make_dir_recursive_absolute(_out)

	if ClassDB.class_exists("Logger"):
		_logger = load(get_script().resource_path.get_base_dir() + "/error_logger.gd").new()
		OS.add_logger(_logger)
	else:
		_notes.append("Logger API missing (Godot older than 4.5): only the runner's log scan counts errors")

	var parsed = JSON.parse_string(FileAccess.get_file_as_string(_scenario_path))
	if typeof(parsed) != TYPE_DICTIONARY:
		_abort("scenario is missing or not a JSON object: %s" % _scenario_path)
		return
	_scn = parsed
	_steps = _scn.get("steps", [])
	_max_frames = int(_scn.get("max_frames", 600))
	_film_cfg = _scn.get("filmstrip", {})
	_trace_cfg = _scn.get("trace", {})
	# Seed before the main scene's _ready, so its randomness is reproducible too.
	seed(int(_scn.get("seed", 0)))
	_end_frame = _compute_end()
	if not _trace_cfg.is_empty():
		_trace = FileAccess.open(_out.path_join("trace.jsonl"), FileAccess.WRITE)


func _process(_delta: float) -> void:
	if _finishing:
		return
	if not _started:
		var tree := get_tree()
		if tree.current_scene == null:
			return
		var want: String = _scn.get("scene", "")
		if want != "" and tree.current_scene.scene_file_path != want:
			if tree.change_scene_to_file(want) != OK:
				_abort("could not open scene %s" % want)
			return
		_started = true

	_frame += 1
	for r in _releases.duplicate():
		if r[0] == _frame:
			Input.parse_input_event(r[1])
			_releases.erase(r)
	for step in _steps:
		if int(step.get("at", 0)) == _frame:
			_run_step(step)
	_tick_windows()
	_record_trace()
	_record_film()
	if _frame >= _end_frame or _frame >= _max_frames:
		_finish()


# ------------------------------------------------------------------ steps --

func _run_step(step: Dictionary) -> void:
	var hold := int(step.get("hold", 1))
	if step.has("action"):
		var down := InputEventAction.new()
		down.action = step["action"]
		down.pressed = true
		down.strength = float(step.get("strength", 1.0))
		_press(down, hold)
	elif step.has("key"):
		var code := OS.find_keycode_from_string(str(step["key"]))
		if code == KEY_NONE:
			_result(_label(step, "key"), "input", "not_assessed", "unknown key name: %s" % step["key"])
			return
		var k := InputEventKey.new()
		k.keycode = code
		k.physical_keycode = code
		k.pressed = true
		_press(k, hold)
	elif step.has("click"):
		var m := InputEventMouseButton.new()
		var p: Array = step["click"]
		m.position = Vector2(p[0], p[1])
		m.global_position = m.position
		m.button_index = MOUSE_BUTTON_RIGHT if step.get("button", "left") == "right" else MOUSE_BUTTON_LEFT
		m.pressed = true
		_press(m, hold)
	elif step.has("mouse_move"):
		var mv := InputEventMouseMotion.new()
		var q: Array = step["mouse_move"]
		mv.position = Vector2(q[0], q[1])
		mv.global_position = mv.position
		Input.parse_input_event(mv)
	elif step.has("set"):
		var target := _node(step.get("node", ""))
		if target == null:
			_result(_label(step, "set"), "set", "not_assessed", "node not found: %s" % step.get("node", ""))
			return
		for prop in step["set"]:
			var v = step["set"][prop]
			target.set_indexed(NodePath(prop), str_to_var(v) if typeof(v) == TYPE_STRING else v)
	elif step.has("do"):
		var r := _eval(step["do"], step.get("node", ""))
		if not r.ok:
			_result(_label(step, "do"), "do", "not_assessed", r.error)
	elif step.has("expect") or step.has("always"):
		_windows.append({
			"step": step,
			"kind": "always" if step.has("always") else "expect",
			"expr": step.get("always", step.get("expect")),
			"until": _frame + int(step.get("for", step.get("within", 0))),
		})
	elif step.has("shot"):
		_shot(step)
	else:
		_result(_label(step, "step"), "step", "not_assessed", "step has no known verb: %s" % JSON.stringify(step))


func _press(ev: InputEvent, hold: int) -> void:
	Input.parse_input_event(ev)
	if hold <= 0:
		return                          # held to the end of the run
	var up: InputEvent = ev.duplicate()
	up.set("pressed", false)
	_releases.append([_frame + hold, up])


func _tick_windows() -> void:
	for w in _windows.duplicate():
		var step: Dictionary = w.step
		var r := _eval(w.expr, step.get("node", ""))
		var label := _label(step, w.expr)
		if not r.ok:
			_result(label, w.kind, "not_assessed", r.error, step)
		elif typeof(r.value) != TYPE_BOOL:
			_result(label, w.kind, "not_assessed", "expression returned %s, not a bool" % type_string(typeof(r.value)), step)
		elif w.kind == "expect" and r.value:
			_result(label, "expect", "pass", "true at frame %d" % _frame, step)
		elif w.kind == "always" and not r.value:
			_result(label, "always", "fail", "false at frame %d" % _frame, step)
		elif _frame >= w.until:
			if w.kind == "always":
				_result(label, "always", "pass", "true every frame %d-%d" % [int(step.get("at", 0)), _frame], step)
			else:
				var span := "at frame %d" % _frame if w.until == int(step.get("at", 0)) else "in frames %d-%d" % [int(step.get("at", 0)), _frame]
				_result(label, "expect", "fail", "never true %s" % span, step)
		else:
			continue
		_windows.erase(w)


# ---------------------------------------------------------------- capture --

func _shot(step: Dictionary) -> void:
	var name: String = step["shot"]
	var entry := {"name": name, "frame": _frame, "status": "not_assessed", "path": null}
	_shots.append(entry)
	if _headless:
		entry.detail = "headless run: no renderer, so no picture (run with --render)"
		return
	_inflight += 1
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	var dir := _out.path_join("shots")
	DirAccess.make_dir_recursive_absolute(dir)
	entry.path = dir.path_join(name + ".png")
	img.save_png(entry.path)
	entry.status = "captured"
	var base := _scenario_path.get_base_dir().path_join("baselines").path_join(_scn.get("name", "scenario")).path_join(name + ".png")
	if _update_baselines:
		DirAccess.make_dir_recursive_absolute(base.get_base_dir())
		img.save_png(base)
		entry.baseline = base
		entry.detail = "baseline written"
	elif FileAccess.file_exists(base):
		var tol := float(step.get("tolerance", 0.02))
		var diff := _diff(img, Image.load_from_file(base))
		entry.baseline = base
		entry.diff = diff
		entry.status = "pass" if diff >= 0.0 and diff <= tol else "fail"
		entry.detail = "size differs from baseline" if diff < 0.0 else "%.2f%% of pixels differ (tolerance %.2f%%)" % [diff * 100.0, tol * 100.0]
	_inflight -= 1


func _diff(a: Image, b: Image) -> float:
	if b == null or a.get_size() != b.get_size():
		return -1.0
	var w := 256
	var h := maxi(1, int(round(256.0 * a.get_height() / a.get_width())))
	var x := a.duplicate() as Image
	var y := b.duplicate() as Image
	for im in [x, y]:
		im.convert(Image.FORMAT_RGBA8)
		im.resize(w, h, Image.INTERPOLATE_BILINEAR)
	var differ := 0
	for j in h:
		for i in w:
			var p := x.get_pixel(i, j)
			var q := y.get_pixel(i, j)
			if maxf(maxf(absf(p.r - q.r), absf(p.g - q.g)), absf(p.b - q.b)) > 0.08:
				differ += 1
	return float(differ) / float(w * h)


func _record_film() -> void:
	if _film_cfg.is_empty() or _headless:
		return
	var from := int(_film_cfg.get("from", 0))
	var every := maxi(1, int(_film_cfg.get("every", 6)))
	if _frame < from or (_frame - from) % every != 0 or _film.size() >= int(_film_cfg.get("count", 12)):
		return
	_inflight += 1
	var at := _frame
	await RenderingServer.frame_post_draw
	_film.append([at, get_viewport().get_texture().get_image()])
	_inflight -= 1


func _write_film() -> Variant:
	if _film_cfg.is_empty():
		return null
	if _headless or _film.is_empty():
		_notes.append("filmstrip not captured: %s" % ("headless run, no renderer" if _headless else "no frames reached"))
		return null
	var first: Image = _film[0][1]
	var tw := 320
	var th := maxi(1, int(round(320.0 * first.get_height() / first.get_width())))
	var cols := int(ceil(sqrt(_film.size())))
	var rows := int(ceil(float(_film.size()) / cols))
	var sheet := Image.create(cols * tw + (cols + 1) * 4, rows * th + (rows + 1) * 4, false, Image.FORMAT_RGBA8)
	sheet.fill(Color(0.08, 0.08, 0.1))
	var frames: Array = []
	for i in _film.size():
		var im: Image = _film[i][1]
		im.convert(Image.FORMAT_RGBA8)
		im.resize(tw, th, Image.INTERPOLATE_BILINEAR)
		sheet.blit_rect(im, Rect2i(0, 0, tw, th), Vector2i(4 + (i % cols) * (tw + 4), 4 + (i / cols) * (th + 4)))
		frames.append(_film[i][0])
	var path := _out.path_join("filmstrip.png")
	sheet.save_png(path)
	return {"path": path, "frames": frames, "columns": cols}


func _record_trace() -> void:
	if _trace == null:
		return
	if _frame % maxi(1, int(_trace_cfg.get("every", 1))) != 0:
		return
	var row := {"f": _frame}
	var watch: Dictionary = _trace_cfg.get("watch", {})
	for path in watch:
		var n := _node(path)
		for prop in watch[path]:
			row["%s.%s" % [path, prop]] = var_to_str(n.get_indexed(NodePath(prop))) if n else "<missing>"
	_trace.store_line(JSON.stringify(row))


# ----------------------------------------------------------------- finish --

func _finish() -> void:
	_finishing = true
	while _inflight > 0:
		await RenderingServer.frame_post_draw
	for w in _windows:
		_result(_label(w.step, w.expr), w.kind, "not_assessed",
			"run ended at frame %d before the check's window closed" % _frame, w.step)
	_windows.clear()
	for step in _steps:
		if int(step.get("at", 0)) > _frame:
			_result(_label(step, "step"), "step", "not_assessed", "never reached: at %d, run ended at %d" % [int(step.get("at", 0)), _frame], step)
	if _trace:
		_trace.close()

	var errors: Array = _logger.take() if _logger else []
	var real_errors := errors.filter(func(e): return e.type != "warning")
	var statuses := _checks.map(func(c): return c.status) + _shots.map(func(s): return s.status)
	var status := "pass"
	if statuses.has("fail") or (real_errors.size() > 0 and not _scn.get("allow_errors", false)):
		status = "fail"
	elif statuses.has("not_assessed"):
		status = "not_assessed"
	if _checks.is_empty() and _shots.is_empty() and real_errors.is_empty() and status == "pass":
		_notes.append("no checks or shots: this run only shows the game ran %d frames without errors" % _frame)
	_write_report(status, errors, real_errors.size())
	get_tree().quit({"pass": EXIT_PASS, "fail": EXIT_FAIL}.get(status, EXIT_NOT_ASSESSED))


func _abort(reason: String) -> void:
	_finishing = true
	_notes.append(reason)
	_write_report("not_assessed", _logger.take() if _logger else [], 0)
	get_tree().quit(EXIT_NOT_ASSESSED)


func _write_report(status: String, errors: Array, error_count: int) -> void:
	var report := {
		"harness": VERSION,
		"status": status,
		"scenario": _scn.get("name", _scenario_path.get_file().get_basename()),
		"scenario_path": _scenario_path,
		"godot": Engine.get_version_info().string,
		"renderer": DisplayServer.get_name(),
		"seed": int(_scn.get("seed", 0)),
		"frames_run": _frame,
		"end_frame": _end_frame,
		"checks": _checks,
		"shots": _shots,
		"filmstrip": _write_film() if status != "not_assessed" or _started else null,
		"trace": _out.path_join("trace.jsonl") if _trace_cfg.size() else null,
		"error_count": error_count,
		"warning_count": errors.size() - error_count,
		"errors": errors.slice(0, 50),
		"notes": _notes,
	}
	var f := FileAccess.open(_out.path_join("report.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify(report, "  "))
	f.close()


# ---------------------------------------------------------------- helpers --

func _compute_end() -> int:
	if _scn.has("frames"):
		return int(_scn["frames"])
	var last := 0
	for step in _steps:
		var at := int(step.get("at", 0))
		last = maxi(last, at + maxi(int(step.get("hold", 1)), int(step.get("for", step.get("within", 0)))))
	if not _film_cfg.is_empty():
		last = maxi(last, int(_film_cfg.get("from", 0)) + int(_film_cfg.get("every", 6)) * int(_film_cfg.get("count", 12)))
	return last + int(_scn.get("tail", 10))


func _eval(expr: String, node_path: String) -> Dictionary:
	var base := _node(node_path)
	if base == null:
		return {"ok": false, "error": "node not found: %s" % (node_path if node_path != "" else "<current scene>")}
	var e := Expression.new()
	if e.parse(expr, PackedStringArray(["scene", "tree", "frame"])) != OK:
		return {"ok": false, "error": "expression does not parse: %s (%s)" % [expr, e.get_error_text()]}
	# show_error = false: a bad scenario expression must not count as a game error.
	var v = e.execute([get_tree().current_scene, get_tree(), _frame], base, false)
	if e.has_execute_failed():
		return {"ok": false, "error": "expression failed: %s (%s)" % [expr, e.get_error_text()]}
	return {"ok": true, "value": v}


func _node(path: String) -> Node:
	var scene := get_tree().current_scene
	if path == "" or path == ".":
		return scene
	if path.begins_with("/"):
		return get_tree().root.get_node_or_null(path)
	return scene.get_node_or_null(path) if scene else null


func _result(label: String, kind: String, status: String, detail: String, step: Dictionary = {}) -> void:
	_checks.append({"label": label, "kind": kind, "status": status, "frame": _frame,
		"at": int(step.get("at", _frame)), "detail": detail})


func _label(step: Dictionary, fallback: String) -> String:
	return str(step.get("label", fallback))


func _user_args() -> Dictionary:
	var out := {}
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--"):
			var kv := a.substr(2).split("=", true, 1)
			out[kv[0]] = kv[1] if kv.size() > 1 else ""
	return out
