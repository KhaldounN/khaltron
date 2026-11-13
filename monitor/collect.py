"""One refresh: ask every reader, and put the answers together for the window."""

import threading
import time
import traceback
from dataclasses import dataclass, field

from . import appcontrol, planned, startup
from .config import BOOK, CONFIG
from .model import Job
from .sources import book_library, book_main, book_stage2, processes, programs, scheduled
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
    jobs_mb: float = 0.0    # RAM used by every running job together (each process counted once)
    jobs_cpu: float = 0.0   # their CPU, percent of the whole CPU
    programs: list = field(default_factory=list)  # every program on the PC (sources/programs.py), busiest first
    samples: dict = field(default_factory=dict)   # this refresh's process sample (pid -> programs.Sample)
    controls: dict = field(default_factory=dict)  # program name -> appcontrol.Control (what its buttons may do)
    startup: list = field(default_factory=list)   # [(startup.StartupApp, RAM it uses now or None)]
    taken: float = 0.0


_tasks: tuple[float, list[Job]] = (0.0, [])
_startup: list | None = None  # the Startup apps tab's rows, re-read on the slow refresh
_reading = threading.Event()  # a scheduled-task reading is under way


def _read_tasks():
    global _tasks
    try:
        found = scheduled.read(CONFIG["scheduled_tasks"])
        _tasks = (time.time(), found if found is not None else _tasks[1])
    except Exception:  # noqa: BLE001 - try again at the next interval
        _tasks = (time.time(), _tasks[1])
    finally:
        _reading.clear()


def refresh_tasks_soon() -> None:
    """Re-read the scheduled tasks at the next refresh (after 'Run task now')."""
    global _tasks
    _tasks = (0.0, _tasks[1])


def collect(slow: bool = False) -> State:
    """`slow`: also the slower readers (the library count). Scheduled tasks are read in their own thread."""
    global _tasks
    began = time.time()
    state = State()

    def attempt(what, read):
        try:
            return read()
        except Exception:  # noqa: BLE001 - one broken reader must not blank the whole window
            state.errors.append(f"{what}: {traceback.format_exc(limit=2).strip().splitlines()[-1]}")
            return None

    # ONE look at every process for this refresh, shared by every reader below
    taken = state.samples = attempt("process sample", programs.sample) or {}
    procs = attempt("processes", lambda: processes.snapshot(taken)) or {}
    state.health = attempt("health", health_source.read)
    state.programs = attempt("programs", lambda: programs.read(taken)) or []
    h = state.health
    if h and state.programs:
        # what no program owns, so the section adds up to the PC's totals (as Task Manager's do)
        cpu_left = h.cpu - sum(a.cpu for a in state.programs)
        ram_left = h.used_mb - sum(a.memory_mb for a in state.programs)
        if cpu_left >= 0.5:
            state.programs.append(programs.Program("Windows: drivers, interrupts, short-lived processes", 0, cpu_left,
                                                   0.0, False, []))
        if ram_left > 0:
            state.programs.append(programs.Program("Windows: kernel, drivers, shared and cache memory", 0, 0.0,
                                                   ram_left, False, []))
        state.programs.sort(key=lambda a: (-round(a.cpu, 1), -a.memory_mb))
    state.processes = attempt("processes", lambda: processes.rows(procs)) or []
    # the Startup apps tab: only on the slow refresh (once a minute; was every refresh, ~12 ms each)
    global _startup
    if slow or _startup is None:
        apps = attempt("startup apps", startup.read) or []
        memory = attempt("startup apps", lambda: startup.running_mb(apps, taken, appcontrol._exe)) or {}
        _startup = [(app, memory.get(app.name)) for app in apps]
    state.startup = _startup
    state.controls = attempt("program controls", lambda: appcontrol.controls(
        state.programs, taken, programs.my_session())) or {}

    # running first: the book analysis, then stage 2, the library job, and planned jobs
    # the Book Analyzer's own jobs, only when that project is there (config.json "book_analyzer")
    has_book = (BOOK / "analyzer").exists()
    main = (attempt("book analyses", lambda: book_main.read(BOOK / "results" / "jobs", procs))
            if has_book else None) or ([], [])
    stage2 = (attempt("stage 2", lambda: book_stage2.read(BOOK, procs)) if has_book else None) or ([], [], [])
    library = (attempt("library", lambda: book_library.read(BOOK, procs, slow)) if has_book else None) or ([], [])
    entries = attempt("planned", planned.load) or []
    plan = attempt("planned", lambda: planned.jobs_from(entries)) or ([], [], [])
    for job in plan[0]:
        job.memory_mb = processes.tree_memory(job.pid, procs)

    # the library job's current book also shows as a main analysis: keep both (the library row shows the count)
    state.running = main[0] + stage2[0] + library[0] + plan[0]
    from . import eta
    for job in state.running:  # time left, for jobs that say how far they are and have no better estimate
        if job.eta_minutes is None:
            job.eta_minutes = eta.from_progress(job.progress, job.started)
    # what the jobs use: per job (with its children), and all together with no process counted twice (the
    # library job's worker is also listed as its own book analysis)
    counted: set[int] = set()
    for job in state.running:
        job.cpu = processes.tree_cpu(job.pid, procs)
        counted |= processes.family(job.pid)
    state.jobs_mb = sum(procs[p].memory_mb for p in counted if p in procs)
    state.jobs_cpu = sum(procs[p].cpu for p in counted if p in procs) / processes.CORES
    state.waiting = plan[1] + stage2[1] + library[1]
    state.finished = sorted(main[1] + stage2[2] + plan[2], key=lambda j: j.finished or 0, reverse=True)[:40]
    status = book_stage2.folder(BOOK) / "status.json"
    from .util import read_json
    state.stage2_paused = has_book and read_json(status, {}).get("state") == "paused"
    state.queue_paused = planned.queue_paused()

    # scheduled tasks: a PowerShell call of ~6 s (it loads Windows' task module), so every 10 minutes, in a thread of
    # its own at low priority; the refresh never waits for it and shows the last reading meanwhile (2026-11-13: it
    # was every minute, in the refresh itself)
    if time.time() - _tasks[0] >= CONFIG.get("tasks_refresh_seconds", 600) and not _reading.is_set():
        _reading.set()
        threading.Thread(target=_read_tasks, daemon=True).start()
    state.tasks = _tasks[1]
    state.taken = time.time() - began
    return state
