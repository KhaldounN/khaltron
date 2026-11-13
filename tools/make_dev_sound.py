"""Makes assets/khaltron-dev-mode.wav: development mode's start-up sound (2026-11-13), built from plain sine and
square waves so it is ours (no licence). 44.1 kHz stereo, 16-bit. Three parts, each can be switched on or off:
  "hum"    0.95 s  a power-up whir: a low hum rising 70 -> 440 Hz, with a servo-like flutter
  "chirps" 0.70 s  a run of quick digital chirps, hopping left and right (data, a computer booting)
  "chime"  0.90 s  an "online" chime: two rising bell notes (E5, B5)
The parts that are on play one after another (the chirps overlap the hum's fade by 0.25 s, as in the first version).
History: first all three (2.3 s); then only the hum; then the owner chose the second part (see PARTS).
Run:  .venv\\Scripts\\python.exe tools\\make_dev_sound.py [parts...] [--out file.wav]"""

import array
import math
import random
import sys
import wave
from pathlib import Path

RATE = 44100
PARTS = ["chirps"]  # the owner's choice (2026-11-13); any of "hum", "chirps", "chime", in this order
OUT = Path(__file__).resolve().parent.parent / "assets" / "khaltron-dev-mode.wav"
LENGTHS = {"hum": 0.95, "chirps": 0.75, "chime": 0.90}


def envelope(k: float, attack: float, release: float) -> float:
    return min(1.0, k / attack if attack else 1.0, (1 - k) / release if release else 1.0)


def make(parts: list[str], out: Path) -> float:
    random.seed(9000)  # the same chirps every time
    # where each part starts: one after another, the chirps over the hum's last 0.25 s
    starts, t = {}, 0.0
    for part in [p for p in ("hum", "chirps", "chime") if p in parts]:
        if part == "chirps" and "hum" in starts:
            t -= 0.25
        starts[part] = t
        t += LENGTHS[part]
    length = t + 0.05
    left = [0.0] * int(RATE * length)
    right = [0.0] * int(RATE * length)

    def add(start, seconds, wave_at, pan=0.0):
        first, count = int(start * RATE), int(seconds * RATE)
        gain_l, gain_r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        for i in range(count):
            if first + i >= len(left):
                break
            value = wave_at(i / RATE, i / count)
            left[first + i] += value * gain_l * 1.41
            right[first + i] += value * gain_r * 1.41

    if "hum" in starts:  # frequency rises on a curve, a little flutter, fading in and out
        phase = {"p": 0.0}

        def whir(t, k):
            freq = 70 + 370 * (k ** 1.8)
            phase["p"] += 2 * math.pi * freq / RATE
            p = phase["p"]
            tone = .55 * math.sin(p) + .25 * math.sin(2 * p) + .12 * math.sin(3 * p)
            flutter = 1 - .25 * (0.5 + 0.5 * math.sin(2 * math.pi * (14 + 30 * k) * t))
            return .32 * tone * flutter * envelope(k, .25, .2)

        add(starts["hum"], 0.95, whir)

    if "chirps" in starts:  # short soft-square blips on a pentatonic scale, hopping between the ears
        scale = [1046.5, 1174.7, 1318.5, 1568.0, 1760.0, 2093.0, 2349.3, 2637.0]
        for n in range(10):
            freq = random.choice(scale)

            def blip(t, k, f=freq):
                square = sum(math.sin(2 * math.pi * f * h * t) / h for h in (1, 3, 5))
                return .10 * square * envelope(k, .08, .5)

            add(starts["chirps"] + n * 0.068, 0.05, blip, pan=-.6 if n % 2 else .6)

    if "chime" in starts:  # two bell-like notes, each a sine with a quiet octave and a gentle decay
        for offset, freq in ((0.0, 659.3), (0.18, 987.8)):
            def bell(t, k, f=freq):
                tone = math.sin(2 * math.pi * f * t) + .35 * math.sin(2 * math.pi * 2 * f * t) \
                    + .12 * math.sin(2 * math.pi * 3.01 * f * t)
                return .26 * tone * math.exp(-4.2 * t) * min(1.0, t / .004)

            add(starts["chime"] + offset, length - starts["chime"] - offset, bell)

    peak = max(max(abs(v) for v in left), max(abs(v) for v in right)) or 1.0
    scale = 0.89 / peak  # normalise to -1 dBFS
    frames = array.array("h")
    for a, b in zip(left, right):
        frames.append(int(a * scale * 32767))
        frames.append(int(b * scale * 32767))
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(frames.tobytes())
    return length


if __name__ == "__main__":
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else OUT
    parts = [a for a in args if a in LENGTHS] or PARTS
    print(f"wrote {out} ({make(parts, out):.2f} s: {' + '.join(parts)})")
