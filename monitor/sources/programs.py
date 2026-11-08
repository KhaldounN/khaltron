"""Every program running on this PC, grouped by program (Chrome's 30 processes are one row), with its share of the
whole CPU and its RAM, so you can see where the PC's power goes: your apps and games, your background jobs, and
Windows itself. Read-only: nothing here can be stopped from the window.

How it is measured, the way Task Manager does it: ONE Windows call (NtQuerySystemInformation) returns every
process's CPU time, private memory and session at once. Asking about each process one by one took 4-8 seconds
on ~350 processes; this takes a few milliseconds.
- CPU: the CPU time each process used since the last look, divided by the time passed x the logical processors,
  so 100% = the whole CPU (the first look has nothing to compare with, so it shows 0).
- RAM: the private working set: the RAM only that process holds (Task Manager's "Memory" column).
- Yours or Windows': programs you start run in your login session; Windows services run in session 0."""

import ctypes
import os
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass

# friendly names for common programs (by process name, lower case); anything else shows its own name
FRIENDLY = {
    "chrome.exe": "Google Chrome", "msedge.exe": "Microsoft Edge", "msedgewebview2.exe": "Edge WebView (apps)",
    "firefox.exe": "Firefox", "brave.exe": "Brave", "opera.exe": "Opera", "code.exe": "Visual Studio Code",
    "explorer.exe": "File Explorer", "discord.exe": "Discord", "spotify.exe": "Spotify", "steam.exe": "Steam",
    "steamwebhelper.exe": "Steam", "epicgameslauncher.exe": "Epic Games", "teams.exe": "Microsoft Teams",
    "ms-teams.exe": "Microsoft Teams", "outlook.exe": "Outlook", "winword.exe": "Word", "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint", "onedrive.exe": "OneDrive", "slack.exe": "Slack", "zoom.exe": "Zoom",
    "obs64.exe": "OBS Studio", "python.exe": "Python (incl. your background jobs)",
    "pythonw.exe": "Python (incl. your background jobs)", "node.exe": "Node.js", "claude.exe": "Claude",
    "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell", "windowsterminal.exe": "Windows Terminal",
    "openconsole.exe": "Windows Terminal", "conhost.exe": "Console windows", "taskmgr.exe": "Task Manager",
    "msmpeng.exe": "Microsoft Defender", "tailscaled.exe": "Tailscale", "tailscale-ipn.exe": "Tailscale",
    "searchhost.exe": "Windows Search", "searchindexer.exe": "Windows Search", "dwm.exe": "Windows (desktop)",
    "memory compression": "Windows (memory compression)", "system": "Windows (kernel)",
}
SYSTEM_GROUP = "Windows & services"


@dataclass
class Program:
    name: str
    processes: int
    cpu: float        # percent of the whole CPU
    memory_mb: float  # private working set, added up
    yours: bool       # started in your login session (not a Windows service)
    pids: list[int]


# --- one call for every process (Windows) ---------------------------------------------------------------------
class _UnicodeString(ctypes.Structure):
    _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]


class _ProcessInfo(ctypes.Structure):
    """The start of SYSTEM_PROCESS_INFORMATION (the fields used here; the rest is skipped by NextEntryOffset)."""
    _fields_ = [("NextEntryOffset", wintypes.ULONG), ("NumberOfThreads", wintypes.ULONG),
                ("WorkingSetPrivateSize", ctypes.c_longlong), ("HardFaultCount", wintypes.ULONG),
                ("NumberOfThreadsHighWatermark", wintypes.ULONG), ("CycleTime", ctypes.c_ulonglong),
                ("CreateTime", ctypes.c_longlong), ("UserTime", ctypes.c_longlong),
                ("KernelTime", ctypes.c_longlong), ("ImageName", _UnicodeString), ("BasePriority", ctypes.c_long),
                ("UniqueProcessId", ctypes.c_void_p), ("InheritedFromUniqueProcessId", ctypes.c_void_p),
                ("HandleCount", wintypes.ULONG), ("SessionId", wintypes.ULONG)]


_buffer = ctypes.create_string_buffer(1 << 20)


def snapshot() -> dict[int, tuple[str, int, int, int]]:
    """pid -> (name, cpu time in 100 ns units, private working set in bytes, session)."""
    global _buffer
    query = ctypes.windll.ntdll.NtQuerySystemInformation
    needed = wintypes.ULONG(0)
    while True:
        status = query(5, _buffer, len(_buffer), ctypes.byref(needed)) & 0xFFFFFFFF  # 5: process information
        if status == 0xC0000004:  # the buffer is too small: grow it and ask again
            _buffer = ctypes.create_string_buffer(max(needed.value, len(_buffer)) * 2)
            continue
        if status != 0:
            raise OSError(f"NtQuerySystemInformation failed: {status:#x}")
        break
    found, offset = {}, 0
    while True:
        entry = _ProcessInfo.from_buffer(_buffer, offset)
        pid = entry.UniqueProcessId or 0
        name = (ctypes.wstring_at(entry.ImageName.Buffer, entry.ImageName.Length // 2)
                if entry.ImageName.Buffer and entry.ImageName.Length else "")
        if pid:  # pid 0 is the System Idle Process: not work
            found[pid] = (name, entry.UserTime + entry.KernelTime, entry.WorkingSetPrivateSize, entry.SessionId)
        if not entry.NextEntryOffset:
            return found
        offset += entry.NextEntryOffset


def _my_session() -> int:
    session = wintypes.DWORD(0)
    ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session))
    return session.value


CORES = os.cpu_count() or 1
_last: tuple[float, dict[int, int]] = (0.0, {})  # (when, pid -> cpu time) from the previous look
_session: int | None = None


def read() -> list[Program]:
    """Programs, busiest first (CPU, then RAM). Empty on a system other than Windows."""
    global _last, _session
    if sys.platform != "win32":
        return []
    if _session is None:
        _session = _my_session()
    now = time.perf_counter()
    found = snapshot()
    before_time, before = _last
    elapsed = (now - before_time) * 1e7 * CORES if before_time else 0  # in 100 ns units, all processors
    _last = (now, {pid: cpu for pid, (_, cpu, _, _) in found.items()})

    groups: dict[str, Program] = {}
    for pid, (name, cpu_time, private, session) in found.items():
        used = cpu_time - before.get(pid, cpu_time)
        cpu = max(0.0, used / elapsed * 100) if elapsed else 0.0
        yours = session == _session
        key = name.lower()
        label = FRIENDLY.get(key) or (os.path.splitext(name)[0] if yours and name else SYSTEM_GROUP)
        group = groups.get(label)
        if group is None:
            group = groups[label] = Program(label, 0, 0.0, 0.0, False, [])
        group.processes += 1
        group.cpu += cpu
        group.memory_mb += private / 2 ** 20
        group.yours = group.yours or yours
        group.pids.append(pid)
    return sorted(groups.values(), key=lambda g: (-round(g.cpu, 1), -g.memory_mb))
