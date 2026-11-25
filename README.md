# Super Gamedev Agent

<p align="center">
  <a href="https://lwz7512.github.io/super-gamedev-agent/">
    <img src="site/assets/banner.svg" width="100%"
         alt="Super Gamedev Agent: a studio layer of 49 agents and 75 workflows over a knowledge layer of 79 skills across 12 engines">
  </a>
</p>

<p align="center">
  <b><a href="https://lwz7512.github.io/super-gamedev-agent/">Documentation site</a></b> ·
  <a href="https://lwz7512.github.io/super-gamedev-agent/agents/">Agents</a> ·
  <a href="https://lwz7512.github.io/super-gamedev-agent/skills/">Studio skills</a> ·
  <a href="https://lwz7512.github.io/super-gamedev-agent/library/">Knowledge library</a> ·
  <a href="https://lwz7512.github.io/super-gamedev-agent/guide/workflow.html">Workflow guide</a>
</p>

A Claude Code game-development setup that combines two projects:

| Layer | Source | What it gives you |
|-------|--------|-------------------|
| **Studio** (process) | [Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios) `abc0de7` | 49 role agents (directors → leads → specialists), 77 workflow skills (`/prototype`, `/start`, `/brainstorm`, GDDs, ADRs, stories, sprints, `/gate-check`, `/cut`, release), 15 safety/quality hooks, path-scoped coding rules, a tested idea → brief → playable browser build → grow → ship pipeline, and rigor tiers (`minimal`/`standard`/`full`) |
| **Knowledge** (technique) | [awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills) `c6ca6c4` | 79 skills across 12 engines (Godot, Unity, Unreal, Phaser, PixiJS, three.js, Ebitengine, Bevy, Defold, LÖVE, pygame, Roblox), 15 disciplines (AI, save systems, game feel, shaders, procedural gen, …), 9 genres, Steam/itch publishing, and a router that picks the 2–3 that fit. Pinned to current engine releases (Godot 4.7.2, Unity 6.3 LTS, Unreal 5.8, …) with runnable checker scripts |

The studio decides **what** to build and **how the work flows**. The knowledge
library makes the code **correct for your engine and version**. Each studio agent
knows which library skills belong to its role (e.g. `ai-programmer` → `game-ai`,
`ai-behavior-trees-utility-ai`, `unreal-behavior-trees`; `release-manager` →
`steam-publish`, `godot-export`).

## Start a new game

```bash
bin/new-game.sh ~/games/my-game            # pick the engine later with /start
bin/new-game.sh ~/games/my-game godot      # or name its library group now
cd ~/games/my-game && claude
```

Then say **"make me a game"** (`/prototype` — questions, a one-page brief, a
playable browser build checked in a headless browser) or run **`/start`** for
guided onboarding. Engine work goes through the `router` skill automatically.

## Knowledge library

Claude lists every skill in `.claude/skills/` and cuts descriptions past its
listing budget, so the 79 library skills are not all switched on at once:

```bash
bash .claude/scripts/library.sh status        # what is active
bash .claude/scripts/library.sh groups        # every group and its skills
bash .claude/scripts/library.sh activate godot   # or unity, unreal, web, phaser, pixijs,
                                                 # threejs, ebitengine, bevy, pygame, love2d,
                                                 # defold, roblox, workflows
bash .claude/scripts/library.sh deactivate godot
```

- Always on: `router` + `core` (all disciplines, all genres, Steam and itch publishing).
- `/setup-engine` offers to activate the chosen engine's group (§9.5), and the
  session-start hook mentions it if the project's engine group is off.
- The router can still read an inactive skill straight from `.claude/library/`.
- `game-jam`, `prototype-fast` and `game-docs` are left out of `core` because
  `/prototype`, `/brainstorm` and the design-doc skills own those jobs here;
  `activate workflows` turns them on.

**Engine coverage.** Godot, Unity, Unreal and Web get the full studio pipeline
(specialist agents, scaffold, test runners) plus the library. Ebitengine, Bevy,
Defold, LÖVE, pygame and Roblox get the library and the engine-agnostic studio
workflow: set `engine.code_root` in `project.yaml`, leave `engine.name` unset.

**Recommended setting.** With an engine active, about 120 skills are listed. If
Claude starts missing skills, raise the listing budget in your user settings:
`"skillListingBudgetFraction": 0.02` (see the
[skills docs](https://code.claude.com/docs/en/skills)).

## Play and verify (Godot)

Agents can **play** a Godot game, not just read its code. A scenario presses
inputs at exact frames, checks values on live nodes, records every engine and
script error, and saves screenshots plus a filmstrip of the motion:

```json
{"name": "jump", "seed": 7, "steps": [
  {"at": 70, "action": "jump", "hold": 8},
  {"at": 72, "expect": "position.y < 210", "node": "Player", "within": 30, "label": "jump clears 80px"},
  {"at": 0,  "always": "position.y < 700", "node": "Player", "for": 240, "label": "never falls through the floor"},
  {"at": 90, "shot": "apex"}],
 "filmstrip": {"from": 66, "every": 4, "count": 12}}
```

```bash
bash .claude/scripts/godot-verify.sh install                        # once per game
bash .claude/scripts/godot-verify.sh run tests/scenarios/jump.json  # pass / fail / not assessed
bash .claude/scripts/godot-verify.sh determinism tests/scenarios/jump.json
```

Or just ask: `/play-verify write the double jump works and the player can't clip
through walls`. It writes the scenario from the acceptance criteria, runs it,
looks at the pictures and reports the studio's `Run result:` line. The harness
is injected per run through a temporary `override.cfg`, so `project.godot` is
never edited. `godot-verify.sh selftest` proves the harness on a fixture game
(on CI too: `.github/workflows/godot-verify.yml`). Full reference:
[`.claude/docs/godot-verify.md`](.claude/docs/godot-verify.md).

## Make assets (art and sound)

`/make-assets` produces game art and sound from specs and keeps the licence
trail: **generate → clean up → check → look → import → look in-engine → record.**

| Source | What | How |
|---|---|---|
| [OpenArt](https://openart.ai/mcp/) | sprites, tiles, icons, UI art | official MCP server in `.mcp.json` (sign in with `/mcp`); results come in with `ingest` |
| [ElevenLabs](https://elevenlabs.io) | sound effects, voice lines | REST with `ELEVENLABS_API_KEY`; every paid call is shown first and needs a yes |
| sfxr synth | retro/prototype SFX | local and free; a preset plus a seed always gives the same sound |
| placeholders | greybox sprites | local and free; a release check fails while any remain |

```bash
bash .claude/scripts/asset-forge.sh init
bash .claude/scripts/asset-forge.sh add slime --kind image --category enemy --prompt "green slime, side view"
bash .claude/scripts/asset-forge.sh ingest <openart-result-url> --id slime --provider openart --model <model>
bash .claude/scripts/asset-forge.sh normalize slime && asset-forge.sh qa && asset-forge.sh sheet
bash .claude/scripts/asset-forge.sh godot && bash .claude/scripts/godot-verify.sh run tests/scenarios/asset-gallery.json
bash .claude/scripts/asset-forge.sh ledger check --release
```

Cleanup keys out the flat background colour the prompt asks for (or a fake
checkerboard), cleans the edge fringe, and fits, anchors and palette-locks each
sprite. For sounds it trims, fades, levels the peak and closes loop seams.
QA checks size, alpha, palette, frame baselines, silence, clipping and loop
seams. The ledger writes `assets/provenance.yaml` and enforces each provider's
commercial-use terms (OpenArt Plus or higher; any paid ElevenLabs plan) when
`project.goal` is to sell. Reference: [`.claude/docs/asset-forge.md`](.claude/docs/asset-forge.md).

## Keeping up to date

```bash
bin/update-upstream.sh            # report what changed in both upstreams
bin/update-upstream.sh --library  # replace the vendored library and re-validate
```

The library is an unmodified copy, so it is replaced wholesale. The studio base
is merged by hand; the files changed locally are:

- `CLAUDE.md` — title and the **Knowledge Layer** section
- `.claude/agents/*.md` — a **Knowledge Library** section at the end of 44 agents
- `.claude/skills/setup-engine/SKILL.md` — §9.5 Activate the Knowledge Library
- `.claude/scripts/skill-lint.sh` — `all` skips library copies (marker file `.library`)
- `.claude/hooks/session-start.sh` — runs `library.sh check`
- new: `.claude/scripts/library.sh`, `.claude/library/`, `bin/`, `UPSTREAM.lock`, this README,
  the documentation site (`site/`, deployed by `.github/workflows/pages.yml`)
- new (run-and-verify layer): `.claude/scripts/godot-verify.sh`, `.claude/engines/godot/verify/`,
  `.claude/skills/play-verify/`, `.claude/docs/godot-verify.md`, `.github/workflows/godot-verify.yml`;
  a pointer in `.claude/docs/run-and-observe.md` and `skills-reference.md`, a
  **Run and Verify (Godot)** section in 9 agents, a Godot step in `/setup-engine` §9.5
- new (asset production layer): `.claude/scripts/asset-forge.sh`, `.claude/scripts/assetforge/`,
  `.claude/skills/make-assets/`, `.claude/docs/asset-forge.md`, `.mcp.json` (OpenArt MCP),
  `.github/workflows/asset-forge.yml`; an **Asset Production** section in 4 agents, a
  `/make-assets` handoff at the end of `/asset-spec`, a row in `skills-reference.md`
- moved: the studio's own README is `docs/CCGS-README.md` (full feature tour, hooks, rigor tiers)

## Checks

```bash
bash .claude/scripts/skill-lint.sh all                    # studio skills
bash .claude/scripts/agent-check.sh                       # studio agents
bash .claude/scripts/godot-verify.sh selftest             # run-and-verify harness (needs Godot)
bash .claude/scripts/asset-forge.sh selftest              # asset pipeline (SGA_TEST_GODOT=1 adds the Godot import test)
(cd .claude/library && python3 -I scripts/validate-skills.py)   # library skills
```

## License

Studio layer: MIT, © Donchitos (`LICENSE`). Knowledge library: Apache-2.0,
© gamedev-skills contributors (`.claude/library/LICENSE`, `.claude/library/NOTICE`),
included unmodified.
