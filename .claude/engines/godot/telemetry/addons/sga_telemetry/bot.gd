class_name SgaBot
extends RefCounted
## Base class for simulation bots (playtest.sh simulate <bot>).
##
## A bot plays through the same input map a person does. Override setup() and
## act(); use press()/release()/tap() for input and scene()/node() to read the
## game. Keep decisions on `rng`, which is seeded per run, so a run repeats.
##
##   extends SgaBot
##   func act(frame: int) -> void:
##       hold("move_right")
##       var p := node("Player") as CharacterBody2D
##       if p.is_on_floor() and p.position.x > 250.0:
##           tap("jump")

var tree: SceneTree
var rng := RandomNumberGenerator.new()
var frame := 0
var _release_at := {}


## Called once before the first frame, with the run number.
func setup(_run: int) -> void:
	pass


## Called every frame. Decide and press.
func act(_frame: int) -> void:
	pass


func scene() -> Node:
	return tree.current_scene


func node(path: String) -> Node:
	if path.begins_with("/"):
		return tree.root.get_node_or_null(path)
	return tree.current_scene.get_node_or_null(path) if tree.current_scene else null


## Press an action and release it after `frames` frames.
func press(action: String, frames: int = 1) -> void:
	if not _release_at.has(action):
		_send(action, true)
	_release_at[action] = frame + max(1, frames)


## Keep an action held (call every frame you want it down).
func hold(action: String) -> void:
	press(action, 2)


func tap(action: String) -> void:
	press(action, 1)


func release(action: String) -> void:
	if _release_at.has(action):
		_release_at.erase(action)
		_send(action, false)


func held(action: String) -> bool:
	return _release_at.has(action)


func _tick(f: int) -> void:
	frame = f
	for a in _release_at.keys():
		if _release_at[a] <= f:
			release(a)
	act(f)


func _send(action: String, down: bool) -> void:
	var ev := InputEventAction.new()
	ev.action = action
	ev.pressed = down
	ev.strength = 1.0 if down else 0.0
	Input.parse_input_event(ev)
