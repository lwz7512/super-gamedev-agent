extends "res://addons/sga_telemetry/bot.gd"
## The bot that needs no game code: presses random actions from the input map,
## held for random lengths, with pauses. Finds crashes, errors, soft-locks and
## places a careless player gets stuck. Built-in ui_* actions are left out unless
## the run sets --sga-monkey-ui (menus driven by ui_accept and friends).

var actions: PackedStringArray = []
var _next := 0


func setup(_run: int) -> void:
	var with_ui := OS.get_cmdline_user_args().has("--sga-monkey-ui")
	for a in InputMap.get_actions():
		var s := str(a)
		if with_ui or not s.begins_with("ui_"):
			actions.append(s)


func act(f: int) -> void:
	if actions.is_empty() or f < _next:
		return
	if rng.randf() < 0.15:
		_next = f + rng.randi_range(5, 30)          # a pause, as people do
		return
	press(actions[rng.randi_range(0, actions.size() - 1)], rng.randi_range(2, 40))
	_next = f + rng.randi_range(3, 20)
