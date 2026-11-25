# Godot Run-and-Verify

The run-and-verify layer lets an agent **play** a Godot game and **observe**
it: scripted input at exact frames, checks against live nodes, screenshots, a
filmstrip of motion, a state trace, and every engine or script error the run
logged. It extends `.claude/docs/run-and-observe.md`. That procedure takes one
picture; this one plays the game to the state the picture needs, and checks
what a picture cannot show: timing, movement, values, errors and repeatability.

**A test proves the logic, a picture proves the look, a scenario proves the
play.** Use all three; none replaces the others, and none replaces a person
playing it (`/team-qa`).

## Pieces

| Piece | Where | What it does |
|---|---|---|
| Harness | `addons/sga_verify/` in the game (from `.claude/engines/godot/verify/addons/`) | An autoload that plays the scenario and writes `report.json` |
| Runner | `bash .claude/scripts/godot-verify.sh` | Finds Godot, adds the autoload for one run, enforces a timeout, reads the log, prints observations |
| Scenarios | `tests/scenarios/*.json` in the game | What to press, when, and what must be true |
| Skill | `/play-verify` | Writes the scenario from the acceptance criteria, runs it, looks at the pictures, reports the `Run result:` line |
| Self-test | `godot-verify.sh selftest` | Plays a fixture game and confirms a pass, a fail, a runtime error, a parse error, a not-assessed run and a determinism run each report as they should |

The harness is never listed in `project.godot`: the runner writes a temporary
`override.cfg` that adds it, and restores the old file afterwards. Without
`-- --sga-scenario=…` on the command line it does nothing. Keep it out of
exports with the export filter `addons/sga_verify/*`.

## Commands

```bash
bash .claude/scripts/godot-verify.sh install                       # once per game; asks first via /play-verify
bash .claude/scripts/godot-verify.sh run tests/scenarios/jump.json # play one scenario
bash .claude/scripts/godot-verify.sh smoke [res://scene.tscn] --frames 300 [--render]
bash .claude/scripts/godot-verify.sh determinism tests/scenarios/jump.json
bash .claude/scripts/godot-verify.sh selftest                      # check the harness itself
```

Options: `--out DIR` (default `production/qa/verify/<scenario>/`; for story
evidence pass `production/qa/evidence/<story-slug>/`), `--render` or
`--headless` (default: render only when the scenario takes pictures),
`--update-baselines`, `--timeout S` (default 120), `--resolution WxH` (default:
the project's window size), `--project DIR`. Extra engine flags go in
`SGA_GODOT_ARGS`, e.g. `--rendering-driver opengl3` on a CI machine.

**Exit codes and words.** `0` / `pass`: every check held and the game logged no
error. `1` / `fail`: a check broke, a screenshot differs from its baseline, or
the game logged an error. `3` / `not_assessed`: the run could not show the
answer: no Godot, no harness, a timeout, a crash, a node path that does not
exist, a step never reached. `not_assessed` outranks `pass` and never hides a
`fail`.

## Scenario format

```json
{
  "name": "jump",
  "scene": "res://levels/test_room.tscn",
  "seed": 7,
  "steps": [
    {"at": 0,   "expect": "is_on_floor()", "node": "Player", "within": 60, "label": "lands after spawn"},
    {"at": 0,   "always": "position.y < 700", "node": "Player", "for": 240, "label": "never falls through the floor"},
    {"at": 70,  "action": "jump", "hold": 8},
    {"at": 72,  "expect": "position.y < 210", "node": "Player", "within": 30, "label": "jump clears 80px"},
    {"at": 90,  "shot": "apex"},
    {"at": 200, "expect": "jumps == 1", "node": "Player"}
  ],
  "filmstrip": {"from": 66, "every": 4, "count": 12},
  "trace": {"every": 1, "watch": {"Player": ["position", "velocity"]}}
}
```

Top level: `name`, `scene` (launch this scene instead of the main scene),
`seed` (global RNG seed, default 0), `frames` (end frame; default: the last step
plus `tail`, 10), `max_frames` (hard stop, default 600), `allow_errors` (default
false), `steps`, `filmstrip`, `trace`.

Every step has `at`, the frame it happens on (frame 0 is the first frame of
the scene). `node` is a path from the scene root (`Player`, `UI/HUD/Score`), or
absolute from `/root` (`/root/GameState`); empty means the scene root.

| Step | Fields | Does |
|---|---|---|
| `action` | `action`, `hold` (frames, default 1; 0 = until the end), `strength` | Presses an input-map action, releases it after `hold` |
| `key` | `key` (Godot key name: `Space`, `A`, `Escape`), `hold` | A key press as if typed |
| `click` | `click: [x, y]`, `button` (`left`/`right`), `hold` | A mouse click at window coordinates |
| `mouse_move` | `mouse_move: [x, y]` | Moves the mouse |
| `set` | `set: {"prop": value}`, `node` | Sets properties to reach a state; strings go through `str_to_var`, so `"Vector2(100, 40)"` works |
| `do` | `do: "expression"`, `node` | Calls methods on the node: `"take_damage(10)"`, `"open_shop()"` |
| `expect` | `expect: "expression"`, `node`, `within` (frames), `label` | Must be true at `at`, or at some frame up to `at + within` |
| `always` | `always: "expression"`, `node`, `for` (frames), `label` | Must be true on every frame from `at` to `at + for` |
| `shot` | `shot: "name"`, `tolerance` (default 0.02) | Screenshot; compared to `baselines/<scenario>/<name>.png` beside the scenario when one exists |

Expressions are Godot `Expression`s run on the node: properties, method calls
and maths (`velocity.length() > 100`, `get_child_count() == 3`). Three names
are always available: `scene` (the scene root), `tree` (the `SceneTree`) and
`frame`. An expression that does not parse, fails, or returns something other
than a bool makes that check `not_assessed`, not `fail`: the scenario is wrong,
not the game.

**Timing.** Input sent on frame N reaches the game on frame N or N+1; checks on
frame N see the state at the start of frame N. Runs use `--fixed-fps 60`, so
every frame advances 1/60 s of game time however fast the machine is. Write
`within` windows instead of exact frames for anything physics-driven.

## Outputs

In the output folder: `report.json` (every check with frame and detail, every
error with file and line), `godot.log`, `shots/<name>.png`, `filmstrip.png` (a
grid read left to right, top to bottom; `report.json` lists its frames) and
`trace.jsonl` (one JSON row per traced frame).

`Read` the shots and the filmstrip. The harness checks numbers; only looking
checks that the jump *looks* right, that the text fits, that the colours
match the art bible.

## Baselines

`--update-baselines` saves each shot as the new baseline beside the scenario
(`tests/scenarios/baselines/<scenario>/<shot>.png`). Commit them. Later runs
compare after scaling both to 256 px wide: the share of pixels that differ by
more than 8% in any channel must stay under `tolerance`. Update a baseline only
after looking at the new picture and deciding the change is intended.

## Determinism

`determinism` plays a scenario twice headless and compares the trace rows. It
needs a `trace` block. A difference is reported at the first row that differs.
The usual causes: a `RandomNumberGenerator` created without a seed (the
scenario's `seed` only covers the global `randf()`/`randi()` family), reading
`Time` or the OS clock, threads, or iterating a dictionary filled in a
different order. Repeatable runs are what make a replay or a bug report
reproducible; they are only promised on the same machine and Godot build.

## Limits

- **Headless runs draw nothing.** Shots and filmstrips need a window
  (`--render`, the default when a scenario has them). On macOS a window opens
  briefly. Inside a sandbox that refuses windows, the run is `not_assessed`;
  see "Sandbox" in `run-and-observe.md`.
- **Audio is not observed.** A scenario can check that a player is
  `playing`, not that it sounds right.
- **Feel still needs a person.** A filmstrip shows motion and timing; whether
  it feels good is a playtest question.
- **Godot 4.5+.** Error capture uses the `Logger` class; on older versions only
  the log scan counts errors, and the report says so.

## On CI

A Linux runner needs a virtual display for shots: install `xvfb` and Mesa,
then `xvfb-run -a env SGA_GODOT_ARGS="--rendering-driver opengl3" bash
.claude/scripts/godot-verify.sh run …`. Headless-only scenarios need neither.
This repo's `.github/workflows/godot-verify.yml` runs the self-test that way.
