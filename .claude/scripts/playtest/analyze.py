"""Load telemetry sessions and turn them into findings.

A session is one JSONL file written by sga_telemetry (one row per event:
t, f, ev, sid, scene, run, p). Sessions with a `bot` in session_start are
simulation runs and are analysed apart from people's sessions: a bot's deaths
say nothing about how people feel, and people's frame times say nothing about
a headless run.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PASS, FAIL, NA = "pass", "fail", "not_assessed"

DEFAULT_CONFIG = {
    "funnel": [],                 # e.g. ["session_start", "level_start", "level_end level=1", "level_end level=3"]
    "level_prop": "level",
    "heatmap_events": ["death"],
    "backgrounds": {},            # scene path -> screenshot png, drawn under heatmaps
    "thresholds": {
        "crash_rate": 0.02,
        "error_session_share": 0.05,
        "frame_p95_ms": 33.4,
        "funnel_step_dropoff": 0.5,
        "level_completion": 0.5,
        "feedback_rating": 3.0,
        "sim_stall_rate": 0.05,
    },
}


@dataclass
class Session:
    sid: str
    path: Path
    rows: list = field(default_factory=list)
    start: dict = field(default_factory=dict)
    ended: bool = False
    killed: bool = False

    @property
    def bot(self) -> str:
        return (self.start.get("p") or {}).get("bot", "") or ""

    @property
    def is_sim(self) -> bool:
        return bool(self.bot)

    @property
    def outcome(self) -> str | None:
        ends = [r for r in self.rows if r.get("ev") == "run_end"]
        return (ends[-1].get("p") or {}).get("outcome") if ends else None

    def seconds(self) -> float:
        if self.is_sim:                     # game time: fixed 60 fps
            return max((r.get("f", 0) for r in self.rows), default=0) / 60.0 - self.rows[0].get("f", 0) / 60.0
        for r in reversed(self.rows):
            if r.get("ev") == "session_end":
                return float((r.get("p") or {}).get("seconds", r.get("t", 0) / 1000))
        return self.rows[-1].get("t", 0) / 1000.0 if self.rows else 0.0

    def events(self, name: str) -> list:
        return [r for r in self.rows if r.get("ev") == name]


def load(dirs: list[Path]) -> tuple[list[Session], list[str]]:
    """All sessions under the given folders; problems come back as notes, not exceptions."""
    by_sid: dict[str, Session] = {}
    notes = []
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.rglob("*.jsonl")):
            rows, bad = [], 0
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    if isinstance(r, dict) and "ev" in r:
                        rows.append(r)
                    else:
                        bad += 1
                except json.JSONDecodeError:
                    bad += 1               # a crash can cut the last line short
            if bad:
                notes.append(f"{f.name}: {bad} unreadable line(s) skipped")
            if not rows:
                continue
            sid = rows[0].get("sid") or f.stem
            s = by_sid.get(sid)
            if s is None or len(rows) > len(s.rows):      # the collector and the local file may both have it
                s = Session(sid, f, rows)
                by_sid[sid] = s
            s.start = next((r for r in rows if r.get("ev") == "session_start"), rows[0])
            s.ended = any(r.get("ev") == "session_end" for r in rows)
            s.killed = (f.parent / "killed").exists()
    return list(by_sid.values()), notes


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * q)))]


def _match(row: dict, step: str) -> bool:
    name, *conds = step.split()
    if row.get("ev") != name:
        return False
    p = row.get("p") or {}
    for c in conds:
        k, _, v = c.partition("=")
        if str(p.get(k)) != v:
            return False
    return True


def funnel(sessions: list[Session], steps: list[str]) -> list[dict]:
    out = []
    reached = sessions
    for i, step in enumerate(steps):
        nxt = []
        for s in reached:
            # the step must come after the previous step's first occurrence
            prev_idx = s._funnel_idx if i else -1
            hit = next((j for j, r in enumerate(s.rows) if j > prev_idx and _match(r, step)), None)
            if hit is not None:
                s._funnel_idx = hit
                nxt.append(s)
        before = len(reached) if i else len(sessions)
        out.append({"step": step, "sessions": len(nxt),
                    "share_of_start": round(len(nxt) / len(sessions), 4) if sessions else 0.0,
                    "dropoff": round(1 - len(nxt) / before, 4) if before else 0.0})
        reached = nxt
    return out


def levels(sessions: list[Session], prop: str) -> list[dict]:
    stats = defaultdict(lambda: {"starts": 0, "completions": 0, "times": [], "deaths": 0, "sessions": set()})
    for s in sessions:
        current = None
        started_at = {}
        for r in s.rows:
            p = r.get("p") or {}
            if r.get("ev") == "level_start" and prop in p:
                current = str(p[prop])
                st = stats[current]
                st["starts"] += 1
                st["sessions"].add(s.sid)
                started_at[current] = r.get("f", 0) / 60.0 if s.is_sim else r.get("t", 0) / 1000.0
            elif r.get("ev") == "level_end" and prop in p:
                lv = str(p[prop])
                stats[lv]["completions"] += 1
                if lv in started_at:
                    now = r.get("f", 0) / 60.0 if s.is_sim else r.get("t", 0) / 1000.0
                    stats[lv]["times"].append(now - started_at.pop(lv))
            elif r.get("ev") == "death":
                lv = str(p.get(prop, current)) if (p.get(prop) is not None or current) else None
                if lv:
                    stats[lv]["deaths"] += 1
    out = []
    for lv, st in sorted(stats.items(), key=lambda kv: (len(kv[0]), kv[0])):
        out.append({"level": lv, "starts": st["starts"], "completions": st["completions"],
                    "completion_rate": round(st["completions"] / st["starts"], 4) if st["starts"] else None,
                    "median_seconds": round(statistics.median(st["times"]), 1) if st["times"] else None,
                    "deaths": st["deaths"], "deaths_per_start": round(st["deaths"] / st["starts"], 2) if st["starts"] else None})
    return out


def errors(sessions: list[Session]) -> list[dict]:
    groups: dict[tuple, dict] = {}
    for s in sessions:
        for r in s.events("error"):
            p = r.get("p") or {}
            key = (p.get("message", "?"), p.get("where", "?"))
            g = groups.setdefault(key, {"message": key[0], "where": key[1], "type": p.get("type", "error"),
                                        "events": 0, "sessions": set(), "scenes": Counter()})
            g["events"] += 1
            g["sessions"].add(s.sid)
            g["scenes"][r.get("scene", "")] += 1
    out = [{**{k: v for k, v in g.items() if k not in ("sessions", "scenes")}, "sessions": len(g["sessions"]),
            "scene": g["scenes"].most_common(1)[0][0]} for g in groups.values() if g["type"] != "warning"]
    return sorted(out, key=lambda g: (-g["sessions"], -g["events"]))


def perf(sessions: list[Session]) -> list[dict]:
    by_scene = defaultdict(lambda: {"p95": [], "avg": [], "max": [], "mem": []})
    for s in sessions:
        for r in s.events("perf"):
            p = r.get("p") or {}
            b = by_scene[r.get("scene", "")]
            b["p95"].append(float(p.get("ft_p95", 0)))
            b["avg"].append(float(p.get("ft_avg", 0)))
            b["max"].append(float(p.get("ft_max", 0)))
            b["mem"].append(float(p.get("mem_mb", 0)))
    return [{"scene": sc or "(none)", "samples": len(b["p95"]), "frame_ms_avg": round(statistics.median(b["avg"]), 2),
             "frame_ms_p95": round(_pct(b["p95"], 0.95), 2), "frame_ms_worst": round(max(b["max"]), 2),
             "memory_mb_max": round(max(b["mem"]), 1)} for sc, b in sorted(by_scene.items())]


def feedback(sessions: list[Session]) -> list[dict]:
    out = []
    for s in sessions:
        for r in s.events("feedback"):
            p = r.get("p") or {}
            shot = p.get("screenshot") or ""
            out.append({"sid": s.sid, "rating": p.get("rating"), "text": p.get("text", ""),
                        "scene": p.get("scene") or r.get("scene", ""), "recent": p.get("recent", []),
                        "screenshot": str(s.path.parent / shot) if shot else ""})
    return out


def positions(sessions: list[Session], names: list[str]) -> dict[str, list]:
    pts = defaultdict(list)
    for s in sessions:
        for r in s.rows:
            if r.get("ev") in names:
                pos = (r.get("p") or {}).get("pos")
                if isinstance(pos, list) and len(pos) >= 2:
                    pts[r.get("scene", "")].append((float(pos[0]), float(pos[1]), r.get("ev")))
    return dict(pts)


def _far(state: dict, viewport: tuple[int, int]) -> bool:
    """A watched position far outside the level: a body that fell out of the world."""
    vw, vh = viewport
    for v in state.values():
        if isinstance(v, list) and len(v) in (2, 3) and all(isinstance(x, (int, float)) for x in v):
            if not (-3 * vw <= v[0] <= 4 * vw and -3 * vh <= v[1] <= 4 * vh):
                return True
    return False


def sim_outcomes(sims: list[Session], viewport: tuple[int, int] = (1152, 648)) -> list[dict]:
    by_bot = defaultdict(list)
    for s in sims:
        by_bot[s.bot].append(s)
    out = []
    for bot, runs in sorted(by_bot.items()):
        outcomes = Counter((s.outcome or ("killed" if s.killed else "no run_end")) for s in runs)
        won = [s.seconds() for s in runs if s.outcome == "won"]
        stalls = []
        for s in runs:
            if s.outcome in ("stalled", "timeout"):
                st = ((s.events("run_end")[-1].get("p") or {}).get("state") or {})
                stalls.append({"sid": s.sid, "run": s.rows[-1].get("run"), "outcome": s.outcome, "state": st,
                               "scene": s.rows[-1].get("scene", ""),
                               "note": "far outside the level (fell out of the world?)" if _far(st, viewport) else ""})
        out.append({"bot": bot, "runs": len(runs), "outcomes": dict(outcomes),
                    "win_rate": round(outcomes.get("won", 0) / len(runs), 4),
                    "stall_rate": round((outcomes.get("stalled", 0)) / len(runs), 4),
                    "left_level": sum(1 for x in stalls if x["note"]),
                    "median_seconds_to_win": round(statistics.median(won), 2) if won else None,
                    "error_runs": sum(1 for s in runs if s.events("error")),
                    "unfinished": sum(1 for s in runs if not s.ended),
                    "stalls": stalls[:50]})
    return out


def analyse(sessions: list[Session], config: dict) -> dict:
    cfg = {**DEFAULT_CONFIG, **config, "thresholds": {**DEFAULT_CONFIG["thresholds"], **config.get("thresholds", {})}}
    people = [s for s in sessions if not s.is_sim]
    sims = [s for s in sessions if s.is_sim]
    crashed = [s for s in people if not s.ended]
    durations = [s.seconds() for s in people]
    result = {
        "overview": {
            "player_sessions": len(people),
            "installs": len({(s.start.get("p") or {}).get("iid") for s in people}),
            "play_hours": round(sum(durations) / 3600, 2),
            "median_session_minutes": round(statistics.median(durations) / 60, 1) if durations else None,
            "versions": dict(Counter((s.start.get("p") or {}).get("version", "") or "?" for s in people)),
            "platforms": dict(Counter((s.start.get("p") or {}).get("platform", "?") for s in people)),
            "crashed_sessions": len(crashed),
            "crash_rate": round(len(crashed) / len(people), 4) if people else None,
            "sim_runs": len(sims),
        },
        "funnel": funnel(people, cfg["funnel"]) if cfg["funnel"] and people else [],
        "levels": levels(people, cfg["level_prop"]),
        "errors": errors(people),
        "perf": perf(people),
        "feedback": feedback(people),
        "positions": positions(people, cfg["heatmap_events"]),
        "sim": sim_outcomes(sims, _viewport(sessions)),
        "sim_levels": levels(sims, cfg["level_prop"]),
        "sim_errors": errors(sims),
        "sim_positions": positions(sims, cfg["heatmap_events"]),
        "viewport": _viewport(sessions),
    }
    result["checks"] = checks(result, cfg["thresholds"], people)
    return result


def _viewport(sessions: list[Session]) -> tuple[int, int]:
    for s in sessions:
        v = (s.start.get("p") or {}).get("viewport")
        if isinstance(v, list) and len(v) == 2 and v[0] and v[1]:
            return int(v[0]), int(v[1])
    return 1152, 648


def checks(r: dict, t: dict, people: list[Session]) -> list[dict]:
    rows = []

    def add(name, status, detail):
        rows.append({"check": name, "status": status, "detail": detail})

    ov = r["overview"]
    if not people:
        for name in ("crash rate", "errors", "frame time", "funnel", "level completion", "feedback"):
            add(name, NA, "no player sessions yet")
    else:
        cr = ov["crash_rate"]
        add("crash rate", PASS if cr <= t["crash_rate"] else FAIL,
            f"{ov['crashed_sessions']} of {ov['player_sessions']} sessions ended without a clean exit ({cr:.0%}, max {t['crash_rate']:.0%})")
        err_sessions = len({s.sid for s in people if s.events("error")})
        share = err_sessions / len(people)
        add("errors", PASS if share <= t["error_session_share"] else FAIL,
            f"{err_sessions} sessions logged errors ({share:.0%}, max {t['error_session_share']:.0%}); {len(r['errors'])} distinct")
        if r["perf"]:
            worst = max(r["perf"], key=lambda p: p["frame_ms_p95"])
            add("frame time", PASS if worst["frame_ms_p95"] <= t["frame_p95_ms"] else FAIL,
                f"worst scene {worst['scene']}: p95 {worst['frame_ms_p95']} ms (max {t['frame_p95_ms']})")
        else:
            add("frame time", NA, "no perf samples (sessions shorter than 5 s?)")
        if r["funnel"]:
            bad = [f for f in r["funnel"][1:] if f["dropoff"] > t["funnel_step_dropoff"]]
            add("funnel", FAIL if bad else PASS,
                "; ".join(f"{f['step']}: {f['dropoff']:.0%} drop" for f in bad) or
                f"no step loses more than {t['funnel_step_dropoff']:.0%}")
        else:
            add("funnel", NA, "no funnel configured (production/playtest/config.json \"funnel\")")
        lv = [l for l in r["levels"] if l["completion_rate"] is not None]
        if lv:
            bad = [l for l in lv if l["completion_rate"] < t["level_completion"]]
            add("level completion", FAIL if bad else PASS,
                "; ".join(f"level {l['level']}: {l['completion_rate']:.0%} of {l['starts']} starts" for l in bad) or
                f"every level at {t['level_completion']:.0%}+")
        else:
            add("level completion", NA, "no level_start/level_end events")
        ratings = [f["rating"] for f in r["feedback"] if isinstance(f["rating"], (int, float)) and f["rating"] > 0]
        if ratings:
            avg = statistics.mean(ratings)
            add("feedback", PASS if avg >= t["feedback_rating"] else FAIL, f"average {avg:.1f} of 5 from {len(ratings)} ratings")
        else:
            add("feedback", NA, "no rated feedback")
    if r["sim"]:
        for b in r["sim"]:
            ok = b["stall_rate"] <= t["sim_stall_rate"] and b["error_runs"] == 0 and b["unfinished"] == 0
            add(f"bot {b['bot']}", PASS if ok else FAIL,
                f"{b['runs']} runs: {b['outcomes']}; stall rate {b['stall_rate']:.0%} (max {t['sim_stall_rate']:.0%}), "
                f"{b['error_runs']} with errors, {b['unfinished']} unfinished"
                + (f", {b['left_level']} left the level" if b["left_level"] else ""))
    return rows


def overall(checks_: list[dict]) -> str:
    s = [c["status"] for c in checks_]
    return FAIL if FAIL in s else NA if (NA in s or not s) else PASS
