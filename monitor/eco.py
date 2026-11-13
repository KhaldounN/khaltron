"""Efficiency mode for background apps (2026-11-13): Windows 11's own "efficiency mode", the green leaf in Task
Manager. The program keeps running, only slowly: Windows' power throttling ("EcoQoS": it runs on the slowest,
most frugal settings) plus the lowest ("idle") priority, and its memory is handed back to Windows.

Gaming and development mode use this for background apps (OneDrive, Plex, Widgets, Phone Link, Adobe sync...)
instead of freezing them: a frozen app can't answer anyone, so its network connections time out and whatever it
holds (files, a keyboard hook) waits. Your own jobs (the Book Analyzer, planned jobs) are still frozen.
Off: power throttling back to Windows' choice, and the priority it had (unless someone changed it meanwhile)."""

import ctypes
import sys
from ctypes import wintypes

import psutil

IDLE = 0x40
_POWER_THROTTLING = 4               # ProcessPowerThrottling
_EXECUTION_SPEED = 0x1              # PROCESS_POWER_THROTTLING_EXECUTION_SPEED
_ACCESS = 0x0200 | 0x1000           # PROCESS_SET_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION


class _Throttle(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]


def _throttle(pid: int, on: bool) -> bool:
    if sys.platform != "win32":
        return False
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(_ACCESS, False, pid)
    if not handle:
        return False
    try:
        # on: throttle execution speed; off: no rule at all (Windows decides again, as before)
        state = _Throttle(1, _EXECUTION_SPEED if on else 0, _EXECUTION_SPEED if on else 0)
        return bool(kernel.SetProcessInformation(handle, _POWER_THROTTLING, ctypes.byref(state), ctypes.sizeof(state)))
    finally:
        kernel.CloseHandle(handle)


def slow_down(process: psutil.Process) -> int | None:
    """Put one process in efficiency mode. Returns its priority before (to put back), or None if Windows refused."""
    try:
        before = int(process.nice())
        if not _throttle(process.pid, True):
            return None
        process.nice(IDLE)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None
    return before


def restore(items: list[dict]) -> int:
    """Take processes (recorded as pid, created, before) out of efficiency mode. Returns how many."""
    done = 0
    for item in items:
        try:
            process = psutil.Process(item["pid"])
            if abs(process.create_time() - item["created"]) > 1:  # the number now belongs to another program
                continue
            _throttle(process.pid, False)
            if int(process.nice()) == IDLE:  # not changed by someone else meanwhile
                process.nice(item.get("before", 0x20))
            done += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass
    return done
