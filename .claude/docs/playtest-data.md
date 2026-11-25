# Playtest Data — Telemetry, Bots, Reports

The playtest and telemetry layer brings evidence from play back into design:
what people and bots actually did, where they got stuck, what broke, how fast
it ran and what players said. It fills the "Quantitative Data" section of
`/playtest-report`, gives `/balance-check` real distributions, and turns soak
tests into runs a bot can do overnight. Run it through `/playtest-data`.

**Telemetry says what happened, not why.** Pair numbers with watching people
play and with their own words (the feedback form, `/playtest-report`).

## Pieces

| Piece | Where | What it does |
|---|---|---|
| Telemetry addon | `addons/sga_telemetry/` in the game (from `.claude/engines/godot/telemetry/addons/`), autoload `Telemetry` | One JSONL file per session in `user://telemetry/`; errors, frame times, scene changes, crashes, your game events; optional upload; F8 feedback form in playtest builds |
| Simulation | `Telemetry` + `sim.gd`, driven by `playtest.sh simulate` | Headless bot runs in parallel, seeded and repeatable; a watchdog ends runs that stop making progress (soft-locks) |
| Bots | `monkey` (built in, random input from the input map) or your own `tests/bots/<name>.gd` (`extends SgaBot`) | Monkey finds crashes, errors, soft-locks and falls out of the world with no game code; a scripted bot measures win rates and times |
| Collector | `playtest.sh collect` | A small HTTP server that stores uploaded sessions in `production/playtest/inbox/` |
| Analysis | `playtest.sh report` / `check` | Funnel, level completion and deaths, death heatmaps, grouped errors, frame-time percentiles, feedback, bot outcomes and stuck positions; threshold checks |
| Skill | `/playtest-data` | Sets it up, runs bots, gathers sessions, reads the report and charts, and routes findings |

## Commands

```bash
bash .claude/scripts/playtest.sh install [--playtest] [--endpoint URL] [--token T] [--consent required|not-required]
bash .claude/scripts/playtest.sh init                         # production/playtest/config.json
bash .claude/scripts/playtest.sh simulate monkey --runs 200 --watch Player:position
bash .claude/scripts/playtest.sh simulate res://tests/bots/speedrunner.gd --runs 50
bash .claude/scripts/playtest.sh collect [--port 8787] [--token T]
bash .claude/scripts/playtest.sh ingest ~/Downloads/tester-ana.zip
bash .claude/scripts/playtest.sh report [--only players|sims] [--label week-3]
bash .claude/scripts/playtest.sh check | status | selftest
```

Exit codes: `0` pass · `1` a check failed · `3` not assessed (no data, no
Godot, nothing installed). Reports go to `production/playtest/reports/<label>/`
(simulations: `production/playtest/sim/<label>/`) as `report.md` plus PNG charts.

## Instrumenting the game

`install` copies the addon and adds `Telemetry` as the **first** autoload in
`project.godot` (so it is ready before your own singletons). Then, in game code:

```gdscript
Telemetry.event("level_start", {"level": 2})              # funnel steps, level stats
Telemetry.event("level_end", {"level": 2})
Telemetry.event("death", {"pos": player.global_position, "cause": "spikes"})   # heatmaps
Telemetry.progress("checkpoint", {"id": 3})              # progress: resets the bots' stall watchdog
Telemetry.event("purchase", {"item": "sword", "gold": 120})   # anything design wants to count
Telemetry.run_end("won")                                  # a run's outcome; ends a bot run
```

Recorded automatically: `session_start` (version, platform, viewport, install
id), `scene` changes, `error` (every engine/script error, first three of each
per session), `perf` every 5 s (average, p95 and worst frame time, memory,
node count), `session_end`, and `previous_session_crashed` when the last
session never ended cleanly. Vectors become `[x, y]`.

**What counts as progress** is the game's call: coins, checkpoints, rooms,
dialogue choices. A bot run with no `progress` for `--stall` frames (900 = 15 s
of game time) ends as `stalled`, with the `--watch` state recorded, which is
how soft-locks and "stuck in the geometry" show up.

## Writing a bot

```gdscript
# tests/bots/speedrunner.gd: run with  playtest.sh simulate res://tests/bots/speedrunner.gd --runs 50
extends SgaBot

func setup(run: int) -> void:
    pass                                    # per-run choices go on `rng`, so a seed repeats

func act(frame: int) -> void:
    var p := node("Player") as CharacterBody2D
    if p == null:
        return
    hold("move_right")                      # held while called every frame
    if p.is_on_floor() and _gap_ahead(p):
        tap("jump")
    if rng.randf() < 0.01:
        press("attack", 10)                 # down for 10 frames

func _gap_ahead(p: CharacterBody2D) -> bool:
    return p.position.x > 248.0 and p.position.x < 285.0
```

A bot presses the same input actions a person does, so it tests the real
controls. `node()` reads the scene; `rng` is seeded per run. Keep bots small:
one bot per question ("can the level be finished?", "how long does a careful
player take?", "does spamming attack break the combo system?").

## Consent and privacy

Release builds record **nothing until the player agrees**
(`Telemetry.set_consent(true)` from your settings or first-run screen;
`set_consent(false)` stops it). Playtest builds (`install --playtest`, or
`--playtest` on the command line) record from the start and show "PLAYTEST
BUILD · F8 feedback" in the corner, so testers know. Nothing personal is
recorded: the install id is a random number kept in `user://`. Tell testers
what is collected; for players in the EU or UK, a consent prompt is the
expected default. Turn a playtest build back into a release one with
`install --no-playtest` before shipping.

## Getting sessions back

- **In the room or on your network:** `playtest.sh collect`, then
  `playtest.sh install --playtest --endpoint http://<your LAN address>:8787/v1/events`
  and export the build. Sessions upload every 10 s and at exit.
- **Over the internet:** run the collector behind HTTPS (any reverse proxy),
  set `--token` on both sides. The collector checks session ids before they
  become file names and caps request sizes; it does nothing else.
- **No server:** testers press F8, then "Open data folder", and send you the
  files (or a zip of the folder): `playtest.sh ingest <zip or folder>`. The
  folder is `user://telemetry/`: on macOS
  `~/Library/Application Support/Godot/app_userdata/<game>/telemetry/`, on
  Windows `%APPDATA%\Godot\app_userdata\<game>\telemetry\`.

The local file is always written, so an upload that fails loses nothing.

## Config (`production/playtest/config.json`)

```json
{
  "funnel": ["session_start", "level_start level=1", "level_end level=1", "level_end level=3"],
  "level_prop": "level",
  "heatmap_events": ["death"],
  "backgrounds": {"res://levels/forest.tscn": "production/qa/verify/forest/shots/overview.png"},
  "thresholds": {"crash_rate": 0.02, "error_session_share": 0.05, "frame_p95_ms": 33.4,
                 "funnel_step_dropoff": 0.5, "level_completion": 0.5, "feedback_rating": 3.0,
                 "sim_stall_rate": 0.05}
}
```

A funnel step is an event name with optional `prop=value` conditions; each
step must come after the previous one in the same session. Heatmap
backgrounds line up with the first screen of the level: take one with
`/play-verify` (a `shot` at frame 1).

## Checks

| Check | Fails when | Not assessed when |
|---|---|---|
| crash rate | sessions without a clean exit > `crash_rate` | no player sessions |
| errors | sessions that logged an error > `error_session_share` | no player sessions |
| frame time | any scene's p95 frame time > `frame_p95_ms` | no perf samples |
| funnel | any step loses > `funnel_step_dropoff` of those who reached the step before | no funnel configured |
| level completion | any level completes < `level_completion` of its starts | no level events |
| feedback | average rating < `feedback_rating` | no ratings |
| bot `<name>` | stall rate > `sim_stall_rate`, or any run logged an error, or a run never exited | (one row per bot run) |

Bots are reported apart from people: a bot's deaths say nothing about how
the game feels, and a headless run's frame times say nothing about a player's
machine (bots record no `perf`).

## Limits

- **Godot only** for the addon and the bots; the collector and the analysis
  read any engine's sessions written in the same JSONL format.
- **Sim runs measure a bot.** A random monkey's win rate is not the game's
  difficulty; a scripted bot's is only as good as its script.
- **Thresholds are defaults.** A puzzle game expects drop-off a shooter does
  not; set them per game in the config.
- **Crashes in exported builds** are counted (no clean exit) but not
  symbolicated. For native crash stacks, add Sentry's Godot SDK; Claude can then
  read the issues through the Sentry connector.
