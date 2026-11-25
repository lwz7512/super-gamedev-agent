extends SgaBot
## Walks right and never jumps: falls in the pit every time (a soft-lock).

func act(_frame: int) -> void:
	hold("move_right")
