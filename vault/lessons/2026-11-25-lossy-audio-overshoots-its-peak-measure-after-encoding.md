---
title: Lossy audio overshoots its peak: measure after encoding
date: 2026-11-25
game: super-gamedev-agent
engine: any
kind: technique
tags: [audio, ogg, mp3, loudness]
skills: [audio-design, make-assets]
status: active
---

A square-wave SFX levelled to -1 dBFS came back at 0 dBFS with clipped samples after Vorbis (libvorbis on Linux) and MP3 (LAME) encoding. Evidence: asset-forge CI failure; reproduced locally with LAME.

Next time: encode, decode, measure the real peak, and lower the gain by the overshoot (repeat until it fits). Never trust the pre-encode peak for a lossy file.
