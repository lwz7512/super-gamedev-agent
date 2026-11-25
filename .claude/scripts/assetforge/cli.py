"""asset-forge: the asset production pipeline (run through asset-forge.sh).

  init                     style.json + manifest.json + _raw/_inbox folders
  add <id> ...             add a manifest entry
  prompt <id>              the full generation prompt (paste into the OpenArt MCP call)
  gen <id> [--yes]         generate: synth / placeholder locally, elevenlabs (paid, needs --yes)
  ingest <url|file> --id   bring in a generator result (OpenArt MCP URL) or a downloaded file
  normalize <id>           raw take -> game-ready file (key, fit, palette | trim, level, encode)
  qa [ids]                 technical checks against the style lock
  sheet [ids]              contact sheet PNG to look at
  godot [ids]              import into Godot, SpriteFrames, gallery + scenario for godot-verify
  ledger check|sync        provenance and licence terms
  status                   the manifest at a glance
  selftest                 run the pipeline's own tests

Exit: 0 done/pass, 1 a check failed, 3 not assessed or a problem to fix,
4 a paid call needs approval (rerun with --yes after the person agrees).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (FAIL, NA, PASS, STATUSES, ForgeError, Project, hex_rgb, parse_size,  # noqa: E402
                    project_root, save_json, say, today, worst)

MARK = {PASS: "ok  ", FAIL: "FAIL", NA: "N/A "}


def _record(proj: Project, aid: str) -> tuple[Path, dict]:
    p = proj.raw / aid / "record.json"
    rec = json.loads(p.read_text()) if p.exists() else {"id": aid, "takes": []}
    return p, rec


def _add_take(proj: Project, aid: str, file: Path, info: dict) -> dict:
    p, rec = _record(proj, aid)
    take = {"take": len(rec["takes"]) + 1, "file": file.name, "date": today(), **info}
    rec["takes"].append(take)
    save_json(p, rec)
    return take


def default_path(style: dict, a: dict) -> str:
    kind = a["kind"]
    if kind == "image":
        folder = {"character": "characters", "enemy": "enemies", "item": "items", "tile": "tiles",
                  "ui": "ui", "background": "backgrounds"}.get(a.get("category", ""), "sprites")
        suffix = "_ph" if a.get("provider") == "placeholder" else ""
        return f"assets/{folder}/{a['id']}{suffix}.png"
    fmt = style["audio"]["format"]
    return f"assets/{'sfx' if kind == 'sfx' else 'voice' if kind == 'voice' else 'music'}/{a['id']}.{fmt}"


def build_prompt(proj: Project, a: dict) -> str:
    art = proj.style["art"]
    cat = proj.category(a)
    parts = []
    if art.get("style_prompt"):
        parts.append(art["style_prompt"].rstrip("."))
    parts.append(a.get("prompt", a["id"]).rstrip("."))
    if a.get("view"):
        parts.append(f"{a['view']} view")
    if cat.get("anchor") != "fill" and cat.get("alpha", art["alpha"]) != "none":
        # OpenArt documents no transparent output, so ask for a flat key colour
        # that normalize can remove exactly.
        parts.append(f"single subject centred, full body in frame, on a perfectly flat solid {art['key_color']} background, "
                     f"no gradient, no shadow on the background")
    if art["kind"] == "pixel":
        parts.append(f"clean pixel art, readable at {cat.get('size', '32x32')} pixels, limited palette, crisp edges")
    if art["palette"]:
        parts.append("colours only from this palette: " + ", ".join(art["palette"]))
    if art.get("avoid"):
        parts.append("avoid: " + art["avoid"])
    return ". ".join(parts) + "."


# ---------------------------------------------------------------- commands --

def cmd_init(proj: Project, args) -> int:
    from common import DEFAULT_STYLE
    proj.ensure_dirs()
    if proj.style_path.exists():
        say(f"kept {proj.rel(proj.style_path)}")
    else:
        style = json.loads(json.dumps(DEFAULT_STYLE))
        style["art"]["kind"] = args.kind
        if args.kind == "hd":
            style["art"].update({"alpha": "smooth", "max_colors": 256})
            for c in style["art"]["categories"].values():
                w, h = parse_size(c["size"])
                c["size"] = f"{w * 4}x{h * 4}" if c.get("anchor") != "fill" else c["size"]
        save_json(proj.style_path, style)
        say(f"wrote {proj.rel(proj.style_path)}: fill art.style_prompt, art.palette and the plans from the art bible")
    if not proj.manifest_path.exists():
        save_json(proj.manifest_path, {"schema": 1, "assets": []})
        say(f"wrote {proj.rel(proj.manifest_path)}")
    say(f"folders: {proj.rel(proj.raw)}/ (generator output), {proj.rel(proj.inbox)}/ (drop files here); Godot ignores both")
    return 0


def cmd_add(proj: Project, args) -> int:
    m = proj.manifest()
    if any(a["id"] == args.id for a in m["assets"]):
        raise ForgeError(f"'{args.id}' is already in the manifest")
    a = {"id": args.id, "kind": args.kind, "status": "planned"}
    for k in ("category", "prompt", "provider", "view", "size", "preset", "text", "voice_id"):
        v = getattr(args, k, None)
        if v not in (None, ""):
            a[k] = v
    if args.kind == "image" and "category" not in a:
        raise ForgeError("an image needs --category (one of the categories in style.json)")
    a.setdefault("provider", "openart" if args.kind == "image" else "elevenlabs" if args.kind == "voice" else "synth")
    if args.frames > 1:
        a["frames"], a["fps"] = args.frames, args.fps
    if args.loop:
        a["loop"] = True
    if args.seed is not None:
        a["seed"] = args.seed
    if args.duration:
        a["duration"] = args.duration
    a["path"] = args.path or default_path(proj.style, a)
    m["assets"].append(a)
    proj.save_manifest(m)
    say(f"added {args.id} -> {a['path']} ({a['provider']})")
    return 0


def cmd_prompt(proj: Project, args) -> int:
    a = proj.entry(proj.manifest(), args.id)
    say(build_prompt(proj, a))
    if int(a.get("frames", 1)) > 1:
        say(f"\n(animation: {a['frames']} frames. Generate frame 1, then each later frame as an edit of frame 1 "
            f"with the pose for that frame, and ingest each with --frame N.)")
    return 0


def cmd_gen(proj: Project, args) -> int:
    import providers
    m = proj.manifest()
    a = proj.entry(m, args.id)
    proj.ensure_dirs()
    d = proj.raw / a["id"]
    d.mkdir(parents=True, exist_ok=True)
    prov = args.provider or a.get("provider")
    style = proj.style
    if prov == "openart":
        say("OpenArt runs through its MCP server, which Claude calls directly (https://mcp.openart.ai/mcp).")
        say(f"Prompt:\n{build_prompt(proj, a)}\n")
        say(f"Then: asset-forge.sh ingest <result URL> --id {a['id']} --provider openart --model <model used>")
        return 0
    if prov == "synth":
        import audioops
        import synth
        seed = args.seed if args.seed is not None else int(a.get("seed", 1))
        preset = a.get("preset") or a["id"].split("-")[0]
        params = synth.preset(preset, seed)
        samples = synth.render(params, seed, float(a.get("duration", style["audio"]["sfx_max_seconds"])))
        out = d / f"synth-{preset}-{seed}.wav"
        audioops.write_wav(out, samples)
        _add_take(proj, a["id"], out, {"provider": "synth", "model": f"sfxr {preset} seed {seed}", "params": params})
        say(f"synth {preset} seed {seed}: {len(samples) / 44100:.2f}s -> {proj.rel(out)}")
    elif prov == "placeholder":
        size = parse_size(proj.category(a).get("size", "32x32"))
        frames = int(a.get("frames", 1))
        for f in range(frames):
            out = d / f"placeholder-{f}.png"
            providers.placeholder(out, size, a.get("label", a["id"]), args.colour or "#7c5cff",
                                  "circle" if a.get("category") in ("item",) else "box")
            _add_take(proj, a["id"], out, {"provider": "placeholder", "frame": f})
        say(f"placeholder {size[0]}x{size[1]} x{frames} -> {proj.rel(d)}")
    elif prov == "elevenlabs":
        cfg = style["providers"]["elevenlabs"]
        try:
            if a["kind"] == "voice":
                files = providers.elevenlabs_voice(a.get("text") or a.get("prompt", ""), d, cfg,
                                                   a.get("voice_id") or cfg.get("voice_id", ""), args.count, args.yes)
            else:
                files = providers.elevenlabs_sfx(a.get("prompt", a["id"]), d, cfg, a.get("duration"),
                                                 bool(a.get("loop")), a.get("prompt_influence"), args.count, args.yes)
        except providers.NeedsApproval as e:
            say(f"NEEDS APPROVAL: {e}")
            say("Ask the person; on yes, run the same command with --yes.")
            return 4
        for i, f in enumerate(files):
            fresh = d / f"elevenlabs-{len(_record(proj, a['id'])[1]['takes']) + 1}{f.suffix}"
            f.rename(fresh)
            _add_take(proj, a["id"], fresh, {"provider": "elevenlabs", "via": "api",
                                             "model": cfg["tts_model" if a["kind"] == "voice" else "sfx_model"],
                                             "prompt": a.get("text") or a.get("prompt", "")})
            say(f"elevenlabs -> {proj.rel(fresh)}")
    else:
        raise ForgeError(f"unknown provider '{prov}' (openart, elevenlabs, synth, placeholder)")
    a["status"] = "generated"
    proj.save_manifest(m)
    return 0


def cmd_ingest(proj: Project, args) -> int:
    import providers
    m = proj.manifest()
    a = proj.entry(m, args.id)
    proj.ensure_dirs()
    d = proj.raw / a["id"]
    n = len(_record(proj, a["id"])[1]["takes"]) + 1
    src = args.source
    if src.startswith(("http://", "https://")):
        f = providers.download(src, d, f"take{n}")
    else:
        sp = Path(src)
        if not sp.exists():
            raise ForgeError(f"no such file: {src}")
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"take{n}{sp.suffix.lower()}"
        shutil.copyfile(sp, f)
    info = {"provider": args.provider or "", "via": args.via, "model": args.model or "",
            "prompt": args.prompt or build_prompt(proj, a) if (args.provider == "openart") else args.prompt or "",
            "source_url": src if src.startswith("http") else ""}
    if args.frame is not None:
        info["frame"] = args.frame
    if not args.provider:
        info.update({"origin": args.origin or "unknown", "tool": args.tool or "",
                     "source": {"vendor": args.vendor or "", "url": args.source_url or ""},
                     "licence": {"id": args.licence} if args.licence else {}})
        if (args.origin or "unknown") == "unknown":
            say("note: no --origin given; the ledger will mark this file 'unknown' and refuse to ship it")
    take = _add_take(proj, a["id"], f, info)
    a["status"] = "generated"
    proj.save_manifest(m)
    say(f"ingested take {take['take']} -> {proj.rel(f)}")
    return 0


def cmd_normalize(proj: Project, args) -> int:
    import ledger
    m = proj.manifest()
    a = proj.entry(m, args.id)
    _, rec = _record(proj, a["id"])
    if not rec["takes"]:
        raise ForgeError(f"no takes for {a['id']}: run gen or ingest first")
    style = proj.style
    dest = proj.root / a["path"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    frames = int(a.get("frames", 1))
    if a.get("kind", "image") == "image":
        import imageops
        cat = proj.category(a)
        size = parse_size(cat.get("size", "32x32"))
        pixel = style["art"]["kind"] == "pixel"
        binary = cat.get("alpha", style["art"]["alpha"]) == "binary"
        takes = _pick(rec, args.take, frames)
        out = []
        for t in takes:
            img = imageops.load(proj.raw / a["id"] / t["file"])
            note = "background kept (fill)"
            if t.get("provider") == "placeholder":
                note = "placeholder: drawn exact, not keyed"
            elif cat.get("anchor") != "fill" and cat.get("alpha", style["art"]["alpha"]) != "none":
                img, note = imageops.key_background(img, style["art"]["key_color"], args.tolerance, binary)
            img = imageops.fit(img, size, cat.get("anchor", "center"), int(cat.get("padding", 0)), pixel)
            if pixel or style["art"]["palette"]:
                img = imageops.lock_palette(img, style["art"]["palette"], int(style["art"]["max_colors"]), binary)
            out.append(img)
            say(f"take {t['take']}: {note}")
        result = imageops.strip(out) if frames > 1 else out[0]
        result.save(dest)
        say(f"{a['id']}: {result.width}x{result.height} -> {a['path']}")
        main = takes[0]
    else:
        import audioops
        t = _pick(rec, args.take, 1)[0]
        samples, rate = audioops.read_wav(proj.raw / a["id"] / t["file"])
        st = style["audio"]
        cleaned = audioops.clean(samples, rate, float(st["peak_dbfs"]), float(st["lead_silence_ms"]), bool(a.get("loop")))
        peak = audioops.encode_within_peak(cleaned, rate, dest, float(st["peak_dbfs"]), proj.raw / a["id"] / "_clean.wav")
        say(f"{a['id']}: {len(cleaned) / rate:.2f}s, peak {peak:.2f} dBFS after encoding -> {a['path']}")
        main = t
    record = dict(main)
    record["record"] = proj.rel(proj.raw / a["id"] / "record.json")
    res = ledger.upsert(proj, ledger.entry_for(proj, a, record))
    a["status"] = "normalized"
    a["take"] = main["take"]
    proj.save_manifest(m)
    say(f"provenance: {res}")
    return 0


def _pick(rec: dict, take: int | None, frames: int) -> list[dict]:
    takes = rec["takes"]
    if frames > 1:
        by_frame = {}
        for t in takes:
            if "frame" in t:
                by_frame[int(t["frame"])] = t       # latest take per frame wins
        missing = [i for i in range(frames) if i not in by_frame]
        if missing:
            raise ForgeError(f"frames {missing} have no take (ingest with --frame N)")
        return [by_frame[i] for i in range(frames)]
    if take:
        hit = [t for t in takes if t["take"] == take]
        if not hit:
            raise ForgeError(f"no take {take}")
        return hit
    return [takes[-1]]


def _select(proj: Project, ids: list[str]) -> tuple[dict, list[dict]]:
    m = proj.manifest()
    return m, [proj.entry(m, i) for i in ids] if ids else list(m["assets"])


def cmd_qa(proj: Project, args) -> int:
    import qa
    m, assets = _select(proj, args.ids)
    if not assets:
        say("NOT ASSESSED: the manifest has no assets")
        return 3
    overall, results = qa.run(proj, assets)
    for r in results:
        say(f"{MARK[r['status']]} {r['id']}  ({r['path']})")
        for c in r["checks"]:
            if c["status"] != PASS or args.verbose:
                say(f"       {MARK[c['status']]} {c['check']}: {c['detail']}")
        a = proj.entry(m, r["id"])
        if a.get("status") in (None, "planned", "generated", "normalized", "qa-pass", "qa-fail"):
            a["status"] = {PASS: "qa-pass", FAIL: "qa-fail"}.get(r["status"], a.get("status"))
    proj.save_manifest(m)
    out = proj.out / "qa.json"
    save_json(out, {"status": overall, "results": results})
    say(f"STATUS: {overall}  (details: {proj.rel(out)})")
    return {PASS: 0, FAIL: 1}.get(overall, 3)


def cmd_sheet(proj: Project, args) -> int:
    import sheet
    _, assets = _select(proj, args.ids)
    out = Path(args.out) if args.out else proj.out / "sheet.png"
    sheet.build(proj, assets, out)
    say(f"contact sheet: {out}  (Read it to look at the assets)")
    return 0


def cmd_godot(proj: Project, args) -> int:
    import godot
    m, assets = _select(proj, args.ids)
    assets = [a for a in assets if (proj.root / a["path"]).exists()]
    if not assets:
        say("NOT ASSESSED: no produced assets to import")
        return 3
    status, rows = godot.run(proj, assets, args.set_nearest)
    for r in rows:
        say(f"{MARK[r['status']]} {r['check']}: {r['detail']}")
    scn = godot.gallery(proj, assets)
    say(f"gallery: tests/asset_gallery/ · scenario: {proj.rel(scn)}")
    say(f"look in-engine: bash .claude/scripts/godot-verify.sh run {proj.rel(scn)}")
    if status == PASS:
        for a in assets:
            if a.get("status") == "qa-pass":
                a["status"] = "imported"
        proj.save_manifest(m)
    say(f"STATUS: {status}")
    return {PASS: 0, FAIL: 1}.get(status, 3)


def cmd_ledger(proj: Project, args) -> int:
    import ledger
    if args.action == "sync":
        m = proj.manifest()
        for a in m["assets"]:
            if not (proj.root / a["path"]).exists():
                continue
            _, rec = _record(proj, a["id"])
            take = next((t for t in rec["takes"] if t["take"] == a.get("take")), rec["takes"][-1] if rec["takes"] else None)
            if take:
                take = dict(take, record=proj.rel(proj.raw / a["id"] / "record.json"))
                say(f"{a['id']}: {ledger.upsert(proj, ledger.entry_for(proj, a, take))}")
        return 0
    overall, rows, summary = ledger.check(proj, args.release)
    for r in rows:
        if r["status"] != PASS or args.verbose:
            say(f"{MARK[r['status']]} {r['path']}: {r['detail']}")
    say(f"goal: {summary['goal']} · {summary['files']} files · {summary['ai_generated']} AI-generated"
        + (" (Steam's content survey asks you to disclose these)" if summary["ai_generated"] else ""))
    if summary["orphans"]:
        say(f"note: entries for files that no longer exist: {', '.join(summary['orphans'][:8])}")
    say(f"STATUS: {overall}")
    return {PASS: 0, FAIL: 1}.get(overall, 3)


def cmd_status(proj: Project, args) -> int:
    m = proj.manifest()
    if not m["assets"]:
        say("manifest is empty: asset-forge.sh add <id> --kind image --category character --prompt \"...\"")
        return 0
    w = max(len(a["id"]) for a in m["assets"])
    for a in m["assets"]:
        exists = "✓" if (proj.root / a["path"]).exists() else " "
        say(f"{a['id']:<{w}}  {a.get('kind', 'image'):<5}  {a.get('provider', ''):<11}  {a.get('status', 'planned'):<10}  {exists} {a['path']}")
    return 0


def cmd_selftest(proj: Project, args) -> int:
    import unittest
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent / "tests"))
    r = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if r.wasSuccessful() else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="asset-forge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", help="game root (default: current folder)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("--kind", choices=["pixel", "hd"], default="pixel")
    s = sub.add_parser("add")
    s.add_argument("id"); s.add_argument("--kind", choices=["image", "sfx", "voice", "music"], default="image")
    s.add_argument("--category"); s.add_argument("--prompt"); s.add_argument("--provider",
        choices=["openart", "elevenlabs", "synth", "placeholder", "manual"])
    s.add_argument("--view"); s.add_argument("--size"); s.add_argument("--path"); s.add_argument("--preset")
    s.add_argument("--text"); s.add_argument("--voice-id", dest="voice_id")
    s.add_argument("--frames", type=int, default=1); s.add_argument("--fps", type=float, default=8)
    s.add_argument("--loop", action="store_true"); s.add_argument("--seed", type=int); s.add_argument("--duration", type=float)
    s = sub.add_parser("prompt"); s.add_argument("id")
    s = sub.add_parser("gen"); s.add_argument("id"); s.add_argument("--yes", action="store_true")
    s.add_argument("--count", type=int, default=1); s.add_argument("--seed", type=int)
    s.add_argument("--provider"); s.add_argument("--colour")
    s = sub.add_parser("ingest"); s.add_argument("source"); s.add_argument("--id", required=True)
    s.add_argument("--provider", choices=["openart", "elevenlabs"]); s.add_argument("--via", default="mcp")
    s.add_argument("--model"); s.add_argument("--prompt"); s.add_argument("--frame", type=int)
    s.add_argument("--origin", choices=["ai", "bought", "cc0", "you", "outsourced", "licensed", "code", "unknown"])
    s.add_argument("--tool"); s.add_argument("--vendor"); s.add_argument("--source-url", dest="source_url")
    s.add_argument("--licence")
    s = sub.add_parser("normalize"); s.add_argument("id"); s.add_argument("--take", type=int)
    s.add_argument("--tolerance", type=float, default=40.0)
    for name in ("qa", "sheet", "godot"):
        s = sub.add_parser(name); s.add_argument("ids", nargs="*")
        if name == "qa":
            s.add_argument("-v", "--verbose", action="store_true")
        if name == "sheet":
            s.add_argument("--out")
        if name == "godot":
            s.add_argument("--set-nearest", action="store_true",
                           help="set the project's default canvas texture filter to Nearest (pixel art)")
    s = sub.add_parser("ledger"); s.add_argument("action", choices=["check", "sync"])
    s.add_argument("--release", action="store_true"); s.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("status")
    sub.add_parser("selftest")
    args = p.parse_args(argv)
    try:
        proj = Project(project_root(args.project))
        return globals()[f"cmd_{args.cmd}"](proj, args)
    except ForgeError as e:
        say(f"NOT ASSESSED: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
