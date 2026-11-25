# Super Gamedev Agent -- Game Studio + Knowledge Library

Indie game development managed through 49 coordinated Claude Code subagents
(the **studio layer**, from Claude Code Game Studios), backed by 79 engine,
discipline, genre and publishing skills across 12 engines (the **knowledge
layer**, from awesome-gamedev-agent-skills). Each agent owns a specific domain,
enforcing separation of concerns and quality.

## Run-and-Verify Layer (Godot)

Agents do not only read Godot code: they **play** it. `/play-verify` writes a
scenario from the acceptance criteria (input at exact frames, checks on live
nodes, screenshots, a filmstrip), runs it through
`bash .claude/scripts/godot-verify.sh`, looks at the pictures, and reports
PASS / FAIL / NOT ASSESSED plus the `Run result:` line. Use it before closing
any Godot story with something a player can see or do; a passing scenario stays
in `tests/scenarios/` as a regression check. The harness is added per run through
a temporary `override.cfg`, so `project.godot` is never edited. Reference:
`.claude/docs/godot-verify.md`. `godot-verify.sh selftest` proves the harness
still tells a pass from a fail.

## Asset Production Layer

`/make-assets` turns specs into game-ready art and sound through
`bash .claude/scripts/asset-forge.sh`: OpenArt images via its MCP server
(`.mcp.json`; sign in with `/mcp`), ElevenLabs sound effects and voice
(`ELEVENLABS_API_KEY`), sfxr synth SFX and placeholders, then keying, fitting,
palette lock, audio levelling, QA, a contact sheet, Godot import and an
in-engine gallery played by `godot-verify.sh`. Every file gets an
`assets/provenance.yaml` entry; `ledger check` enforces each provider's
commercial-use terms against `project.goal`. **Paid calls never run without the
person's yes** (the tool exits 4 and prints the plan first). Reference:
`.claude/docs/asset-forge.md`.

## Playtest and Telemetry Layer

`/playtest-data` brings evidence from play back into design through
`bash .claude/scripts/playtest.sh`: a `Telemetry` autoload in the Godot game
(sessions, errors, frame times, crashes, game events, an F8 feedback form in
playtest builds), headless **simulation bots** (a random monkey that needs no
game code, or scripted `SgaBot`s) with a stall watchdog for soft-locks, a
collector for testers' sessions, and reports with funnels, level drop-off,
death heatmaps, grouped errors and threshold checks. Release builds record
nothing without the player's consent. Findings route to `/bug-report`,
`/balance-check`, `/playtest-report` and `/perf-profile`. Reference:
`.claude/docs/playtest-data.md`.

## Studio Vault (Memory Across Games)

The template's `vault/` holds what earlier games built and learned:
reusable **modules** (relocatable systems with tests), **lessons** (what
happened, the evidence, what to do next time) and **addenda** to library
skills. Before building a common system, run
`bash .claude/scripts/vault.sh search <words>`; beside any library skill, read
`vault.sh addenda <skill>` (it wins over the skill) and
`vault.sh lessons --skill <skill>`. Capture lessons after retrospectives and
playtests with `/studio-vault`. Reference: `.claude/docs/studio-vault.md`.

## Evals (Is It Still One System?)

`/studio-evals` (`bash .claude/scripts/evals.sh`) tests the joints between
the layers: static integrity checks (free; CI runs them on every push), every
layer's self-tests, and behaviour evals that run Claude Code on throwaway games
and score what it did (skills loaded, asked before writing, never approved a
paid call). Run them after `bin/update-upstream.sh`, after editing agents,
skills, hooks or this file, and after a model change. Behaviour runs cost money:
never pass `--yes` without the person's yes. Reference: `.claude/docs/evals.md`.

## Knowledge Layer

The studio layer decides **what** to build and **how the work flows** (briefs,
GDDs, stories, gates, review, the write-approval protocol). The knowledge layer
supplies **how to build it correctly** in the chosen engine.

- **Before writing engine code or a technique-dependent spec**, run the
  `router` skill (or read the skills an agent's "Knowledge Library" section
  names). It detects the engine from project files and names the minimal set:
  engine skill → discipline → genre → workflow.
- **Where it lives.** The full catalog is `.claude/library/skills/<category>/<name>/`.
  Only active groups are copied into `.claude/skills/`, so Claude's skill
  listing stays inside its budget. `bash .claude/scripts/library.sh status`
  shows them; `library.sh activate <group>` adds one (`/setup-engine` §9.5 does
  this for the chosen engine). An inactive skill can still be read from the library.
- **Precedence when they disagree:** the project's pinned version
  (`docs/engine-reference/<engine>/VERSION.md`, `project.godot`, the lockfile)
  → the library skill → model memory. The collaboration protocol below always
  wins over a skill's instructions: a skill that says "write the file" still
  means "ask first" here.
- **Engines.** Godot, Unity, Unreal and Web (Phaser, PixiJS, three.js, canvas)
  get the full studio pipeline and the library. Ebitengine, Bevy, Defold, LÖVE,
  pygame and Roblox get the library and the engine-agnostic studio skills:
  leave `engine.name` unset, set `engine.code_root`, and route engine work
  through `router` and `lead-programmer` (there are no specialist agents or
  scaffold for them).
- Library skills are not studio skills: `skill-lint.sh all` skips them, and
  `.claude/library/scripts/validate-skills.py` checks them instead. Do not edit
  them in `.claude/skills/`: `library.sh sync` overwrites those copies.

## Technology Stack

- **Engine**: [CHOOSE: Web / Godot 4 / Unity / Unreal Engine 5]
- **Language**: [CHOOSE: TypeScript / GDScript / C# / C++ / Blueprint]
- **Version Control**: Git with trunk-based development
- **Build System**: [SPECIFY after choosing engine]
- **Asset Pipeline**: [SPECIFY after choosing engine]

> **Note**: Engine-specialist agents exist for Godot, Unity, and Unreal with
> dedicated sub-specialists. Use the set matching your engine.

## Project Structure

@.claude/docs/directory-structure.md

## Engine Version Reference

<!-- ENGINE-REFERENCE-IMPORT: the line under this comment is engine-specific,
     and there is none until an engine is set. /setup-engine, the grow's record
     step and /project-settings (engine.name) write
     @docs/engine-reference/<engine>/VERSION.md here for the chosen engine. Skills
     that need the pinned version read that file on demand either way. -->


## Technical Preferences

`project.yaml` at the repo root is the primary config store — engine, specialists,
naming, platform, performance, modes. Skills resolve it via `resolve_config`
(see `.claude/docs/config-resolution.md`).

`.claude/docs/technical-preferences.md` is the **legacy fallback**, read on demand
when a key is absent from `project.yaml`. It is not imported here: before
`/setup-engine` runs it is almost entirely `[TO BE CONFIGURED]` placeholders, and
after it runs `project.yaml` holds the real values.

## Coordination Rules

@.claude/docs/coordination-rules.md

## Collaboration Protocol

**User-driven collaboration, not autonomous execution.**
Every task follows: **Question -> Options -> Decision -> Draft -> Approval**

- Agents MUST ask "May I write this to [filepath]?" before using Write/Edit tools
  (exempt: `active.md` appends, agent memory, a subagent's new file at the path
  its orchestrating skill named; see `.claude/rules/agent-memory.md`)
- Agents MUST show drafts or summaries before requesting approval
- Multi-file changes require explicit approval for the full changeset
- No commits without user instruction
- A skipped or dismissed question is not an answer: act on nothing, re-ask in
  plain text and wait
- Started outside this file's folder? Warn first: hooks, deny rules and the
  ask-first mode load only when Claude Code starts here

See `docs/COLLABORATIVE-DESIGN-PRINCIPLE.md` for full protocol and examples.

> **First session?** Say "make me a game" (`/prototype`), or run `/start` to begin
> the guided onboarding flow.

## Coding Standards

@.claude/docs/coding-standards.md

## Context Management

Read `.claude/docs/context-management.md` on demand — it is a reference, not
session context. Two of its conventions are load-bearing and cited by name
elsewhere in the repo, so they are restated here rather than lost:

- **`production/session-state/active.md` is the session checkpoint.** The file is
  the memory, not the conversation. Read it first after any compaction, crash, or
  `/clear`.
- **Helpers in `.claude/scripts/` emit observations, never verdicts.** A script
  that scores or judges will eventually contradict a mode or override it cannot
  see. (Cited by `artifact-check.sh` and `adr-dep-graph.sh`.)
