# save-slots (Godot 4.5+)

Numbered save slots with atomic writes, one backup per slot, exact types
(`JSON.from_native`/`to_native`: ints stay ints, Vector2/Color survive) and
versioned migration. Installs as the `SaveSlots` autoload.

```gdscript
SaveSlots.save_slot(1, {"level": 3, "pos": player.position, "inventory": inventory.to_dict()})
var data := SaveSlots.load_slot(1)          # {} when empty or unreadable
for s in SaveSlots.list_slots():            # [{slot, saved_at, version}] for a load menu
    print(s)
```

When the save shape changes: bump `SAVE_VERSION` in `save_slots.gd` and
register the step from the old version at startup:

```gdscript
SaveSlots.register_migration(1, func(d: Dictionary) -> Dictionary:
    d["coins"] = d.get("gold", 0)            # v1 had "gold"; v2 calls it "coins"
    d.erase("gold")
    return d)
```

Signals: `saved(slot)`, `loaded(slot, data)`, `failed(slot, reason)`.
Keep save data to plain values and dictionaries; store resources by path.
Design background: the library skill `save-systems`.
