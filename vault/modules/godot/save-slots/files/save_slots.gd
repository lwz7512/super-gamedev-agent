extends Node
## Save slots for Godot 4.5+ (studio vault module "save-slots"). Autoload: SaveSlots.
##
## - Atomic writes: the new file is written beside the old one and swapped in,
##   so a crash mid-save never leaves a half-written slot.
## - One backup per slot (<slot>.json.bak); a corrupt slot falls back to it.
## - Exact types: JSON.from_native/to_native keep ints, Vector2, Color and
##   nested dictionaries as they were (plain JSON turns every number into a float).
## - Versioned: bump SAVE_VERSION when the data shape changes and register a
##   migration from the old version; old saves are upgraded as they load.
##
##   SaveSlots.save_slot(1, {"level": 3, "pos": player.position})
##   var data := SaveSlots.load_slot(1)        # {} when the slot is empty or unreadable
##   SaveSlots.register_migration(1, func(d): d["coins"] = 0; return d)   # v1 -> v2

signal saved(slot: int)
signal loaded(slot: int, data: Dictionary)
signal failed(slot: int, reason: String)

const SAVE_VERSION := 1

var directory := "user://saves"
var _migrations := {}


func save_slot(slot: int, data: Dictionary) -> Error:
	DirAccess.make_dir_recursive_absolute(directory)
	var path := _path(slot)
	var tmp := path + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		var err := FileAccess.get_open_error()
		failed.emit(slot, "cannot write %s (error %d)" % [tmp, err])
		return err
	f.store_string(JSON.stringify({
		"version": SAVE_VERSION,
		"saved_at": Time.get_datetime_string_from_system(true),
		"data": JSON.from_native(data),
	}))
	f.close()
	if FileAccess.file_exists(path):
		if FileAccess.file_exists(path + ".bak"):
			DirAccess.remove_absolute(path + ".bak")       # rename will not overwrite on Windows
		DirAccess.rename_absolute(path, path + ".bak")
	var moved := DirAccess.rename_absolute(tmp, path)
	if moved == OK:
		saved.emit(slot)
	else:
		failed.emit(slot, "could not move the new save into place (error %d)" % moved)
	return moved


func load_slot(slot: int) -> Dictionary:
	for candidate in [_path(slot), _path(slot) + ".bak"]:
		var data = _read(candidate)
		if data is Dictionary:
			loaded.emit(slot, data)
			return data
	if has_slot(slot):
		failed.emit(slot, "slot %d and its backup are unreadable" % slot)
	return {}


func has_slot(slot: int) -> bool:
	return FileAccess.file_exists(_path(slot)) or FileAccess.file_exists(_path(slot) + ".bak")


func delete_slot(slot: int) -> void:
	for p in [_path(slot), _path(slot) + ".bak"]:
		if FileAccess.file_exists(p):
			DirAccess.remove_absolute(p)


## [{slot, saved_at, version}] for every slot on disk, for a load menu.
func list_slots() -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	if not DirAccess.dir_exists_absolute(directory):
		return out
	for f in DirAccess.get_files_at(directory):
		if f.begins_with("slot_") and f.ends_with(".json"):
			var raw = _parse(FileAccess.get_file_as_string(directory.path_join(f)))
			if raw is Dictionary:
				out.append({"slot": int(f.trim_prefix("slot_").trim_suffix(".json")),
					"saved_at": raw.get("saved_at", ""), "version": int(raw.get("version", 0))})
	return out


## fn(data: Dictionary) -> Dictionary upgrades a save from `from_version` to the next.
func register_migration(from_version: int, fn: Callable) -> void:
	_migrations[from_version] = fn


func _read(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		return null
	var raw = _parse(FileAccess.get_file_as_string(path))
	if not (raw is Dictionary) or not raw.has("data"):
		return null
	var version := int(raw.get("version", 0))
	var data = JSON.to_native(raw["data"])
	if not (data is Dictionary):
		return null
	while version < SAVE_VERSION:
		if not _migrations.has(version):
			push_warning("SaveSlots: no migration from version %d in %s" % [version, path])
			return null
		data = _migrations[version].call(data)
		version += 1
	if version > SAVE_VERSION:
		push_warning("SaveSlots: %s was saved by a newer build (v%d)" % [path, version])
		return null
	return data


## JSON.parse_string logs an engine error on bad input; a corrupt save is an
## expected case here (the backup covers it), so parse quietly.
func _parse(text: String) -> Variant:
	var json := JSON.new()
	return json.data if json.parse(text) == OK else null


func _path(slot: int) -> String:
	return directory.path_join("slot_%d.json" % slot)
