---
name: make-assets
description: "Produces game art and sound from specs: OpenArt images via its MCP, ElevenLabs sound effects and voice, sfxr synth SFX and placeholders, then cleans them up (key out backgrounds, fit, palette lock, level audio), checks them, imports them into Godot, looks at them in-engine and records licences. PASS/FAIL/NOT ASSESSED. Use to make, generate, replace or fix sprites, tiles, icons, UI art, sound effects or voice lines, or to check assets and their licences before release."
argument-hint: "[<asset-id> | spec:<target> | sfx <what> | voice <line> | placeholders | check | ledger [--release] | setup]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, AskUserQuestion, Bash(bash .claude/scripts/asset-forge.sh *), Bash(bash .claude/scripts/godot-verify.sh *)
---

# Make Assets

Runs the asset production layer: **generate → clean up → check → look →
import → look in-engine → record**. The tool does the deterministic work and
reports observations; this skill decides, looks at the pictures, and asks the
person at every step that costs money or writes their files.

Reference for every command, generator, licence rule and limit:
`.claude/docs/asset-forge.md`. Read the section you need.

## Parse Arguments

- **`<asset-id>`**: produce or redo that manifest entry (Phase 2 onward).
- **`spec:<target>`**: turn `design/assets/specs/<target>-assets.md` (from
  `/asset-spec`) into manifest entries, then produce them.
- **`sfx <what>`** / **`voice <line>`**: one sound or voice line, start to end.
- **`placeholders`**: greybox every planned image so the build can run now.
- **`check`**: QA, contact sheet and ledger over everything; no generation.
- **`ledger [--release]`**: licence and provenance check only.
- **`setup`**: Phase 1 only.
- **No argument**: show `asset-forge.sh status` and ask what to make.

## Phase 1: Setup

1. **Style lock.** If `assets/style.json` is missing, read the art bible
   (`design/art/art-bible.md`) and any `/asset-spec` output, propose the
   values (kind pixel or hd, category sizes, palette, key colour that the art
   never uses, preview background, one-line style prompt), and ask:
   "May I write `assets/style.json` and `assets/manifest.json`?" On yes:
   `bash .claude/scripts/asset-forge.sh init --kind <kind>`, then edit the
   style file with the approved values.
2. **Plans.** Ask which OpenArt and ElevenLabs plans the person is on and
   record them in `providers.<name>.plan`: the ledger needs them to check
   commercial-use terms.
3. **Tools.** `asset-forge.sh status` reports a missing Pillow (offer
   `asset-forge.sh setup`, which makes `.claude/.venv`). OpenArt needs the MCP
   server signed in: if no OpenArt tools are available, ask the person to run
   `/mcp` and sign in to `openart`. ElevenLabs needs `ELEVENLABS_API_KEY` in the
   environment; never ask for the key in chat or write it to a file.

## Phase 2: Plan the Assets

1. Each asset becomes one manifest entry (`asset-forge.sh add …`): id, kind,
   category, the prompt (subject, pose, view: what changes between assets;
   the style lock supplies the rest), provider, frames and fps for animations,
   loop for music and ambience.
2. Choose the provider per asset: OpenArt for final art, placeholders until
   the art direction is approved, sfxr synth for retro or prototype SFX,
   ElevenLabs for realistic SFX and voice.
3. Show the plan as a table, including **what each paid call costs in
   generations** (count × takes), and ask before writing the manifest entries.

## Phase 3: Generate

- **OpenArt:** for each image, run `asset-forge.sh prompt <id>` and pass that
  prompt to the OpenArt MCP generation tool (ask for 2 to 4 variants on the
  first, approved target; families reuse it as the reference image). Then
  `asset-forge.sh ingest <result-url> --id <id> --provider openart --model <model>`.
  For an animation, generate frame 1, then each later frame as an edit of
  frame 1, and ingest each with `--frame <n>`.
- **ElevenLabs:** `asset-forge.sh gen <id>` prints the plan and exits 4.
  Ask: "This makes N ElevenLabs call(s): <plan>. Go ahead?" Only on yes, run
  it again with `--yes`.
- **Synth / placeholder:** `asset-forge.sh gen <id>` (free; for synth try
  2–3 seeds and keep the one that fits).

Generate one approved target before a family. Never start a large paid batch
without the count confirmed.

## Phase 4: Clean Up, Check, Look

1. `asset-forge.sh normalize <id>` per asset (pick a take with `--take N`).
2. `asset-forge.sh qa` and `asset-forge.sh sheet`, then `Read` the sheet.
   Judge what the checks cannot: on-style, readable at native size, the
   silhouette clear on the game background, the waveform shape right for the
   sound. A failed check: fix the source (regenerate with a sharper prompt,
   a thicker outline, a different seed) rather than lowering the bar.
3. Show the sheet and the QA table to the person, and ask which assets to
   approve.

## Phase 5: Import and Look In-Engine (Godot)

1. Ask: "May I import these into the Godot project (writes `.import`
   settings, SpriteFrames for animations, and a gallery in
   `tests/asset_gallery/`)?" For pixel art, ask separately before
   `--set-nearest`, which edits `project.godot`.
2. `asset-forge.sh godot [ids] [--set-nearest]`, then
   `bash .claude/scripts/godot-verify.sh run tests/scenarios/asset-gallery.json`.
   `Read` the gallery shot and the filmstrip: blur means the filter is
   wrong, a missing sprite means it failed to load.
3. Not a Godot project: skip with **NOT ASSESSED** for the in-engine look and
   say which engine skill covers its import.

## Phase 6: Record and Verdict

1. `asset-forge.sh ledger check` (`--release` before shipping).
2. Mark approved assets `approved` in the manifest and update
   `design/assets/asset-manifest.md` statuses (ask before writing).
3. Verdict, in order:
   - **FAIL**: a QA check, the gallery run, or the ledger failed. Name each.
   - **NOT ASSESSED**: something could not be checked (no Godot, no ffmpeg,
     a plan not recorded, the person has not looked yet). Say what would
     make it assessable.
   - **PASS**: every asset passed QA, loaded and looked right in-engine,
     and has a clean ledger entry.

Report the verdict, the table of assets with status, what you saw in the
sheet and gallery, the paid calls made, and anything left as a placeholder.

## Next Steps

- New art for a system or character: `/asset-spec` first, then this skill.
- Assets that change what the player sees in a story: close the story with
  `/play-verify` and `/story-done`.
- Before a release: this skill with `ledger --release`, then
  `/release-checklist` (Steam's AI disclosure uses the ledger's count).
