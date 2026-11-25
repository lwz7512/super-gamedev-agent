#!/bin/bash
# evals.sh — evaluation of the combined studio (layer 5).
#
#   evals.sh static                    integrity checks (free; CI runs these)
#   evals.sh selftests [--godot]       every layer's test suite
#   evals.sh behavior [--case ID] --yes   real Claude Code runs, scored (costs money)
#   evals.sh --help                    every command
#
# Reference: .claude/docs/evals.md. Needs Python 3.9+; behaviour runs need the
# claude CLI signed in.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 2>/dev/null)"
[ -n "$PY" ] || { echo "NOT ASSESSED: python3 not found"; exit 3; }
exec "$PY" "$HERE/evals/cli.py" "$@"
