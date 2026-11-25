#!/bin/bash
# godot-verify.sh — run-and-verify layer for Godot: play the game, observe it.
#
# Usage (from the Godot project root, or pass --project DIR):
#   godot-verify.sh install                  copy the harness into addons/sga_verify/
#   godot-verify.sh run <scenario.json>      play a scenario; report.json + shots
#        [--out DIR] [--render|--headless] [--update-baselines]
#        [--timeout SECONDS] [--resolution WxH]
#   godot-verify.sh smoke [res://scene.tscn] [--frames N] [--render]
#                                            boot, run N frames, count errors
#   godot-verify.sh determinism <scenario.json> [--out DIR]
#                                            run twice headless, compare traces
#   godot-verify.sh selftest                 prove the harness on its fixture:
#                                            a pass, a fail, a runtime error, a parse
#                                            error, a not-assessed
#                                            and a determinism run
#
# A scenario (format: .claude/docs/godot-verify.md) drives input at exact
# frames, checks expressions against live nodes, and takes screenshots, a
# filmstrip and a state trace. The harness is added as an autoload through a
# temporary override.cfg, so project.godot is never edited.
#
# Output is observations: what held, what broke, what could not be checked.
# Exit: 0 every check held and no errors · 1 a check failed or the game logged
# an error · 3 not assessed (no Godot, no harness, timeout, crash, or a check
# that could not be evaluated). The skill (/play-verify) turns this into the
# studio's `Run result:` line.
#
# Extra engine flags: SGA_GODOT_ARGS (e.g. "--rendering-driver opengl3"); extra
# game arguments (after --): SGA_USER_ARGS (e.g. "--playtest").
# Godot is found from $GODOT, `engine.path` in project.yaml, PATH (godot,
# godot4), then the standard macOS app locations.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUDIO="$(cd "$HERE/../.." && pwd)"
ADDON_SRC="$STUDIO/.claude/engines/godot/verify/addons/sga_verify"
FIXTURE="$STUDIO/.claude/engines/godot/verify/fixture"
MARK="; sga-verify: temporary, restored after the run"

PROJ=""; OUT=""; MODE=auto; UPDATE=""; TIMEOUT=120; RES=""; FRAMES=120
POS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJ="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --render) MODE=render; shift ;;
    --headless) MODE=headless; shift ;;
    --update-baselines) UPDATE=1; shift ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --resolution) RES="$2"; shift 2 ;;
    --frames) FRAMES="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) POS+=("$1"); shift ;;
  esac
done
CMD="${POS[0]:-}"

na() { echo "NOT ASSESSED: $*"; exit 3; }

find_project() {
  [ -n "$PROJ" ] && { [ -f "$PROJ/project.godot" ] || na "no project.godot in $PROJ"; PROJ="$(cd "$PROJ" && pwd)"; return; }
  if [ -f project.godot ]; then PROJ="$PWD"
  elif [ -f "$STUDIO/project.godot" ]; then PROJ="$STUDIO"
  else na "no project.godot here or at $STUDIO (pass --project DIR)"; fi
}

find_godot() {
  local c p
  for c in "${GODOT:-}" \
           "$(bash "$STUDIO/.claude/hooks/yaml-helper.sh" get_effective_yaml_key engine.path 2>/dev/null | tr -d '"')" \
           "$(command -v godot 2>/dev/null)" "$(command -v godot4 2>/dev/null)" \
           /Applications/Godot.app/Contents/MacOS/Godot "$HOME/Applications/Godot.app/Contents/MacOS/Godot" \
           /Applications/Godot_mono.app/Contents/MacOS/Godot; do
    [ -n "$c" ] || continue
    # engine.path may name the .app or folder rather than the binary
    for p in "$c" "$c/Contents/MacOS/Godot"; do
      [ -f "$p" ] && [ -x "$p" ] && { G="$p"; return; }
    done
  done
  na "Godot binary not found (set GODOT=/path/to/godot or engine.path in project.yaml)"
}

version_note() {
  local have want
  have=$("$G" --version 2>/dev/null | head -1)
  want=$(grep -o 'config/features=PackedStringArray("[0-9.]*' "$PROJ/project.godot" | grep -o '[0-9.]*$')
  echo "godot: $G ($have)"
  case "$have" in "$want".*|"$want") ;; *) [ -n "$want" ] && echo "note: project targets Godot $want, this binary is $have" ;; esac
}

need_harness() {
  [ -f "$PROJ/addons/sga_verify/verify.gd" ] || na "harness not installed in $PROJ (run: godot-verify.sh install)"
  if ! cmp -s "$ADDON_SRC/verify.gd" "$PROJ/addons/sga_verify/verify.gd"; then
    echo "note: addons/sga_verify differs from the studio copy; 'install' updates it"
  fi
}

# override.cfg adds the autoload for this run only. An existing file is kept
# and restored; a stale one from a killed run is cleaned up first.
OVR_BACKUP=""
inject() {
  local o="$PROJ/override.cfg"
  if [ -f "$o" ] && head -1 "$o" | grep -qF "$MARK"; then
    if [ -f "$o.sga-backup" ]; then mv "$o.sga-backup" "$o"; else rm "$o"; fi
  fi
  if [ -f "$o" ]; then cp "$o" "$o.sga-backup"; OVR_BACKUP=1; fi
  {
    echo "$MARK"
    [ -n "$OVR_BACKUP" ] && cat "$o.sga-backup"
    printf '\n[autoload]\nSgaVerify="*res://addons/sga_verify/verify.gd"\n'
  } > "$o.tmp" && mv "$o.tmp" "$o"
  trap restore EXIT INT TERM
}
restore() {
  local o="$PROJ/override.cfg"
  if head -1 "$o" 2>/dev/null | grep -qF "$MARK"; then
    if [ -n "$OVR_BACKUP" ]; then mv "$o.sga-backup" "$o"; else rm -f "$o"; fi
  fi
}

# The window opens at the size the project designs for: the window override,
# else the viewport size, else Godot's 1152x648 default. --resolution wins.
project_resolution() {
  [ -n "$RES" ] && return
  local f="$PROJ/project.godot" w h
  w=$(grep -E '^window/size/window_width_override=' "$f" | cut -d= -f2)
  h=$(grep -E '^window/size/window_height_override=' "$f" | cut -d= -f2)
  [ -n "$w" ] && [ "$w" != 0 ] || w=$(grep -E '^window/size/viewport_width=' "$f" | cut -d= -f2)
  [ -n "$h" ] && [ "$h" != 0 ] || h=$(grep -E '^window/size/viewport_height=' "$f" | cut -d= -f2)
  RES="${w:-1152}x${h:-648}"
}

ensure_import() {
  [ -d "$PROJ/.godot" ] && return
  echo "importing project (first run)..."
  "$G" --headless --path "$PROJ" --import >/dev/null 2>&1
}

json_get() {  # json_get <file> <python expression on d>
  python3 -I -c "import json,sys; d=json.load(open(sys.argv[1])); v=$2; print('' if v is None else v)" "$1" 2>/dev/null
}

# run_once <scenario-abs> <out-dir> <mode> -> sets RC
run_once() {
  local scn="$1" out="$2" mode="$3" scene flags log pid waited=0
  mkdir -p "$out"
  rm -f "$out/report.json" "$out/trace.jsonl" "$out/filmstrip.png"   # never read a stale report
  rm -rf "$out/shots"
  scene=$(json_get "$scn" "d.get('scene')")
  if [ "$mode" = headless ]; then flags="--headless"; else project_resolution; flags="--windowed --resolution $RES"; fi
  flags="$flags ${SGA_GODOT_ARGS:-}"      # e.g. --rendering-driver opengl3 on CI
  log="$out/godot.log"
  # shellcheck disable=SC2086
  "$G" $flags --path "$PROJ" --fixed-fps 60 ${scene:+"$scene"} -- \
       "--sga-scenario=$scn" "--sga-out=$out" ${UPDATE:+--sga-update-baselines} ${SGA_USER_ARGS:-} > "$log" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$waited" -ge "$TIMEOUT" ]; then
      kill "$pid" 2>/dev/null; sleep 1; kill -9 "$pid" 2>/dev/null
      echo "timeout after ${TIMEOUT}s" > "$out/timeout"
      break
    fi
    sleep 1; waited=$((waited + 1))
  done
  wait "$pid" 2>/dev/null; RC=$?
}

# summarise <out-dir> -> prints observations, sets STATUS (pass|fail|not_assessed)
summarise() {
  local out="$1"
  if [ ! -f "$out/report.json" ]; then
    STATUS=not_assessed
    if [ -f "$out/timeout" ]; then echo "NOT ASSESSED: the run did not finish within ${TIMEOUT}s"
    elif grep -q 'Unable to create DisplayServer' "$out/godot.log" 2>/dev/null; then
      echo "NOT ASSESSED: Godot could not open a window (sandbox or no display); retry outside the sandbox or with --headless"
    else echo "NOT ASSESSED: no report (Godot exited $RC before the scenario finished: crash, or the game quit itself)"; fi
    echo "log tail ($out/godot.log):"; tail -n 15 "$out/godot.log" 2>/dev/null | sed 's/^/  /'
    return
  fi
  python3 -I - "$out/report.json" "$out/godot.log" <<'PY'
import json, re, sys
r = json.load(open(sys.argv[1]))
try:
    log = open(sys.argv[2], errors="replace").read().splitlines()
except OSError:
    log = []
# Errors the harness's Logger never sees: anything before it started (a failed
# autoload) and parse errors at any time (Godot reports those outside Logger,
# confirmed on 4.7.2). A missing audio device is the machine, not the game:
# noted, not counted.
ERR = re.compile(r"^(SCRIPT |USER |SHADER )?ERROR:|Parse Error|^\s*Failed to load script")
start = next((i for i, l in enumerate(log) if l.startswith("sga_verify: harness started")), len(log))
early, env = [], []
for i, line in enumerate(log):
    if not ERR.search(line) or (i >= start and "Parse Error" not in line):
        continue
    nxt = log[i + 1] if i + 1 < len(log) else ""
    (env if "audio_driver" in nxt else early).append(line.strip())
mark = {"pass": "held  ", "fail": "BROKE ", "not_assessed": "N/A   "}
print(f"scenario: {r['scenario']}  ·  {r['frames_run']} frames  ·  seed {r['seed']}  ·  {r['godot']} ({r['renderer']})")
for c in r["checks"]:
    print(f"  {mark.get(c['status'], c['status'])} {c['label']}: {c['detail']}")
for s in r["shots"]:
    st = {"captured": "shot  ", "pass": "shot ok", "fail": "SHOT ≠"}.get(s["status"], "N/A   ")
    print(f"  {st} {s['name']} @{s['frame']}: {s.get('path') or ''} {s.get('detail', '')}".rstrip())
if r.get("filmstrip"):
    f = r["filmstrip"]
    print(f"  film   {f['path']} (frames {f['frames'][0]}-{f['frames'][-1]}, {f['columns']} per row)")
if r.get("trace"):
    print(f"  trace  {r['trace']}")
print(f"  errors {r['error_count']} · warnings {r['warning_count']}" + (f" · {len(early)} more in the log the harness cannot capture (startup, parse errors)" if early else ""))
for e in [e for e in r["errors"] if e["type"] != "warning"][:8]:
    print(f"    {e['type']}: {e['message']}  ({e['where']})")
for line in early[:5]:
    print(f"    startup: {line}")
if env:
    print("  note: no audio device, so the game ran on Godot's dummy audio driver (sound not observed)")
for n in r["notes"]:
    print(f"  note: {n}")
status = r["status"]
if early and status != "fail" and not r.get("allow_errors"):
    status = "fail"
print(f"STATUS: {status}")
open(sys.argv[1] + ".status", "w").write(status)
PY
  STATUS=$(cat "$out/report.json.status" 2>/dev/null || echo not_assessed)
  rm -f "$out/report.json.status"
}

exit_for() { case "$1" in pass) exit 0 ;; fail) exit 1 ;; *) exit 3 ;; esac; }

abs() { (cd "$(dirname "$1")" && echo "$(pwd)/$(basename "$1")"); }

case "$CMD" in
  install)
    find_project
    mkdir -p "$PROJ/addons/sga_verify"
    cp "$ADDON_SRC"/*.gd "$ADDON_SRC"/README.md "$PROJ/addons/sga_verify/"
    echo "installed: $PROJ/addons/sga_verify/"
    echo "It does nothing unless launched by godot-verify.sh. To keep it out of builds, add"
    echo "addons/sga_verify/* to each export preset's 'Filters to exclude files'."
    ;;
  run)
    [ -n "${POS[1]:-}" ] || na "usage: godot-verify.sh run <scenario.json>"
    [ -f "${POS[1]}" ] || na "scenario not found: ${POS[1]}"
    command -v python3 >/dev/null || na "python3 is needed to read scenario and report JSON"
    find_project; find_godot; need_harness; version_note
    SCN=$(abs "${POS[1]}")
    NAME=$(json_get "$SCN" "d.get('name')"); NAME=${NAME:-$(basename "$SCN" .json)}
    OUT=${OUT:-$PROJ/production/qa/verify/$NAME}; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
    if [ "$MODE" = auto ]; then
      if grep -qE '"(shot|filmstrip)"' "$SCN"; then MODE=render; else MODE=headless; fi
    fi
    echo "mode: $MODE · out: $OUT"
    ensure_import; inject
    run_once "$SCN" "$OUT" "$MODE"
    summarise "$OUT"; exit_for "$STATUS"
    ;;
  smoke)
    command -v python3 >/dev/null || na "python3 is needed to read the report JSON"
    find_project; find_godot; need_harness; version_note
    OUT=${OUT:-$PROJ/production/qa/verify/smoke}; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
    SCN="$OUT/smoke.scenario.json"
    SCENE="${POS[1]:-}"
    if [ "$MODE" = render ]; then SHOT=", \"steps\": [{\"at\": $FRAMES, \"shot\": \"smoke\"}]"; else SHOT=", \"steps\": []"; MODE=headless; fi
    printf '{"name": "smoke", "frames": %s%s%s}\n' "$FRAMES" "${SCENE:+, \"scene\": \"$SCENE\"}" "$SHOT" > "$SCN"
    echo "mode: $MODE · out: $OUT"
    ensure_import; inject
    run_once "$SCN" "$OUT" "$MODE"
    summarise "$OUT"; exit_for "$STATUS"
    ;;
  determinism)
    [ -f "${POS[1]:-}" ] || na "usage: godot-verify.sh determinism <scenario.json>"
    command -v python3 >/dev/null || na "python3 is needed to read scenario and report JSON"
    find_project; find_godot; need_harness; version_note
    SCN=$(abs "${POS[1]}")
    grep -q '"trace"' "$SCN" || na "the scenario has no \"trace\" block, so there is nothing to compare"
    NAME=$(json_get "$SCN" "d.get('name')"); NAME=${NAME:-$(basename "$SCN" .json)}
    OUT=${OUT:-$PROJ/production/qa/verify/$NAME-determinism}; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
    ensure_import; inject
    for i in 1 2; do
      run_once "$SCN" "$OUT/run$i" headless
      [ -s "$OUT/run$i/trace.jsonl" ] || { summarise "$OUT/run$i"; na "run $i wrote no trace"; }
    done
    if cmp -s "$OUT/run1/trace.jsonl" "$OUT/run2/trace.jsonl"; then
      echo "same: $(wc -l < "$OUT/run1/trace.jsonl" | tr -d ' ') trace rows identical across two runs (seed $(json_get "$SCN" "d.get('seed', 0)"))"
      exit 0
    fi
    LINE=$(cmp "$OUT/run1/trace.jsonl" "$OUT/run2/trace.jsonl" | grep -o 'line [0-9]*' | grep -o '[0-9]*')
    echo "DIFFERENT: the runs diverge at trace row $LINE"
    echo "  run1: $(sed -n "${LINE}p" "$OUT/run1/trace.jsonl")"
    echo "  run2: $(sed -n "${LINE}p" "$OUT/run2/trace.jsonl")"
    echo "  usual causes: an unseeded RandomNumberGenerator, Time/OS clock reads, threads, or dictionary order"
    exit 1
    ;;
  selftest)
    command -v python3 >/dev/null || na "python3 is needed to read scenario and report JSON"
    find_godot
    T=$(mktemp -d "${TMPDIR:-/tmp}/sga-verify-selftest.XXXXXX")
    cp -R "$FIXTURE/." "$T/"
    mkdir -p "$T/addons/sga_verify"; cp "$ADDON_SRC"/*.gd "$T/addons/sga_verify/"
    PROJ="$T"; version_note; ensure_import
    fails=0
    while read -r name want; do
      out="$T/out/$name"
      bash "$0" run "$T/tests/scenarios/$name.json" --project "$T" --out "$out" --timeout "$TIMEOUT" > "$T/$name.txt" 2>&1
      got=$(grep -o '^STATUS: .*' "$T/$name.txt" | cut -d' ' -f2); got=${got:-not_assessed}
      if [ "$got" = "$want" ]; then echo "  ok   $name: $got (expected)"
      else echo "  FAIL $name: got $got, expected $want"; sed 's/^/       /' "$T/$name.txt" | tail -n 25; fails=$((fails + 1)); fi
    done < "$T/tests/expected.txt"
    if bash "$0" determinism "$T/tests/scenarios/jump.json" --project "$T" --out "$T/out/det" > "$T/det.txt" 2>&1; then
      echo "  ok   determinism: $(grep '^same' "$T/det.txt")"
    else echo "  FAIL determinism:"; sed 's/^/       /' "$T/det.txt"; fails=$((fails + 1)); fi
    echo "fixture copy and outputs: $T"
    [ "$fails" -eq 0 ] && { echo "SELFTEST: all as expected"; exit 0; }
    echo "SELFTEST: $fails unexpected"; exit 1
    ;;
  *) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
