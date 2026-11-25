"""Procedural sound effects: a port of DrPetter's sfxr synthesizer.

Same algorithm and parameter ranges as sfxr/jsfxr (square, saw, sine and noise
oscillators, ADSR-style envelope with punch, frequency slide and delta slide,
vibrato, arpeggio, duty sweep, retrigger, phaser, low- and high-pass filters),
with the preset generators that made sfxr the jam-game standard. A preset plus
a seed always gives the same sound.
"""

from __future__ import annotations

import math
import random

PRESETS = ("coin", "laser", "explosion", "powerup", "hit", "jump", "blip")
RATE = 44100


def defaults() -> dict:
    return {
        "wave": 0, "base_freq": 0.3, "freq_limit": 0.0, "freq_ramp": 0.0, "freq_dramp": 0.0,
        "duty": 0.0, "duty_ramp": 0.0, "vib_strength": 0.0, "vib_speed": 0.0,
        "env_attack": 0.0, "env_sustain": 0.3, "env_punch": 0.0, "env_decay": 0.4,
        "lpf_freq": 1.0, "lpf_ramp": 0.0, "lpf_resonance": 0.0, "hpf_freq": 0.0, "hpf_ramp": 0.0,
        "pha_offset": 0.0, "pha_ramp": 0.0, "repeat_speed": 0.0, "arp_speed": 0.0, "arp_mod": 0.0,
        "sound_vol": 0.5,
    }


def preset(name: str, seed: int) -> dict:
    """sfxr's generator for `name`, drawn from a seeded RNG."""
    if name not in PRESETS:
        raise ValueError(f"unknown preset '{name}' (one of: {', '.join(PRESETS)})")
    r = random.Random(seed).random
    p = defaults()
    if name == "coin":
        p["base_freq"] = 0.4 + r() * 0.5
        p["env_attack"] = 0.0
        p["env_sustain"] = r() * 0.1
        p["env_decay"] = 0.1 + r() * 0.4
        p["env_punch"] = 0.3 + r() * 0.3
        if r() < 0.5:
            p["arp_speed"] = 0.5 + r() * 0.2
            p["arp_mod"] = 0.2 + r() * 0.4
    elif name == "laser":
        p["wave"] = int(r() * 3)
        if p["wave"] == 2 and r() < 0.5:
            p["wave"] = int(r() * 2)
        p["base_freq"] = 0.5 + r() * 0.5
        p["freq_limit"] = max(0.2, p["base_freq"] - 0.2 - r() * 0.6)
        p["freq_ramp"] = -0.15 - r() * 0.2
        if r() < 0.33:
            p["base_freq"] = 0.3 + r() * 0.6
            p["freq_limit"] = r() * 0.1
            p["freq_ramp"] = -0.35 - r() * 0.3
        if r() < 0.5:
            p["duty"] = r() * 0.5
            p["duty_ramp"] = r() * 0.2
        else:
            p["duty"] = 0.4 + r() * 0.5
            p["duty_ramp"] = -r() * 0.7
        p["env_attack"] = 0.0
        p["env_sustain"] = 0.1 + r() * 0.2
        p["env_decay"] = r() * 0.4
        if r() < 0.5:
            p["env_punch"] = r() * 0.3
        if r() < 0.33:
            p["pha_offset"] = r() * 0.2
            p["pha_ramp"] = -r() * 0.2
        if r() < 0.5:
            p["hpf_freq"] = r() * 0.3
    elif name == "explosion":
        p["wave"] = 3
        if r() < 0.5:
            p["base_freq"] = 0.1 + r() * 0.4
            p["freq_ramp"] = -0.1 + r() * 0.4
        else:
            p["base_freq"] = 0.2 + r() * 0.7
            p["freq_ramp"] = -0.2 - r() * 0.2
        p["base_freq"] *= p["base_freq"]
        if r() < 0.2:
            p["freq_ramp"] = 0.0
        if r() < 0.33:
            p["repeat_speed"] = 0.3 + r() * 0.5
        p["env_attack"] = 0.0
        p["env_sustain"] = 0.1 + r() * 0.3
        p["env_decay"] = r() * 0.5
        if r() < 0.5:
            p["pha_offset"] = -0.3 + r() * 0.9
            p["pha_ramp"] = -r() * 0.3
        p["env_punch"] = 0.2 + r() * 0.6
        if r() < 0.5:
            p["vib_strength"] = r() * 0.7
            p["vib_speed"] = r() * 0.6
        if r() < 0.33:
            p["arp_speed"] = 0.6 + r() * 0.3
            p["arp_mod"] = 0.8 - r() * 1.6
    elif name == "powerup":
        if r() < 0.5:
            p["wave"] = 1
        else:
            p["duty"] = r() * 0.6
        if r() < 0.5:
            p["base_freq"] = 0.2 + r() * 0.3
            p["freq_ramp"] = 0.1 + r() * 0.4
            p["repeat_speed"] = 0.4 + r() * 0.4
        else:
            p["base_freq"] = 0.2 + r() * 0.3
            p["freq_ramp"] = 0.05 + r() * 0.2
            if r() < 0.5:
                p["vib_strength"] = r() * 0.7
                p["vib_speed"] = r() * 0.6
        p["env_attack"] = 0.0
        p["env_sustain"] = r() * 0.4
        p["env_decay"] = 0.1 + r() * 0.4
    elif name == "hit":
        p["wave"] = int(r() * 3)
        if p["wave"] == 2:
            p["wave"] = 3
        if p["wave"] == 0:
            p["duty"] = r() * 0.6
        p["base_freq"] = 0.2 + r() * 0.6
        p["freq_ramp"] = -0.3 - r() * 0.4
        p["env_attack"] = 0.0
        p["env_sustain"] = r() * 0.1
        p["env_decay"] = 0.1 + r() * 0.2
        if r() < 0.5:
            p["hpf_freq"] = r() * 0.3
    elif name == "jump":
        p["wave"] = 0
        p["duty"] = r() * 0.6
        p["base_freq"] = 0.3 + r() * 0.3
        p["freq_ramp"] = 0.1 + r() * 0.2
        p["env_attack"] = 0.0
        p["env_sustain"] = 0.1 + r() * 0.3
        p["env_decay"] = 0.1 + r() * 0.2
        if r() < 0.5:
            p["hpf_freq"] = r() * 0.3
        if r() < 0.5:
            p["lpf_freq"] = 1.0 - r() * 0.6
    elif name == "blip":
        p["wave"] = int(r() * 2)
        if p["wave"] == 0:
            p["duty"] = r() * 0.6
        p["base_freq"] = 0.2 + r() * 0.4
        p["env_attack"] = 0.0
        p["env_sustain"] = 0.1 + r() * 0.1
        p["env_decay"] = r() * 0.2
        p["hpf_freq"] = 0.1
    return p


def render(p: dict, seed: int = 0, max_seconds: float = 4.0) -> list[float]:
    """Synthesise samples in [-1, 1] at 44.1 kHz from sfxr parameters."""
    noise_rng = random.Random(seed ^ 0x5F3759DF)
    s = {}

    def reset(restart: bool) -> None:
        s["fperiod"] = 100.0 / (p["base_freq"] ** 2 + 0.001)
        s["fmaxperiod"] = 100.0 / (p["freq_limit"] ** 2 + 0.001)
        s["fslide"] = 1.0 - p["freq_ramp"] ** 3 * 0.01
        s["fdslide"] = -p["freq_dramp"] ** 3 * 0.000001
        s["square_duty"] = 0.5 - p["duty"] * 0.5
        s["square_slide"] = -p["duty_ramp"] * 0.00005
        am = p["arp_mod"]
        s["arp_mod"] = 1.0 - am * am * 0.9 if am >= 0 else 1.0 + am * am * 10.0
        s["arp_time"] = 0
        s["arp_limit"] = 0 if p["arp_speed"] == 1.0 else int((1.0 - p["arp_speed"]) ** 2 * 20000 + 32)
        if restart:
            return
        s["fltp"] = s["fltdp"] = s["fltphp"] = 0.0
        s["fltw"] = p["lpf_freq"] ** 3 * 0.1
        s["fltw_d"] = 1.0 + p["lpf_ramp"] * 0.0001
        s["fltdmp"] = min(0.8, 5.0 / (1.0 + p["lpf_resonance"] ** 2 * 20.0) * (0.01 + s["fltw"]))
        s["flthp"] = p["hpf_freq"] ** 2 * 0.1
        s["flthp_d"] = 1.0 + p["hpf_ramp"] * 0.0003
        s["vib_phase"] = 0.0
        s["vib_speed"] = p["vib_speed"] ** 2 * 0.01
        s["vib_amp"] = p["vib_strength"] * 0.5
        s["env_vol"] = 0.0
        s["env_stage"] = 0
        s["env_time"] = 0
        s["env_length"] = [max(1, int(p["env_attack"] ** 2 * 100000)),
                           max(1, int(p["env_sustain"] ** 2 * 100000)),
                           max(1, int(p["env_decay"] ** 2 * 100000))]
        po = p["pha_offset"]
        s["fphase"] = po * po * 1020.0 * (1 if po >= 0 else -1)
        pr = p["pha_ramp"]
        s["fdphase"] = pr * pr * 1.0 * (1 if pr >= 0 else -1)
        s["ipp"] = 0
        s["phaser"] = [0.0] * 1024
        s["noise"] = [noise_rng.random() * 2.0 - 1.0 for _ in range(32)]
        s["rep_time"] = 0
        s["rep_limit"] = 0 if p["repeat_speed"] == 0 else int((1.0 - p["repeat_speed"]) ** 2 * 20000 + 32)
        s["phase"] = 0

    reset(False)
    out: list[float] = []
    wave = p["wave"]
    limit = int(max_seconds * RATE)
    while len(out) < limit:
        s["rep_time"] += 1
        if s["rep_limit"] and s["rep_time"] >= s["rep_limit"]:
            s["rep_time"] = 0
            reset(True)
        s["arp_time"] += 1
        if s["arp_limit"] and s["arp_time"] >= s["arp_limit"]:
            s["arp_limit"] = 0
            s["fperiod"] *= s["arp_mod"]
        s["fslide"] += s["fdslide"]
        s["fperiod"] *= s["fslide"]
        if s["fperiod"] > s["fmaxperiod"]:
            s["fperiod"] = s["fmaxperiod"]
            if p["freq_limit"] > 0:
                break
        rfperiod = s["fperiod"]
        if s["vib_amp"] > 0:
            s["vib_phase"] += s["vib_speed"]
            rfperiod = s["fperiod"] * (1.0 + math.sin(s["vib_phase"]) * s["vib_amp"])
        period = max(8, int(rfperiod))
        s["square_duty"] = min(0.5, max(0.0, s["square_duty"] + s["square_slide"]))

        s["env_time"] += 1
        if s["env_time"] > s["env_length"][s["env_stage"]]:
            s["env_time"] = 0
            s["env_stage"] += 1
            if s["env_stage"] == 3:
                break
        t = s["env_time"] / s["env_length"][s["env_stage"]]
        if s["env_stage"] == 0:
            s["env_vol"] = t
        elif s["env_stage"] == 1:
            s["env_vol"] = 1.0 + (1.0 - t) * 2.0 * p["env_punch"]
        else:
            s["env_vol"] = 1.0 - t

        s["fphase"] += s["fdphase"]
        iphase = min(1023, abs(int(s["fphase"])))
        if s["flthp_d"] != 0:
            s["flthp"] = min(0.1, max(0.00001, s["flthp"] * s["flthp_d"]))

        ssample = 0.0
        for _ in range(8):           # 8x supersampling, as in sfxr
            s["phase"] += 1
            if s["phase"] >= period:
                s["phase"] %= period
                if wave == 3:
                    s["noise"] = [noise_rng.random() * 2.0 - 1.0 for _ in range(32)]
            fp = s["phase"] / period
            if wave == 0:
                sample = 0.5 if fp < s["square_duty"] else -0.5
            elif wave == 1:
                sample = 1.0 - fp * 2.0
            elif wave == 2:
                sample = math.sin(fp * 2.0 * math.pi)
            else:
                sample = s["noise"][int(s["phase"] * 32 / period) % 32]
            pp = s["fltp"]
            s["fltw"] = min(0.1, max(0.0, s["fltw"] * s["fltw_d"]))
            if p["lpf_freq"] != 1.0:
                s["fltdp"] += (sample - s["fltp"]) * s["fltw"]
                s["fltdp"] -= s["fltdp"] * s["fltdmp"]
            else:
                s["fltp"] = sample
                s["fltdp"] = 0.0
            s["fltp"] += s["fltdp"]
            s["fltphp"] += s["fltp"] - pp
            s["fltphp"] -= s["fltphp"] * s["flthp"]
            sample = s["fltphp"]
            s["phaser"][s["ipp"] & 1023] = sample
            sample += s["phaser"][(s["ipp"] - iphase + 1024) & 1023]
            s["ipp"] = (s["ipp"] + 1) & 1023
            ssample += sample * s["env_vol"]
        ssample = ssample / 8.0 * 0.05 * 2.0 * p["sound_vol"] * 4.0
        out.append(max(-1.0, min(1.0, ssample)))
    return out
