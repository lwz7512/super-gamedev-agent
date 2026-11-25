extends Node2D
# Deliberate parse error for the self-test's "parse" scenario: the run must
# fail on it even though no check in the scenario breaks.
func _ready() -> void
	print("unreachable")
