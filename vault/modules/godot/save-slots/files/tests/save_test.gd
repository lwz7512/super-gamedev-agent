extends Node
## Self-test for save-slots, played by `vault.sh verify save-slots`.
## Each flag is checked by the scenario in the module's tests/.

var roundtrip_ok := false
var backup_ok := false
var migration_ok := false
var empty_ok := false


func _ready() -> void:
	var s: Node = get_node("/root/SaveSlots")
	s.directory = "user://save_slots_test"
	for i in [1, 2, 3]:
		s.delete_slot(i)
	# Round trip keeps types.
	var data := {"pos": Vector2(3, 4), "hp": 7, "items": ["sword", 2], "tint": Color(1, 0, 0)}
	s.save_slot(1, data)
	roundtrip_ok = s.load_slot(1) == data
	# A corrupt slot falls back to the previous save.
	s.save_slot(2, {"hp": 1})
	s.save_slot(2, {"hp": 2})
	var f := FileAccess.open(s.directory.path_join("slot_2.json"), FileAccess.WRITE)
	f.store_string("{ not json")
	f.close()
	backup_ok = s.load_slot(2) == {"hp": 1}
	# An old save is migrated on load.
	var old := FileAccess.open(s.directory.path_join("slot_3.json"), FileAccess.WRITE)
	old.store_string(JSON.stringify({"version": 0, "data": JSON.from_native({"gold": 5})}))
	old.close()
	s.register_migration(0, func(d: Dictionary) -> Dictionary: d["gems"] = d.get("gold", 0) * 2; return d)
	migration_ok = s.load_slot(3) == {"gold": 5, "gems": 10}
	empty_ok = s.load_slot(9) == {} and not s.has_slot(9)
