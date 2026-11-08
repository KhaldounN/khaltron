"""Compares each refresh with the one before and says what changed: a job started, finished or failed, memory
ran low. Jobs that vanished without a finished record (a script closed, a crash) are kept in state/history.json
so the Finished tab still shows them."""

import time

from .collect import State
from .config import CONFIG, STATE
from .model import FAILED, Job
from .util import read_json, write_json

HISTORY = STATE / "history.json"
KEEP = 40
RECOVER_MB = 300  # memory must come back this far above the limit before a new warning


class Watcher:
    def __init__(self):
        self.running: dict[str, Job] | None = None  # None until the first refresh: nothing "starts" at launch
        self.low = False

    def changes(self, state: State) -> list[tuple[str, str]]:
        """(title, message) for each thing worth a notification."""
        out = []
        now = {job.id: job for job in state.running}
        if self.running is not None:
            finished = {job.id: job for job in state.finished}
            waiting = {job.id for job in state.waiting}
            for job_id, job in now.items():
                if job_id not in self.running:
                    out.append(("Job started", job.name))
            for job_id, job in self.running.items():
                if job_id in now:
                    continue
                if job_id in waiting:  # back in its queue: paused (stage 2 makes way for a book analysis)
                    out.append(("Job paused", f"{job.name}\nIt is back in the queue."))
                    continue
                if job_id.startswith("s2:"):
                    # stage 2's log names the book differently; done if nothing failed
                    out.append(("Job finished", job.name))
                    continue
                record = finished.get(job_id)
                if record is None:
                    record = Job(id=job_id, name=job.name, source=job.source, state="ended",
                                 step="no longer running (finished, stopped or crashed)", started=job.started,
                                 finished=time.time(), log=job.log, actions=["log"] if job.log else [])
                    remember(record)
                verb = "failed" if record.state == FAILED else "stopped" if record.state == "stopped" else "finished"
                detail = f"\n{record.step}" if record.step else ""
                out.append((f"Job {verb}", f"{job.name}{detail}"))
        self.running = now

        health = state.health
        if health:
            limit = CONFIG["low_memory_mb"]
            if health.free_mb < limit and not self.low:
                self.low = True
                out.append(("Memory is low", f"Only {health.free_mb / 1024:.1f} GB left for new work. A job may be "
                                             "ended by Windows (out of memory)."))
            elif health.free_mb > limit + RECOVER_MB:
                self.low = False
        return out


def remember(job: Job) -> None:
    found = read_json(HISTORY, [])
    found.append({"id": job.id, "name": job.name, "source": job.source, "state": job.state, "step": job.step,
                  "started": job.started, "finished": job.finished, "log": job.log})
    write_json(HISTORY, found[-KEEP:])


def history() -> list[Job]:
    out = []
    for e in read_json(HISTORY, []):
        out.append(Job(id=f"hist:{e['id']}:{int(e.get('finished') or 0)}", name=e["name"], source=e["source"],
                       state=e["state"], step=e.get("step", ""), started=e.get("started"), finished=e.get("finished"),
                       log=e.get("log"), actions=["log"] if e.get("log") else []))
    return out
