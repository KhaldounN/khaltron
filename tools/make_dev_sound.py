"""Makes assets/khaltron-dev-mode.wav: development mode's start-up sound (2026-11-13), built from plain sine waves
so it is ours (no licence). 0.95 s, 44.1 kHz stereo, 16-bit: a power-up whir, a low hum rising 70 -> 440 Hz with a
servo-like flutter. (It first had digital chirps and an "online" chime after it, 2.3 s in all; the owner kept only
the whir, 2026-11-13.)
Run:  .venv\\Scripts\\python.exe tools\\make_dev_sound.py   (change the numbers below and run it again)"""

import array
import math
import wave
from pathlib import Path

RATE = 44100
LENGTH = 0.95
OUT = Path(__file__).resolve().parent.parent / "assets" / "khaltron-dev-mode.wav"

left = [0.0] * int(RATE * LENGTH)
right = [0.0] * int(RATE * LENGTH)


def add(start: float, seconds: float, wave_at, pan: float = 0.0):
    """Mix wave_at(t, k) (t: seconds since this part began, k: 0..1 through it) in at `start`. pan -1 left .. 1 right."""
    first, count = int(start * RATE), int(seconds * RATE)
    gain_l, gain_r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
    for i in range(count):
        if first + i >= len(left):
            break
        value = wave_at(i / RATE, i / count)
        left[first + i] += value * gain_l * 1.41
        right[first + i] += value * gain_r * 1.41


def envelope(k: float, attack: float, release: float) -> float:
    return min(1.0, k / attack if attack else 1.0, (1 - k) / release if release else 1.0)


# 1. the power-up whir: frequency rises on a curve, a little flutter, fading in and out
phase = {"p": 0.0}


def whir(t, k):
    freq = 70 + 370 * (k ** 1.8)
    phase["p"] += 2 * math.pi * freq / RATE
    p = phase["p"]
    tone = .55 * math.sin(p) + .25 * math.sin(2 * p) + .12 * math.sin(3 * p)  # warm, a bit buzzy
    flutter = 1 - .25 * (0.5 + 0.5 * math.sin(2 * math.pi * (14 + 30 * k) * t))
    return .32 * tone * flutter * envelope(k, .25, .2)


add(0.0, 0.95, whir)

# normalise to -1 dBFS and write
peak = max(max(abs(v) for v in left), max(abs(v) for v in right)) or 1.0
scale = 0.89 / peak
frames = array.array("h")
for a, b in zip(left, right):
    frames.append(int(a * scale * 32767))
    frames.append(int(b * scale * 32767))
OUT.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(OUT), "wb") as out:
    out.setnchannels(2)
    out.setsampwidth(2)
    out.setframerate(RATE)
    out.writeframes(frames.tobytes())
print(f"wrote {OUT} ({LENGTH} s)")
