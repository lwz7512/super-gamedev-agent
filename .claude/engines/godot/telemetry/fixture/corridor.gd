extends Node2D
## A corridor: coins are progress, the pit is a soft-lock (deep walls, no way
## out, no run_end), the goal wins. Telemetry calls are guarded so the scene
## also runs without the addon.

@onready var player: CharacterBody2D = $Player
var in_pit := false


func _ready() -> void:
	_t("event", ["level_start", {"level": 1}])
	for c in [$Coin1, $Coin2]:
		c.body_entered.connect(_on_coin.bind(c))
	$Pit.body_entered.connect(_on_pit)
	$Goal.body_entered.connect(_on_goal)


func _on_coin(body: Node, coin: Area2D) -> void:
	if body != player:
		return              # the floor overlaps the trigger areas too
	_t("progress", ["coin", {"x": coin.position.x}])
	coin.queue_free()


func _on_pit(body: Node) -> void:
	if body == player and not in_pit:
		in_pit = true
		_t("event", ["death", {"pos": player.global_position, "cause": "pit"}])


func _on_goal(body: Node) -> void:
	if body != player:
		return
	_t("event", ["level_end", {"level": 1, "seconds": Time.get_ticks_msec() / 1000.0}])
	_t("run_end", ["won"])


func _t(method: String, args: Array) -> void:
	var tel := get_node_or_null("/root/Telemetry")
	if tel:
		tel.callv(method, args)
