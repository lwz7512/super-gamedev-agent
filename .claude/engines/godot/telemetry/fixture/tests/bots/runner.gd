extends SgaBot
## Plays the corridor well: runs right and jumps the pit from its edge.

func act(_frame: int) -> void:
	var p := node("Player") as CharacterBody2D
	if p == null:
		return
	hold("move_right")
	if p.is_on_floor() and p.position.x > 248.0 and p.position.x < 285.0:
		tap("jump")
