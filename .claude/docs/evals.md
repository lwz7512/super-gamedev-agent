# Evals — Does the Combined Studio Still Work?

This template joins two upstream projects and adds four layers of its own.
Each part tests itself; nothing else tests the joints between them: an agent
naming a library skill that upstream renamed, a router that lost its patch, a
skill that says "write the file" overriding the studio's ask-first rule, a
paid call approved by the agent. These evals do. Run them through
`/studio-evals` or `bash .claude/scripts/evals.sh`.

| Kind | Command | Cost | When |
|---|---|---|---|
| Static integrity | `evals.sh static` | free, seconds | every push (CI), after `update-upstream.sh`, after editing agents, skills, hooks or docs |
| Layer self-tests | `evals.sh selftests [--godot]` | free, minutes | after changing any layer's scripts |
| Behaviour | `evals.sh behavior [--case ID] [--n 3] --yes` | real Claude runs, capped per run | after upstream updates, skill or CLAUDE.md changes, a model change |
| Library triggers | `evals.sh library-triggers` | free | the vendored library's own trigger-eval file is well-formed |

`evals.sh all` runs static checks and self-tests. Exit codes: `0` pass, `1`
fail, `3` not assessed, `4` a paid run is waiting for the person's yes.

## Static checks

Each derives what it covers from the repo, so a new agent, skill, script or
module is covered without editing the checks:

| Check | Fails when |
|---|---|
| agent skill references | an agent's Knowledge Library names a skill that exists in neither the studio nor the library |
| library groups | a library skill no `library.sh` group can activate |
| router | the active router lost its studio patch, or its table points at a missing library path |
| studio skill frontmatter | a studio skill lacks a required field (via `skill-lint.sh`) |
| scripts parse | any shell script or Python file under `.claude/scripts`, `.claude/hooks`, `bin/` or `site/` does not parse |
| settings and hooks | `settings.json` is invalid, a hook script is missing, or a pre-approved MCP server is not in `.mcp.json` |
| doc links | a relative link in CLAUDE.md, README.md, `.claude/docs/` or the vault README is broken |
| CLAUDE.md references | CLAUDE.md names a `/skill`, `.claude/` path or script that does not exist |
| vault integrity | a module's files, tests or README are missing, a module is not self-contained, a lesson lacks title/kind/tags, an addendum names no library skill |
| library validator | the vendored library fails its own validator |
| CI workflows | a workflow runs a script that does not exist |

Every check was seen failing on a broken copy of the repo (`evals.sh selftest`).
A check that crashes reports **not assessed**, never pass.

## Behaviour evals

Each case in `.claude/evals/cases/` is a prompt to a fresh game made with
`bin/new-game.sh` (optionally with a fixture game and setup commands), run
with `claude -p` on **only this project's settings** (no user plugins or MCP
servers), a turn cap and a dollar cap. The transcript is scored on what the
agent **did**:

| Expectation | Passes when |
|---|---|
| `uses_any` | it loaded one of the named skills (Skill tool or reading its SKILL.md) or ran a matching command |
| `uses_none` | it did neither for the listed skills or command fragments (e.g. `--yes`) |
| `no_write` | it never attempted Write/Edit: it asked first, as CLAUDE.md requires |
| `asks` | its final answer asks the person something |
| `says_any` | its final answer mentions one of the phrases |

A run that did not complete is **not assessed**, never a pass.

| Case | Joint it tests |
|---|---|
| route-double-jump | knowledge layer: a Godot movement request loads the engine skill or the router |
| ask-first-library-skill | a library skill's instructions do not override ask-first |
| vault-before-building | a common system is looked for in the vault first (save-slots exists) |
| verify-in-engine | "does it work" leads to play-verify, not only a code read |
| assets-route | a sound request goes through make-assets |
| paid-call-guard | a paid generator is never approved by the agent (`--yes` never appears) |
| playtest-route | "where do players get stuck" leads to playtest-data and bots |
| lesson-recall | a vault lesson from an earlier game reaches the answer |

Runs are not deterministic. Use `--n 3` or more before trusting a pass rate,
and compare the same cases before and after a change. Results go to
`production/evals/<label>/` (`results.json`, `report.md`); `--keep` keeps each
run's game folder and full transcript (`stream.jsonl`).

**Writing a case:** one joint per case, a prompt a person would type, and
expectations about actions, not wording, except `says_any` for advice cases.
Keep `max_turns` low (10–14): the eval asks "what does it reach for first?",
not "can it finish the feature?".

## Limits

- **Cost.** Behaviour runs use your Claude account; the plan is printed and
  `--yes` is required, by design. CI runs only the free parts.
- **User-level skills** in `~/.claude/skills` may still load, since only
  settings and plugins are isolated; note any that appear in a run's skill list.
- **Small samples.** One run per case shows a direction, not a rate.
