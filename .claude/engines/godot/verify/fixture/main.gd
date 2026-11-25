extends Node2D

@onready var coin: Node2D = $Coin


func _ready() -> void:
	# Random placement, so the self-test can show that a seeded run repeats.
	coin.position = Vector2(randf_range(80.0, 560.0), randf_range(120.0, 260.0))


func explode() -> void:
	# Deliberate bug for the self-test's error scenario.
	var missing: Node = null
	missing.get_name()
