"""Makes assets/khaltron-dev-mode.wav: development mode's start-up sound (2026-11-13), built from plain sine and
square waves so it is ours (no licence). About 2.3 s, 44.1 kHz stereo, 16-bit:
  0.00-0.95 s  a power-up whir: a low hum rising 70 -> 440 Hz, with a servo-like flutter
  0.70-1.40 s  a run of quick digital chirps, hopping left and right (data, a computer booting)
  1.40-2.30 s  an "online" chime: two rising bell notes (E5, B5)
Run:  .venv\\Scripts\\python.exe tools\\make_dev_sound.py   (change the numbers below and run it again)"""

import array
import math
import random
import wave
from pathlib import Path

RATE = 44100
LENGTH = 2.3
OUT = Path(__file__).resolve().parent.parent / "assets" / "khaltron-dev-mode.wav"
random.seed(9000)  # the same sound every time

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

# 2. digital chirps: short soft-square blips on a pentatonic scale, high, hopping between the ears
SCALE = [1046.5, 1174.7, 1318.5, 1568.0, 1760.0, 2093.0, 2349.3, 2637.0]
for n in range(10):
    freq = random.choice(SCALE)
    start = 0.70 + n * 0.068

    def blip(t, k, f=freq):
        square = sum(math.sin(2 * math.pi * f * h * t) / h for h in (1, 3, 5))  # rounded square: a retro beep
        return .10 * square * envelope(k, .08, .5)

    add(start, 0.05, blip, pan=-.6 if n % 2 else .6)

# 3. the "online" chime: two bell-like notes, each a sine with a quiet octave and a gentle decay
for start, freq in ((1.40, 659.3), (1.58, 987.8)):
    def bell(t, k, f=freq):
        tone = math.sin(2 * math.pi * f * t) + .35 * math.sin(2 * math.pi * 2 * f * t) \
            + .12 * math.sin(2 * math.pi * 3.01 * f * t)
        return .26 * tone * math.exp(-4.2 * t) * min(1.0, t / .004)

    add(start, LENGTH - start, bell)

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
