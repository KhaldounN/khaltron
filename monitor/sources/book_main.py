"""Book Analyzer's main analyses (app/jobs.py): one status file per book in results/jobs/<key>.json, written by
analyzer/worker.py every few seconds: state, step, fraction, pid, started, updated, book."""

import time
from pathlib import Path

from ..model import DONE, FAILED, RUNNING, Job
from ..util import alive, read_json
from . import pretty_book
from .processes import tree_memory

STALE_SECONDS = 15 * 60  # the same rule as app/jobs.py: silent this long = gone


def read(jobs_dir: Path, procs: dict) -> tuple[list[Job], list[Job]]:
    """(running, finished)."""
    running, finished = [], []
    for path in sorted(jobs_dir.glob("*.json")) if jobs_dir.exists() else []:
        found = read_json(path, None)
        if not isinstance(found, dict):
            continue
        key = path.stem
        log = path.with_suffix(".log")
        job = Job(id=f"main:{key}", name=f"Analyze {pretty_book(found.get('book'))}", source="Book Analyzer",
                  state=found.get("state", ""), step=found.get("step", ""), progress=found.get("fraction"),
                  started=found.get("started"), pid=found.get("pid") or None,
                  log=str(log) if log.exists() else None, ref={"key": key})
        silent = time.time() - found.get("updated", found.get("started", 0)) > STALE_SECONDS
        if job.state == RUNNING and (silent or not alive(job.pid)):
            job.state, job.step = FAILED, "the worker stopped without a word (out of memory, or stopped)"
        if job.state == RUNNING:
            job.memory_mb = tree_memory(job.pid, procs)
            if job.progress and job.progress > 0.05 and job.started:
                spent = time.time() - job.started
                job.eta_minutes = spent / job.progress * (1 - job.progress) / 60
            job.actions = ["stop", "log"]
            running.append(job)
        else:
            job.finished = found.get("updated")
            if job.state == FAILED and found.get("error"):
                job.step = str(found["error"]).strip().splitlines()[-1][:200]
            elif job.state == DONE and found.get("minutes"):
                job.step = f"took {found['minutes']:.0f} min"
            job.actions = ["log"] if job.log else []
            finished.append(job)
    return running, finished
