# Addenda for the library skill `save-systems`

Read with the skill. These come from this studio's own games and take precedence over the skill where they disagree; the library itself is left unmodified so upstream updates still apply.

## Save files: JSON.from_native/to_native keep Godot types

_From lesson `2026-11-25-save-files-json-from-native-to-native-keep-godot-types` (super-gamedev-agent, 2026-11-25)._

Plain JSON turns every number into a float and cannot hold Vector2 or Color. JSON.from_native/to_native (4.4+) round-trip ints, Vector2, Color and nested dictionaries exactly (checked on 4.7.2: decoded == original). And JSON.parse_string logs an engine error on bad input; for files that may be corrupt (saves) parse with JSON.new().parse(), which returns an error code quietly. Evidence: the vault module save-slots failed verify on that logged error until it switched.

Next time: use the vault module save-slots, or follow both rules by hand.

