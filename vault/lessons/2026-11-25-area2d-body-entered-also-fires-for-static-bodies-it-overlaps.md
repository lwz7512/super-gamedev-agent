---
title: Area2D body_entered also fires for static bodies it overlaps
date: 2026-11-25
game: super-gamedev-agent
engine: godot
kind: pitfall
tags: [physics, area2d, triggers]
skills: [godot-physics, level-design]
status: active
---

Coins, a pit trigger and a goal all fired on frame 1 because their Area2Ds overlapped the floor and wall StaticBody2Ds. Evidence: the telemetry fixture's first run recorded death, two coins and level_end at frame 1.

Next time: in every body_entered handler check the body is the player (or use collision layers/masks so triggers only see the player layer).
