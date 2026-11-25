#!/bin/bash
# vault.sh — the studio vault: reusable modules harvested from your games,
# lessons each game taught, addenda to library skills, and the game registry.
#
#   vault.sh search save            what exists before you build it
#   vault.sh add save-slots         install a module into this game
#   vault.sh harvest <name> <path>  keep a system this game built well
#   vault.sh lessons --skill X      what earlier games learned
#   vault.sh --help                 every command
#
# The vault is the template repo's vault/ folder (found through
# .claude/sga-template in a game made by bin/new-game.sh). Reference:
# .claude/docs/studio-vault.md. Needs Python 3.9+.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 2>/dev/null)"
[ -n "$PY" ] || { echo "NOT ASSESSED: python3 not found"; exit 3; }
exec "$PY" "$HERE/vault/cli.py" "$@"
