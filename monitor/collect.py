"""One refresh: ask every reader, and put the answers together for the window."""

import time
import traceback
from dataclasses import dataclass, field

from . import planned
from .config import BOOK, CONFIG
from .model import Job
from .sources import book_library, book_main, book_stage2, processes, scheduled
from .sources import health as health_source


@dataclass
class State:
    health: health_source.Health | None = None
    running: list[Job] = field(default_factory=list)
    waiting: list[Job] = field(default_factory=list)
    finished: list[Job] = field(default_factory=list)
    tasks: list[Job] = field(default_factory=list)
    processes: list[Job] = field(default_factory=list)
    stage2_paused: bool = False
    queue_paused: bool = False
    errors: list[str] = field(default_factory=list)
    taken: float = 0.0


_tasks: tuple[float, list[Job]] = (0.0, [])


def collect(slow: bool = False) -> State:
    """`slow`: also re-read the scheduled tasks (a PowerShell call, ~1 s)."""
    global _tasks
    began = time.time()
    state = State()

    def attempt(what, read):
        try:
            return read()
        except Exception:  # noqa: BLE001 - one broken reader must not blank the whole window
            state.errors.append(f"{what}: {traceback.format_exc(limit=2).strip().splitlines()[-1]}")
            return None

    procs = attempt("processes", processes.snapshot) or {}
    state.health = attempt("health", health_source.read)
    state.processes = attempt("processes", lambda: processes.rows(procs)) or []

    # running first: the book analysis, then stage 2, the library job, and planned jobs
    main = attempt("book analyses", lambda: book_main.read(BOOK / "results" / "jobs", procs)) or ([], [])
    stage2 = attempt("stage 2", lambda: book_stage2.read(BOOK, procs)) or ([], [], [])
    library = attempt("library", lambda: book_library.read(BOOK, procs, slow)) or ([], [])
    entries = attempt("planned", planned.load) or []
    plan = attempt("planned", lambda: planned.jobs_from(entries)) or ([], [], [])
    for job in plan[0]:
        job.memory_mb = processes.tree_memory(job.pid, procs)

    # the library job's current book also shows as a main analysis: keep both (the library row shows the count)
    state.running = main[0] + stage2[0] + library[0] + plan[0]
    state.waiting = plan[1] + stage2[1] + library[1]
    state.finished = sorted(main[1] + stage2[2] + plan[2], key=lambda j: j.finished or 0, reverse=True)[:40]
    status = book_stage2.folder(BOOK) / "status.json"
    from .util import read_json
    state.stage2_paused = read_json(status, {}).get("state") == "paused"
    state.queue_paused = planned.queue_paused()

    if slow or not _tasks[0]:
        found = attempt("scheduled tasks", lambda: scheduled.read(CONFIG["scheduled_tasks"]))
        if found is not None:
            _tasks = (time.time(), found)
    state.tasks = _tasks[1]
    state.taken = time.time() - began
    return state
