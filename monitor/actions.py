"""What the window's buttons do. Each action has a question the window asks first ("Are you sure?"), except
the harmless ones (opening a log or a folder)."""

import os
import subprocess
import time

from . import planned, protect, runner
from .config import BOOK
from .model import Job
from .sources import book_stage2
from .util import NO_WINDOW, detached, read_json, write_json

LABELS = {
    "stop": "Stop", "pause2": "Pause stage 2", "resume2": "Resume stage 2", "log": "Open log", "folder": "Open folder",
    "up": "Move up", "down": "Move down", "remove": "Remove", "runnow": "Run next", "runtask": "Run task now",
}
HARMLESS = {"log", "folder"}


def question(job: Job, action: str) -> str:
    """The confirmation text: what will happen."""
    name = f"'{job.name}'"
    if action == "stop":
        if job.source == "Book Analyzer":
            return (f"Stop {name}?\n\nThe analysis ends now and its progress is lost; the website will show it as "
                    "failed, with 'Try again'.")
        if job.source == "Library":
            return (f"Stop the library pre-analysis?\n\nThe book being read now is lost; finished books are kept. "
                    "It skips them when started again.")
        if job.source == "Planned" and job.state == "waiting":
            return f"Stop {name}?\n\nThis script is waiting on its own; it will be ended."
        return f"Stop {name} (process {job.pid}) and everything it started?"
    if action == "pause2":
        return ("Pause stage 2?\n\nThe stage being worked on is redone later (finished stages are kept). The book "
                "stays in the queue. It starts again with 'Resume stage 2', or by itself after the next book analysis.")
    if action == "resume2":
        return "Resume stage 2?\n\nIts worker starts on the first book in its queue (if no book analysis is running)."
    if action == "remove":
        return f"Remove {name} from the queue?\n\nIt won't run. (A stage 2 book is added again if it is opened on the website.)"
    if action in ("up", "down"):
        return f"Move {name} {action} in the queue?"
    if action == "runnow":
        extra = "" if job.source == "Stage 2" else " It no longer waits for anything else."
        return f"Run {name} next?\n\nIt moves to the front of its queue.{extra}"
    if action == "runtask":
        return f"Run the scheduled task {name} now?"
    return f"{LABELS.get(action, action)} {name}?"


def do(job: Job, action: str) -> str:
    """Carry out the action; returns a short message for the status bar. Raises on failure."""
    if action == "log":
        os.startfile(job.log)
        return "Log opened."
    if action == "folder":
        os.startfile(job.folder)
        return "Folder opened."
    if job.source == "Planned":
        return _planned(job, action)
    if job.source == "Stage 2":
        return _stage2(job, action)
    if action == "stop" and job.pid:
        protect.stop_tree(job.pid)
        return f"Stopped {job.name}."
    if action == "runtask":
        subprocess.run(["powershell", "-NoProfile", "-Command", "Start-ScheduledTask -TaskName $args[0]",
                        job.ref["task"]], capture_output=True, creationflags=NO_WINDOW, check=True)
        return f"Started the task {job.name}."
    raise ValueError(f"'{action}' can't be done on this row")


def _planned(job: Job, action: str) -> str:
    job_id = job.ref["plan"]
    if action == "stop":
        if job.state == "running" and job.pid:
            reason = protect.why_protected(job.pid)
            if reason:
                raise protect.Protected(f"Not stopped: {reason}.")
            planned.update(job_id, state=planned.STOPPING)
            protect.stop_tree(job.pid)
        elif job.pid:  # a tracked script waiting on its own
            protect.stop_tree(job.pid)
            planned.update(job_id, state="stopped", finished=time.time(), step="stopped from the window")
        return f"Stopped {job.name}."
    if action == "remove":
        planned.remove(job_id)
        return f"Removed {job.name}."
    if action in ("up", "down"):
        planned.move(job_id, -1 if action == "up" else 1)
        return f"Moved {job.name} {action}."
    if action == "runnow":
        planned.run_now(job_id)
        runner.wake()
        return f"{job.name} is next."
    raise ValueError(action)


# --- stage 2 ---------------------------------------------------------------------------------------------------
def _book_python(code: str) -> None:
    """Run a line of Book Analyzer code with its own Python, so stage 2 is paused/woken by its own rules."""
    python = BOOK / ".venv" / "Scripts" / "python.exe"
    done = subprocess.run([str(python), "-c", code], cwd=str(BOOK), capture_output=True, text=True,
                          creationflags=NO_WINDOW, timeout=60)
    if done.returncode:
        raise RuntimeError((done.stderr or done.stdout).strip().splitlines()[-1] if (done.stderr or done.stdout) else "failed")


def pause_stage2() -> str:
    _book_python("from analyzer import second_stage as s; s.pause()")
    return "Stage 2 paused."


def resume_stage2() -> str:
    _book_python("from analyzer import second_stage as s; s.wake()")
    return "Stage 2 woken (it starts unless a book analysis is running)."


def _stage2(job: Job, action: str) -> str:
    if action in ("pause2", "stop"):
        return pause_stage2()
    if action == "resume2":
        return resume_stage2()
    path = book_stage2.folder(BOOK) / "queue.json"
    queue = read_json(path, [])
    status = read_json(book_stage2.folder(BOOK) / "status.json", {})
    working = status.get("key") if book_stage2.is_running(status) else None
    key = job.ref["key"]
    keys = [q.get("key") for q in queue]
    if key not in keys:
        raise ValueError("it is no longer in stage 2's queue")
    at = keys.index(key)
    first = 1 if working and keys and keys[0] == working else 0  # the book being worked on stays first
    entry = queue.pop(at)
    if action == "remove":
        message = f"Removed {job.name} from stage 2's queue."
    elif action == "runnow":
        queue.insert(first, entry)
        message = f"{job.name} is next in stage 2."
    else:
        target = max(first, min(len(queue), at + (-1 if action == "up" else 1)))
        queue.insert(target, entry)
        message = f"Moved {job.name} {action}."
    write_json(path, queue)
    if action == "runnow" and not working:
        resume_stage2()
    return message


# --- the Start menu ---------------------------------------------------------------------------------------------
def start_library() -> str:
    script = BOOK / "scripts" / "run_library.ps1"
    detached(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", str(script)],
             cwd=BOOK, priority="below")
    return "Library pre-analysis started (it skips books that are done)."


def set_queue_paused(paused: bool) -> str:
    planned.pause_queue(paused)
    if not paused:
        runner.wake()
    return "Planned queue paused: running jobs go on, no new one starts." if paused else "Planned queue resumed."
