# Super Gamedev Agent

<p align="center">
  <a href="https://lwz7512.github.io/super-gamedev-agent/">
    <img src="site/assets/banner.svg" width="100%"
         alt="Super Gamedev Agent: a pixel-art level where a hero jumps from Idea to Brief, Build, Verify, Art and sound, Playtest and Ship, watched by a team of AI roles and you, the director">
  </a>
</p>

<p align="center">
  <b><a href="https://lwz7512.github.io/super-gamedev-agent/">Documentation site</a></b> ·
  <a href="https://lwz7512.github.io/super-gamedev-agent/guide/workflow.html">Workflow guide</a> ·
  <a href="https://lwz7512.github.io/super-gamedev-agent/skills/">Skills</a> ·
  <a href="https://lwz7512.github.io/super-gamedev-agent/vault/">Vault</a>
</p>

<p align="center">
  <a href="https://github.com/lwz7512/super-gamedev-agent/actions/workflows/studio-evals.yml"><img alt="Studio evals" src="https://github.com/lwz7512/super-gamedev-agent/actions/workflows/studio-evals.yml/badge.svg"></a>
  <a href="https://github.com/lwz7512/super-gamedev-agent/actions/workflows/godot-verify.yml"><img alt="Godot verify" src="https://github.com/lwz7512/super-gamedev-agent/actions/workflows/godot-verify.yml/badge.svg"></a>
  <a href="https://github.com/lwz7512/super-gamedev-agent/actions/workflows/playtest.yml"><img alt="Playtest" src="https://github.com/lwz7512/super-gamedev-agent/actions/workflows/playtest.yml/badge.svg"></a>
</p>

**Describe a game to Claude, and it helps you make it.** It asks a few
questions, writes a one-page plan, builds a version you can play, tests it,
helps with art and sound, and helps you finish and share it. It always asks
before it changes your files, and you can always go back.

You don't need to know how to code. If you do, it goes as deep as you want:
real game engines, design documents, a team of specialist AI agents, and
playtesting with bots.

## Which path is yours?

| You are… | Start with | Your first session |
|---|---|---|
| **New to making games** | [Your first game](#your-first-game) | about 30 minutes to a playable game in your browser |
| **A hobby developer with an idea** | [Make your idea](#make-your-idea) | an evening: a prototype you can show friends |
| **Already using a game engine** (Godot, Unity, Unreal, web) | [Bring your engine](#bring-your-engine) | set up your engine and keep building |
| **Shipping games regularly, alone or as a small team** | [Studio mode](#studio-mode) | planning, specialists, playtest data, reuse between games |
| **Customising this template** | [Under the hood](#under-the-hood) | how it is built, kept up to date and tested |

## Before you start

You need four things. All are free except Claude Code, which uses your Claude plan.

1. **[Claude Code](https://code.claude.com/docs/en/setup):** the AI assistant you talk to.
2. **[Git](https://git-scm.com/):** keeps every version of your game, so any change can be undone.
3. **[Python 3](https://www.python.org/):** the project's helper tools run on it.
4. **Chrome, Edge or Chromium:** your first games are browser games, tested in it.

Later, when you want them:

- **[Godot 4.5+](https://godotengine.org/)** (free): a full game engine; this
  template supports it best.
- **[Node.js](https://nodejs.org/):** to grow a browser game into a full web project.
- **ffmpeg:** for sound files. On macOS: `brew install ffmpeg`.

Then get the template once:

```bash
git clone https://github.com/lwz7512/super-gamedev-agent.git
```

Every game you make is its own copy, created from this template with
`bin/new-game.sh`.

## Your first game

*For complete beginners. No code, no engine.*

**1. Make a project and open Claude in it.**

```bash
super-gamedev-agent/bin/new-game.sh ~/games/my-first-game
cd ~/games/my-first-game
claude
```

**2. Say what you want to make.** Type it as you would to a friend:

```
/prototype a cat that collects fish while dodging seagulls
```

Not sure yet? Type `/start` and it will guide you. Even "a racing game" is
enough: it offers two or three one-line ideas to pick from.

**3. Answer a few questions.** About how it should feel, look and play. Every
question has a usual answer, so **"you pick"** is always fine.

**4. Read the one-page plan.** It lands in `design/game-brief.md`. Say
**"build it"**, or change something first.

**5. Play it.** The game appears in `prototypes/<name>/`. Double-click its
`index.html` to play in your browser. Claude has already played it with
scripted key presses and fixed obvious problems, but you are the real tester.

**6. Change it by asking.** In plain words:

- "make the seagulls slower at the start"
- "add a score and a high score"
- "the cat should feel bouncier when it jumps"
- "add a tweak panel so I can try different speeds myself"

Every change you accept is saved as a checkpoint, so you can always say
"undo that" or "go back to before the seagulls".

**7. Share it.** Say **"share it"** for a clean copy ready to upload to
[itch.io](https://itch.io) or send as a link.

**Stuck?** Type `/next-step` and it names the one thing to do next.
Claude asks **"May I write …?"** before changing files; you are always in charge.

## Make your idea

*For hobby developers: you have an idea and want to see it become a real game.*

1. **Prototype first.** Do [Your first game](#your-first-game) with your idea.
   A small playable version tells you more than any plan.
2. **Grow it.** When you like it, say **"grow it"**. It becomes a proper web
   project, and you add **one feature per session**: name it, and it is built,
   tested and saved.
3. **Or move to Godot.** For a bigger 2D or 3D game, make a Godot project:
   `bin/new-game.sh ~/games/my-game godot`, then `/start`. Claude learns Godot's
   current version and plays your game itself to check changes (`/play-verify`).
4. **Art and sound without paying.** Placeholder sprites and retro sound
   effects are built in and free: "make placeholder art for the player and
   enemies", "make a coin sound effect". When you are ready for real art,
   [OpenArt](https://openart.ai) and [ElevenLabs](https://elevenlabs.io) are
   connected too (paid plans; Claude always shows the cost and asks first).
5. **Let bots play first** (Godot games). "Run some bots on this level" sends
   automatic players through your game to find places they get stuck or fall
   out of the world, before your friends do.
6. **Then friends.** Send the game to a few people and ask what confused
   them. In a Godot game, a playtest build adds an **F8** feedback button
   (with a screenshot) and a report of where players quit and died.
7. **Finish.** `/cut` suggests what to cut and a polish list; then publish on
   itch.io or Steam.

## Bring your engine

*For developers who already use a game engine.*

```bash
super-gamedev-agent/bin/new-game.sh ~/games/my-game godot     # or unity, unreal, web, phaser, threejs...
cd ~/games/my-game && claude                                  # then /setup-engine
```

- **Godot** has the most support: version-pinned engine knowledge, specialist
  agents (GDScript, C#, shaders, GDExtension), automated play-testing from
  scenarios, Godot asset import, telemetry and simulation bots.
- **Unity, Unreal and web** (Phaser, PixiJS, three.js) get specialist agents,
  engine knowledge and the full planning workflow.
- **Ebitengine, Bevy, Defold, LÖVE, pygame and Roblox** get engine knowledge
  and the engine-neutral workflow.
- **An existing game?** `/prototype --from <path>` brings in a browser game;
  `/adopt` audits an existing project and plans how to bring it in.

Agents read current engine guidance before writing code (12 engines, pinned to
versions like Godot 4.7.2, Unity 6.3 LTS and Unreal 5.8), so they don't
suggest APIs your engine version no longer has.

## Studio mode

*For people shipping games regularly, alone or in a small team.*

Everything above, plus the parts a studio uses:

- **More structure when you want it:** `/project-settings modes.rigor=standard`
  (or `full`) adds design documents, architecture decisions, stories, sprints
  and phase gates. Read the [workflow guide](docs/WORKFLOW-GUIDE.md).
- **49 specialist agents** (creative and technical directors, designers,
  programmers, artists, QA, release) and team skills such as `/team-combat`
  and `/team-release` that coordinate them.
- **Evidence from play:** telemetry, feedback, bots and reports with
  funnels, drop-off and heatmaps (`/playtest-data`).
- **Memory across games:** reusable systems and lessons learned, offered to
  every new game (`/studio-vault`).
- **Licences tracked:** where every asset came from and whether its terms
  allow selling the game (`/make-assets`).
- **Checks on the setup itself:** `/studio-evals` tells you the whole system
  still works after updates.

The [documentation site](https://lwz7512.github.io/super-gamedev-agent/) has
every agent, skill and guide.

## Under the hood

This template combines two open-source projects and adds five layers.

- **Studio:** [Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios),
  the agents, workflow skills, hooks and rules. Its own tour: [docs/CCGS-README.md](docs/CCGS-README.md).
- **Knowledge:** [awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills),
  vendored unmodified in `.claude/library/`, activated per engine with `.claude/scripts/library.sh`.
- Added layers, one reference each:
  [run-and-verify](.claude/docs/godot-verify.md) ·
  [asset production](.claude/docs/asset-forge.md) ·
  [playtest data](.claude/docs/playtest-data.md) ·
  [studio vault](.claude/docs/studio-vault.md) ·
  [evals](.claude/docs/evals.md).

How Claude uses them is set out in [CLAUDE.md](CLAUDE.md).

**Keeping up to date:**

```bash
bin/update-upstream.sh            # what changed in both upstream projects
bin/update-upstream.sh --library  # take the new library, re-validate, run the static checks
```

**Checks:**

```bash
bash .claude/scripts/evals.sh all --godot      # integrity checks + every layer's tests
```

<details>
<summary>Files this template changes or adds in the studio base (for merging upstream updates)</summary>

- `CLAUDE.md`: title, the layer table and the layer sections
- `.claude/agents/*.md`: a **Knowledge Library** section in 44 agents (with vault addenda), plus
  **Run and Verify** (9), **Asset Production** (4) and **Playtest Data** (8) sections
- `.claude/skills/setup-engine/SKILL.md`: §9.5 (library activation, the Godot harness)
- `.claude/skills/asset-spec`, `playtest-report`, `retrospective`: a handoff line in their last section
- `.claude/docs/run-and-observe.md`, `skills-reference.md`, `docs/WORKFLOW-GUIDE.md`: pointers to the layers
- `.claude/scripts/skill-lint.sh`: `all` skips library copies; `.claude/hooks/session-start.sh`: library and vault briefs
- `.claude/settings.json`: `enabledMcpjsonServers: ["openart"]`; `.gitignore`: library, `bin/`, layer outputs
- new: `.claude/library/`, `.claude/scripts/{library,godot-verify,asset-forge,playtest,vault,evals}.sh` and their
  packages, `.claude/engines/godot/{verify,telemetry}/`, five skills, five docs, `.claude/evals/`, `vault/`,
  `.mcp.json`, `bin/`, `site/`, `UPSTREAM.lock`, five workflows in `.github/workflows/`
- moved: the studio's own README is `docs/CCGS-README.md`

</details>

## Words you'll see

| Word | Means |
|---|---|
| **Slash command** | A word starting with `/` that you type to Claude, like `/prototype` or `/next-step`. |
| **Skill** | What a slash command runs: a written procedure Claude follows. Many load by themselves when relevant. |
| **Agent** | A specialist Claude hands work to, such as a game designer or a Godot programmer. |
| **Engine** | Software games are built in, like Godot or Unity. Your first games need none: they run in a browser. |
| **Brief** | The one-page plan for your game: the idea, the look, the first minute, what to build first. |
| **Prototype** | A quick playable version, to find out whether the idea is fun. |
| **Scenario** | A script of key presses and checks Claude uses to play your Godot game and confirm it works. |
| **Vault** | This template's shared memory: code and lessons from earlier games, offered to new ones. |

## What it costs

- **Claude Code** uses your Claude plan. Bigger builds use more; say "build it
  at medium" for a cheaper, simpler first version.
- **Everything else in the template is free**, including placeholder art, retro
  sound effects, bots and reports.
- **Optional paid services**, used only if you set them up: OpenArt for art
  (Plus plan or higher if you will sell the game) and ElevenLabs for sound and
  voice (any paid plan to sell). Claude shows what a paid request will do and
  waits for your yes.

## License

Studio layer: MIT, © Donchitos (`LICENSE`). Knowledge library: Apache-2.0,
© gamedev-skills contributors (`.claude/library/LICENSE`, `.claude/library/NOTICE`),
included unmodified.
