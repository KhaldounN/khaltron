"""Never let a frozen program slow down the keyboard or mouse.

Some programs watch every key press and mouse move (a "low-level hook": hotkey tools, screen recorders, Photoshop
Express's helper). Windows waits for each hook to answer before your key reaches the app; a FROZEN program can't
answer, so every press waits for Windows' timeout (~300 ms, found 2026-11-13: freezing PSExpressBroker.exe made every
key tap take 614 ms instead of 1 ms).

So whenever Khaltron freezes a program it has not checked before, it times one invisible F24 key tap and a
zero-distance mouse move (F24 exists on no keyboard; no app uses it). Slow -> that program is woken at once and
remembered as never-freeze. Fast -> remembered as safe, never checked again. Both lists: state/input_hooks.json."""

import ctypes
import sys
import time
from ctypes import wintypes as w

from .config import CONFIG, STATE
from .util import read_json, write_json

FILE = STATE / "input_hooks.json"
SLOW_MS = 100   # a healthy tap takes ~1-2 ms; a frozen hook adds ~300 ms per key down and up
# known to watch the keyboard: never frozen, even before a check (config "input_hooks" adds names)
KNOWN = {"psexpressbroker.exe"} | {n.lower() for n in CONFIG.get("input_hooks", [])}


class _KI(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MI(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD), ("time", w.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("ki", _KI), ("mi", _MI), ("pad", ctypes.c_byte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _U)]


def probe_ms() -> float:
    """How long Windows takes to accept an F24 tap plus a zero-distance mouse move (ms). Hooks run before it
    returns, so a frozen hook owner shows up here. 0 when not on Windows."""
    if sys.platform != "win32":
        return 0.0
    send = ctypes.windll.user32.SendInput
    events = []
    for flags in (0, 2):  # key down, key up
        item = _INPUT(type=1)
        item.u.ki = _KI(0x87, 0, flags, 0, 0)  # VK_F24
        events.append(item)
    mouse = _INPUT(type=0)
    mouse.u.mi = _MI(0, 0, 0, 0x0001, 0, 0)  # MOUSEEVENTF_MOVE by 0,0
    events.append(mouse)
    start = time.perf_counter()
    for item in events:  # one at a time: each waits for the hooks
        send(1, ctypes.byref(item), ctypes.sizeof(_INPUT))
    return (time.perf_counter() - start) * 1000


def _lists() -> dict:
    found = read_json(FILE, None)
    if not isinstance(found, dict):
        found = {}
    return {"hooks": list(found.get("hooks", [])), "safe": list(found.get("safe", []))}


def never_freeze(name: str) -> bool:
    """True for a program known (or found) to watch the keyboard or mouse."""
    name = name.lower()
    return name in KNOWN or name in _lists()["hooks"]


def checked(name: str) -> bool:
    return name.lower() in _lists()["safe"]


def verdict(name: str, slow_ms: float | None = None) -> bool:
    """Call right after freezing a program not checked before. Times the input; True = fine (keep it frozen),
    False = it watches the input (the caller must wake it now). Remembers the answer by program name."""
    slow = probe_ms() if slow_ms is None else slow_ms
    lists, name = _lists(), name.lower()
    ok = slow < SLOW_MS
    key = "safe" if ok else "hooks"
    if name not in lists[key]:
        lists[key].append(name)
        if not ok and name in lists["safe"]:
            lists["safe"].remove(name)
        try:
            write_json(FILE, lists)
        except OSError:
            pass
    return ok
