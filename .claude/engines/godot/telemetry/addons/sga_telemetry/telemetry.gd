extends Node
## Telemetry and playtest capture (Super Gamedev Agent, layer 3). Autoload: Telemetry.
##
## One JSONL file per session in user://telemetry/ (the source of truth), plus an
## optional batch upload to a collector (.claude/scripts/playtest.sh collect).
## Records: session start/end, scene changes, every engine/script error, frame-time
## samples, crashes (a previous session with no clean end), in-game feedback (F8 in
## playtest builds) and simulation runs driven by a bot (--sga-sim).
##
## Off until the player consents (set_consent(true)), unless this is a playtest build
## (project setting sga_telemetry/playtest_build, or the --playtest argument) or a
## simulation run. Nothing personal is recorded: an install id is a random number.
##
## Game code:  Telemetry.event("level_start", {"level": 2})
##             Telemetry.progress("checkpoint", {"id": 3})   # also feeds the stall watchdog
##             Telemetry.event("death", {"pos": player.global_position, "cause": "spikes"})
##             Telemetry.run_end("won")                       # a run's outcome (ends a bot run)

const VERSION := "sga_telemetry 1"
const SETTINGS := "sga_telemetry/"

signal event_recorded(name: String, props: Dictionary)

var enabled := false
var playtest := false
var session_id := ""
var install_id := ""
var run_id := ""
var last_progress_frame := 0

var _dir := "user://telemetry"
var _file: FileAccess
var _start_ms := 0
var _scene := ""
var _recent: Array = []
var _logger: Object = null
var _errors_seen := {}
var _frame_ms := PackedFloat32Array()
var _perf_left := 5.0
var _flush_left := 2.0
var _endpoint := ""
var _token := ""
var _outbox: Array = []
var _sending: Array = []
var _http: HTTPRequest
var _post_left := 10.0
var _ended := false
var _sim: Node = null
var _args := {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	process_priority = -2000
	_args = _user_args()
	if _args.has("sga-telemetry-dir"):
		_dir = _args["sga-telemetry-dir"]
	playtest = bool(_setting("playtest_build", false)) or _args.has("playtest")
	_endpoint = str(_args.get("sga-endpoint", _setting("endpoint", "")))
	_token = str(_setting("token", ""))
	install_id = _install_id()
	var consent := _consent()
	var simulating: bool = _args.has("sga-sim")
	if playtest or simulating or not bool(_setting("require_consent", true)) or consent:
		_begin()
	if simulating:
		_sim = load(get_script().resource_path.get_base_dir() + "/sim.gd").new()
		_sim.name = "Sim"
		add_child(_sim)
		_sim.setup(self, _args)
	elif playtest and DisplayServer.get_name() != "headless":
		var form: Node = load(get_script().resource_path.get_base_dir() + "/feedback.gd").new()
		form.name = "Feedback"           # /root/Telemetry/Feedback, for tests and scenarios
		add_child(form)


## Record an event. Props: numbers, strings, bools, Vector2/3, arrays, dictionaries.
func event(name: String, props: Dictionary = {}) -> void:
	if not enabled:
		return
	var row := {"t": Time.get_ticks_msec() - _start_ms, "ev": name, "sid": session_id,
		"f": Engine.get_process_frames(), "scene": _scene}
	if run_id != "":
		row["run"] = run_id
	if not props.is_empty():
		row["p"] = _clean(props)
	_file.store_line(JSON.stringify(row))
	_recent.append(row)
	if _recent.size() > 40:
		_recent.pop_front()
	if _endpoint != "" and _outbox.size() < 5000:
		_outbox.append(row)
	event_recorded.emit(name, props)


## An event that also counts as progress: the simulation's stall watchdog resets on it.
func progress(name: String, props: Dictionary = {}) -> void:
	last_progress_frame = Engine.get_process_frames()
	var p := props.duplicate()
	p["progress"] = true
	event(name, p)


## The outcome of a run ("won", "lost", "quit", ...). Ends the run in a simulation.
func run_end(outcome: String, props: Dictionary = {}) -> void:
	if _sim:
		_sim.finish(outcome, props)
	else:
		var p := props.duplicate()
		p["outcome"] = outcome
		event("run_end", p)


func set_consent(allowed: bool) -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("telemetry", "consent", allowed)
	cfg.save("user://telemetry_consent.cfg")
	if allowed and not enabled:
		_begin()
	elif not allowed and enabled and not playtest:
		end_session("consent withdrawn")
		enabled = false


func recent_events() -> Array:
	return _recent.duplicate()


func session_path() -> String:
	return ProjectSettings.globalize_path(_dir.path_join(session_id + ".jsonl"))


func telemetry_dir() -> String:
	return ProjectSettings.globalize_path(_dir)


# ---------------------------------------------------------------- session --

func _begin() -> void:
	enabled = true
	DirAccess.make_dir_recursive_absolute(_dir)
	var previous := _unfinished_session()
	var rng := RandomNumberGenerator.new()      # never the global RNG: it would change the game
	rng.randomize()
	session_id = "%d-%08x" % [int(Time.get_unix_time_from_system()), rng.randi()]
	if _args.has("sga-run"):
		run_id = str(_args["sga-run"])
	_file = FileAccess.open(_dir.path_join(session_id + ".jsonl"), FileAccess.WRITE)
	if _file == null:
		push_warning("Telemetry: cannot write to %s" % _dir)
		enabled = false
		return
	_start_ms = Time.get_ticks_msec()
	if ClassDB.class_exists("Logger"):
		_logger = load(get_script().resource_path.get_base_dir() + "/error_logger.gd").new()
		OS.add_logger(_logger)
	if _endpoint != "":
		_http = HTTPRequest.new()
		_http.timeout = 10.0
		add_child(_http)
		_http.request_completed.connect(_on_posted)
	var win := DisplayServer.window_get_size() if DisplayServer.get_name() != "headless" else Vector2i.ZERO
	event("session_start", {
		"harness": VERSION, "iid": install_id,
		"version": str(ProjectSettings.get_setting("application/config/version", "")),
		"godot": Engine.get_version_info().string, "platform": OS.get_name(),
		"locale": OS.get_locale_language(), "window": win,
		"viewport": Vector2(ProjectSettings.get_setting("display/window/size/viewport_width", 1152),
			ProjectSettings.get_setting("display/window/size/viewport_height", 648)),
		"playtest": playtest, "bot": str(_args.get("sga-sim", "")),
		"seed": int(_args.get("sga-seed", -1)),
	})
	if previous != "":
		event("previous_session_crashed", {"sid": previous})


func end_session(reason: String = "quit") -> void:
	if not enabled or _ended:
		return
	_ended = true
	_drain_errors()
	event("session_end", {"seconds": (Time.get_ticks_msec() - _start_ms) / 1000.0, "reason": reason})
	_file.flush()
	if _endpoint != "" and not _outbox.is_empty():
		_post_blocking(_outbox)       # the last batch must arrive, or the collector sees a crash


func _exit_tree() -> void:
	end_session("quit")


func _process(delta: float) -> void:
	if not enabled or _ended:
		return
	var cs := get_tree().current_scene
	var path := cs.scene_file_path if cs else ""
	if path != _scene:
		_scene = path
		event("scene", {"path": path})
	_drain_errors()
	if _sim == null:
		_frame_ms.append(delta * 1000.0)
		_perf_left -= delta
		if _perf_left <= 0.0:
			_perf_left = 5.0
			_perf_sample()
	_flush_left -= delta
	if _flush_left <= 0.0:
		_flush_left = 2.0
		_file.flush()
	if _http:
		_post_left -= delta
		if _post_left <= 0.0 and _sending.is_empty() and not _outbox.is_empty():
			_post_left = 10.0
			_sending = _outbox.duplicate()
			_outbox.clear()
			var err := _http.request(_endpoint, _headers(), HTTPClient.METHOD_POST, JSON.stringify(_sending))
			if err != OK:
				_outbox = _sending + _outbox
				_sending = []


func _perf_sample() -> void:
	if _frame_ms.is_empty():
		return
	var sorted := _frame_ms.duplicate()
	sorted.sort()
	var total := 0.0
	for v in sorted:
		total += v
	event("perf", {
		"fps": Engine.get_frames_per_second(),
		"ft_avg": snappedf(total / sorted.size(), 0.01),
		"ft_p95": snappedf(sorted[int((sorted.size() - 1) * 0.95)], 0.01),
		"ft_max": snappedf(sorted[sorted.size() - 1], 0.01),
		"mem_mb": snappedf(Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0, 0.1),
		"nodes": int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)),
	})
	_frame_ms.clear()


func _drain_errors() -> void:
	if _logger == null:
		return
	for e in _logger.take():
		var key: String = e.message + "@" + e.where
		_errors_seen[key] = int(_errors_seen.get(key, 0)) + 1
		if _errors_seen[key] <= 3:         # the first three of each; counts are in the report
			event("error", e)


func _unfinished_session() -> String:
	var files := DirAccess.get_files_at(_dir)
	var newest := ""
	for f in files:
		if f.ends_with(".jsonl") and f > newest:
			newest = f
	if newest == "":
		return ""
	var text := FileAccess.get_file_as_string(_dir.path_join(newest)).strip_edges()
	var last := text.substr(text.rfind("\n") + 1)
	return "" if last.contains("\"session_end\"") or last == "" else newest.get_basename()


# ------------------------------------------------------------------- upload --

func _headers() -> PackedStringArray:
	var h := PackedStringArray(["Content-Type: application/json"])
	if _token != "":
		h.append("X-Playtest-Token: " + _token)
	return h


func _on_posted(result: int, code: int, _h: PackedStringArray, _b: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or code < 200 or code >= 300:
		_outbox = _sending + _outbox     # keep for the next attempt
	_sending = []


func _post_blocking(rows: Array) -> void:
	var m := RegEx.create_from_string("^(https?)://([^/:]+)(?::(\\d+))?(/.*)?$").search(_endpoint)
	if m == null:
		return
	var tls := m.get_string(1) == "https"
	var port := int(m.get_string(3)) if m.get_string(3) != "" else (443 if tls else 80)
	var client := HTTPClient.new()
	if client.connect_to_host(m.get_string(2), port, TLSOptions.client() if tls else null) != OK:
		return
	var deadline := Time.get_ticks_msec() + 2500
	while client.get_status() in [HTTPClient.STATUS_CONNECTING, HTTPClient.STATUS_RESOLVING]:
		client.poll()
		if Time.get_ticks_msec() > deadline:
			return
		OS.delay_msec(5)
	if client.get_status() != HTTPClient.STATUS_CONNECTED:
		return
	var path := m.get_string(4) if m.get_string(4) != "" else "/"
	client.request(HTTPClient.METHOD_POST, path, _headers(), JSON.stringify(rows))
	while client.get_status() == HTTPClient.STATUS_REQUESTING and Time.get_ticks_msec() < deadline:
		client.poll()
		OS.delay_msec(5)
	while client.get_status() == HTTPClient.STATUS_BODY and Time.get_ticks_msec() < deadline:
		client.poll()
		client.read_response_body_chunk()
		OS.delay_msec(2)


# ------------------------------------------------------------------ helpers --

func _clean(v: Variant) -> Variant:
	match typeof(v):
		TYPE_DICTIONARY:
			var d := {}
			for k in v:
				d[str(k)] = _clean(v[k])
			return d
		TYPE_ARRAY, TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_STRING_ARRAY:
			return Array(v).map(func(x): return _clean(x))
		TYPE_VECTOR2, TYPE_VECTOR2I:
			return [snappedf(v.x, 0.01), snappedf(v.y, 0.01)]
		TYPE_VECTOR3, TYPE_VECTOR3I:
			return [snappedf(v.x, 0.01), snappedf(v.y, 0.01), snappedf(v.z, 0.01)]
		TYPE_FLOAT:
			return snappedf(v, 0.0001)
		TYPE_INT, TYPE_BOOL, TYPE_STRING, TYPE_NIL:
			return v
		TYPE_STRING_NAME, TYPE_NODE_PATH:
			return str(v)
		_:
			return var_to_str(v)


func _setting(key: String, default: Variant) -> Variant:
	return ProjectSettings.get_setting(SETTINGS + key, default)


func _install_id() -> String:
	var cfg := ConfigFile.new()
	cfg.load("user://telemetry_consent.cfg")
	var iid: String = cfg.get_value("telemetry", "install_id", "")
	if iid == "":
		var rng := RandomNumberGenerator.new()
		rng.randomize()
		iid = "%08x%08x" % [rng.randi(), rng.randi()]
		cfg.set_value("telemetry", "install_id", iid)
		cfg.save("user://telemetry_consent.cfg")
	return iid


func _consent() -> bool:
	var cfg := ConfigFile.new()
	cfg.load("user://telemetry_consent.cfg")
	return bool(cfg.get_value("telemetry", "consent", false))


func _user_args() -> Dictionary:
	var out := {}
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--"):
			var kv := a.substr(2).split("=", true, 1)
			out[kv[0]] = kv[1] if kv.size() > 1 else ""
	return out
