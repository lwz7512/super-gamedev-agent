---
name: play-verify
description: "Plays a Godot game with scripted input and observes it: checks values on live nodes, catches engine and script errors, takes screenshots and a motion filmstrip, and confirms runs repeat. PASS/FAIL/NOT ASSESSED. Use to verify a Godot feature or story works in the running game, reproduce a bug, check a change broke nothing, or get the Run result for a Godot story."
argument-hint: "[scenario.json | write <what to verify> | smoke [scene] | determinism <scenario.json> | install | selftest]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, AskUserQuestion, Bash(bash .claude/scripts/godot-verify.sh *), Bash(bash .claude/hooks/yaml-helper.sh get_effective_yaml_key *), Bash(mkdir -p production/qa/*)
---

# Play and Verify (Godot)

Plays the game the way a tester would, from a scenario: input at exact frames,
expressions checked against live nodes, screenshots, a filmstrip and a state
trace. The runner reports observations; this skill turns them into a verdict
and the studio's `Run result:` line (`.claude/docs/run-and-observe.md`).

Reference for every step type, output and limit: `.claude/docs/godot-verify.md`.
Read the section you need, not the whole file.

**What it can and cannot establish.** It establishes that the game did what
the scenario says on these frames, logged no error, and (with `determinism`)
repeats. It does not establish that it feels good or sounds right: say which
half you covered, and leave feel to a person (`/team-qa`).

## Parse Arguments

- **`<path>.json`**: run that scenario (Phase 3 onward).
- **`write <what to verify>`**, or a story path: write a scenario from the
  request or the story's acceptance criteria (Phase 2), then run it.
- **`smoke [res://scene.tscn]`**: boot the scene, run 120 frames, count errors.
  Add `--render` for a picture.
- **`determinism <path>.json`**: play it twice and compare traces.
- **`install`**: put the harness in the game (Phase 1 only).
- **`selftest`**: check the harness itself on its fixture game.
- **No argument**: ask what to verify, then treat the answer as `write`.

## Phase 1: Preconditions

1. **Godot project.** `project.godot` at the project root (or ask for the
   folder and pass `--project`). Not a Godot project: stop with
   **NOT ASSESSED** and point to `.claude/docs/run-and-observe.md` for the
   other engines.
2. **Harness.** If `addons/sga_verify/verify.gd` is missing, ask:
   "May I write the verification harness to `addons/sga_verify/` (two scripts
   and a README; it does nothing unless this skill launches the game)?" On yes:
   `bash .claude/scripts/godot-verify.sh install`. On no: **NOT ASSESSED**,
   reason "harness not installed".
3. **Godot binary.** The runner finds it (`$GODOT`, `engine.path`, `PATH`, the
   standard app folders). If it reports none, ask for the path and suggest
   setting `engine.path` with `/project-settings`.

## Phase 2: Write the Scenario

Skip when a scenario path was given.

1. Gather the criteria: the story's acceptance criteria, the GDD section it
   cites, or the user's words. Each criterion that something on screen or in a
   node can show becomes one check; say which criteria a scenario cannot show
   (feel, sound) instead of dropping them.
2. Find the real node paths and property names with Grep and Read on the
   scene (`.tscn`) and its scripts. Never guess a path: a wrong one is a
   `not_assessed` check, not a test.
3. Reach the state directly: `scene` to launch the right scene, `set`/`do`
   steps to give the player the item or the 1 HP, instead of playing through
   menus.
4. Prefer `within` windows to exact frames for physics; add an `always`
   invariant for what must never happen (falling through the floor, the health
   going negative); add a `shot` at each moment a criterion is about the look;
   add a `filmstrip` around any movement; add a `trace` of the moving nodes.
5. Show the draft scenario, then ask: "May I write this to
   `tests/scenarios/<name>.json`?" Write it only on yes.

## Phase 3: Run

```
bash .claude/scripts/godot-verify.sh run tests/scenarios/<name>.json [--out production/qa/evidence/<story-slug>]
```

For story evidence, pass the story's evidence folder as `--out` so the shots
are retained where `/story-done` looks for them. The runner picks a window
when the scenario takes pictures and headless otherwise. A run that cannot
open a window inside the sandbox is retried once outside it (see "Sandbox" in
`run-and-observe.md`); refused, it is **NOT ASSESSED**.

## Phase 4: Look

1. Read every line the runner printed: `held`, `BROKE`, `N/A`, the error list
   with file and line, and the notes.
2. `Read` each screenshot and the filmstrip. Compare them to the criteria the
   numbers cannot cover: is it on screen, does the text fit, is the motion an
   arc and not a teleport, does it match the art bible. Note what you saw in
   one line per picture.
3. A `BROKE` check or an error: read the code around the reported line before
   concluding, and say whether the game or the scenario is wrong. A scenario
   that was wrong is fixed and run again (ask before writing the change); a
   game that was wrong is the finding.

## Phase 5: Verdict and Run Result

| Runner status | What you saw in the pictures | Verdict | `Run result:` line |
|---|---|---|---|
| `pass` | matches the criteria | **PASS** | `OBSERVED — <one line> — <evidence path>` |
| `pass` | something wrong on screen | **FAIL** | `OBSERVED — <the defect> — <path>` |
| `fail` | any | **FAIL** | `OBSERVED — <which check broke or which error> — <path>` |
| `not_assessed` | any | **NOT ASSESSED** | `NOT VERIFIED — <reason the runner gave>` |

Report, in this order: the verdict; one line per check; the errors; what each
picture showed; what the scenario could not cover (feel, audio); the output
folder. A **NOT ASSESSED** names its reason and what would make it assessable.
Never round it up to PASS.

## Phase 6: Keep It (optional)

- **Regression.** A passing scenario stays in `tests/scenarios/`. Offer
  `--update-baselines` once the pictures were looked at and approved, so later
  runs compare against them; ask before writing baselines.
- **Repeatability.** For replays, seeds or a hard-to-reproduce bug, run
  `determinism`. A divergence names the first frame and the usual causes.

## Next Steps

- **PASS** on a story: `/story-done` with the evidence folder.
- **FAIL** from the game: fix it and re-run this scenario, or `/bug-report`
  with the scenario path as the reproduction steps.
- **Many scenarios before a hand-off:** `/smoke-check`, then `/team-qa` for
  the feel a scenario cannot judge.
