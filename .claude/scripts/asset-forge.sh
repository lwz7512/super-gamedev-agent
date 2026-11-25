#!/bin/bash
# asset-forge.sh — the asset production layer: generate, clean up, check,
# import and record game art and sound.
#
#   asset-forge.sh setup          make .claude/.venv with Pillow (only if no Python here has it)
#   asset-forge.sh <command> ...  see: asset-forge.sh --help
#
# Generators: OpenArt images through its MCP server (Claude calls it, results
# come in with `ingest`), ElevenLabs sound effects and voice (paid: --yes after
# the person agrees), sfxr synth and placeholders (free, local). Everything else
# (keying, fitting, palette, QA, contact sheets, Godot import, the in-engine
# gallery and the licence ledger) is local. Reference: .claude/docs/asset-forge.md
#
# Needs Python 3.9+ with Pillow; ffmpeg for mp3/ogg audio.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUDIO="$(cd "$HERE/../.." && pwd)"
VENV="$STUDIO/.claude/.venv"

has_pil() { "$1" -c 'import sys, PIL; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; }

if [ "${1:-}" = setup ]; then
  command -v python3 >/dev/null || { echo "NOT ASSESSED: python3 not found"; exit 3; }
  python3 -m venv "$VENV" && "$VENV/bin/python" -m pip install -q "Pillow>=10,<13" \
    && echo "ready: $VENV (Pillow $("$VENV/bin/python" -c 'import PIL; print(PIL.__version__)'))"
  exit $?
fi

PY=""
for c in "$VENV/bin/python" "$(command -v python3 2>/dev/null)"; do
  [ -n "$c" ] && [ -x "$c" ] && has_pil "$c" && { PY="$c"; break; }
done
if [ -z "$PY" ]; then
  echo "NOT ASSESSED: no Python 3.9+ with Pillow found. Run: bash .claude/scripts/asset-forge.sh setup"
  exit 3
fi
exec "$PY" "$HERE/assetforge/cli.py" "$@"
