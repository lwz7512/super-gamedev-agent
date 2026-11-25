---
name: studio-vault
description: "Carries what one game learned and built into the next: finds and installs reusable modules from the studio vault, harvests a well-built system out of this game, keeps installed modules up to date, records lessons with evidence and promotes them into library-skill addenda or skill improvements. PASS/FAIL/NOT ASSESSED for module verification. Use before building a common system (save, input, UI, dialogue...), after a retrospective or post-mortem, when something should be remembered next time, or to reuse code across games."
argument-hint: "[find <what> | add <module> | harvest <name> <path...> | update | lesson | promote <lesson> | verify <module>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, AskUserQuestion, Bash(bash .claude/scripts/vault.sh *), Bash(bash .claude/scripts/godot-verify.sh *)
---

# Studio Vault

Keeps the studio's memory across games: **reuse before building, harvest what
worked, remember what hurt.** The tool moves files and keeps records; this
skill decides what is worth keeping, shows the person, and asks before
anything is written to the game or the vault.

Reference: `.claude/docs/studio-vault.md`. Read the section you need.

## Parse Arguments

- **`find <what>`** (or a request to build a common system): Phase 1.
- **`add <module>`**: Phase 2.
- **`harvest <name> <path...>`**: Phase 3.
- **`update`**: Phase 4.
- **`lesson`** / **`promote <lesson>`**: Phase 5.
- **`verify <module>`**: Phase 3, step 4 only.
- **No argument**: `vault.sh brief`, `vault.sh outdated`, then ask.

## Phase 1: Find Before Building

1. `bash .claude/scripts/vault.sh search <words>` and `vault.sh lessons --text <words>`.
2. For a hit, `vault.sh show <module>`: read its README, files, autoloads
   and input actions, and check its `engine_min` against the project's pinned
   version.
3. Tell the person what exists and what it would and would not cover for this
   game, then recommend: add it, adapt it, or build fresh (say why).

## Phase 2: Add a Module

1. Ask: "May I add `<module>` to the game? It writes `<install_dir>/`, adds
   these autoloads/input actions to `project.godot`, and records it in
   `modules.lock.json`."
2. On yes: `vault.sh add <module>`. Then show the README's usage lines in the
   context of this game's code, and suggest a `/play-verify` scenario that
   uses it here.

## Phase 3: Harvest a System

1. Choose the files with the person: the system's scripts, scenes and data,
   not the game's own content. Keep the set small and self-contained.
2. Ask before writing to the vault: "May I harvest `<paths>` into the vault
   as `<name>`?" Then `vault.sh harvest <name> <paths> --description … --tags …`.
3. If it reports **external references** or undefined input actions, fix them
   (harvest the referenced files too, or remove the dependency) and harvest
   again. A module that is not self-contained is not reusable.
4. Write the README (how to use it, with code) and at least one test
   scenario (`files/tests/<scene>.tscn` + `tests/<name>.json` with
   `res://__module__/` paths); ask before writing. Then
   `vault.sh verify <name>`:
   - **PASS**: installs into an empty project, imports cleanly, scenarios held.
   - **FAIL**: name the error or the broken check, fix, verify again.
   - **NOT ASSESSED**: no Godot, or no test scenario; say which.
5. Remind the person to commit the template repo.

## Phase 4: Keep Modules Current

`vault.sh outdated`. For each newer version: `vault.sh diff <name>`; no local
edits, ask and `vault.sh update <name>`; local edits, ask whether they are an
improvement to `push` back (then verify) or a game-specific change to keep
(leave the module as it is and note it).

## Phase 5: Lessons

1. Capture: from the retrospective, post-mortem, playtest report or the
   conversation, draft each lesson as what happened, the evidence (a run, a
   report, a commit, a number) and what to do next time. Refuse to record one
   without evidence; say so.
2. Show the drafts and ask before saving; save each with
   `vault.sh lesson add --title … --kind … --tags … --skills … --body-file …`.
3. Promote a lesson that should change how a skill works:
   `vault.sh promote <lesson> --skill <skill>`. For a library skill this
   writes an addendum; for a studio skill, continue with `/skill-improve <skill>`.

## Next Steps

- After adding a module: `/play-verify` with a scenario that uses it.
- After harvesting: commit the template repo; the next `bin/new-game.sh`
  game sees it at session start.
- After lessons: `/skill-improve` for promoted studio-skill lessons.
