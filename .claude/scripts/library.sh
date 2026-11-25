#!/bin/bash
# library.sh — activate gamedev knowledge-library skills for this project.
#
# The library (.claude/library/, vendored from awesome-gamedev-agent-skills)
# holds 79 engine, discipline, genre and workflow skills. Claude Code lists
# every skill in .claude/skills/ in its context, and past the listing budget
# descriptions get cut, so only the groups this project needs are copied in.
# The router (always active) can still read any inactive skill straight from
# .claude/library/skills/.
#
# Usage:
#   library.sh status                 active groups and skills
#   library.sh groups                 every group and the skills in it
#   library.sh activate <group>...    copy groups into .claude/skills/
#   library.sh deactivate <group>...  remove them again ("all" = every library skill)
#   library.sh sync                   re-copy active skills from the library
#                                     (after tools/update-upstream.sh)
#   library.sh check                  one line if the project's engine group is
#                                     not active (session-start runs this)
#
# Groups: core (disciplines + genres + itch/steam publishing; always wanted),
#   workflows (all five, incl. game-jam/prototype-fast/game-docs), router,
#   godot, unity, unreal, ebitengine, web (phaser + pixijs + threejs),
#   phaser, pixijs, threejs, bevy, pygame, love2d, defold, roblox.
# Engine names as project.yaml records them (Godot, Unity, Unreal, Web) are
# accepted in any case.
#
# Every copied folder gets a .library marker naming its source. deactivate and
# sync only ever touch folders that carry it, so CCGS skills are never removed.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LIB="$ROOT/.claude/library"
SK="$ROOT/.claude/skills"
MARK=".library"

[ -d "$LIB/skills" ] || { echo "library.sh: no library at $LIB" >&2; exit 1; }

# group -> library-relative skill folders
known_group() {
  case " $LIB_GROUPS pixi three love " in *" $(echo "$1" | tr '[:upper:]' '[:lower:]') "*) return 0 ;; esac
  return 1
}

group_paths() {
  known_group "$1" || return 1
  case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
    # core leaves out game-jam, prototype-fast and game-docs: CCGS's /prototype,
    # /brainstorm and design-doc skills own those jobs here, and two listed
    # skills for one job split the trigger. The router can still read them.
    core)       ls -d "$LIB"/skills/disciplines/*/ "$LIB"/skills/genres/*/ \
                      "$LIB"/skills/workflows/itch-publish/ "$LIB"/skills/workflows/steam-publish/ ;;
    workflows)  ls -d "$LIB"/skills/workflows/*/ ;;
    router)     echo "$LIB/router/" ;;
    godot)      ls -d "$LIB"/skills/godot/*/ ;;
    unity)      ls -d "$LIB"/skills/unity/*/ ;;
    unreal)     ls -d "$LIB"/skills/unreal/*/ ;;
    ebitengine) ls -d "$LIB"/skills/ebitengine/*/ ;;
    web)        ls -d "$LIB"/skills/web-engines/*/ ;;
    phaser)     ls -d "$LIB"/skills/web-engines/phaser-*/ ;;
    pixijs|pixi) ls -d "$LIB"/skills/web-engines/pixijs-*/ ;;
    threejs|three) ls -d "$LIB"/skills/web-engines/threejs-*/ ;;
    bevy)       ls -d "$LIB"/skills/other-engines/bevy-*/ ;;
    pygame)     ls -d "$LIB"/skills/other-engines/pygame-*/ ;;
    love2d|love) ls -d "$LIB"/skills/other-engines/love2d-*/ ;;
    defold)     ls -d "$LIB"/skills/other-engines/defold-*/ ;;
    roblox)     ls -d "$LIB"/skills/other-engines/roblox-*/ ;;
    *) return 1 ;;
  esac 2>/dev/null | sed 's|/$||'
}

LIB_GROUPS="core workflows router godot unity unreal ebitengine web phaser pixijs threejs bevy pygame love2d defold roblox"

# Copy one library folder into .claude/skills/<name>/ with a marker.
install_one() {
  src="$1"; name="${src##*/}"; dst="$SK/$name"
  if [ -e "$dst" ] && [ ! -f "$dst/$MARK" ]; then
    echo "  SKIP $name: .claude/skills/$name exists and is not a library copy" >&2
    return 0
  fi
  rm -r "$dst" 2>/dev/null
  cp -R "$src" "$dst"
  echo "${src#$LIB/}" > "$dst/$MARK"
  # The router is the library's index: tell it where the catalog lives.
  if [ "$name" = router ]; then patch_router "$dst/SKILL.md"; fi
  echo "  + $name"
}

patch_router() {
  f="$1"
  grep -q 'LIBRARY-ROOT' "$f" && return 0
  tmp="$f.tmp"
  awk '
    /^# Master Router/ && !done {
      print; print ""
      print "<!-- LIBRARY-ROOT: added by .claude/scripts/library.sh -->"
      print "> **Catalog location in this project.** Every `skills/<category>/<name>/` path below is"
      print "> relative to `.claude/library/`. Skills already active in `.claude/skills/<name>/` are the"
      print "> same files; read an inactive one directly from `.claude/library/skills/...`, and suggest"
      print "> `bash .claude/scripts/library.sh activate <group>` if the project will keep needing it."
      print "> This router supplies **technical knowledge**; the studio workflow (briefs, stories, gates,"
      print "> agent roles, write-approval) still follows `CLAUDE.md`."
      print "> **Studio corrections.** After reading a library skill, run"
      print "> `bash .claude/scripts/vault.sh addenda <skill>`: addenda come from games made with this studio and"
      print "> win where they disagree with the skill. `vault.sh lessons --skill <skill>` lists what earlier"
      print "> games learned with it, and `vault.sh search <words>` finds a module already built for the job."
      done=1; next
    }
    { print }' "$f" > "$tmp" && mv "$tmp" "$f"
}

active_names() {
  for d in "$SK"/*/; do [ -f "$d$MARK" ] && basename "$d"; done
}

cmd="${1:-status}"; [ $# -gt 0 ] && shift
case "$cmd" in
  groups)
    for g in $LIB_GROUPS; do
      printf '%-11s %s\n' "$g" "$(group_paths "$g" | xargs -n1 basename | tr '\n' ' ')"
    done ;;
  status)
    n=$(active_names | wc -l | tr -d ' ')
    echo "Active library skills: $n (of $(find "$LIB/skills" -name SKILL.md | wc -l | tr -d ' ') + router)"
    for g in $LIB_GROUPS; do
      tot=0; on=0
      for p in $(group_paths "$g"); do
        tot=$((tot+1)); [ -f "$SK/${p##*/}/$MARK" ] && on=$((on+1))
      done
      [ $on -gt 0 ] && echo "  $g: $on/$tot"
    done
    echo "Total skills listed to Claude: $(ls -d "$SK"/*/ | wc -l | tr -d ' ')" ;;
  activate)
    [ $# -gt 0 ] || { echo "usage: library.sh activate <group>..." >&2; exit 2; }
    for g in "$@"; do
      known_group "$g" || { echo "unknown group: $g (see: library.sh groups)" >&2; exit 2; }
      paths=$(group_paths "$g")
      echo "$g:"
      for p in $paths; do install_one "$p"; done
    done ;;
  deactivate)
    [ $# -gt 0 ] || { echo "usage: library.sh deactivate <group>...|all" >&2; exit 2; }
    for g in "$@"; do
      if [ "$g" = all ]; then names=$(active_names)
      else known_group "$g" || { echo "unknown group: $g" >&2; exit 2; }
        names=$(group_paths "$g" | xargs -n1 basename)
      fi
      for n in $names; do
        [ -f "$SK/$n/$MARK" ] && rm -r "$SK/$n" && echo "  - $n"
      done
    done ;;
  sync)
    for n in $(active_names); do
      src="$LIB/$(cat "$SK/$n/$MARK")"
      if [ -d "$src" ]; then install_one "$src"
      else echo "  ! $n: source $src gone from the library; left as is" >&2; fi
    done ;;
  check)
    # One-line observation for session-start: is the project's engine group
    # active? Reports, never activates (helpers emit observations, not verdicts).
    eng=$(bash "$ROOT/.claude/hooks/yaml-helper.sh" get_effective_yaml_key engine.name 2>/dev/null | tr -d '"' )
    want=""
    case "$eng" in
      Godot) want=godot ;; Unity) want=unity ;; Unreal) want=unreal ;;
      Web) want=web ;;
      *)  # engines CCGS does not configure: read the project fingerprint
        if grep -qs 'hajimehoshi/ebiten' "$ROOT/go.mod"; then want=ebitengine
        elif grep -qs 'bevy' "$ROOT/Cargo.toml"; then want=bevy
        elif [ -f "$ROOT/game.project" ]; then want=defold
        elif ls "$ROOT"/*.rbxl* "$ROOT"/*.project.json >/dev/null 2>&1; then want=roblox
        elif grep -qs 'love\.' "$ROOT/main.lua"; then want=love2d
        elif grep -qsl '^import pygame' "$ROOT"/*.py >/dev/null 2>&1; then want=pygame
        fi ;;
    esac
    [ -n "$want" ] || exit 0
    on=0
    for p in $(group_paths "$want"); do [ -f "$SK/${p##*/}/$MARK" ] && on=$((on+1)); done
    if [ "$want" = web ] && [ $on -gt 0 ]; then exit 0; fi   # one web starter's skills is enough
    if [ $on -eq 0 ]; then
      echo "Knowledge library: the ${eng:-$want} skills are not active. bash .claude/scripts/library.sh activate $want"
    fi ;;
  -h|--help|help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "unknown command: $cmd (try --help)" >&2; exit 2 ;;
esac
