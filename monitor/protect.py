"""Processes the monitor must never stop: the read-aloud voice server, the Book Analyzer website (and its
watchdog), and the monitor itself. Checked again right before every stop, on the process AND all its children."""

import os
import subprocess

import psutil

from .sources.processes import KNOWN
from .util import NO_WINDOW

NEVER = [needle for needle, _, protected in KNOWN if protected]


class Protected(Exception):
    pass


def why_protected(pid: int) -> str | None:
    """The reason this process (or one of its children) may not be stopped, or None."""
    if pid in (os.getpid(), os.getppid(), 0, 4):
        return "it is Khaltron 9000 itself (or Windows)"
    try:
        process = psutil.Process(pid)
        family = [process] + process.children(recursive=True)
    except psutil.NoSuchProcess:
        return None
    except psutil.AccessDenied:
        return "Windows does not allow it (a system process)"
    for member in family:
        try:
            cmdline = " ".join(member.cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        for needle, label, protected in KNOWN:
            if protected and needle in cmdline:
                return f"it is (or runs) the {label}, which is protected"
    return None


def stop_tree(pid: int) -> None:
    """End a process and everything it started (refused for protected ones)."""
    reason = why_protected(pid)
    if reason:
        raise Protected(f"Not stopped: {reason}.")
    if not psutil.pid_exists(pid):
        return
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
