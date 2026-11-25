"""Technical QA for each manifest asset against the style lock.

Every check is pass / fail / not_assessed with a reason. A missing tool
(ffmpeg for ogg) or a missing file is not_assessed or fail, never a pass.
"""

from __future__ import annotations

from pathlib import Path

import audioops
import imageops
from common import FAIL, NA, PASS, ForgeError, Project, parse_size, worst


def check_image(proj: Project, a: dict) -> list[dict]:
    style = proj.style["art"]
    cat = proj.category(a)
    path = proj.root / a["path"]
    rows = []
    add = lambda name, ok, detail: rows.append({"check": name, "status": PASS if ok else FAIL, "detail": detail})
    if not path.exists():
        return [{"check": "exists", "status": FAIL, "detail": f"{a['path']} not produced yet"}]
    img = imageops.load(path)
    frames = int(a.get("frames", 1))
    if "size" not in cat:
        rows.append({"check": "size", "status": NA, "detail": f"category '{a.get('category')}' has no size in style.json"})
        w = h = None
    else:
        w, h = parse_size(cat["size"])
        add("size", img.size == (w * frames, h), f"{img.width}x{img.height}, want {w * frames}x{h}" + (f" ({frames} frames)" if frames > 1 else ""))
    m = imageops.measure(img, style["palette"])
    add("not empty", not m["empty"], "has visible pixels" if not m["empty"] else "fully transparent")
    wants_alpha = cat.get("alpha", style["alpha"]) != "none"
    if wants_alpha:
        add("transparency", m["transparent_ratio"] > 0, f"{m['transparent_ratio']:.0%} transparent")
        add("no fake checkerboard", not m["checkerboard"], "checkerboard baked into the pixels" if m["checkerboard"] else "clean")
        if cat.get("alpha", style["alpha"]) == "binary":
            add("hard alpha edges", m["semi_alpha_pixels"] == 0, f"{m['semi_alpha_pixels']} half-transparent pixels")
        if cat.get("anchor") != "fill" and int(cat.get("padding", 0)) > 0:
            add("inside padding", not m["touches_edge"], "touches the canvas edge (clipped?)" if m["touches_edge"] else "clear of the edge")
    if style["kind"] == "pixel":
        add("colour count", m["colours"] <= int(style["max_colors"]), f"{m['colours']} colours, max {style['max_colors']}")
    if style["palette"]:
        share = m["palette_share"]
        add("palette lock", share is not None and share >= 0.999, f"{(share or 0):.1%} of pixels on the palette")
    if frames > 1 and w:
        bases = []
        for i in range(frames):
            fm = imageops.measure(img.crop((i * w, 0, (i + 1) * w, h)), [])
            bases.append(fm["baseline"])
        ok = None not in bases and max(bases) - min(bases) <= 1
        add("frame baseline", ok, f"bottom rows per frame: {bases}")
    return rows


def check_audio(proj: Project, a: dict) -> list[dict]:
    st = proj.style["audio"]
    path = proj.root / a["path"]
    if not path.exists():
        return [{"check": "exists", "status": FAIL, "detail": f"{a['path']} not produced yet"}]
    try:
        samples, rate = audioops.read_wav(path)
    except ForgeError as e:
        return [{"check": "readable", "status": NA, "detail": str(e)}]
    m = audioops.analyse(samples, rate)
    rows = []
    add = lambda name, ok, detail: rows.append({"check": name, "status": PASS if ok else FAIL, "detail": detail})
    add("not silent", m["rms_dbfs"] > -45, f"RMS {m['rms_dbfs']} dBFS")
    add("headroom", m["peak_dbfs"] <= float(st["peak_dbfs"]) + 0.3 and m["clipped"] == 0,
        f"peak {m['peak_dbfs']} dBFS, {m['clipped']} clipped samples (target {st['peak_dbfs']})")
    if a.get("kind") == "sfx":
        add("length", m["seconds"] <= float(a.get("max_seconds", st["sfx_max_seconds"])),
            f"{m['seconds']}s (max {a.get('max_seconds', st['sfx_max_seconds'])}s)")
        if not a.get("loop"):
            add("starts promptly", m["lead_silence_ms"] <= float(st["lead_silence_ms"]),
                f"{m['lead_silence_ms']} ms before the sound starts (max {st['lead_silence_ms']})")
    if a.get("loop"):
        add("seamless loop", m["loop_jump"] < 0.05, f"jump of {m['loop_jump']} at the loop point")
    return rows


def run(proj: Project, assets: list[dict]) -> tuple[str, list[dict]]:
    results = []
    for a in assets:
        kind = a.get("kind", "image")
        rows = check_image(proj, a) if kind == "image" else check_audio(proj, a)
        results.append({"id": a["id"], "path": a.get("path"), "status": worst(r["status"] for r in rows), "checks": rows})
    return worst(r["status"] for r in results), results
