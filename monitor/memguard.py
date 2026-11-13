"""The memory guard for running jobs (2026-11-13). The queue's guard (runner.memory_short) only holds back jobs that
haven't started; this one watches the ones already running, whoever started them (the website, the phone, stage 2).

While free RAM is under config "memory_pause_mb" (1 GB): freeze the biggest of your own jobs (Book Analyzer workers,
stage 2, planned jobs; never your work list, Claude's processes or anything else), one per check, and tell you.
Once free RAM is back over "memory_resume_mb" (3 GB): wake them again, one per minute, oldest first, so they don't
all come back at once and fill the memory again. Frozen jobs carry on where they stopped (their status files get a
fresh time first, like after gaming mode). Kept in state/memguard.json. Does nothing while gaming or development
mode is on: those manage freezing themselves. Low memory was there at both of the owner's crashes on 2026-11-13."""

import time

import psutil

from . import gaming, mywork, planned
from .config import CONFIG, STATE
from .util import read_json, write_json

FILE = STATE / "memguard.json"
RESUME_GAP = 60  # seconds between waking two jobs


def _load() -> list[dict]:
    found = read_json(FILE, [])
    return found if isinstance(found, list) else []


def _own_jobs() -> list[psutil.Process]:
    """Your own running jobs: the known job scripts and the planned queue's jobs (with their children)."""
    found: dict[int, psutil.Process] = {}
    for process in psutil.process_iter(["name", "create_time"]):
        name = (process.info.get("name") or "").lower()
        if not name.startswith(("python", "powershell", "pwsh")) or name in mywork.names():
            continue
        cmdline = gaming._cmdline(process)
        if any(n in cmdline for n in gaming.NEVER):
            continue
        if any(needle in cmdline for needle in gaming.JOB_NEEDLES):
            found[process.pid] = process
    for entry in planned.load():
        if entry.get("state") in (planned.RUNNING, planned.STOPPING) and entry.get("pid"):
            try:
                root = psutil.Process(entry["pid"])
                for process in [root] + root.children(recursive=True):
                    if not any(n in gaming._cmdline(process) for n in gaming.NEVER):
                        found[process.pid] = process
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return list(found.values())


def check(free_mb: float | None = None) -> list[tuple[str, str]]:
    """One look (the Job Monitor calls this on each refresh). Returns notifications to show, as (title, message)."""
    if gaming.is_on() or _dev_on():
        return []
    pause_at, resume_at = CONFIG.get("memory_pause_mb", 1024), CONFIG.get("memory_resume_mb", 3072)
    if not pause_at:
        return []
    free = psutil.virtual_memory().available / 2 ** 20 if free_mb is None else free_mb
    held = [item for item in _load() if _alive(item)]
    if free < pause_at:
        mine = {(item["pid"], item["created"]) for item in held}
        candidates = []
        for process in _own_jobs():
            try:
                if (process.pid, process.create_time()) in mine or process.status() == psutil.STATUS_STOPPED:
                    continue
                candidates.append((process.memory_info().rss, process))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if not candidates:
            write_json(FILE, held)
            return []
        size, process = max(candidates, key=lambda c: c[0])
        try:
            created = process.create_time()
            process.suspend()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return []
        gaming._trim(process.pid)
        label = next((lbl for needle, lbl, _ in gaming.KNOWN if needle in gaming._cmdline(process)), "Planned job")
        held.append({"pid": process.pid, "created": created, "label": label, "since": time.time()})
        write_json(FILE, held)
        return [("Memory low: a job is paused", f"{label} ({size / 2 ** 20:.0f} MB) is frozen until "
                 f"{resume_at / 1024:.0f} GB of memory is free again ({free / 1024:.1f} GB now). Nothing is lost.")]
    if held and free > resume_at:
        last = max((item.get("woken", 0) for item in _load()), default=0)
        if time.time() - last < RESUME_GAP:
            return []
        first = min(held, key=lambda item: item["since"])
        gaming.wake_frozen([first])
        rest = [item for item in held if item is not first]
        if rest:
            rest[0]["woken"] = time.time()  # remembers when the last one woke (the gap before the next)
        write_json(FILE, rest)
        return [("Memory is back: a job carries on", f"{first['label']} carries on where it stopped.")]
    if len(held) != len(_load()):
        write_json(FILE, held)  # forget jobs that ended meanwhile
    return []


def release_all() -> int:
    """Wake every job the guard froze (Khaltron quitting, or you asked). Returns how many."""
    held = [item for item in _load() if _alive(item)]
    woken, _ = gaming.wake_frozen(held) if held else (0, 0)
    FILE.unlink(missing_ok=True)
    return woken


def _alive(item: dict) -> bool:
    try:
        return abs(psutil.Process(item["pid"]).create_time() - item["created"]) <= 1
    except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
        return False


def _dev_on() -> bool:
    from . import devmode
    return devmode.is_on()
