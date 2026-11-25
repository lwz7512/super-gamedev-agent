"""assets/provenance.yaml: one entry per shipped file, in the studio's format.

The file is shared with the studio's one-shot pipeline and with people, so it
is edited block by block: entries this tool did not write, comments and the
header are left exactly as they are.

Licence facts, read from the official pages on 2026-11-25:
- OpenArt (https://openart.ai/terms/, https://openart.ai/suite/pricing):
  commercial use needs the Plus plan or higher; Starter and free are
  non-commercial. OpenArt claims no copyright in output (ToS 4.1).
- ElevenLabs (https://elevenlabs.io/terms-of-use 1(c),
  https://elevenlabs.io/creative-terms Exhibit 4 s2): free users are
  non-commercial; any paid plan (Starter and up) may use output commercially.
  Sound effects may ship inside a game but never on their own (no SFX packs,
  no isolated sample files for sale).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from common import FAIL, NA, PASS, Project, today

HEADER = """# Where each file in assets/ came from, one entry per file, added with it.
# Fields: path, origin (ai | bought | cc0 | you | outsourced | template | plugin | licensed | code | unknown),
# tool, model, source {vendor, product, url}, licence {id, url}, date, ships, placeholder,
# plan (the generator plan the file was made on), restrictions, record (the raw generation record).
# asset-forge (.claude/scripts/asset-forge.sh) writes and checks the entries it makes.
"""

TERMS = {
    "openart": {
        "vendor": "OpenArt", "licence": {"id": "LicenseRef-OpenArt-Terms", "url": "https://openart.ai/terms/"},
        "commercial_plans": {"plus", "pro", "wonder", "team", "enterprise"},
        "non_commercial_plans": {"free", "trial", "starter"},
        "rule": "commercial use needs OpenArt Plus or higher",
    },
    "elevenlabs": {
        "vendor": "ElevenLabs", "licence": {"id": "LicenseRef-ElevenLabs-Terms", "url": "https://elevenlabs.io/terms-of-use"},
        "commercial_plans": {"starter", "creator", "pro", "scale", "business", "enterprise"},
        "non_commercial_plans": {"free"},
        "rule": "commercial use needs a paid ElevenLabs plan (Starter or higher)",
        "restrictions": "ship only inside the game; no standalone SFX/sample redistribution (ElevenLabs Creative Terms, Exhibit 4 s2)",
    },
}

SHIPPABLE = {".png", ".webp", ".jpg", ".jpeg", ".svg", ".gif", ".wav", ".ogg", ".mp3",
             ".ttf", ".otf", ".woff2", ".glb", ".gltf", ".tres", ".json"}
SKIP = {"style.json", "manifest.json", "provenance.yaml"}
COMMERCIAL_GOALS = {"sell", "early_access", "publisher", "mobile"}


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v)
    if s == "" or re.search(r"[:#{}\[\],&*!|>'\"%@`]|^\s|\s$", s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def render(e: dict) -> str:
    lines = [f"- path: {_scalar(e['path'])}"]
    for k in ("origin", "tool", "model", "source", "licence", "date", "ships", "placeholder",
              "plan", "restrictions", "record"):
        v = e.get(k)
        if v in (None, "", {}) or (k == "placeholder" and not v):
            continue
        if isinstance(v, dict):
            inner = ", ".join(f"{a}: {_scalar(b)}" for a, b in v.items() if b not in (None, ""))
            lines.append(f"  {k}: {{{inner}}}")
        else:
            lines.append(f"  {k}: {_scalar(v)}")
    lines.append("  # asset-forge")
    return "\n".join(lines) + "\n"


def split_blocks(text: str) -> tuple[str, list[str]]:
    """Header (comments before the first entry) and one text block per entry."""
    parts = re.split(r"(?m)^(?=- path:)", text)
    head = parts[0] if parts and not parts[0].startswith("- path:") else ""
    return head, [p for p in parts if p.startswith("- path:")]


def parse_block(block: str) -> dict:
    out: dict = {}
    for line in block.splitlines():
        m = re.match(r"^(?:- |  )([a-z_]+):\s*(.*?)\s*(?:#.*)?$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        if v.startswith("{") and v.endswith("}"):
            d = {}
            for part in re.findall(r'(\w+):\s*("(?:[^"\\]|\\.)*"|[^,}]+)', v[1:-1]):
                d[part[0]] = part[1].strip().strip('"')
            out[k] = d
        else:
            v = v.strip('"')
            out[k] = {"true": True, "false": False}.get(v, v)
    out["_ours"] = "# asset-forge" in block
    return out


def read(proj: Project) -> tuple[str, list[str]]:
    if not proj.ledger_path.exists():
        return HEADER, []
    return split_blocks(proj.ledger_path.read_text(encoding="utf-8"))


def upsert(proj: Project, entry: dict) -> str:
    """Add or replace the entry for entry['path']. Returns 'added' / 'updated' / 'kept'."""
    head, blocks = read(proj)
    found = False
    for i, b in enumerate(blocks):
        cur = parse_block(b)
        if cur.get("path") == entry["path"]:
            if not cur["_ours"]:
                return "kept"            # a person or the one-shot pipeline wrote it
            blocks[i] = render(entry)
            found = True
            break
    if not found:
        blocks.append(render(entry))
    proj.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(b if b.endswith("\n") else b + "\n" for b in blocks)
    proj.ledger_path.write_text((head or HEADER) + body, encoding="utf-8")
    return "updated" if found else "added"


def entry_for(proj: Project, a: dict, record: dict) -> dict:
    tool = record.get("provider", "")
    style = proj.style
    e = {"path": a["path"], "date": record.get("date", today()), "ships": True,
         "record": record.get("record", "")}
    if tool in TERMS:
        t = TERMS[tool]
        e.update({"origin": "ai", "tool": f"{tool} ({record.get('via', 'api')})", "model": record.get("model", ""),
                  "source": {"vendor": t["vendor"]}, "licence": t["licence"],
                  "plan": style["providers"].get(tool, {}).get("plan", ""),
                  "restrictions": t.get("restrictions", "")})
    elif tool in ("synth", "placeholder"):
        e.update({"origin": "code", "tool": f"asset-forge {tool}", "placeholder": tool == "placeholder"})
    else:
        e.update({"origin": record.get("origin", "unknown"), "tool": record.get("tool", tool),
                  "model": record.get("model", ""), "source": record.get("source", {}),
                  "licence": record.get("licence", {})})
    return e


def project_goal(proj: Project) -> str:
    helper = proj.root / ".claude/hooks/yaml-helper.sh"
    if helper.exists():
        r = subprocess.run(["bash", str(helper), "get_effective_yaml_key", "project.goal"],
                           cwd=proj.root, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip().strip('"')
    return ""


def check(proj: Project, release: bool) -> tuple[str, list[dict], dict]:
    """Every shipped file has an entry; plan terms fit a commercial goal; placeholders flagged."""
    _, blocks = read(proj)
    entries = {e["path"]: e for e in (parse_block(b) for b in blocks)}
    goal = project_goal(proj)
    commercial = goal in COMMERCIAL_GOALS or goal == ""
    rows, ai = [], 0
    files = sorted(p for p in proj.assets.rglob("*")
                   if p.is_file() and p.suffix.lower() in SHIPPABLE and p.name not in SKIP
                   and not any(part.startswith("_") or part.startswith(".") for part in p.relative_to(proj.assets).parts))
    for f in files:
        rel = proj.rel(f)
        e = entries.get(rel)
        if not e:
            rows.append({"path": rel, "status": FAIL, "detail": "no provenance entry"})
            continue
        if str(e.get("ships", "true")).lower() == "false":
            rows.append({"path": rel, "status": PASS, "detail": "does not ship"})
            continue
        status, notes = PASS, []
        if e.get("origin") == "ai":
            ai += 1
        if e.get("origin") in ("unknown", "", None):
            status, notes = FAIL, ["origin unknown: cannot ship"]
        if e.get("placeholder") is True:
            notes.append("placeholder")
            if release:
                status = FAIL
        vendor = next((k for k in TERMS if str(e.get("tool", "")).lower().startswith(k)), None)
        if vendor:
            t, plan = TERMS[vendor], str(e.get("plan", "")).lower()
            if plan in t["commercial_plans"]:
                notes.append(f"{vendor} {plan}: commercial use allowed")
            elif plan in t["non_commercial_plans"]:
                notes.append(f"{vendor} {plan}: non-commercial only; {t['rule']}")
                if commercial:
                    status = FAIL
            else:
                notes.append(f"{vendor} plan not recorded; {t['rule']} (set providers.{vendor}.plan in style.json)")
                if commercial and status == PASS:
                    status = NA
        if e.get("origin") in ("cc0", "licensed", "bought") and not e.get("licence"):
            status, notes = FAIL, notes + ["licence missing"]
        rows.append({"path": rel, "status": status, "detail": "; ".join(notes) or "ok"})
    orphans = [p for p in entries if not (proj.root / p).exists()]
    summary = {"goal": goal or "(unset: checked as commercial)", "files": len(files), "ai_generated": ai,
               "orphans": orphans}
    statuses = [r["status"] for r in rows]
    overall = FAIL if FAIL in statuses else NA if NA in statuses else PASS
    if not files:
        overall = NA
    return overall, rows, summary
