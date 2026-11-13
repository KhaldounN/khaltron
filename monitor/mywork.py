"""Your own list of programs that count as your work (2026-11-13): marked in the Programs tab ("Mark as my work").

Gaming and development mode never freeze or slow them down, and development mode protects everything they start,
like Claude's. This replaces guessing from names and process trees, which needed a patch for each surprise.
Kept in state/my_work.json as program file names ("blender.exe"); read again only when the file changes."""

import os

import psutil

from .config import STATE
from .util import read_json, write_json

FILE = STATE / "my_work.json"
_cache: dict = {"mtime": None, "names": frozenset()}


def names() -> frozenset[str]:
    """The program file names on your list, lower case."""
    try:
        mtime = os.path.getmtime(FILE)
    except OSError:
        return frozenset()
    if mtime != _cache["mtime"]:
        found = read_json(FILE, [])
        _cache.update(mtime=mtime, names=frozenset(str(n).lower() for n in found if isinstance(n, str)))
    return _cache["names"]


def _exes(pids: list[int]) -> set[str]:
    out = set()
    for pid in pids:
        try:
            out.add(psutil.Process(pid).name().lower())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return out


def mark(program: str, pids: list[int], mine: bool) -> str:
    """Add (mine=True) or remove a program, given its processes. Returns a message for the status bar."""
    exes = _exes(pids)
    if not exes:
        return f"{program} isn't running any more: nothing to mark."
    current = set(names())
    current = current | exes if mine else current - exes
    write_json(FILE, sorted(current))
    if mine:
        return (f"{program} is now your work: gaming and development mode leave it (and what it starts) alone. "
                "Undo with 'Not my work'.")
    return f"{program} is no longer on your work list."
