"""The playtest report: Markdown with charts, written beside them."""

from __future__ import annotations

import re
from pathlib import Path

from analyze import FAIL, NA, PASS, overall

MARK = {PASS: "PASS", FAIL: "FAIL", NA: "NOT ASSESSED"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "scene"


def _table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    if not rows:
        return "_none_\n"
    head = "| " + " | ".join(c[1] for c in cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = ""
    for r in rows:
        cells = []
        for key, _ in cols:
            v = r.get(key)
            if v is None:
                cells.append("–")
            elif key.endswith(("rate", "share", "of_start", "dropoff")) and isinstance(v, float):
                cells.append(f"{v:.0%}")
            else:
                cells.append(str(v).replace("|", "\\|"))
        body += "| " + " | ".join(cells) + " |\n"
    return head + body


def _charts(result: dict, out_dir: Path, config: dict, sims_only: bool) -> dict:
    import charts
    t = config["thresholds"]
    images = {}
    if result["funnel"] and not sims_only:
        images["funnel"] = charts.bars(out_dir / "funnel.png", "Funnel: share of sessions reaching each step",
                                       [(f["step"], f["share_of_start"], "bad" if f["dropoff"] > t["funnel_step_dropoff"] else "")
                                        for f in result["funnel"]], "%")
    lv = [l for l in result["levels"] if l["completion_rate"] is not None]
    if lv and not sims_only:
        images["levels"] = charts.bars(out_dir / "levels.png", "Level completion (players)",
                                       [(f"level {l['level']} ({l['starts']} starts)", l["completion_rate"],
                                         "bad" if l["completion_rate"] < t["level_completion"] else "ok") for l in lv], "%")
    if result["sim"]:
        items = []
        for b in result["sim"]:
            for o, n in sorted(b["outcomes"].items()):
                tone = "ok" if o == "won" else "bad" if o in ("stalled", "killed", "no run_end") else ""
                items.append((f"{b['bot'].split('/')[-1]}: {o}", n, tone))
        images["outcomes"] = charts.bars(out_dir / "sim-outcomes.png", "Simulation outcomes (runs)", items)
    for key, label in (("positions", "players"), ("sim_positions", "bots")):
        if key == "positions" and sims_only:
            continue
        for scene, pts in result[key].items():
            name = f"heatmap-{label}-{_slug(scene.split('/')[-1].replace('.tscn', ''))}.png"
            images[f"{key}:{scene}"] = charts.heatmap(
                out_dir / name, f"{', '.join(config['heatmap_events'])} · {label} · {scene}",
                pts, tuple(result["viewport"]), config.get("backgrounds", {}).get(scene))
    return images


def _player_sections(result: dict, images: dict) -> list[str]:
    md = []
    if result["funnel"]:
        md += ["## Funnel\n", f"![funnel]({images['funnel'].name})\n" if "funnel" in images else "",
               _table(result["funnel"], [("step", "Step"), ("sessions", "Sessions"), ("share_of_start", "Of start"),
                                         ("dropoff", "Lost at this step")])]
    md += ["## Levels (players)\n", f"![levels]({images['levels'].name})\n" if "levels" in images else "",
           _table(result["levels"], [("level", "Level"), ("starts", "Starts"), ("completions", "Completions"),
                                     ("completion_rate", "Completion rate"), ("median_seconds", "Median s"),
                                     ("deaths", "Deaths"), ("deaths_per_start", "Deaths/start")])]
    heat = [v for k, v in images.items() if k.startswith("positions:")]
    if heat:
        md += ["### Where it happens\n"] + [f"![{p.stem}]({p.name})\n" for p in heat]
    md += ["## Errors (players)\n", _table(result["errors"][:30], [("sessions", "Sessions"), ("events", "Events"), ("type", "Type"),
                                                                    ("message", "Message"), ("where", "Where"), ("scene", "Scene")])]
    md += ["## Frame time (players)\n", _table(result["perf"], [("scene", "Scene"), ("samples", "Samples"), ("frame_ms_avg", "Median ms"),
                                                               ("frame_ms_p95", "p95 ms"), ("frame_ms_worst", "Worst ms"),
                                                               ("memory_mb_max", "Max MB")])]
    md += ["## Player feedback\n"]
    if not result["feedback"]:
        return md + ["_none_\n"]
    for f in result["feedback"]:
        stars = int(f["rating"] or 0)
        md.append(f"- {'★' * stars}{'☆' * (5 - stars)} *{f['scene'] or '?'}*: {f['text'] or '(no note)'}"
                  + (f" · [screenshot]({f['screenshot']})" if f["screenshot"] else "")
                  + (f"\n  - just before: {', '.join(f['recent'][-6:])}" if f["recent"] else ""))
    return md + [""]


def _sim_sections(result: dict, images: dict) -> list[str]:
    md = ["## Simulation\n", f"![outcomes]({images['outcomes'].name})\n" if "outcomes" in images else "",
          _table([{**b, "outcomes": ", ".join(f"{k} {v}" for k, v in b["outcomes"].items())} for b in result["sim"]],
                 [("bot", "Bot"), ("runs", "Runs"), ("outcomes", "Outcomes"), ("win_rate", "Win rate"), ("stall_rate", "Stall rate"),
                  ("left_level", "Left the level"), ("median_seconds_to_win", "Median s to win"), ("error_runs", "Runs with errors"),
                  ("unfinished", "Unfinished")])]
    stalls = [s for b in result["sim"] for s in b["stalls"]]
    if stalls:
        md += ["### Where bots got stuck\n",
               _table(stalls[:20], [("run", "Run"), ("outcome", "Outcome"), ("scene", "Scene"), ("state", "State"), ("note", "Note")])]
    md += [f"![{p.stem}]({p.name})\n" for k, p in images.items() if k.startswith("sim_positions:")]
    if result["sim_levels"]:
        md += ["### Levels (bots)\n", _table(result["sim_levels"], [("level", "Level"), ("starts", "Starts"), ("completions", "Completions"),
                                                                     ("completion_rate", "Completion rate"), ("median_seconds", "Median s"),
                                                                     ("deaths", "Deaths")])]
    if result["sim_errors"]:
        md += ["### Errors in simulation\n", _table(result["sim_errors"][:20], [("sessions", "Runs"), ("message", "Message"), ("where", "Where")])]
    return md


def write(result: dict, out_dir: Path, title: str, config: dict, charts_ok: bool) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ov = result["overview"]
    # A bots-only run says nothing about people: leave out the player sections
    # and the player checks rather than filling the page with "not assessed".
    sims_only = ov["player_sessions"] == 0 and bool(result["sim"])
    images = _charts(result, out_dir, config, sims_only) if charts_ok else {}
    shown = [c for c in result["checks"] if c["check"].startswith("bot ")] if sims_only else result["checks"]
    md = [f"# {title}\n",
          f"**Verdict: {MARK[overall(shown)]}** (thresholds from `production/playtest/config.json`)\n",
          "## Checks\n",
          _table([{**c, "status": MARK[c["status"]]} for c in shown], [("check", "Check"), ("status", "Result"), ("detail", "Detail")])]
    if not sims_only:
        md += ["## Overview\n",
               f"- Player sessions: **{ov['player_sessions']}** from {ov['installs']} installs, {ov['play_hours']} hours, "
               f"median session {ov['median_session_minutes']} min",
               f"- Crashed sessions (no clean exit): {ov['crashed_sessions']}"
               + (f" ({ov['crash_rate']:.0%})" if ov["crash_rate"] is not None else ""),
               f"- Versions: {ov['versions'] or '–'} · platforms: {ov['platforms'] or '–'}",
               f"- Simulation runs: {ov['sim_runs']}\n"]
        md += _player_sections(result, images)
    if result["sim"]:
        md += _sim_sections(result, images)
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path
