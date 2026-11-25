---
title: Run the monkey bot before people play
date: 2026-11-25
game: super-gamedev-agent
engine: any
kind: process
tags: [playtest, bots, level-design, qa]
skills: [playtest-data, level-design]
status: active
---

A random-input bot with no game code found that about half its runs walked off an unwalled level edge and fell forever (y > 13000), on its first 24 runs, in 3 seconds. Evidence: playtest.sh simulate monkey on the telemetry fixture.

Next time: run 'playtest.sh simulate monkey --watch Player:position' after every level change; fix any 'left the level' and 'stalled' before a person sees the build.
