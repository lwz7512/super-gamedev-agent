"""Static integrity checks for the combined studio: free, deterministic, run in CI.

Each check derives its set from the repo (rule 5 of .claude/rules/skill-authoring.md):
a new agent, skill, script or module is covered without editing this file.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

PASS, FAIL, NA = "pass", "fail", "not_assessed"
# SGA_EVAL_ROOT points the checks at another checkout (the tests break a copy).
ROOT = Path(os.environ.get("SGA_EVAL_ROOT") or Path(__file__).resolve().parents[3]).resolve()
LIB = ROOT / ".claude/library"


def _row(name, status, detail, items=None):
    return {"check": name, "status": status, "detail": detail, "items": items or []}


def studio_skills() -> set[str]:
    return {p.parent.name for p in (ROOT / ".claude/skills").glob("*/SKILL.md") if not (p.parent / ".library").exists()}


def library_skills() -> set[str]:
    names = {p.parent.name for p in LIB.glob("skills/*/*/SKILL.md")}
    return names | {"router"}


def check_agent_skill_refs():
    """Every skill an agent's Knowledge Library section names exists."""
    known = studio_skills() | library_skills()
    bad = []
    for p in sorted((ROOT / ".claude/agents").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        m = re.search(r"(?ms)^## Knowledge Library\n(.*?)(?=^## |\Z)", text)
        if not m:
            continue
        for line in m.group(1).splitlines():
            if line.startswith("- **"):
                for name in re.findall(r"`([a-z0-9][a-z0-9-]+)`", line):
                    if name not in known:
                        bad.append(f"{p.stem}: {name}")
    return _row("agent skill references", FAIL if bad else PASS,
                f"{len(bad)} unknown skill name(s)" if bad else "every skill named in an agent's Knowledge Library exists", bad)


def check_library_groups():
    """Every library skill can be activated by some library.sh group."""
    r = subprocess.run(["bash", str(ROOT / ".claude/scripts/library.sh"), "groups"], capture_output=True, text=True)
    if r.returncode != 0:
        return _row("library groups", NA, f"library.sh groups failed: {r.stderr.strip()[:200]}")
    covered = set()
    for line in r.stdout.splitlines():
        covered.update(line.split()[1:])
    orphans = sorted(library_skills() - covered)
    return _row("library groups", FAIL if orphans else PASS,
                f"{len(orphans)} library skill(s) no group activates" if orphans else f"all {len(library_skills())} library skills reachable", orphans)


def check_router():
    active = ROOT / ".claude/skills/router/SKILL.md"
    if not active.exists():
        return _row("router", FAIL, "the router is not active (library.sh activate router)")
    text = active.read_text(encoding="utf-8")
    missing = [m for m in ("LIBRARY-ROOT", "vault.sh addenda") if m not in text]
    paths = set(re.findall(r"`(skills/[a-z0-9-]+/[a-z0-9-]*)/?`", text))
    gone = sorted(p for p in paths if not list(LIB.glob(p.rstrip("/") + "*")))
    bad = [f"router note missing: {m}" for m in missing] + [f"table path not in library: {p}" for p in gone]
    return _row("router", FAIL if bad else PASS, "; ".join(bad) if bad else f"patched; {len(paths)} table paths resolve", bad)


def check_skill_lint():
    r = subprocess.run(["bash", str(ROOT / ".claude/scripts/skill-lint.sh"), "all"], capture_output=True, text=True)
    rows = [l.split("\t") for l in r.stdout.splitlines()]
    bad = [f"{x[1]}: {x[2]} {x[3]}" for x in rows if x and x[0] == "check1" and ("frontmatter=ok" not in x[2] or x[3] != "missing=-")]
    unread = [l for l in r.stdout.splitlines() if l.startswith("NOT_READ")]
    checked = next((l for l in r.stdout.splitlines() if l.startswith("checked")), "checked ? of ?")
    if r.returncode != 0 and not rows:
        return _row("studio skill frontmatter", NA, f"skill-lint failed: {r.stderr[:200]}")
    return _row("studio skill frontmatter", FAIL if bad or unread else PASS,
                f"{checked.replace(chr(9), ' ')}" + (f"; {len(bad)} with missing fields" if bad else ""), bad + unread)


def check_scripts_parse():
    bad = []
    shells = list((ROOT / ".claude/scripts").glob("*.sh")) + list((ROOT / ".claude/hooks").glob("*.sh")) + list((ROOT / "bin").glob("*.sh"))
    for s in shells:
        r = subprocess.run(["bash", "-n", str(s)], capture_output=True, text=True)
        if r.returncode != 0:
            bad.append(f"{s.relative_to(ROOT)}: {r.stderr.strip()[:120]}")
    pys = [p for p in (ROOT / ".claude/scripts").rglob("*.py") if "__pycache__" not in p.parts] + list((ROOT / "site").glob("*.py"))
    for p in pys:
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")      # parse only; writes nothing
        except SyntaxError as e:
            bad.append(f"{p.relative_to(ROOT)}:{e.lineno}: {e.msg}")
    return _row("scripts parse", FAIL if bad else PASS, f"{len(shells)} shell + {len(pys)} Python files" + (f", {len(bad)} broken" if bad else ""), bad)


def check_settings():
    bad = []
    try:
        s = json.loads((ROOT / ".claude/settings.json").read_text())
    except json.JSONDecodeError as e:
        return _row("settings and hooks", FAIL, f".claude/settings.json is not valid JSON: {e}")
    for event, groups in s.get("hooks", {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                for path in re.findall(r"\$CLAUDE_PROJECT_DIR/([^\"'\s]+)", h.get("command", "")):
                    if not (ROOT / path).exists():
                        bad.append(f"{event}: {path} missing")
    mcp = json.loads((ROOT / ".mcp.json").read_text()).get("mcpServers", {}) if (ROOT / ".mcp.json").exists() else {}
    for name in s.get("enabledMcpjsonServers", []):
        if name not in mcp:
            bad.append(f"enabledMcpjsonServers names '{name}', which .mcp.json does not define")
    return _row("settings and hooks", FAIL if bad else PASS, "valid; every hook script exists" if not bad else f"{len(bad)} problem(s)", bad)


def check_doc_links():
    docs = [ROOT / "CLAUDE.md", ROOT / "README.md"] + sorted((ROOT / ".claude/docs").glob("*.md")) + [ROOT / "vault/README.md"]
    bad = []
    for d in docs:
        if not d.exists():
            continue
        text = re.sub(r"(?s)```.*?```", "", d.read_text(encoding="utf-8"))
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            path = target.split("#")[0]
            if path and not (d.parent / path).exists():
                bad.append(f"{d.relative_to(ROOT)} -> {target}")
    return _row("doc links", FAIL if bad else PASS, f"{len(docs)} documents" + (f", {len(bad)} broken link(s)" if bad else ", every relative link resolves"), bad)


def check_claude_md_refs():
    """Every /skill and .claude/... path CLAUDE.md names exists."""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    # Claude Code's own commands are not files in this repo, so they cannot be
    # derived; extend this list when CLAUDE.md starts naming another one.
    builtin = {"clear", "mcp", "help", "compact", "config", "hooks", "init", "memory", "model", "permissions", "agents", "skills"}
    known = studio_skills() | library_skills() | builtin
    bad = [f"/{s}" for s in sorted(set(re.findall(r"`/([a-z][a-z0-9-]+)`", text))) if s not in known]
    bad += [p for p in sorted(set(re.findall(r"`(\.claude/[A-Za-z0-9_./-]+)`", text)))
            if "<" not in p and not (ROOT / p).exists()]
    bad += [p for p in sorted(set(re.findall(r"bash (\.claude/scripts/[a-z-]+\.sh)", text))) if not (ROOT / p).exists()]
    return _row("CLAUDE.md references", FAIL if bad else PASS, "every skill and path it names exists" if not bad else f"{len(bad)} missing", bad)


def check_vault():
    vault = ROOT / "vault"
    if not vault.exists():
        return _row("vault integrity", NA, "no vault/ in this checkout")
    bad = []
    for mj in sorted(vault.glob("modules/*/*/module.json")):
        try:
            m = json.loads(mj.read_text())
        except json.JSONDecodeError as e:
            bad.append(f"{mj.parent.name}: module.json invalid ({e})")
            continue
        for f in m.get("files", []):
            if not (mj.parent / "files" / f).exists():
                bad.append(f"{m.get('name')}: file {f} missing")
        for t in m.get("tests", []):
            if not (mj.parent / t).exists():
                bad.append(f"{m.get('name')}: test {t} missing")
        if m.get("external_refs"):
            bad.append(f"{m.get('name')}: not self-contained ({', '.join(m['external_refs'][:3])})")
        if not (mj.parent / "README.md").exists():
            bad.append(f"{m.get('name')}: no README")
    for lp in sorted(vault.glob("lessons/*.md")):
        head = lp.read_text(encoding="utf-8")[:600]
        for field in ("title:", "kind:", "tags:"):
            if field not in head:
                bad.append(f"lesson {lp.stem}: no {field[:-1]}")
    for ad in sorted(vault.glob("addenda/*.md")):
        if ad.stem not in library_skills():
            bad.append(f"addenda for unknown library skill {ad.stem}")
    n = (len(list(vault.glob("modules/*/*/module.json"))), len(list(vault.glob("lessons/*.md"))), len(list(vault.glob("addenda/*.md"))))
    return _row("vault integrity", FAIL if bad else PASS, f"{n[0]} module(s), {n[1]} lesson(s), {n[2]} addenda" + (f"; {len(bad)} problem(s)" if bad else ""), bad)


def check_library_intact():
    v = LIB / "scripts/validate-skills.py"
    if not v.exists():
        return _row("library validator", NA, "no validate-skills.py in the library")
    r = subprocess.run(["python3", "-I", str(v)], cwd=LIB, capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]
    return _row("library validator", PASS if r.returncode == 0 else FAIL, tail[0][:200])


def check_workflows():
    bad = []
    wfs = sorted((ROOT / ".github/workflows").glob("*.yml"))
    for wf in wfs:
        for path in set(re.findall(r"(\.claude/scripts/[A-Za-z0-9_./-]+\.(?:sh|py))", wf.read_text())):
            if not (ROOT / path).exists():
                bad.append(f"{wf.name}: {path}")
        for path in set(re.findall(r"(?:python3? )(site/[a-z_]+\.py)", wf.read_text())):
            if not (ROOT / path).exists():
                bad.append(f"{wf.name}: {path}")
    return _row("CI workflows", FAIL if bad else PASS, f"{len(wfs)} workflow(s)" + (f", {len(bad)} missing script(s)" if bad else ", every script they run exists"), bad)


CHECKS = [check_agent_skill_refs, check_library_groups, check_router, check_skill_lint, check_scripts_parse,
          check_settings, check_doc_links, check_claude_md_refs, check_vault, check_library_intact, check_workflows]


def run() -> list[dict]:
    rows = []
    for c in CHECKS:
        try:
            rows.append(c())
        except Exception as e:                      # a crashed check is a check that did not run
            rows.append(_row(c.__name__.replace("check_", "").replace("_", " "), NA, f"check crashed: {e!r}"))
    return rows
