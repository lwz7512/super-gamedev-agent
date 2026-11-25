# Studio Vault — Memory and Reuse Across Games

Each game made from this template starts from zero unless something carries
over. The studio vault is that something: the systems your games built well,
the lessons they taught, and corrections to the library skills, kept in the
template repo's `vault/` folder and offered to every game that follows.
Run it through `/studio-vault`.

| Part | Where | What it holds |
|---|---|---|
| Modules | `vault/modules/<engine>/<name>/` | Reusable systems: files with relocatable paths, their autoloads and input actions, a README, test scenarios, a changelog |
| Lessons | `vault/lessons/<date>-<slug>.md` | What a game taught: what happened, the evidence, what to do next time; tagged by engine, kind, tags and skills |
| Addenda | `vault/addenda/<skill>.md` | Promoted lessons about a library skill, read beside it; they win where they disagree, and the library stays unmodified |
| Registry | `vault/games.json` | Every game made with `bin/new-game.sh`, and which module versions each uses |

A game finds the vault through `.claude/sga-template` (written by
`new-game.sh`; per machine, git-ignored). `SGA_VAULT` overrides it.
Commit the template repo after harvesting, pushing or adding lessons: the
vault's history is its git history.

## Modules

```bash
bash .claude/scripts/vault.sh search save                      # before building anything
bash .claude/scripts/vault.sh show save-slots                  # README, files, autoloads, actions
bash .claude/scripts/vault.sh add save-slots                   # -> res://modules/save_slots/ + modules.lock.json
bash .claude/scripts/vault.sh harvest combo-system systems/combo --description "..." --tags combat
bash .claude/scripts/vault.sh verify combo-system              # empty project: install, import, run its tests
bash .claude/scripts/vault.sh outdated | diff <name> | update <name> | push <name>
```

**Harvest** copies files (a folder or a list) out of the game. Every `res://`
path that points inside the harvested set becomes `res://__module__/...`;
installing replaces that with the game's folder (`res://modules/<name>` by
default, `--dir` to choose). Godot `uid="…"` attributes and `.uid`/`.import`
files are dropped, since Godot regenerates them. Autoloads that point into the
module, and the input actions its scripts read (with their definitions from
`project.godot`), travel with it. A path to a file outside the set is listed as
an **external reference**: harvest exits 1, and the module is not
self-contained until those files are harvested too or the code stops needing
them. Each harvest bumps the minor version and adds a changelog line naming the
game and commit.

**Add** copies the files, registers autoloads and missing input actions in
`project.godot`, and records each file's hash in `modules.lock.json`. It
refuses to write over a folder it did not create.

**Update** takes a newer vault version only when the game has not changed the
module's files; otherwise it lists the local edits and stops: `push` them back
first, or `--force` (old copies kept as `.orig`). **Push** turns the game's copy
back into vault files (paths made relocatable again) as the next minor version,
so one game's fix reaches the next.

**Verify** is the gate for "reusable": it installs the module into an empty
Godot project, imports it, counts errors, and plays each scenario in its
`tests/` through `godot-verify.sh`. A module that works only in the game it
came from fails here. (The seed module failed its first verify: its JSON parser
logged an engine error on a deliberately corrupt save.)

A module needs: a README that shows how to use it, at least one test
scenario (a scene under `files/tests/` plus `tests/<name>.json`, with
`res://__module__/` paths), and a clean verify.

## Lessons

```bash
bash .claude/scripts/vault.sh lessons --skill play-verify       # what earlier games learned
bash .claude/scripts/vault.sh lessons --tag save --engine godot
bash .claude/scripts/vault.sh lesson add --title "..." --kind pitfall --tags a,b --skills s1,s2 --body-file note.md
bash .claude/scripts/vault.sh promote <lesson-id> --skill <skill>
```

A lesson has a title, kind (`pitfall`, `technique`, `process`, `tool`,
`design`), engine, tags, the skills it bears on, and a body in three parts:
what happened, the evidence (a run, a report, a commit), and what to do next
time. A lesson without evidence is an opinion: keep it out.

**Where lessons come from:** `/retrospective` and the post-mortem, a
`/playtest-data` report, a bug that took a day, a CI failure on another
platform, anything that made you say "next time".

**Where they go:** session start prints the latest lessons for the game's
engine (`vault.sh brief`); agents read `vault.sh lessons --skill <skill>` and
`vault.sh addenda <skill>` beside each library skill; the router does too.

**Promotion** makes a lesson lasting. For a library skill (vendored, never
edited) it appends to `vault/addenda/<skill>.md`. For a studio skill it
marks the lesson promoted and hands it to `/skill-improve <skill>` to change
the skill itself with the person's approval. Retire a lesson that stopped
being true by setting `status: retired` in its header.

## Seed content

- Module `save-slots` (Godot 4.5+): atomic writes, a backup per slot, exact
  types through `JSON.from_native`, versioned migration; four checks in its
  scenario.
- Seven lessons learned while building this template's layers (headless
  screenshots, Logger and parse errors, lossy audio peaks, Area2D triggers,
  typed saves, monkey bots, .gitignore traps), two promoted to addenda for
  `godot-gdscript-headless-testing` and `save-systems`.

## Limits

- **Godot modules only** for harvest/add/verify path handling; other engines'
  lessons and addenda work the same.
- **Harvest finds what code references, not what it means.** A module that
  relies on a node path in a scene it does not include will import cleanly
  and fail at run time; write a test scenario that exercises it.
- **One vault per template checkout.** Several machines share it through the
  template's git remote: pull before you harvest, push after.
