"""Pause, resume, close or end any of YOUR programs from the Programs-on-this-PC tab (every action asks first).

Never allowed (the buttons stay greyed out):
- anything that is part of Windows (its program lives in the Windows folder: Explorer, the desktop, sign-in, ...):
  freezing one of those can hang the whole PC;
- Windows services and other users' programs (not in your session), and whatever Windows won't let us open;
- Claude and the terminals it runs in (Khaltron might be talking to you through one of them);
- Khaltron's protected programs (itself, its runner, the voice server, the Book Analyzer website).

Paused programs are remembered in state/paused_apps.json, so they can be resumed even after Khaltron restarts.
Pausing stacks with gaming mode (Windows counts suspends): a program you paused stays paused when gaming mode ends."""

import os
import subprocess
import time
from dataclasses import dataclass, field

import psutil

from . import protect
from .config import STATE
from .util import NO_WINDOW, read_json, write_json

PAUSED = STATE / "paused_apps.json"
WINDOWS_DIR = os.path.normcase(os.environ.get("SystemRoot", r"C:\Windows")) + os.sep
NEVER_REASONS = {
    "claude.exe": "Claude (it may be running this very conversation)",
    "windowsterminal.exe": "the terminal Claude may be running in", "openconsole.exe": "a terminal",
    "conhost.exe": "a terminal", "wt.exe": "a terminal", "code.exe": "the editor Claude may run in",
    "bash.exe": "the shell Claude runs commands in", "sh.exe": "the shell Claude runs commands in",
    "mintty.exe": "a terminal", "msmpeng.exe": "your antivirus", "microsoftsecurityapp.exe": "your antivirus",
    "defendersessionhelper.exe": "your antivirus", "securityhealthsystray.exe": "your antivirus",
    "tailscaled.exe": "your network (Tailscale)", "tailscale-ipn.exe": "your network (Tailscale)",
    "nvcontainer.exe": "the graphics driver", "nvdisplay.container.exe": "the graphics driver",
    "gameinputredistservice.exe": "game controller support", "audiodg.exe": "your sound",
}
NEVER_NAMES = set(NEVER_REASONS)


@dataclass
class Control:
    """What may be done to one program (a group of processes): its pids that may be touched, why not otherwise,
    and which of its processes are paused by you."""
    allowed: list[int] = field(default_factory=list)
    reason: str = ""
    paused: list[int] = field(default_factory=list)


_exe_cache: dict[tuple[int, float], str] = {}


def _exe(pid: int, started: float) -> str:
    key = (pid, started)
    if key not in _exe_cache:
        try:
            _exe_cache[key] = os.path.normcase(psutil.Process(pid).exe())
        except (psutil.Error, OSError):
            _exe_cache[key] = ""
    return _exe_cache[key]


def _blocked(pid: int, sample, mine: int) -> str | None:
    """Why this one process may not be touched (None = it may)."""
    name = (sample.name or "").lower()
    if pid == os.getpid() or pid in (0, 4) or sample.session != mine:
        return "part of Windows or a service"
    if name in NEVER_NAMES:
        return NEVER_REASONS[name]
    exe = _exe(pid, sample.started)
    if not exe:
        return "Windows doesn't allow it"
    if exe.startswith(WINDOWS_DIR):
        return "part of Windows"
    return None


def paused_list() -> list[dict]:
    found = read_json(PAUSED, [])
    return found if isinstance(found, list) else []


def controls(programs: list, samples: dict, mine: int) -> dict[str, Control]:
    """Program name -> Control, for the Programs tab (called in the background, once per refresh)."""
    live = {(pid, s.started) for pid, s in samples.items()}
    paused = {item["pid"] for item in paused_list() if (item["pid"], item["created"]) in live}
    out = {}
    for program in programs:
        control = Control()
        reasons = []
        for pid in program.pids:
            sample = samples.get(pid)
            if sample is None:
                continue
            why = _blocked(pid, sample, mine)
            if why:
                reasons.append(why)
            else:
                control.allowed.append(pid)
            if pid in paused:
                control.paused.append(pid)
        if not control.allowed:
            control.reason = reasons[0] if reasons else "no process to act on"
        out[program.name] = control
    # forget programs that ended (keeps the cache and the paused list small)
    global _exe_cache
    if len(_exe_cache) > 4 * max(1, len(live)):
        _exe_cache = {k: v for k, v in _exe_cache.items() if k in live}
    return out


def _processes(pids: list[int]) -> list[psutil.Process]:
    """The processes, checked again right now (protected ones are left out)."""
    found = []
    for pid in pids:
        if protect.why_protected(pid):
            continue
        try:
            found.append(psutil.Process(pid))
        except psutil.NoSuchProcess:
            pass
    return found


def pause(name: str, pids: list[int]) -> str:
    from . import inputguard
    from .gaming import _trim
    paused = [p for p in paused_list() if psutil.pid_exists(p["pid"])]
    known = {(p["pid"], p["created"]) for p in paused}
    done, watches_input = 0, []
    for process in _processes(pids):
        try:
            created = process.create_time()
            exe = process.name()
            if (process.pid, created) in known:
                continue
            if inputguard.never_freeze(exe):
                watches_input.append(exe)
                continue
            process.suspend()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if not inputguard.checked(exe) and not inputguard.verdict(exe):
            try:  # paused, the keyboard/mouse got slow: wake it now (it watches every key press)
                process.resume()
            except psutil.NoSuchProcess:
                pass
            watches_input.append(exe)
            continue
        _trim(process.pid)
        paused.append({"pid": process.pid, "created": created, "program": name, "since": time.time()})
        done += 1
    write_json(PAUSED, paused)
    if not done and watches_input:
        return (f"Not paused: {name} watches the keyboard and mouse ({', '.join(sorted(set(watches_input)))}); "
                "paused, every key press would lag.")
    if not done:
        return f"Nothing paused: Windows didn't allow pausing {name}."
    return f"Paused {name} ({done} process{'es' if done != 1 else ''}). Resume it from the same tab."


def resume(name: str) -> str:
    keep, done = [], 0
    for item in paused_list():
        if item.get("program") != name:
            keep.append(item)
            continue
        try:
            process = psutil.Process(item["pid"])
            if abs(process.create_time() - item["created"]) <= 1:  # the same program, not a reused number
                process.resume()
                done += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    write_json(PAUSED, keep)
    return f"Resumed {name}." if done else f"{name} wasn't paused any more (it may have closed)."


def close(name: str, pids: list[int]) -> str:
    """Ask politely, like clicking its X: the program can save or ask about unsaved work."""
    for process in _processes(pids):
        subprocess.run(["taskkill", "/PID", str(process.pid)], capture_output=True, creationflags=NO_WINDOW)
    return f"Asked {name} to close (it may ask you to save first)."


def end(name: str, pids: list[int]) -> str:
    """End now, like Task Manager's End task: unsaved work is lost."""
    resume(name)  # a paused process can't end cleanly
    ended = 0
    for process in _processes(pids):
        result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                                creationflags=NO_WINDOW)
        ended += result.returncode == 0
    return f"Ended {name}." if ended else f"{name} had already closed."
