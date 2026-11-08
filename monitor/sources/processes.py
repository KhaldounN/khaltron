"""Python processes on this PC: which known job each one is, and how much memory and CPU it uses.

One snapshot per refresh is shared by every reader (listing processes is the slowest thing the monitor does)."""

import os
from dataclasses import dataclass

import psutil

from ..config import CONFIG
from ..model import RUNNING, Job

# what a command line contains -> (label, protected). Protected ones never get a Stop button (protect.py).
KNOWN = [
    ("piper_server", "Voice server (read-aloud)", True),
    ("streamlit", "Book Analyzer website", True),
    ("run_website.ps1", "Website watchdog", True),
    ("monitor.pyw", "Khaltron (this window)", True),
    ("monitor.runner", "Khaltron queue runner", True),
    ("analyzer.worker", "Book analysis worker", False),
    ("analyzer.second_stage", "Stage 2 worker (deeper analysis)", False),
    ("analyze_library", "Library pre-analysis", False),
    ("deep_analysis", "Deep analysis script", False),
    ("insight_models", "Surprise and irony script", False),
]
PYTHON = {"python.exe", "pythonw.exe", "python", "python3", "powershell.exe", "pwsh.exe"}


@dataclass
class Proc:
    pid: int
    name: str
    cmdline: str
    memory_mb: float
    cpu: float
    started: float
    label: str
    known: bool
    protected: bool


CORES = psutil.cpu_count() or 1  # logical processors: psutil gives a process's CPU as % of ONE of them
_seen: dict[int, psutil.Process] = {}  # kept between refreshes: CPU % is measured since the last look


def label_for(cmdline: str) -> tuple[str, bool, bool]:
    """(label, known, protected) for a command line."""
    for needle, label, protected in KNOWN:
        if needle in cmdline:
            return label, True, protected
    return "", False, False


def snapshot() -> dict[int, Proc]:
    """Every python (and PowerShell) process, with its memory and CPU."""
    found: dict[int, Proc] = {}
    alive = set()
    for process in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "create_time"]):
        info = process.info
        if (info.get("name") or "").lower() not in PYTHON:
            continue
        pid = info["pid"]
        alive.add(pid)
        cached = _seen.setdefault(pid, process)
        try:
            cpu = cached.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            cpu = 0.0
        cmdline = " ".join(info.get("cmdline") or [])
        label, known, protected = label_for(cmdline)
        memory = info.get("memory_info")
        found[pid] = Proc(pid, info["name"], cmdline, memory.rss / 2 ** 20 if memory else 0.0, cpu,
                          info.get("create_time") or 0.0, label, known, protected or pid == os.getpid())
    for pid in list(_seen):
        if pid not in alive:
            del _seen[pid]
    return found


def family(pid: int | None) -> set[int]:
    """A process and everything it started (a job's real size: PowerShell scripts start python children)."""
    if not pid:
        return set()
    try:
        return {pid} | {c.pid for c in psutil.Process(pid).children(recursive=True)}
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {pid}


def tree_memory(pid: int | None, procs: dict[int, Proc]) -> float | None:
    """Memory (working set, as Task Manager's details show) of a process and its children."""
    total = sum(procs[p].memory_mb for p in family(pid) if p in procs)
    return total or None


def tree_cpu(pid: int | None, procs: dict[int, Proc]) -> float | None:
    """CPU of a process and its children, as a percent of the whole CPU (Task Manager's way, so 100 = every core)."""
    if not pid:
        return None
    return sum(procs[p].cpu for p in family(pid) if p in procs) / CORES


def running_with(text: str, procs: dict[int, Proc]) -> Proc | None:
    """The first process whose command line contains `text` (python ones before their PowerShell parents)."""
    hits = [p for p in procs.values() if text in p.cmdline]
    hits.sort(key=lambda p: not p.name.lower().startswith("python"))
    return hits[0] if hits else None


def rows(procs: dict[int, Proc]) -> list[Job]:
    """The Processes tab: every known python process, and unknown ones that are heavy."""
    out = []
    for p in sorted(procs.values(), key=lambda p: -p.memory_mb):
        if not p.name.lower().startswith("python"):
            continue
        heavy = p.memory_mb >= CONFIG["heavy_process_mb"] or p.cpu >= CONFIG["heavy_process_cpu"]
        if not (p.known or heavy):
            continue
        script = next((part for part in p.cmdline.split() if part.endswith((".py", ".pyw"))), p.name)
        out.append(Job(id=f"proc:{p.pid}", name=p.label or f"Other: {os.path.basename(script)}", source="Process",
                       state=RUNNING, step=p.cmdline[-160:], started=p.started, pid=p.pid, memory_mb=p.memory_mb,
                       cpu=p.cpu / CORES, actions=[] if p.protected else ["stop"], ref={"protected": p.protected}))
    return out
