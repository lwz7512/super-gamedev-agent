---
name: studio-evals
description: "Checks that the combined studio still works as one system: static integrity checks (skill references, router patch, hooks, scripts, docs, vault), every layer's self-tests, and behaviour evals that run Claude Code on throwaway games and score what it actually did (skills loaded, ask-before-write, paid-call guards). PASS/FAIL/NOT ASSESSED. Use after updating the upstream projects, editing agents, skills, hooks or CLAUDE.md, changing models, or when something in the studio seems to have stopped working."
argument-hint: "[static | selftests [--godot] | behavior [case...] | all]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, AskUserQuestion, Bash(bash .claude/scripts/evals.sh static*), Bash(bash .claude/scripts/evals.sh selftests*), Bash(bash .claude/scripts/evals.sh all*), Bash(bash .claude/scripts/evals.sh cases*), Bash(bash .claude/scripts/evals.sh library-triggers*), Bash(bash .claude/scripts/evals.sh behavior*)
---

# Studio Evals

Tests the joints between the studio, the library and the four added layers.
Reference: `.claude/docs/evals.md`.

## Parse Arguments

- **`static`**: Phase 1 only.
- **`selftests [--godot]`**: Phase 2 only.
- **`behavior [case...]`**: Phase 3 only.
- **`all`** or no argument: Phases 1 and 2, then offer Phase 3.

## Phase 1: Static Checks

`bash .claude/scripts/evals.sh static`. For each **FAIL**, read the listed
items and find the cause: a renamed upstream skill (fix the agent's Knowledge
Library line), a lost router patch (`library.sh sync`), a broken link or
script. Propose each fix and ask before writing it. A **NOT ASSESSED** check
crashed or had nothing to read: say which and why.

## Phase 2: Self-tests

`bash .claude/scripts/evals.sh selftests` (add `--godot` when Godot is
installed; the layer-1 suite and the Godot integration tests need it). A
failing suite: run it alone for its full output and treat it as a bug in that
layer.

## Phase 3: Behaviour Evals (paid)

1. `bash .claude/scripts/evals.sh cases`, and choose the cases that cover the
   change (all of them after an upstream update).
2. `bash .claude/scripts/evals.sh behavior --case …` prints the plan and
   exits 4. Show the person the plan (runs, model, cap per run, total cap) and
   ask. **Never add `--yes` without their yes in this conversation.**
3. On yes, run with `--yes` (and `--n 3` for a rate rather than an anecdote).
   Read `production/evals/<label>/report.md`. For a failed run, quote what the
   agent loaded and ran, and say which joint broke: a missing trigger in a
   skill description, CLAUDE.md guidance that did not reach the agent, an
   agent section pointing the wrong way.

## Verdict

- **FAIL**: any static check, self-test or behaviour case failed. Name each.
- **NOT ASSESSED**: something could not run (no Godot, no claude CLI, the
  person declined the paid runs). Say what would assess it.
- **PASS**: all that ran passed; list what did not run.

## Next Steps

- A broken skill trigger or instruction: `/skill-improve <skill>`, then
  re-run the failing case.
- After fixes from an upstream update: commit, then `evals.sh static` runs in CI on every push.
- Record anything surprising as a lesson: `/studio-vault lesson`.
