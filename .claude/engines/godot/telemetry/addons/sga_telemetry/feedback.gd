extends CanvasLayer
## In-game feedback for playtest builds: F8 pauses the game and opens a small
## form (a 1-5 rating and a note). Sending saves a screenshot beside the session
## file and records a "feedback" event with the rating, the note, the scene and
## the last 20 events, so the report shows what the player was doing.
## "Open data folder" shows the player where the session files are, for
## playtests without a collector.

var panel: PanelContainer
var note: TextEdit
var rating := 0
var _buttons: Array[Button] = []
var _was_paused := false
var _shot_path := ""


func _ready() -> void:
	layer = 128
	process_mode = Node.PROCESS_MODE_ALWAYS
	_build()
	panel.hide()
	var hint := Label.new()
	hint.text = "PLAYTEST BUILD · F8 feedback"
	hint.add_theme_font_size_override("font_size", 11)
	hint.modulate = Color(1, 1, 1, 0.55)
	hint.position = Vector2(6, 4)
	add_child(hint)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_F8:
		get_viewport().set_input_as_handled()
		if panel.visible:
			close()
		else:
			open()


func open() -> void:
	# Capture before the form covers the game.
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	var tel := get_node("/root/Telemetry")
	_shot_path = tel.telemetry_dir().path_join("%s-feedback-%d.png" % [tel.session_id, Time.get_ticks_msec()])
	img.save_png(_shot_path)
	_was_paused = get_tree().paused
	get_tree().paused = true
	rating = 0
	note.text = ""
	_paint()
	panel.show()
	note.grab_focus()


func close() -> void:
	panel.hide()
	get_tree().paused = _was_paused


## Also callable from code and tests: records the feedback without the form.
func submit(stars: int, text: String) -> void:
	var tel := get_node("/root/Telemetry")
	var scene := get_tree().current_scene
	tel.event("feedback", {
		"rating": stars, "text": text.substr(0, 2000),
		"screenshot": _shot_path.get_file() if _shot_path != "" else "",
		"scene": scene.scene_file_path if scene else "",
		"recent": tel.recent_events().slice(-20).map(func(r): return r.get("ev", "")),
	})
	_shot_path = ""
	if panel.visible:
		close()


func _build() -> void:
	panel = PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(320, 0)
	add_child(panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	panel.add_child(box)
	var title := Label.new()
	title.text = "How is it going?"
	box.add_child(title)
	var stars := HBoxContainer.new()
	box.add_child(stars)
	for i in 5:
		var b := Button.new()
		b.text = str(i + 1)
		b.custom_minimum_size = Vector2(44, 32)
		b.pressed.connect(func(): rating = i + 1; _paint())
		stars.add_child(b)
		_buttons.append(b)
	note = TextEdit.new()
	note.placeholder_text = "What happened? What did you expect?"
	note.custom_minimum_size = Vector2(300, 90)
	box.add_child(note)
	var row := HBoxContainer.new()
	box.add_child(row)
	var send := Button.new()
	send.text = "Send"
	send.pressed.connect(func(): submit(rating, note.text))
	row.add_child(send)
	var cancel := Button.new()
	cancel.text = "Cancel"
	cancel.pressed.connect(close)
	row.add_child(cancel)
	var folder := Button.new()
	folder.text = "Open data folder"
	folder.pressed.connect(func(): OS.shell_open(get_node("/root/Telemetry").telemetry_dir()))
	row.add_child(folder)


func _paint() -> void:
	for i in _buttons.size():
		_buttons[i].modulate = Color(1, 0.75, 0.3) if i < rating else Color(1, 1, 1)
