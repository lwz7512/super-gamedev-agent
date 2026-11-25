---
title: Save files: JSON.from_native/to_native keep Godot types
date: 2026-11-25
game: super-gamedev-agent
engine: godot
kind: technique
tags: [save, json, types]
skills: [save-systems, godot-resources]
status: promoted
---

Plain JSON turns every number into a float and cannot hold Vector2 or Color. JSON.from_native/to_native (4.4+) round-trip ints, Vector2, Color and nested dictionaries exactly (checked on 4.7.2: decoded == original). And JSON.parse_string logs an engine error on bad input; for files that may be corrupt (saves) parse with JSON.new().parse(), which returns an error code quietly. Evidence: the vault module save-slots failed verify on that logged error until it switched.

Next time: use the vault module save-slots, or follow both rules by hand.
