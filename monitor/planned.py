"""The planned-jobs list: jobs Claude (or you, or a script) lines up to run one after another.

state/planned.json is a list of entries, in queue order:
  {id, name, command, cwd, waits_for, log, priority, managed, state, step, pid, added, started, finished, exit_code}

- managed jobs (`jobq add`) are started by the runner (monitor/runner.py), one at a time, in list order, each when
  what it `waits_for` is over.
- tracked jobs (`jobq begin`) are scripts that run themselves and only report here (begin, running, finish), so
  an existing chain script shows up without changing how it runs.

Every change goes through edit(), which holds a small lock file, so the window, the runner and jobq never
overwrite each other's changes."""

import os
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

from .config import BOOK, STATE
from .model import DONE, FAILED, RUNNING, STOPPED, WAITING
from .util import alive, read_json, tail, write_json

FILE = STATE / "planned.json"
LOCK = STATE / "planned.lock"
PAUSED_FLAG = STATE / "queue_paused"
LOGS = STATE / "logs"
KEEP_FINISHED = 30
STOPPING = "stopping"  # the window asked for a stop: the runner records it as stopped, not failed
# what a job can wait for (besides "job:<id>" and "pid:<number>")
WAITS = {
    "library": "the library pre-analysis",
    "stage2": "stage 2 (deeper analysis)",
    "main": "the book analysis running now",
}


@contextmanager
def _locked():
    STATE.mkdir(parents=True, exist_ok=True)
    for attempt in range(100):
        try:
            handle = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(handle)
            break
        except FileExistsError:
            try:  # left behind by a program that was ended mid-edit: take it over after 10 s
                if time.time() - LOCK.stat().st_mtime > 10:
                    LOCK.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            time.sleep(0.05)
    try:
        yield
    finally:
        LOCK.unlink(missing_ok=True)


def load() -> list[dict]:
    found = read_json(FILE, [])
    return found if isinstance(found, list) else []


@contextmanager
def edit():
    """with edit() as entries: change the list in place; it is saved when the block ends."""
    with _locked():
        entries = load()
        yield entries
        finished = [e for e in entries if e.get("state") not in (WAITING, RUNNING, STOPPING)]
        for old in sorted(finished, key=lambda e: e.get("finished") or 0)[:-KEEP_FINISHED or None]:
            entries.remove(old)
        write_json(FILE, entries)


def get(entries: list[dict], job_id: str) -> dict:
    for entry in entries:
        if entry["id"] == job_id:
            return entry
    raise KeyError(f"no planned job {job_id}")


def _resolve(waits: list[str], entries: list[dict]) -> list[str]:
    """'previous' means the last job still in the queue."""
    out = []
    for wait in waits or []:
        if wait == "previous":
            pending = [e for e in entries if e.get("state") in (WAITING, RUNNING)]
            if pending:
                out.append(f"job:{pending[-1]['id']}")
        elif wait:
            out.append(wait)
    return out


def add(name: str, command: list[str], cwd: str | None = None, waits_for: list[str] | None = None,
        log: str | None = None, priority: str = "below") -> str:
    """Queue a job for the runner. Returns its id."""
    job_id = secrets.token_hex(3)
    with edit() as entries:
        entries.append({"id": job_id, "name": name, "command": list(command), "cwd": cwd or str(BOOK),
                        "waits_for": _resolve(waits_for, entries), "log": log or str(LOGS / f"{job_id}.log"),
                        "priority": priority, "managed": True, "state": WAITING, "step": "", "pid": None,
                        "added": time.time(), "started": None, "finished": None, "exit_code": None})
    return job_id


def begin(name: str, pid: int, log: str | None = None, waits_for: list[str] | None = None) -> str:
    """A script that runs itself registers here (it waits on its own, then calls running() and finish())."""
    job_id = secrets.token_hex(3)
    with edit() as entries:
        waits = _resolve(waits_for, entries)
        entries.append({"id": job_id, "name": name, "command": [], "cwd": None, "waits_for": waits, "log": log,
                        "priority": "", "managed": False, "state": WAITING if waits else RUNNING, "step": "",
                        "pid": pid, "added": time.time(), "started": None if waits else time.time(),
                        "finished": None, "exit_code": None})
    return job_id


def update(job_id: str, **fields) -> None:
    with edit() as entries:
        get(entries, job_id).update(fields)


def running(job_id: str) -> None:
    update(job_id, state=RUNNING, started=time.time(), step="")


def finish(job_id: str, exit_code: int | None) -> None:
    update(job_id, state=DONE if not exit_code else FAILED, finished=time.time(), exit_code=exit_code, step="")


def move(job_id: str, delta: int) -> None:
    """Up (-1) or down (+1) among the waiting jobs."""
    with edit() as entries:
        waiting = [e for e in entries if e.get("state") == WAITING]
        entry = get(waiting, job_id)
        at = waiting.index(entry)
        target = at + delta
        if 0 <= target < len(waiting):
            other = waiting[target]
            i, j = entries.index(entry), entries.index(other)
            entries[i], entries[j] = other, entry


def remove(job_id: str) -> None:
    with edit() as entries:
        entry = get(entries, job_id)
        if entry.get("state") == RUNNING:
            raise ValueError("it is running: stop it instead")
        entries.remove(entry)


def run_now(job_id: str) -> None:
    """First in line, and no longer waiting for anything."""
    with edit() as entries:
        entry = get(entries, job_id)
        entries.remove(entry)
        first = next((i for i, e in enumerate(entries) if e.get("state") == WAITING), len(entries))
        entry["waits_for"] = []
        entries.insert(first, entry)


def pause_queue(paused: bool) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    if paused:
        PAUSED_FLAG.write_text(str(time.time()), encoding="utf-8")
    else:
        PAUSED_FLAG.unlink(missing_ok=True)


def queue_paused() -> bool:
    return PAUSED_FLAG.exists()


# --- what a job waits for ------------------------------------------------------------------------------------
def busy(wait: str, entries: list[dict]) -> bool:
    """Is the thing this job waits for still going?"""
    if wait.startswith("job:"):
        try:
            return get(entries, wait[4:]).get("state") in (WAITING, RUNNING, STOPPING)
        except KeyError:
            return False
    if wait.startswith("pid:"):
        return alive(int(wait[4:]))
    if wait == "library":
        from .sources.processes import running_with, snapshot
        return running_with("analyze_library", snapshot()) is not None
    if wait == "stage2":
        from .sources import book_stage2
        return book_stage2.is_running(read_json(book_stage2.folder(BOOK) / "status.json", {}))
    if wait == "main":
        from .sources import book_main
        running, _ = book_main.read(BOOK / "results" / "jobs", {})
        return bool(running)
    return False


def describe(wait: str, entries: list[dict]) -> str:
    if wait.startswith("job:"):
        try:
            return f"'{get(entries, wait[4:])['name']}'"
        except KeyError:
            return "a removed job"
    if wait.startswith("pid:"):
        return f"process {wait[4:]}"
    return WAITS.get(wait, wait)


def blocked_by(entry: dict, entries: list[dict]) -> str | None:
    """'waiting for ...', or None when it may start now."""
    open_waits = [w for w in entry.get("waits_for") or [] if busy(w, entries)]
    if not open_waits:
        return None
    return "waiting for " + " and ".join(describe(w, entries) for w in open_waits)


def check_tracked(entries: list[dict]) -> None:
    """A tracked script whose process is gone but never said finish(): it ended (crashed or was closed)."""
    for entry in entries:
        if not entry.get("managed") and entry.get("state") in (WAITING, RUNNING) and not alive(entry.get("pid")):
            entry.update(state=FAILED, finished=time.time(), step="its process ended without reporting back")


def jobs_from(entries: list[dict]) -> tuple[list, list, list]:
    """(running, waiting, finished) as window rows."""
    from .model import Job
    running, waiting, finished = [], [], []
    paused = queue_paused()
    for entry in entries:
        state = entry.get("state")
        log = entry.get("log")
        job = Job(id=f"plan:{entry['id']}", name=entry.get("name", "?"), source="Planned",
                  state=RUNNING if state == STOPPING else state, step=entry.get("step", ""),
                  started=entry.get("started") or entry.get("added"), finished=entry.get("finished"),
                  pid=entry.get("pid"), log=log if log and Path(log).exists() else None,
                  folder=entry.get("cwd"), ref={"plan": entry["id"]})
        if state in (RUNNING, STOPPING):
            last = tail(Path(log), 1) if log else []
            job.step = "stopping..." if state == STOPPING else (entry.get("step") or (
                f"log: {last[0]}" if last and not last[0].startswith(("===", "    ")) else "started"))
            job.actions = ["stop", "log", "folder"]
            running.append(job)
        elif state == WAITING:
            job.started = entry.get("added")
            reason = entry.get("step") or ("waits for " + " and ".join(
                describe(w, entries) for w in entry.get("waits_for") or []) if entry.get("waits_for") else "next in line")
            job.step = ("queue paused; " if paused and entry.get("managed") else "") + reason
            job.actions = ["up", "down", "remove", "runnow", "log"] if entry.get("managed") else ["stop", "log"]
            waiting.append(job)
        else:
            if entry.get("exit_code") not in (None, 0):
                job.step = f"exit code {entry['exit_code']}" + (f"; {job.step}" if job.step else "")
            job.state = state if state in (DONE, FAILED, STOPPED) else DONE
            job.actions = ["log"] if job.log else []
            finished.append(job)
    return running, waiting, finished
