"""Generators and intake.

- elevenlabs: sound effects and voice lines (REST, ELEVENLABS_API_KEY). Paid:
  never called without --yes; without it the plan is printed and the run stops.
- placeholder: labelled greybox sprites drawn locally (free, `_ph` names).
- synth: sfxr sound effects (free, see synth.py).
- OpenArt is reached through its official MCP server, which Claude calls
  directly (https://mcp.openart.ai/mcp); its result URLs come in through
  `ingest`, like any file downloaded by hand.

API facts were read from the official docs on 2026-11-25:
ElevenLabs POST /v1/sound-generation {text, duration_seconds 0.5-30, loop,
prompt_influence 0-1, model_id} and POST /v1/text-to-speech/{voice_id}
{text, model_id}, header xi-api-key, query output_format.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from common import ForgeError, hex_rgb

USER_AGENT = "asset-forge/1 (super-gamedev-agent)"


class NeedsApproval(Exception):
    """A paid call was planned but not confirmed with --yes (exit 4)."""


def _base() -> str:
    # Overridable so the tests can point the client at a local mock server.
    return os.environ.get("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").rstrip("/")


def _key() -> str:
    k = os.environ.get("ELEVENLABS_API_KEY", "")
    if not k:
        raise ForgeError("ELEVENLABS_API_KEY is not set (create one at elevenlabs.io > Developers > API keys)")
    return k


def _post(url: str, body: dict) -> tuple[bytes, str]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "xi-api-key": _key(), "Content-Type": "application/json", "Accept": "*/*", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        detail = e.read()[:400].decode("utf-8", "replace")
        raise ForgeError(f"ElevenLabs answered {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise ForgeError(f"could not reach ElevenLabs: {e.reason}") from None


def _ext(output_format: str) -> str:
    return {"mp3": ".mp3", "wav": ".wav", "pcm": ".pcm", "opus": ".opus"}.get(output_format.split("_")[0], ".bin")


def elevenlabs_sfx(prompt: str, out_dir: Path, cfg: dict, duration: float | None, loop: bool,
                   influence: float | None, count: int, approved: bool) -> list[Path]:
    fmt = cfg.get("output_format", "mp3_44100_128")
    plan = (f"ElevenLabs sound effects: {count} call(s), model {cfg.get('sfx_model')}, "
            f"{'duration ' + str(duration) + 's' if duration else 'duration chosen by the model'}"
            f"{', looping' if loop else ''}, format {fmt}")
    if not approved:
        raise NeedsApproval(plan)
    if duration is not None and not 0.5 <= duration <= 30:
        raise ForgeError("ElevenLabs sound effects take 0.5 to 30 seconds")
    body = {"text": prompt, "model_id": cfg.get("sfx_model", "eleven_text_to_sound_v2"), "loop": bool(loop)}
    if duration is not None:
        body["duration_seconds"] = duration
    if influence is not None:
        body["prompt_influence"] = influence
    url = f"{_base()}/v1/sound-generation?" + urllib.parse.urlencode({"output_format": fmt})
    out = []
    for i in range(count):
        data, _ = _post(url, body)
        if len(data) < 64:
            raise ForgeError("ElevenLabs returned an empty sound")
        p = out_dir / f"take{i + 1}{_ext(fmt)}"
        p.write_bytes(data)
        out.append(p)
    return out


def elevenlabs_voice(text: str, out_dir: Path, cfg: dict, voice_id: str, count: int, approved: bool) -> list[Path]:
    fmt = cfg.get("output_format", "mp3_44100_128")
    if not voice_id:
        raise ForgeError("no voice: pass --voice-id or set providers.elevenlabs.voice_id in style.json")
    plan = (f"ElevenLabs voice: {count} take(s) of {len(text)} characters, voice {voice_id}, "
            f"model {cfg.get('tts_model')}, format {fmt}")
    if not approved:
        raise NeedsApproval(plan)
    url = f"{_base()}/v1/text-to-speech/{urllib.parse.quote(voice_id)}?" + urllib.parse.urlencode({"output_format": fmt})
    out = []
    for i in range(count):
        data, _ = _post(url, {"text": text, "model_id": cfg.get("tts_model", "eleven_multilingual_v2")})
        p = out_dir / f"take{i + 1}{_ext(fmt)}"
        p.write_bytes(data)
        out.append(p)
    return out


def placeholder(out: Path, size: tuple[int, int], label: str, colour: str, shape: str = "box") -> Path:
    from PIL import Image, ImageDraw
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill = (*hex_rgb(colour), 255)
    edge = tuple(max(0, c - 70) for c in hex_rgb(colour)) + (255,)
    inset = 1 if min(w, h) >= 8 else 0        # leave the category's padding clear
    box = [inset, inset, w - 1 - inset, h - 1 - inset]
    if shape == "circle":
        d.ellipse(box, fill=fill, outline=edge)
    else:
        d.rectangle(box, fill=fill, outline=edge)
    text = label[:3].upper() if min(w, h) < 48 else label[:12]
    try:
        tw = d.textlength(text)
    except Exception:
        tw = len(text) * 6
    if tw < w - 2:
        d.text(((w - tw) / 2, h / 2 - 5), text, fill=(255, 255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def download(url: str, dest_dir: Path, name: str = "download") -> Path:
    """Fetch a generator's result URL (e.g. from the OpenArt MCP) into _raw."""
    u = urllib.parse.urlparse(url)
    local = u.hostname in ("127.0.0.1", "localhost")
    if u.scheme != "https" and not (u.scheme == "http" and local):
        raise ForgeError(f"refusing non-https URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data, ctype = r.read(), r.headers.get("Content-Type", "")
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        raise ForgeError(f"could not download {url}: {e}") from None
    ext = Path(u.path).suffix.lower()
    if ext not in (".png", ".webp", ".jpg", ".jpeg", ".gif", ".mp3", ".wav", ".ogg"):
        ext = {"image/png": ".png", "image/webp": ".webp", "image/jpeg": ".jpg",
               "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/ogg": ".ogg"}.get(ctype.split(";")[0], ".bin")
    dest_dir.mkdir(parents=True, exist_ok=True)
    p = dest_dir / f"{name}{ext}"
    p.write_bytes(data)
    return p
