# Addenda for the library skill `godot-gdscript-headless-testing`

Read with the skill. These come from this studio's own games and take precedence over the skill where they disagree; the library itself is left unmodified so upstream updates still apply.

## Headless Godot never fires RenderingServer.frame_post_draw

_From lesson `2026-11-25-headless-godot-never-fires-renderingserver-frame-post-draw` (super-gamedev-agent, 2026-11-25)._

With --headless the renderer is a dummy, so `await RenderingServer.frame_post_draw` waits forever and the run hangs until killed. Evidence: the first run-and-verify probe hung at 120 s on Godot 4.7.2; the same code finished in under a second with a window.

Next time: never await frame_post_draw when `DisplayServer.get_name() == "headless"`; report screenshots as not assessed there and take them in a windowed run (xvfb on Linux CI).

