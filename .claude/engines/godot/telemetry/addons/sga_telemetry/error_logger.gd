extends Logger
## Collects engine, script and shader errors (and warnings) for telemetry.gd.
## Kept in its own file: `extends Logger` does not parse before Godot 4.5, and
## telemetry.gd only loads this after checking the class exists.

var _mutex := Mutex.new()
var _items: Array = []

const TYPES := ["error", "warning", "script", "shader"]


func _log_error(function: String, file: String, line: int, code: String, rationale: String,
		_editor_notify: bool, error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
	# Called from any thread, so the list is guarded.
	_mutex.lock()
	if _items.size() < 500:
		_items.append({
			"type": TYPES[error_type] if error_type < TYPES.size() else str(error_type),
			"message": rationale if rationale != "" else code,
			"where": "%s:%d" % [file, line],
			"function": function,
			"frame": Engine.get_process_frames(),
		})
	_mutex.unlock()


func _log_message(_message: String, _error: bool) -> void:
	pass


func take() -> Array:
	_mutex.lock()
	var out := _items.duplicate()
	_mutex.unlock()
	return out
