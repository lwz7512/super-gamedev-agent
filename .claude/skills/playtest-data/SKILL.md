---
name: playtest-data
description: "Brings play evidence back into design for Godot games: adds telemetry and an in-game feedback form, runs bots headless (random monkey or scripted) to find crashes, soft-locks and win rates, collects testers' sessions, and reports funnels, level drop-off, death heatmaps, errors, frame times and feedback with charts. PASS/FAIL/NOT ASSESSED. Use for playtest data, analytics, telemetry, where players quit or get stuck, simulation or bot testing, soak runs, or crash and error rates."
argument-hint: "[setup | simulate [monkey|<bot>] | collect | ingest <path> | report | check]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, AskUserQuestion, Bash(bash .claude/scripts/playtest.sh *), Bash(bash .claude/scripts/godot-verify.sh *)
---

# Playtest Data

Runs the playtest and telemetry layer: **instrument → play (people and bots)
→ collect → report → route the findings.** The tool reports observations
against thresholds; this skill reads the report and the charts, explains what
they mean for the design, and hands each finding to the skill that acts on it.

Reference for every command, event, threshold and privacy rule:
`.claude/docs/playtest-data.md`. Read the section you need.

**What the numbers can and cannot say.** They say where people went, quit,
died and waited, and what broke. They do not say why, or whether it was fun.
Always pair them with what players wrote and with watching someone play.

## Parse Arguments

- **`setup`**: Phase 1 only.
- **`simulate [monkey|res://tests/bots/<name>.gd]`**: Phase 3.
- **`collect`** / **`ingest <path>`**: Phase 4.
- **`report`** / **`check`**: Phase 5 onward.
- **No argument**: `playtest.sh status`, then ask what the person wants to learn.

## Phase 1: Instrument the Game

1. Godot only: a `project.godot` must be present. Otherwise stop with
   **NOT ASSESSED** and say the collector and analysis still read sessions any
   engine writes in the documented JSONL format.
2. Ask: "May I add telemetry to the game? It copies `addons/sga_telemetry/`
   and adds a `Telemetry` autoload to `project.godot`." On yes:
   `bash .claude/scripts/playtest.sh install`. Ask separately before
   `--playtest` (records without consent, shows the F8 form) and before
   `--endpoint`.
3. Propose the events this game needs from its GDD and brief: the funnel
   steps, `level_start`/`level_end`, `death` with `pos`, `progress` at each
   real step forward, `run_end` with the outcome, and the economy events
   `/balance-check` will want. Show where each call goes in the code, and ask
   before editing game scripts.
4. `bash .claude/scripts/playtest.sh init`, then fill the funnel and thresholds
   in `production/playtest/config.json` for this game (ask before writing).

## Phase 2: Consent

Before any build leaves the person's machine, confirm how players are told.
Playtest builds show their notice; release builds need
`Telemetry.set_consent(true)` from a first-run or settings screen. A build
for the public that records without consent is a **FAIL**: say so and stop.

## Phase 3: Simulate

1. Monkey first: `bash .claude/scripts/playtest.sh simulate monkey --runs 100 --watch <Player>:position`
   (add `--scene res://…` to start in one level). It needs no game code and
   finds crashes, errors, soft-locks and falls out of the world.
2. For win rates and timing, write a bot: `tests/bots/<name>.gd`,
   `extends SgaBot`, with `act(frame)` using `hold`/`tap` on input actions
   and `node()` to read state (template in the doc). Ask before writing it.
3. Read the printed summary and `Read` the outcome chart and heatmaps. For a
   stalled run, open the state it recorded and, when it helps, replay that
   seed as a `/play-verify` scenario to see it.

## Phase 4: Collect People's Sessions

- In the room or on the network: `playtest.sh collect` (foreground; ask the
  person to run it in their own terminal if it must stay up), and
  `install --playtest --endpoint <printed URL>`.
- Files sent by testers: `playtest.sh ingest <zip or folder>`.

## Phase 5: Report and Read

1. `bash .claude/scripts/playtest.sh report` (or `--only players|sims`).
2. `Read` the report and every chart. For each check that failed, find the
   cause in the data: the funnel step, the level, the error's file and line,
   the scene with the bad frame time, the heatmap cluster, the feedback notes
   around it.
3. Verdict:
   - **FAIL**: a check failed. Name each, with the number and the threshold.
   - **NOT ASSESSED**: a check had no data (no sessions, no funnel, no
     ratings). Say what would assess it.
   - **PASS**: every check passed on enough sessions. Say how many; five
     sessions passing is a hint, not a verdict.

## Phase 6: Route the Findings

| Finding | Goes to |
|---|---|
| Error, crash, soft-lock, fell out of the world | `/bug-report` (with the run's seed, state and error location) |
| Drop-off, level too hard or too easy, economy numbers | `/balance-check` with the level and death numbers |
| What players felt and said | `/playtest-report analyze` with this report as its Quantitative Data |
| Frame time | `/perf-profile` on the named scene |

Ask before writing any of their files; each of those skills asks again for its own.

## Next Steps

- After fixes: re-run the same `simulate` with the same `--seed` and compare
  outcomes; then a new round of people.
- Before release: `playtest.sh check`, `install --no-playtest`, and the
  consent screen in place; then `/release-checklist`.
