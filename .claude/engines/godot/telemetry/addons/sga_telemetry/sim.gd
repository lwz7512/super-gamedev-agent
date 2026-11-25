extends Node
## One simulated run, driven by a bot (telemetry.gd starts this for --sga-sim).
##
## Arguments (after --): --sga-sim=monkey|res://path/to/bot.gd  --sga-run=<id>
## --sga-seed=<n>  --sga-frames=<max frames, default 3600>  --sga-stall=<frames
## without a Telemetry.progress() event before the run counts as stalled, default 900>
## --sga-watch=Path:prop,Path:prop  (state recorded when a run stalls or times out)
##
## Every run ends with one run_end event: won/lost/... from the game's own
## Telemetry.run_end(), or "stalled" / "timeout" from this watchdog.

const MONKEY := "monkey"

var telemetry: Node
var bot: RefCounted
var frame := 0
var max_frames := 3600
var stall_frames := 900
var watch: Array = []
var done := false
var _started := false


func setup(t: Node, args: Dictionary) -> void:
	telemetry = t
	process_mode = Node.PROCESS_MODE_ALWAYS
	process_priority = -1900
	var seed_value := int(args.get("sga-seed", 0))
	seed(seed_value)                          # before the main scene's _ready
	max_frames = int(args.get("sga-frames", 3600))
	stall_frames = int(args.get("sga-stall", 900))
	for w in str(args.get("sga-watch", "")).split(",", false):
		var parts := w.split(":", true, 1)
		if parts.size() == 2:
			watch.append(parts)
	var which: String = str(args.get("sga-sim", MONKEY))
	var path: String = get_script().resource_path.get_base_dir().path_join("monkey_bot.gd") if which == MONKEY else which
	var script = load(path)
	if script == null:
		push_error("sga_telemetry: bot script not found: %s" % path)
		get_tree().quit(3)
		return
	bot = script.new()
	bot.tree = get_tree()
	bot.rng.seed = hash(seed_value) ^ 0x2545F491
	bot.setup(int(args.get("sga-run", 0)))


func _process(_delta: float) -> void:
	if done or bot == null:
		return
	if not _started:
		if get_tree().current_scene == null:
			return
		_started = true
		telemetry.last_progress_frame = Engine.get_process_frames()
	frame += 1
	bot._tick(frame)
	if Engine.get_process_frames() - telemetry.last_progress_frame > stall_frames:
		finish("stalled", {"no_progress_for": stall_frames})
	elif frame >= max_frames:
		finish("timeout")


func finish(outcome: String, props: Dictionary = {}) -> void:
	if done:
		return
	done = true
	var p := props.duplicate()
	p["outcome"] = outcome
	p["frames"] = frame
	if outcome in ["stalled", "timeout"]:
		p["state"] = _state()
	telemetry.event("run_end", p)
	telemetry.end_session("run_end")
	get_tree().quit(0)


func _state() -> Dictionary:
	var out := {}
	var scene := get_tree().current_scene
	for w in watch:
		var n: Node = get_tree().root.get_node_or_null(w[0]) if w[0].begins_with("/") else (scene.get_node_or_null(w[0]) if scene else null)
		out["%s:%s" % [w[0], w[1]]] = n.get_indexed(NodePath(w[1])) if n else null
	return out
