extends CharacterBody2D

const SPEED := 200.0
const JUMP_VELOCITY := -520.0
const GRAVITY := 1400.0

var jumps := 0


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y += GRAVITY * delta
	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY
		jumps += 1
	velocity.x = Input.get_axis("move_left", "move_right") * SPEED
	move_and_slide()
