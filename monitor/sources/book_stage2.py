"""Book Analyzer's stage 2 (analyzer/second_stage.py): the slower extras (deep, surprise, irony) for one book at a
time. Files in results/jobs/second_stage/: status.json (the worker's state), queue.json (books waiting, the one
being worked on first), failed.json (books given up), log.txt (one line per finished book)."""

import re
import time
from datetime import datetime
from pathlib import Path

from ..model import DONE, FAILED, PAUSED, RUNNING, WAITING, Job
from ..util import alive, read_json
from . import pretty_book
from .processes import tree_memory

STAGES = ("deep", "surprise", "irony")
STALE_SECONDS = 20 * 60
FINISHED = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\s+(.+?): ([\d.]+) min$")


def folder(book_root: Path) -> Path:
    return book_root / "results" / "jobs" / "second_stage"


def is_running(status: dict) -> bool:
    return (status.get("state") == RUNNING and alive(status.get("pid"))
            and time.time() - status.get("updated", 0) < STALE_SECONDS)


def read(book_root: Path, procs: dict) -> tuple[list[Job], list[Job], list[Job]]:
    """(running, waiting, finished)."""
    here = folder(book_root)
    status = read_json(here / "status.json", {})
    queue = read_json(here / "queue.json", [])
    if not isinstance(queue, list):
        queue = []
    names = {q.get("key"): q.get("stem") or q.get("key", "")[:12] for q in queue if isinstance(q, dict)}
    log = str(here / "log.txt")
    running, waiting, finished = [], [], []

    working = status.get("key") if is_running(status) else None
    if working:
        stage = status.get("stage", "")
        number = f" ({STAGES.index(stage) + 1} of {len(STAGES)})" if stage in STAGES else ""
        note = f": {status['note']}" if status.get("note") else ""
        running.append(Job(
            id=f"s2:{working}", name=f"Deeper analysis of {pretty_book(names.get(working, working[:12]))}",
            source="Stage 2", state=RUNNING, step=f"{stage}{number}{note}", progress=status.get("fraction"),
            started=status.get("started"), pid=status.get("pid"), log=log,
            memory_mb=tree_memory(status.get("pid"), procs), actions=["pause2", "log"], ref={"key": working}))

    paused = status.get("state") == PAUSED and not working
    for entry in queue:
        if not isinstance(entry, dict) or entry.get("key") == working:
            continue
        key = entry.get("key", "")
        waiting.append(Job(
            id=f"s2:{key}", name=f"Deeper analysis of {pretty_book(names.get(key))}", source="Stage 2",
            state=WAITING, step="stage 2 is paused: Resume to go on" if paused else "in stage 2's queue",
            started=entry.get("added"), log=log, actions=["up", "down", "remove", "runnow"],
            ref={"key": key}))

    for line in reversed(_last_lines(here / "log.txt")):
        hit = FINISHED.match(line)
        if hit:
            stamp = datetime.fromisoformat(hit.group(1)).timestamp()
            finished.append(Job(id=f"s2done:{hit.group(2)}:{int(stamp)}",
                                name=f"Deeper analysis of {pretty_book(hit.group(2))}", source="Stage 2",
                                state=DONE, step=f"took {float(hit.group(3)):.0f} min", finished=stamp, log=log,
                                actions=["log"]))
    for key, stamp in (read_json(here / "failed.json", {}) or {}).items():
        finished.append(Job(id=f"s2fail:{key}", name=f"Deeper analysis of {key[:12]}", source="Stage 2",
                            state=FAILED, step="given up after its worker died 3 times (out of memory?)",
                            finished=stamp if isinstance(stamp, (int, float)) else None, log=log, actions=["log"]))
    return running, waiting, finished


def _last_lines(path: Path, count: int = 30) -> list[str]:
    from ..util import tail
    return tail(path, count)
