"""Audio: read/write 16-bit WAV, measure, clean up, convert, draw waveforms.

Analysis works on mono floats from a 16-bit PCM WAV; any other file (mp3 from
ElevenLabs, ogg) is decoded to WAV with ffmpeg first. Without ffmpeg those
files can be stored but not measured, and QA says so (not assessed).
"""

from __future__ import annotations

import array
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from common import ForgeError


def ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def write_wav(path: Path, samples: list[float], rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array.array("h", (int(max(-1.0, min(1.0, x)) * 32767) for x in samples))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def read_wav(path: Path) -> tuple[list[float], int]:
    """Mono float samples and the sample rate. Non-WAV input goes through ffmpeg."""
    if path.suffix.lower() != ".wav":
        return decode(path)
    try:
        with wave.open(str(path), "rb") as w:
            ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError) as e:
        # Float or 24-bit WAVs are legal but not readable by `wave`: decode instead.
        if ffmpeg():
            return decode(path)
        raise ForgeError(f"cannot read {path.name} as 16-bit WAV ({e}) and ffmpeg is not installed") from None
    if width != 2:
        if ffmpeg():
            return decode(path)
        raise ForgeError(f"{path.name} is {width * 8}-bit; install ffmpeg to read it")
    a = array.array("h")
    a.frombytes(raw)
    if ch > 1:
        a = [sum(a[i:i + ch]) / ch for i in range(0, len(a), ch)]
    return [x / 32768.0 for x in a], rate


def decode(path: Path) -> tuple[list[float], int]:
    if not ffmpeg():
        raise ForgeError(f"ffmpeg is needed to read {path.suffix} audio ({path.name})")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "decoded.wav"
        r = subprocess.run([ffmpeg(), "-v", "error", "-y", "-i", str(path), "-ac", "1",
                            "-ar", "44100", "-c:a", "pcm_s16le", str(out)], capture_output=True, text=True)
        if r.returncode != 0:
            raise ForgeError(f"ffmpeg could not decode {path.name}: {r.stderr.strip()[:200]}")
        return read_wav(out)


def encode(src_wav: Path, dest: Path) -> Path:
    """WAV -> dest's format (.wav copy, .ogg Vorbis, .mp3) via ffmpeg."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffix.lower() == ".wav":
        shutil.copyfile(src_wav, dest)
        return dest
    if not ffmpeg():
        raise ForgeError(f"ffmpeg is needed to write {dest.suffix} (or set audio.format to \"wav\" in style.json)")
    codec = {".ogg": ["-c:a", "libvorbis", "-q:a", "6"], ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"]}.get(dest.suffix.lower())
    if codec is None:
        raise ForgeError(f"unsupported audio format {dest.suffix}")
    if dest.suffix.lower() == ".ogg" and not _has_encoder("libvorbis"):
        # Homebrew's ffmpeg ships without libvorbis; its built-in encoder is
        # marked experimental and only takes stereo, but Godot plays it.
        codec = ["-c:a", "vorbis", "-strict", "-2", "-ac", "2", "-q:a", "6"]
    r = subprocess.run([ffmpeg(), "-v", "error", "-y", "-i", str(src_wav), *codec, str(dest)], capture_output=True, text=True)
    if r.returncode != 0:
        raise ForgeError(f"ffmpeg could not encode {dest.name}: {r.stderr.strip()[:200]}")
    return dest


def _has_encoder(name: str) -> bool:
    r = subprocess.run([ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True)
    return any(line.split()[1:2] == [name] for line in r.stdout.splitlines() if len(line.split()) > 1)


def db(x: float) -> float:
    return 20.0 * math.log10(x) if x > 1e-9 else -120.0


def analyse(samples: list[float], rate: int) -> dict:
    n = len(samples)
    if n == 0:
        return {"seconds": 0.0, "rate": rate, "peak_dbfs": -120.0, "rms_dbfs": -120.0,
                "lead_silence_ms": 0.0, "clipped": 0, "loop_jump": 0.0}
    peak = max(abs(x) for x in samples)
    rms = math.sqrt(sum(x * x for x in samples) / n)
    gate = 10 ** (-50 / 20)                  # -50 dBFS counts as silence
    lead = next((i for i, x in enumerate(samples) if abs(x) > gate), n)
    return {
        "seconds": round(n / rate, 3),
        "rate": rate,
        "peak_dbfs": round(db(peak), 2),
        "rms_dbfs": round(db(rms), 2),
        "lead_silence_ms": round(lead / rate * 1000.0, 1),
        "clipped": sum(1 for x in samples if abs(x) >= 0.999),
        # A loop clicks where the last sample jumps to the first.
        "loop_jump": round(abs(samples[-1] - samples[0]), 4),
    }


def clean(samples: list[float], rate: int, peak_dbfs: float, lead_ms: float, loop: bool) -> list[float]:
    """Trim leading/trailing silence, fade the edges, normalise the peak."""
    gate = 10 ** (-50 / 20)
    first = next((i for i, x in enumerate(samples) if abs(x) > gate), 0)
    last = len(samples) - next((i for i, x in enumerate(reversed(samples)) if abs(x) > gate), 0)
    keep = int(lead_ms / 1000.0 * rate * 0.5)
    s = samples[max(0, first - keep):last] if not loop else samples[:]
    if not s:
        return s
    if loop:
        # Blend the tail into the head and drop the head: the last sample then
        # leads straight into the new first one, so the loop point is continuous.
        f = min(len(s) // 4, int(0.02 * rate))
        if f:
            head, tail = s[:f], s[-f:]
            s = s[f:-f] + [tail[i] * (1 - i / f) + head[i] * (i / f) for i in range(f)]
    else:
        fade = min(len(s) // 4, int(0.004 * rate))     # 4 ms fades stop edge clicks
        for i in range(fade):
            g = i / fade
            s[i] *= g
            s[-1 - i] *= g
    peak = max(abs(x) for x in s) or 1.0
    gain = (10 ** (peak_dbfs / 20)) / peak
    return [x * gain for x in s]


def waveform_png(samples: list[float], rate: int, path: Path, label: str = "", size=(480, 120)):
    from PIL import Image, ImageDraw
    w, h = size
    img = Image.new("RGB", (w, h), (20, 18, 36))
    d = ImageDraw.Draw(img)
    mid = h // 2
    d.line([(0, mid), (w, mid)], fill=(60, 56, 90))
    if samples:
        step = max(1, len(samples) // w)
        for x in range(w):
            chunk = samples[x * step:(x + 1) * step] or [0.0]
            lo, hi = min(chunk), max(chunk)
            d.line([(x, mid - int(hi * (mid - 4))), (x, mid - int(lo * (mid - 4)))], fill=(255, 181, 71))
    secs = len(samples) / rate if rate else 0
    d.text((6, 4), f"{label}  {secs:.2f}s", fill=(235, 233, 250))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return img
