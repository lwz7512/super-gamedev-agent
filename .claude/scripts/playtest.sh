#!/bin/bash
# playtest.sh — the playtest and telemetry layer: in-game telemetry, simulation
# bots, a session collector, and reports with charts.
#
#   playtest.sh install [--playtest] [--endpoint URL]   telemetry into the Godot game
#   playtest.sh simulate monkey --runs 100               headless bot runs
#   playtest.sh collect                                  receive sessions from testers
#   playtest.sh report                                   Markdown + charts from all data
#   playtest.sh --help                                   every command
#
# Reference: .claude/docs/playtest-data.md. Needs Python 3.9+; Pillow for charts
# (it reuses asset-forge's .claude/.venv when one exists).

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUDIO="$(cd "$HERE/../.." && pwd)"
PY=""
for c in "$STUDIO/.claude/.venv/bin/python" "$(command -v python3 2>/dev/null)"; do
  [ -n "$c" ] && [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null && { PY="$c"; break; }
done
[ -n "$PY" ] || { echo "NOT ASSESSED: no Python 3.9+ found"; exit 3; }
exec "$PY" "$HERE/playtest/cli.py" "$@"
