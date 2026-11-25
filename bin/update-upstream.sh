#!/bin/bash
# update-upstream.sh — pull the latest of both source projects.
#
#   bin/update-upstream.sh            # report only
#   bin/update-upstream.sh --library  # also replace .claude/library/ and re-sync
#
# awesome-gamedev-agent-skills is vendored unmodified in .claude/library/, so
# --library replaces it wholesale, re-copies the active skills and runs its
# validator.
#
# Claude Code Game Studios is the base of this repo and some of its files carry
# local changes (see the "Local changes" list in README.md), so it is never
# overwritten: the script lists the files that changed upstream since the
# commit in UPSTREAM.lock, for you to merge by hand (or ask Claude to).

set -eu
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/UPSTREAM.lock"
CCGS_URL=https://github.com/Donchitos/Claude-Code-Game-Studios
AGAS_URL=https://github.com/gamedev-skills/awesome-gamedev-agent-skills
TMP="$(mktemp -d)"
trap 'rm -r "$TMP"' EXIT

locked() { grep "^$1 " "$LOCK" 2>/dev/null | awk '{print $2}'; }

echo "Fetching upstreams..."
git clone -q "$CCGS_URL" "$TMP/ccgs"
git clone -q --depth 1 "$AGAS_URL" "$TMP/agas"
ccgs_new=$(git -C "$TMP/ccgs" rev-parse --short HEAD)
agas_new=$(git -C "$TMP/agas" rev-parse --short HEAD)
ccgs_old=$(locked ccgs); agas_old=$(locked agas)

echo
echo "Claude Code Game Studios: ${ccgs_old:-?} -> $ccgs_new"
if [ -n "$ccgs_old" ] && [ "$ccgs_old" != "$ccgs_new" ]; then
  git -C "$TMP/ccgs" diff --stat "$ccgs_old" HEAD | tail -n 25
  echo "  Merge these by hand; files in README.md's 'Local changes' list need care."
elif [ "$ccgs_old" = "$ccgs_new" ]; then
  echo "  up to date"
fi

echo
echo "awesome-gamedev-agent-skills: ${agas_old:-?} -> $agas_new"
if [ "${1:-}" = "--library" ]; then
  rsync -a --delete --exclude .git --exclude .github "$TMP/agas/" "$ROOT/.claude/library/"
  bash "$ROOT/.claude/scripts/library.sh" sync >/dev/null
  (cd "$ROOT/.claude/library" && python3 -I scripts/validate-skills.py | tail -n 2)
  sed -i.bak "s/^agas .*/agas $agas_new $(date +%F)/" "$LOCK" && rm "$LOCK.bak"
  echo "  library replaced and active skills re-synced"
  echo "  integrity after the update:"
  bash "$ROOT/.claude/scripts/evals.sh" static | sed 's/^/    /'
  echo "  then: evals.sh behavior (paid, asks first) to check the agents still route to renamed skills"
elif [ "$agas_old" != "$agas_new" ]; then
  echo "  run again with --library to take it"
else
  echo "  up to date"
fi
