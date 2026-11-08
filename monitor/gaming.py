"""Gaming mode: hands the PC's CPU and memory back to you while you play.

ON:  pauses the planned queue, FREEZES (suspends) every running background job - book analyses, stage 2, the
     library pre-analysis, planned jobs - so they use no CPU and Windows can move their memory to the page file,
     stops the read-aloud voice server (and keeps it from starting again), and sets Windows' power mode to
     "Best performance". Everything it changed is written to ~/.claude/gaming.json.
OFF: reads that file and undoes exactly those changes, then deletes it. Frozen jobs carry on where they were.

The file existing IS the switch: the status line, the voice scripts and the Claude hooks only check whether it is
there. The website (and its watchdog), the Job Monitor and its runner are never touched, and neither are your own
programs. While gaming mode is on, the Job Monitor calls enforce() on every refresh, so a job that starts anyway
(say, a book analysis started from the phone) is frozen too.

Run:  python -m monitor.gaming on | off | toggle | status"""

import ctypes
import os
import socket
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import psutil

from . import planned
from .config import BOOK, STATE
from .sources.processes import KNOWN
from .util import NO_WINDOW, read_json, write_json

FLAG = Path.home() / ".claude" / "gaming.json"
LOCK = STATE / "gaming.lock"
JOB_NEEDLES = [needle for needle, _, protected in KNOWN if not protected]  # analyzer.worker, second_stage, ...
NEVER = [needle for needle, _, protected in KNOWN if protected]          # website, monitor, runner, voice
WORKERS = ["analyzer.worker", "analyzer.second_stage"]  # write the status files the others read
VOICE = "piper_server"
BEST_PERFORMANCE = "ded574b5-45a0-4f42-8737-46345c09c238"
POWER_MODES = {BEST_PERFORMANCE: "Best performance", "00000000-0000-0000-0000-000000000000": "Balanced",
               "961cc777-2547-4f9d-8174-7d86181b8a7a": "Best power efficiency"}


def is_on() -> bool:
    return FLAG.exists()


# --- Windows power mode (the slider in Settings > System > Power) ------------------------------------------------
class _GUID(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]


def power_mode() -> str | None:
    """The power mode chosen now, as a GUID string (None if Windows won't say)."""
    guid = _GUID()
    try:
        if ctypes.windll.powrprof.PowerGetActualOverlayScheme(ctypes.byref(guid)) != 0:
            return None
    except (AttributeError, OSError):
        return None
    return str(uuid.UUID(bytes_le=bytes(guid.bytes)))


def set_power_mode(mode: str) -> bool:
    guid = _GUID((ctypes.c_ubyte * 16)(*uuid.UUID(mode).bytes_le))
    try:
        return ctypes.windll.powrprof.PowerSetActiveOverlayScheme(guid) == 0
    except (AttributeError, OSError):
        return False


# --- finding and freezing jobs -------------------------------------------------------------------------------------
def _cmdline(process: psutil.Process) -> str:
    try:
        return " ".join(process.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def _job_processes() -> list[psutil.Process]:
    """Every background-job process: known job scripts, plus whatever planned jobs are running (and children)."""
    found: dict[int, psutil.Process] = {}
    for process in psutil.process_iter(["name"]):
        name = (process.info.get("name") or "").lower()
        if not name.startswith(("python", "powershell", "pwsh")):
            continue
        cmdline = _cmdline(process)
        if any(needle in cmdline for needle in JOB_NEEDLES) and not any(n in cmdline for n in NEVER):
            found[process.pid] = process
    for entry in planned.load():
        if entry.get("state") in (planned.RUNNING, planned.STOPPING) and entry.get("pid"):
            try:
                root = psutil.Process(entry["pid"])
                for process in [root] + root.children(recursive=True):
                    if not any(n in _cmdline(process) for n in NEVER):
                        found[process.pid] = process
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return list(found.values())


def _trim(pid: int) -> None:
    """Ask Windows to move a frozen process's memory out of RAM now (to the page file), instead of slowly."""
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x0400 | 0x0100, False, pid)  # PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA
    if handle:
        try:
            ctypes.windll.psapi.EmptyWorkingSet(handle)
        finally:
            kernel.CloseHandle(handle)


def _freeze_new(state: dict) -> list[str]:
    """Suspend job processes not frozen yet; record them in `state`. Returns their descriptions."""
    known = {(p["pid"], p["created"]) for p in state["frozen"]}
    out = []
    for process in _job_processes():
        try:
            created = process.create_time()
            if (process.pid, created) in known:
                continue
            memory = process.memory_info().rss / 2 ** 20
            process.suspend()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        _trim(process.pid)
        cmdline = _cmdline(process)
        label = next((lbl for needle, lbl, _ in KNOWN if needle in cmdline), "Planned job")
        state["frozen"].append({"pid": process.pid, "created": created, "label": label})
        out.append(f"{label} (process {process.pid}, {memory:.0f} MB)")
    return out


def _resume(processes: list[psutil.Process]) -> int:
    done = 0
    for process in processes:
        try:
            process.resume()
            done += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return done


def _refresh_status(pids: set[int]) -> None:
    """Set 'updated' to now in the Book Analyzer status files of these (frozen) workers."""
    jobs = BOOK / "results" / "jobs"
    files = list(jobs.glob("*.json")) + [jobs / "second_stage" / "status.json"] if jobs.exists() else []
    for path in files:
        found = read_json(path, None)
        if isinstance(found, dict) and found.get("state") == "running" and found.get("pid") in pids:
            found["updated"] = time.time()
            try:
                write_json(path, found)
            except OSError:
                pass


# --- the voice server ----------------------------------------------------------------------------------------------
def _stop_voice() -> bool:
    try:  # first say "stop" so it doesn't cut off mid-word with a click
        with socket.create_connection(("127.0.0.1", 59125), timeout=0.5) as client:
            client.sendall(b'{"cmd": "stop"}\n')
    except OSError:
        pass
    stopped = False
    for process in psutil.process_iter(["name"]):
        if (process.info.get("name") or "").lower().startswith("python") and VOICE in _cmdline(process):
            try:
                process.kill()
                stopped = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return stopped


# --- the switch ----------------------------------------------------------------------------------------------------
def free_memory_gb() -> float:
    return psutil.virtual_memory().available / 2 ** 30


def _turn_on() -> str:
    if is_on():
        return "Gaming mode is already ON.\n" + status()
    before = free_memory_gb()
    state = {"since": time.time(), "frozen": [], "queue_was_paused": planned.queue_paused(), "power_before": None}
    # the flag goes first, so the voice can't start again and the monitor freezes any job that starts meanwhile
    write_json(FLAG, state)
    lines = ["Gaming mode ON."]
    if not state["queue_was_paused"]:
        planned.pause_queue(True)
        lines.append("- Planned queue paused (no new job starts).")
    frozen = _freeze_new(state)
    lines += [f"- Frozen: {f}" for f in frozen] or ["- No background job was running."]
    if _stop_voice():
        lines.append("- Voice server stopped (read-aloud is off until gaming mode ends).")
    mode = power_mode()
    if mode and mode != BEST_PERFORMANCE and set_power_mode(BEST_PERFORMANCE):
        state["power_before"] = mode
        lines.append(f"- Power mode: {POWER_MODES.get(mode, mode)} -> Best performance.")
    elif mode == BEST_PERFORMANCE:
        lines.append("- Power mode was already Best performance.")
    write_json(FLAG, state)
    time.sleep(1)  # let Windows hand the trimmed memory back before measuring
    lines.append(f"Free memory: {before:.1f} GB -> {free_memory_gb():.1f} GB. Have fun!")
    return "\n".join(lines)


def _turn_off() -> str:
    if not is_on():
        return "Gaming mode is already OFF."
    state = read_json(FLAG, {}) or {}
    lines = ["Gaming mode OFF."]
    alive, gone = [], 0
    for item in state.get("frozen", []):
        try:
            process = psutil.Process(item["pid"])
            if abs(process.create_time() - item["created"]) > 1:  # the number now belongs to another program
                raise psutil.NoSuchProcess(item["pid"])
            alive.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            gone += 1
    # The Book Analyzer calls a job that hasn't reported for 15 min "crashed". While everything is still frozen,
    # give the frozen workers' status files a fresh time; then wake the workers first and their parents (the
    # library job, which reads those files) a moment later, once the workers have reported again.
    _refresh_status({p.pid for p in alive})
    workers = [p for p in alive if any(n in _cmdline(p) for n in WORKERS)]
    resumed = _resume(workers)
    if workers and len(workers) < len(alive):
        time.sleep(3)
    resumed += _resume([p for p in alive if p not in workers])
    if resumed:
        lines.append(f"- {resumed} frozen job process(es) carry on where they stopped.")
    if gone:
        lines.append(f"- {gone} frozen process(es) were gone (e.g. after a restart); start those jobs again if needed.")
    if not state.get("queue_was_paused"):
        planned.pause_queue(False)
        try:
            from . import runner
            runner.wake()
        except Exception:  # noqa: BLE001 - the runner starts by itself with the next job anyway
            pass
        lines.append("- Planned queue resumed.")
    if state.get("power_before") and set_power_mode(state["power_before"]):
        lines.append(f"- Power mode back to {POWER_MODES.get(state['power_before'], state['power_before'])}.")
    FLAG.unlink(missing_ok=True)
    lines.append("- Read-aloud is allowed again (the voice loads with the next reply).")
    if state.get("since"):
        lines.append(f"Gaming mode was on for {(time.time() - state['since']) / 60:.0f} min.")
    return "\n".join(lines)


def toggle() -> str:
    with _locked() as got:
        if not got:
            return "Gaming mode is busy switching; try again in a moment."
        return _turn_off() if is_on() else _turn_on()


def turn_on() -> str:
    with _locked() as got:
        return _turn_on() if got else "Gaming mode is busy switching; try again in a moment."


def turn_off() -> str:
    with _locked() as got:
        return _turn_off() if got else "Gaming mode is busy switching; try again in a moment."


@contextmanager
def _locked(wait: float = 30):
    """One switch at a time (the hotkey, Claude, the tray and the monitor's enforce() may overlap).
    Yields False if it couldn't get the lock within `wait` seconds."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + wait
    got = False
    while True:
        try:
            os.close(os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            got = True
            break
        except FileExistsError:
            try:  # left behind by a program that was ended mid-switch
                if time.time() - LOCK.stat().st_mtime > 120:
                    LOCK.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.time() >= deadline:
                break
            time.sleep(0.1)
    try:
        yield got
    finally:
        if got:
            LOCK.unlink(missing_ok=True)


def enforce() -> list[str]:
    """While gaming mode is on: freeze jobs that started since. Called by the Job Monitor on every refresh
    (it skips a round rather than wait while a switch is happening)."""
    if not is_on():
        return []
    with _locked(wait=0) as got:
        state = read_json(FLAG, None) if got and is_on() else None
        if not isinstance(state, dict):
            return []
        state.setdefault("frozen", [])
        frozen = _freeze_new(state)
        if frozen:
            write_json(FLAG, state)
        return frozen


def status() -> str:
    mode = power_mode()
    lines = [f"Gaming mode is {'ON' if is_on() else 'OFF'}.", f"Free memory: {free_memory_gb():.1f} GB.",
             f"Power mode: {POWER_MODES.get(mode, mode) if mode else 'unknown'}."]
    if is_on():
        state = read_json(FLAG, {}) or {}
        lines.insert(1, f"On since {time.strftime('%H:%M', time.localtime(state.get('since', time.time())))}; "
                        f"{len(state.get('frozen', []))} job process(es) frozen.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    command = (argv[0] if argv else "status").lower()
    actions = {"on": turn_on, "off": turn_off, "toggle": toggle, "status": status}
    if command not in actions:
        print("Use: gaming on | off | toggle | status")
        return 2
    print(actions[command]())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
