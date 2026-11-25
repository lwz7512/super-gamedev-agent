#!/bin/bash
# new-game.sh — start a new game project from this template.
#
#   bin/new-game.sh <target-dir> [library-group...]
#
# Copies the studio + knowledge library into <target-dir> (which must not
# exist or must be empty), runs `git init` there, and activates any library
# groups given (e.g. `godot`, `phaser`, `roblox`; see
# `.claude/scripts/library.sh groups`). `core` and `router` are always active.
#
# Examples:
#   bin/new-game.sh ~/games/dusk-fishing              # decide the engine later (/start)
#   bin/new-game.sh ~/games/tower-thing godot
#   bin/new-game.sh ~/games/arcade phaser
#
# Then: cd <target-dir> && claude, and say "make me a game" or run /start.

set -eu
TEMPLATE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ $# -ge 1 ] || { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
DEST="$1"; shift

if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
  echo "new-game: $DEST exists and is not empty; pick a new folder" >&2
  exit 1
fi
mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd)"

# Template-only files stay behind: this script, upstream bookkeeping, and any
# local session state or settings from working on the template itself.
rsync -a \
  --exclude '.git/' --exclude 'bin/' --exclude 'UPSTREAM.lock' \
  --exclude 'production/session-state/*' --exclude 'production/session-logs/' \
  --exclude '.claude/settings.local.json' --exclude 'project.local.yaml' \
  --exclude 'CLAUDE.local.md' --exclude '.claude/agent-memory/' \
  "$TEMPLATE/" "$DEST/"
mkdir -p "$DEST/production/session-state"

for g in "$@"; do
  bash "$DEST/.claude/scripts/library.sh" activate "$g" | tail -n +2 | wc -l |
    xargs -I{} echo "activated $g ({} skills)"
done

if command -v git >/dev/null 2>&1 && [ ! -d "$DEST/.git" ]; then
  git -C "$DEST" init -q && echo "git repository initialised (nothing committed)"
fi

bash "$DEST/.claude/scripts/library.sh" status
cat <<EOF

New project: $DEST
  cd "$DEST" && claude
  then say "make me a game" (/prototype) or run /start
EOF
