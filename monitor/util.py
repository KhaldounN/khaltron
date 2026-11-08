"""Small helpers shared by the sources, the runner and the actions."""

import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def read_json(path: Path, default):
    """A JSON file's contents, or `default` when it is missing, half-written or locked."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, value) -> None:
    """Written whole to a temporary file, then moved into place, so a reader never sees half a file.
    Retried, because Windows briefly locks files (antivirus, indexer, another reader)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=1), encoding="utf-8")
    for attempt in range(12):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            time.sleep(0.1 * (attempt + 1))
    temporary.unlink(missing_ok=True)
    raise PermissionError(f"could not write {path}")


def alive(pid: int | None) -> bool:
    """Is this process still running? (On Windows os.kill(pid, 0) would END it, so ask Windows instead.)"""
    if not pid:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def tail(path: Path, lines: int = 8) -> list[str]:
    """The last lines of a (possibly big) log file."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 16_000))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    return [line.rstrip() for line in text.splitlines() if line.strip()][-lines:]


def detached(command: list[str], cwd: Path, log: Path | None = None, env: dict | None = None,
             priority: str = "below") -> subprocess.Popen:
    """Start a program with no window, in its own process group, so it keeps running when whoever started it
    (the window, a Claude session) closes. Below-normal priority by default: the PC stays quick."""
    flags = 0
    if sys.platform == "win32":
        flags = NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | (
            subprocess.NORMAL_PRIORITY_CLASS if priority == "normal" else subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    output = open(log, "a", encoding="utf-8") if log else subprocess.DEVNULL
    try:
        return subprocess.Popen(command, cwd=str(cwd), env=env, stdout=output, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=flags)
    finally:
        if log:
            output.close()


def duration(seconds: float | None) -> str:
    """'45 s', '12 min', '2 h 05 min'."""
    if seconds is None:
        return ""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


def when(stamp: float | None) -> str:
    """A time as '14:05' today, or 'Sat 14:05' on another day."""
    if not stamp:
        return ""
    local = time.localtime(stamp)
    if time.strftime("%Y-%m-%d", local) == time.strftime("%Y-%m-%d"):
        return time.strftime("%H:%M", local)
    return time.strftime("%a %H:%M", local)
