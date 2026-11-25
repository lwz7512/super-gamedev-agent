# Asset Forge — Asset Production

The asset production layer turns a spec into game-ready files and keeps the
record of where each one came from: **generate → clean up → check → look →
import → look in-engine → record.** It sits between `/asset-spec` (what each
asset must be) and the build, and it is run through `/make-assets`.

| Stage | How | Output |
|---|---|---|
| Lock | `assets/style.json` from the art bible: sizes per category, palette, key colour, alpha, audio levels, provider plans | the rules every check uses |
| Plan | `assets/manifest.json`: one entry per asset (id, kind, category, prompt, provider, path, frames, loop) | the work list |
| Generate | **OpenArt** images through its MCP server · **ElevenLabs** SFX and voice (REST) · **sfxr synth** SFX · **placeholders** | takes in `assets/_raw/<id>/` |
| Ingest | `ingest <url or file>`: OpenArt MCP results, downloads, your own art | takes with their origin |
| Normalize | images: remove the key colour or fake checkerboard, clean the fringe, trim, fit, anchor, palette lock, frame strip · audio: trim, fade, level, loop seam, encode | the file at its manifest path |
| QA | size, transparency, fake checkerboard, hard edges, padding, colour count, palette, frame baseline · silence, headroom, clipping, length, prompt start, loop seam | pass / fail / not assessed per check |
| Look | `sheet`: contact sheet (checkerboard and game background, whole-number zoom; sounds as waveforms) | `production/qa/assets/sheet.png` |
| Import | `godot`: import, settings (loop flags, lossless, no mipmaps), SpriteFrames for animations, optional Nearest filter | `.import` files, `*.frames.tres` |
| In-engine | the gallery scene played by `godot-verify.sh` (run-and-verify layer) | screenshot + filmstrip from Godot itself |
| Record | `assets/provenance.yaml` entries; `ledger check` enforces plan terms and placeholders | the licence trail |

```bash
bash .claude/scripts/asset-forge.sh init [--kind pixel|hd]
bash .claude/scripts/asset-forge.sh add hero-idle --kind image --category character --prompt "knight, idle stance, side view"
bash .claude/scripts/asset-forge.sh prompt hero-idle          # the full prompt for the OpenArt MCP call
bash .claude/scripts/asset-forge.sh ingest <openart-url> --id hero-idle --provider openart --model <model>
bash .claude/scripts/asset-forge.sh normalize hero-idle
bash .claude/scripts/asset-forge.sh add jump --kind sfx --preset jump --seed 3 && asset-forge.sh gen jump
bash .claude/scripts/asset-forge.sh add swing --kind sfx --provider elevenlabs --prompt "short sword swing" --duration 0.8
bash .claude/scripts/asset-forge.sh gen swing                 # exit 4: shows the paid plan, asks for --yes
bash .claude/scripts/asset-forge.sh qa && asset-forge.sh sheet
bash .claude/scripts/asset-forge.sh godot [--set-nearest]     # then: godot-verify.sh run tests/scenarios/asset-gallery.json
bash .claude/scripts/asset-forge.sh ledger check [--release]
bash .claude/scripts/asset-forge.sh status | selftest | setup
```

Exit codes: `0` done or pass · `1` a check failed · `3` not assessed or
something to fix (missing file, tool, key) · `4` a paid call is waiting for
the person's yes.

## Generators

**OpenArt (images) — MCP.** OpenArt has no public REST API; its official
agent route is the MCP server `https://mcp.openart.ai/mcp`, signed in with
your OpenArt account (OAuth, no key). It is registered in this repo's
`.mcp.json` and pre-approved in `.claude/settings.json` (`enabledMcpjsonServers`), so it connects without a startup prompt; run `/mcp` once to sign in. Claude calls the OpenArt tools with
the prompt from `asset-forge.sh prompt <id>`, then hands the result URL to
`ingest --provider openart --via mcp --model <model>`. OpenArt's terms forbid
scripts driving the web app (ToS 4.4), so the MCP server, not browser
automation, is the route. OpenArt does not document transparent output, so
every sprite prompt asks for a flat key-colour background (`art.key_color`,
default `#ff00ff`) that `normalize` removes. Pick a key colour the art itself
never uses.

**ElevenLabs (sound effects, voice) — REST.** `ELEVENLABS_API_KEY` in the
environment (never in a file). Sound effects: `POST /v1/sound-generation`
with `text`, `duration_seconds` (0.5–30), `loop`, `prompt_influence`,
`model_id` (`eleven_text_to_sound_v2` default). Voice: `POST
/v1/text-to-speech/{voice_id}` with `text`, `model_id`. The default output is
`mp3_44100_128`; 44.1 kHz WAV/PCM needs the Pro tier
(`providers.elevenlabs.output_format`). Every call is planned first and runs
only with `--yes`, after the person agrees to the count.

**sfxr synth (sound effects) — local, free.** Presets `coin laser explosion
powerup hit jump blip`; a preset plus a seed always gives the same sound.
Good for jams, prototypes and retro styles; try a few seeds and pick by ear.

**Placeholders — local, free.** Labelled boxes at the exact size, named
`_ph`, recorded as placeholders. `ledger check --release` fails while any
remain.

**Your own or licensed files.** Drop them in `assets/_inbox/` and
`ingest <file> --id <id> --origin you|cc0|licensed|bought --licence <SPDX> --vendor … --source-url …`.

## Licence terms the ledger enforces

Read from the official pages on 2026-11-25. Record each plan in
`style.json` (`providers.<name>.plan`); the ledger copies it into every entry
made with that provider.

| Provider | Commercial use | Also |
|---|---|---|
| OpenArt | Plus, Pro, Wonder (Starter and the free trial are non-commercial) — [terms](https://openart.ai/terms/), [pricing](https://openart.ai/suite/pricing) | OpenArt claims no copyright in output (ToS 4.1); watermarks may not be removed |
| ElevenLabs | any paid plan, Starter and up (Free is non-commercial, ToS 1(c)) — [terms](https://elevenlabs.io/terms-of-use) | sound effects may ship inside the game but never on their own: no SFX packs or sample sales ([Creative Terms](https://elevenlabs.io/creative-terms), Exhibit 4 s2) |

`ledger check` reads `project.goal`: for `sell`, `early_access`,
`publisher`, `mobile` **or unset**, a non-commercial plan is a **fail** and an
unrecorded plan is **not assessed**. It also fails any shipped file with no
entry or an `unknown` origin, and counts AI-generated files for Steam's AI
content disclosure. Terms change: re-read them before a release.

## Style lock (`assets/style.json`)

`art.kind` `pixel` (box downscale, palette or colour cap, hard alpha) or `hd`
(Lanczos, soft alpha) · `art.palette` (hex list; empty = no lock) ·
`art.max_colors` · `art.alpha` `binary|smooth` · `art.key_color` ·
`art.preview_background` (the game's typical backdrop) · `art.style_prompt`
(prefixed to every image prompt: the art bible in one line) · `art.avoid` ·
`art.categories.<name>` `{size, anchor: center|bottom-center|fill, padding, alpha}` ·
`audio` `{format: ogg|wav, peak_dbfs, sfx_max_seconds, lead_silence_ms}` ·
`providers`.

## Animations

`--frames N --fps F`: generate frame 1, then each further frame as an edit of
frame 1 (the OpenArt MCP accepts a reference image), ingest each with
`--frame i`, and `normalize` builds one horizontal strip. QA checks that the
frames share a baseline (no bobbing feet), and `godot` writes a SpriteFrames
resource the gallery plays, so the filmstrip shows the animation in-engine.

## Files and git

`assets/_raw/` and `assets/_inbox/` carry a `.gdignore` (Godot skips them);
their media is git-ignored, but each `assets/_raw/<id>/record.json` (prompt,
model, provider, date per take) is kept, and `provenance.yaml` points at it.
`production/qa/assets/` holds QA output and contact sheets. Python 3.9+ with
Pillow is needed (`asset-forge.sh setup` makes `.claude/.venv` when no Python
has it), and ffmpeg for mp3/ogg (Homebrew's ffmpeg lacks libvorbis; the
built-in Vorbis encoder is used instead).

## Limits

- **Judging taste is a person's call.** QA proves size, alpha, palette and
  levels; the contact sheet and gallery let Claude look; whether the art is
  *good* and on-style is decided by the art director and the person.
- **2D and audio only.** 3D assets go through the `blender-game-assets` skill.
- **Godot import only** for now; other engines get the files, QA and ledger.
- **Thin details vanish at sprite size.** Ask the generator for thick
  outlines and simple shapes when the target is 16–32 px.
