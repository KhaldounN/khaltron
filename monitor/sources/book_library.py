"""Book Analyzer's library pre-analysis (scripts/analyze_library.py): analyzes every book in data/ that has no
saved result yet, shortest first, one at a time through the website's own worker. It writes
results/library_progress.log ("2026-11-07 18:09  reading war_and_peace.txt (3280 KB), try 1")."""

import hashlib
import re
import time
from pathlib import Path

from .. import eta
from ..model import RUNNING, WAITING, Job
from ..util import tail
from . import pretty_book
from .processes import running_with, tree_memory

SHOWN = 5  # waiting books listed one by one; the rest are one "... and N more" row
STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d)\s+(.*)$")

_hashes: dict[str, tuple[float, int, str]] = {}  # path -> (mtime, size, sha256): a book is hashed only once
_ready: tuple[float, list[Path]] = (0.0, [])      # (when counted, books not analyzed yet)


def analysis_version(book_root: Path) -> int:
    hit = re.search(r"ANALYSIS_VERSION\s*=\s*(\d+)", (book_root / "analyzer" / "version.py").read_text("utf-8"))
    return int(hit.group(1)) if hit else 0


def _sha(path: Path) -> str:
    stat = path.stat()
    cached = _hashes.get(str(path))
    if cached and cached[:2] == (stat.st_mtime, stat.st_size):
        return cached[2]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _hashes[str(path)] = (stat.st_mtime, stat.st_size, digest)
    return digest


def not_ready(book_root: Path, refresh_seconds: float = 60) -> list[Path]:
    """Library books without a saved analysis, shortest first (the job's own order). Counted at most once a
    minute: it reads every book."""
    global _ready
    if time.time() - _ready[0] < refresh_seconds:
        return _ready[1]
    version = analysis_version(book_root)
    results = book_root / "results"
    books = sorted((book_root / "data").glob("*.txt"), key=lambda p: p.stat().st_size)
    left = [p for p in books if not (results / f"v{version}-{_sha(p)}.pkl").exists()]
    _ready = (time.time(), left)
    return left


def read(book_root: Path, procs: dict, slow: bool) -> tuple[list[Job], list[Job]]:
    """(running, waiting): nothing while the library job isn't running."""
    process = running_with("analyze_library", procs)
    if not process:
        return [], []
    log = book_root / "results" / "library_progress.log"
    lines = tail(log, 6)
    last = STAMP.match(lines[-1]).group(2) if lines and STAMP.match(lines[-1]) else ""
    current = None
    for line in reversed(lines):
        hit = re.search(r"reading (\S+\.txt)", line)
        if hit:
            current = hit.group(1)
            break
    left = not_ready(book_root, 0 if slow and not _ready[0] else 60)
    total = len(list((book_root / "data").glob("*.txt")))
    done = total - len(left)
    try:  # time left: the recent books' speed, times what is left to read (monitor/eta.py)
        minutes = eta.library_minutes(tail(log, 60), [p.stat().st_size / 1024 for p in left])
    except (OSError, ValueError):
        minutes = None
    running = [Job(id="lib:run", name="Library pre-analysis", source="Library", state=RUNNING,
                   step=f"{done} of {total} books ready. Now: {last}", progress=done / total if total else None,
                   started=process.started, pid=process.pid, log=str(log),
                   memory_mb=tree_memory(process.pid, procs), actions=["stop", "log"], eta_minutes=minutes)]
    waiting = []
    queued = [p for p in left if p.name != current]
    for path in queued[:SHOWN]:
        waiting.append(Job(id=f"lib:{path.name}", name=f"Analyze {pretty_book(path.name)}", source="Library",
                           state=WAITING, step="the library job's own order (shortest first)", log=str(log)))
    if len(queued) > SHOWN:
        waiting.append(Job(id="lib:more", name=f"... and {len(queued) - SHOWN} more library books",
                           source="Library", state=WAITING, step="", log=str(log)))
    return running, waiting
