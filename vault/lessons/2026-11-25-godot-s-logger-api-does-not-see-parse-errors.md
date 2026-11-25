---
title: Godot's Logger API does not see parse errors
date: 2026-11-25
game: super-gamedev-agent
engine: godot
kind: pitfall
tags: [errors, logging, testing]
skills: [godot-gdscript-headless-testing, play-verify, playtest-data]
status: active
---

OS.add_logger() (4.5+) captures push_error and runtime script errors with file and line, but a GDScript parse error (and the 'Failed to load script' that follows) never reaches it. Evidence: the play-verify parse-error fixture logged 0 errors through Logger while stderr had both lines.

Next time: count errors from the Logger AND scan the log for 'Parse Error' / 'Failed to load script'; a clean Logger is not a clean run.
