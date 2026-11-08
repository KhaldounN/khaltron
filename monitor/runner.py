"""The queue runner: starts the planned jobs one after another. Run as `pythonw -m monitor.runner`.

It is its own small background process (not part of the window), so the queue keeps going when the window is
closed. wake() starts it when there is work; it stops by itself when the queue is empty. Only one runs at a time
(state/runner.lock holds its process number)."""

import os
import sys
import time
from pathlib import Path

from . import planned
from .config import HOME, STATE
from .model import DONE, FAILED, RUNNING, STOPPED, WAITING
from .util import alive, detached

LOCK = STATE / "runner.lock"
CHECK_SECONDS = 10  # how often a waiting job looks again at what it waits for


def python(console: bool = False) -> str:
    """The project's own Python (it has psutil); pythonw has no console window."""
    exe = HOME / ".venv" / "Scripts" / ("python.exe" if console else "pythonw.exe")
    return str(exe) if exe.exists() else sys.executable


def holder() -> int:
    try:
        return int(LOCK.read_text(encoding="utf-8") or 0)
    except (OSError, ValueError):
        return 0


def is_running() -> bool:
    return alive(holder())


def wake() -> None:
    """Start the runner unless one is already running."""
    if is_running() or os.environ.get("JOB_MONITOR_NO_RUNNER"):
        return
    detached([python(), "-m", "monitor.runner"], cwd=HOME, log=STATE / "runner.log", priority="normal")


def _lock() -> bool:
    STATE.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            handle = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(handle, str(os.getpid()).encode())
            os.close(handle)
            return True
        except FileExistsError:
            if is_running():
                return False
            LOCK.unlink(missing_ok=True)  # left by a runner that was ended
    return False


def command_for(entry: dict) -> list[str]:
    """A .ps1 script is run by PowerShell; anything else as it is."""
    command = list(entry["command"])
    # a relative program (".venv\Scripts\python.exe") means the one in the job's folder: on Windows, Popen
    # does not look for it there by itself
    if command and entry.get("cwd") and not Path(command[0]).is_absolute() and (Path(entry["cwd"]) / command[0]).exists():
        command[0] = str(Path(entry["cwd"]) / command[0])
    if command and command[0].lower().endswith(".ps1"):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", *command]
    return command


def run(entry: dict) -> None:
    log = Path(entry["log"])
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')}  {entry['name']}\n"
                     f"    {' '.join(command_for(entry))}\n    in {entry['cwd']}\n\n")
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    try:
        process = detached(command_for(entry), cwd=Path(entry["cwd"]), log=log, env=env,
                           priority=entry.get("priority") or "below")
    except OSError as error:
        planned.update(entry["id"], state=FAILED, finished=time.time(), step=f"could not start: {error}")
        return
    planned.update(entry["id"], state=RUNNING, pid=process.pid, started=time.time(), step="")
    code = process.wait()
    with planned.edit() as entries:
        now = next((e for e in entries if e["id"] == entry["id"]), None)
        if now is not None:
            stopped = now.get("state") == planned.STOPPING
            now.update(state=STOPPED if stopped else DONE if code == 0 else FAILED, finished=time.time(),
                       exit_code=code, step="")
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')}  finished, exit code {code}\n")


def adopt(entry: dict) -> None:
    """A job left running by an earlier runner (it was ended, or the PC logged off): wait for it to end."""
    while alive(entry.get("pid")):
        time.sleep(2)
    with planned.edit() as entries:
        now = next((e for e in entries if e["id"] == entry["id"]), {})
        if now.get("state") in (RUNNING, planned.STOPPING):
            now.update(state=STOPPED if now["state"] == planned.STOPPING else DONE, finished=time.time(),
                       step="exit code unknown (the runner was restarted while it ran)")


def main() -> None:
    if not _lock():
        return
    try:
        while True:
            with planned.edit() as entries:
                planned.check_tracked(entries)
                orphan = next((e for e in entries if e.get("managed")
                               and e.get("state") in (RUNNING, planned.STOPPING)), None)
            if orphan:
                adopt(orphan)
                continue
            if planned.queue_paused():
                if not any(e.get("managed") and e.get("state") == WAITING for e in planned.load()):
                    return
                time.sleep(5)
                continue
            entries = planned.load()
            nxt = next((e for e in entries if e.get("managed") and e.get("state") == WAITING), None)
            if nxt is None:
                return
            reason = planned.blocked_by(nxt, entries)
            if reason:
                if nxt.get("step") != reason:
                    planned.update(nxt["id"], step=reason)
                time.sleep(CHECK_SECONDS)
                continue
            run(nxt)
    finally:
        if holder() == os.getpid():
            LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
