"""The gaming-mode activation sound (the owner's design: assets/khaltron-gaming-mode.wav, 2.4 s, at 80% volume), and
development mode's start-up sound (assets/khaltron-dev-mode.wav, 2.3 s, made by tools/make_dev_sound.py).

Played with winsound (part of Python on Windows: nothing to install), in the background so the window never waits.
winsound has no volume control and can't play a sound from memory in the background, so the first time a copy at
the chosen volume is written to state/ and that file is played. Config: "gaming_sound" / "dev_sound" (on/off) and
"gaming_sound_volume" / "dev_sound_volume" (0-1)."""

import array
import sys
import wave

from .config import CONFIG, HOME, STATE

SOURCE = HOME / "assets" / "khaltron-gaming-mode.wav"
DEV_SOURCE = HOME / "assets" / "khaltron-dev-mode.wav"


def _at_volume(volume: float, source=SOURCE, name: str = "gaming"):
    """A copy of the sound at this volume (16-bit PCM), made once and kept in state/."""
    target = STATE / f"{name}-sound-{round(volume * 100)}.wav"
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return target
    with wave.open(str(source)) as src:
        params, frames = src.getparams(), src.readframes(src.getnframes())
    if params.sampwidth == 2 and volume < 0.999:
        samples = array.array("h", frames)
        samples = array.array("h", (max(-32768, min(32767, int(v * volume))) for v in samples))
        frames = samples.tobytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as out:
        out.setparams(params)
        out.writeframes(frames)
    return target


def play_gaming() -> bool:
    """Play the activation sound, without waiting for it. False when it is off, missing or not on Windows."""
    return _play(SOURCE, "gaming")


def play_dev() -> bool:
    """Play development mode's start-up sound, without waiting for it."""
    return _play(DEV_SOURCE, "dev")


def _play(source, name: str) -> bool:
    if sys.platform != "win32" or not CONFIG.get(f"{name}_sound", True) or not source.exists():
        return False
    try:
        import winsound
        path = _at_volume(max(0.0, min(1.0, float(CONFIG.get(f"{name}_sound_volume", 0.8)))), source, name)
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        return True
    except (OSError, RuntimeError, wave.Error):
        return False  # a sound is a nicety: never let it stop a mode switching
