---
title: Headless Godot never fires RenderingServer.frame_post_draw
date: 2026-11-25
game: super-gamedev-agent
engine: godot
kind: pitfall
tags: [headless, screenshots, testing, ci]
skills: [godot-gdscript-headless-testing, play-verify]
status: promoted
---

With --headless the renderer is a dummy, so `await RenderingServer.frame_post_draw` waits forever and the run hangs until killed. Evidence: the first run-and-verify probe hung at 120 s on Godot 4.7.2; the same code finished in under a second with a window.

Next time: never await frame_post_draw when `DisplayServer.get_name() == "headless"`; report screenshots as not assessed there and take them in a windowed run (xvfb on Linux CI).
