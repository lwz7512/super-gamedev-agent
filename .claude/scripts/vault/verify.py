"""verify: a module is only reusable if it works in a project that is not the
one it came from. Install it into an empty Godot project, import, count errors,
then play each of its test scenarios through godot-verify.sh (run-and-verify)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from store import STUDIO, TOKEN, Vault

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "playtest"))
from godot import PlaytestError, find_godot  # noqa: E402

PASS, FAIL, NA = "pass", "fail", "not_assessed"


def verify(vault: Vault, name: str, keep: bool = False) -> tuple[str, list[dict]]:
    import modules
    m = vault.module(name)
    rows = []
    try:
        g = find_godot(STUDIO)
    except PlaytestError as e:
        return NA, [{"check": "godot", "status": NA, "detail": str(e)}]
    root = Path(tempfile.mkdtemp(prefix=f"vault-verify-{name}-"))
    try:
        feature = m.get("engine_min") or "4.5"
        (root / "project.godot").write_text(
            f'config_version=5\n\n[application]\n\nconfig/name="verify-{name}"\nconfig/features=PackedStringArray("{feature}")\n')
        for r in m.get("requires", []):
            modules.add(vault, root, r)
        for line in modules.add(vault, root, name):
            rows.append({"check": "install", "status": PASS, "detail": line})
        if m.get("external_refs"):
            rows.append({"check": "self-contained", "status": FAIL,
                         "detail": "refers to files outside the module: " + ", ".join(m["external_refs"][:6])})
        r = subprocess.run([g, "--headless", "--path", str(root), "--import"], capture_output=True, text=True, timeout=600)
        log = r.stdout + r.stderr
        errors = [l for l in log.splitlines() if l.startswith(("ERROR:", "SCRIPT ERROR:")) or "Parse Error" in l]
        rows.append({"check": "imports cleanly", "status": FAIL if errors else PASS,
                     "detail": "; ".join(errors[:4]) if errors else "no errors importing into an empty project"})
        tests = m.get("tests", [])
        if not tests:
            rows.append({"check": "tests", "status": NA, "detail": "the module has no test scenarios (add tests/<name>.json)"})
        else:
            gv = STUDIO / ".claude/scripts/godot-verify.sh"
            subprocess.run(["bash", str(gv), "install", "--project", str(root)], capture_output=True, check=True)
            for t in tests:
                scn = json.loads((Path(m["_dir"]) / t).read_text().replace(TOKEN, m["install_dir"].rstrip("/")))
                sp = root / "tests/scenarios" / Path(t).name
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(json.dumps(scn))
                res = subprocess.run(["bash", str(gv), "run", str(sp), "--project", str(root), "--out", str(root / "out" / sp.stem)],
                                     capture_output=True, text=True, timeout=600)
                status = {0: PASS, 1: FAIL}.get(res.returncode, NA)
                lines = [l.strip() for l in res.stdout.splitlines() if l.strip().startswith(("held", "BROKE", "N/A", "error", "script:", "NOT ASSESSED"))]
                rows.append({"check": f"scenario {sp.stem}", "status": status, "detail": "; ".join(lines[:6])})
    finally:
        if keep:
            rows.append({"check": "scratch project", "status": PASS, "detail": str(root)})
        else:
            shutil.rmtree(root, ignore_errors=True)
    statuses = [r["status"] for r in rows]
    return (FAIL if FAIL in statuses else NA if NA in statuses else PASS), rows
