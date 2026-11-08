"""One row in the window: a job that is running, waiting in a queue, or finished."""

from dataclasses import dataclass, field

RUNNING, WAITING, DONE, FAILED, STOPPED, PAUSED = "running", "waiting", "done", "failed", "stopped", "paused"


@dataclass
class Job:
    id: str                      # unique and stable across refreshes: "main:<key>", "s2:<key>", "plan:<id>"...
    name: str                    # what the window shows
    source: str                  # "Book Analyzer", "Stage 2", "Library", "Planned", "Process"
    state: str                   # one of the constants above
    step: str = ""               # what it is doing now, or what it waits for
    progress: float | None = None  # 0..1 when known
    started: float | None = None   # time.time() values
    finished: float | None = None
    pid: int | None = None
    log: str | None = None       # a log file to open
    folder: str | None = None    # a folder to open
    memory_mb: float | None = None
    cpu: float | None = None     # percent of the WHOLE CPU (all cores), like Task Manager
    eta_minutes: float | None = None
    actions: list[str] = field(default_factory=list)  # buttons this row allows: see actions.py
    ref: dict = field(default_factory=dict)           # whatever the actions need (queue key, task name...)
