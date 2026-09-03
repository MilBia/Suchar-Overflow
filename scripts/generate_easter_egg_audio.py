#!/usr/bin/env python3
"""Regenerate the self-hosted easter-egg sound effects.

The easter-egg audio helper in ``static/js/features/easter_eggs.js`` plays two
short cues (see issue #282). Rather than vendoring third-party samples and
tracking their licences by hand (as with ``flatpickr.LICENSE.txt``), the sounds
are synthesised here from scratch with the standard library only, so they are
original works the project can release under CC0 — see
``suchar_overflow/static/audio/AUDIO_CREDITS.txt``.

Output is plain 16-bit mono WAV: no external encoder (so this runs anywhere
Python does — the Django image included), and unlike a Vorbis/Opus re-encode it
is byte-deterministic, so a re-run with unchanged parameters leaves ``git diff``
clean. The samples are a fraction of a second each; both files together are well
under 50 kB.

Usage::

    just gen-audio            # or: python scripts/generate_easter_egg_audio.py

Writes ``rimshot.wav`` and ``dust.wav`` into ``suchar_overflow/static/audio/``.
"""

import math
import random
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 22_050
REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = REPO_ROOT / "suchar_overflow" / "static" / "audio"

Samples = list[float]


def _silence(seconds: float) -> Samples:
    return [0.0] * int(seconds * SAMPLE_RATE)


def _mix(base: Samples, overlay: Samples, at_seconds: float) -> None:
    """Add ``overlay`` into ``base`` in place, starting at ``at_seconds``."""
    start = int(at_seconds * SAMPLE_RATE)
    for i, value in enumerate(overlay):
        idx = start + i
        if idx < len(base):
            base[idx] += value


def _tom(freq_start: float, freq_end: float, duration: float, gain: float) -> Samples:
    """A pitched drum hit: a sine that glides down and decays exponentially."""
    n = int(duration * SAMPLE_RATE)
    out: Samples = []
    phase = 0.0
    for i in range(n):
        progress = i / n
        freq = freq_start + (freq_end - freq_start) * progress
        phase += 2 * math.pi * freq / SAMPLE_RATE
        envelope = math.exp(-progress * 5.0)
        out.append(math.sin(phase) * envelope * gain)
    return out


def _cymbal(duration: float, gain: float, rng: random.Random) -> Samples:
    """A 'tss': white noise crudely high-passed (signal minus its running mean)."""
    n = int(duration * SAMPLE_RATE)
    out: Samples = []
    running_mean = 0.0
    for i in range(n):
        white = rng.uniform(-1.0, 1.0)
        running_mean += (white - running_mean) * 0.35
        high_passed = white - running_mean
        envelope = math.exp(-(i / n) * 9.0)
        out.append(high_passed * envelope * gain)
    return out


def _poof(duration: float, gain: float, rng: random.Random) -> Samples:
    """A soft 'dust' puff: noise through a one-pole low-pass whose cutoff falls."""
    n = int(duration * SAMPLE_RATE)
    out: Samples = []
    low = 0.0
    attack = int(0.005 * SAMPLE_RATE)
    for i in range(n):
        progress = i / n
        white = rng.uniform(-1.0, 1.0)
        # Cutoff coefficient slides from fairly open to almost shut.
        coeff = 0.25 * (1.0 - progress) + 0.02
        low += (white - low) * coeff
        envelope = math.exp(-progress * 6.0)
        if i < attack:
            envelope *= i / attack
        out.append(low * envelope * gain)
    return out


def _write_wav(samples: Samples, path: Path) -> None:
    frames = bytearray()
    for value in samples:
        clamped = max(-1.0, min(1.0, math.tanh(value)))
        frames += struct.pack("<h", int(clamped * 32_767))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))


def build_rimshot() -> Samples:
    """'Ba dum tss' — two toms and a cymbal splash."""
    rng = random.Random(0xBAD)  # noqa: S311 - cosmetic seed, not security
    track = _silence(0.62)
    _mix(track, _tom(190.0, 120.0, 0.13, 0.9), at_seconds=0.0)
    _mix(track, _tom(150.0, 95.0, 0.15, 0.9), at_seconds=0.14)
    _mix(track, _cymbal(0.28, 0.5, rng), at_seconds=0.30)
    return track


def build_dust() -> Samples:
    """A short, soft puff of settling dust."""
    rng = random.Random(0xD05)  # noqa: S311 - cosmetic seed, not security
    track = _silence(0.34)
    _mix(track, _poof(0.33, 1.4, rng), at_seconds=0.0)
    return track


def main() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    for name, builder in {"rimshot": build_rimshot, "dust": build_dust}.items():
        path = AUDIO_DIR / f"{name}.wav"
        _write_wav(builder(), path)
        print(f"wrote {path.relative_to(REPO_ROOT)} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
