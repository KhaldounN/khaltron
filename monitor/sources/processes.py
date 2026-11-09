"""Python processes on this PC: which known job each one is, and how much memory and CPU it uses.

One snapshot per refresh is shared by every reader (listing processes is the slowest thing the monitor does)."""

import os
from dataclasses import dataclass

import psutil

from pathlib import Path

from ..config import CONFIG, HAS_BOOK
from ..model import RUNNING, Job

# what a command line contains -> (label, protected). Protected ones never get a Stop button (protect.py).
KNOWN = [
    ("monitor.pyw", "Khaltron 9000 (this window)", True),
    ("monitor.runner", "Khaltron 9000 queue runner", True),
] + ([("piper_server", "Voice server (read-aloud)", True)]          # the owner's read-aloud voice, if present
     if (Path.home() / ".claude" / "tts" / "piper_server.py").exists() else []) + (
    [("streamlit", "Book Analyzer website", True), ("run_website.ps1", "Website watchdog", True)]
    if HAS_BOOK else []) + [tuple(entry) for entry in CONFIG.get("known_processes", [])] + [
    # the Book Analyzer's job scripts (they only match those command lines)
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


CORES = psutil.cpu_count() or 1  # logical processors: Proc.cpu is a % of ONE of them, like psutil's
_cmdlines: dict[tuple[int, float], str] = {}  # (pid, start time) -> command line: it never changes
_children: dict[int, list[int]] = {}          # parent pid -> its child pids, from the last snapshot


def label_for(cmdline: str) -> tuple[str, bool, bool]:
    """(label, known, protected) for a command line."""
    for needle, label, protected in KNOWN:
        if needle in cmdline:
            return label, True, protected
    return "", False, False


def _cmdline(pid: int, started: float) -> str:
    key = (pid, round(started, 2))
    if key not in _cmdlines:
        try:
            _cmdlines[key] = " ".join(psutil.Process(pid).cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            _cmdlines[key] = ""
    return _cmdlines[key]


def snapshot(taken: dict | None = None) -> dict[int, Proc]:
    """Every python (and PowerShell) process, with its memory and CPU, from the refresh's shared sample
    (programs.sample(): one Windows call for all processes). Only these few processes' command lines are read,
    once each. Before, asking Windows about every process's memory and command line took ~2.5 s a refresh."""
    from . import programs
    taken = programs.sample() if taken is None else taken
    if not taken:  # not Windows
        return _snapshot_psutil()
    _children.clear()
    found: dict[int, Proc] = {}
    for pid, item in taken.items():
        _children.setdefault(item.ppid, []).append(pid)
        if item.name.lower() not in PYTHON:
            continue
        cmdline = _cmdline(pid, item.started)
        label, known, protected = label_for(cmdline)
        found[pid] = Proc(pid, item.name, cmdline, item.private_mb, item.cpu * CORES, item.started, label, known,
                          protected or pid == os.getpid())
    alive = {(pid, round(item.started, 2)) for pid, item in taken.items()}
    for key in [k for k in _cmdlines if k not in alive]:
        del _cmdlines[key]
    return found


def _snapshot_psutil() -> dict[int, Proc]:
    """The same with psutil, for a system other than Windows (slower)."""
    found: dict[int, Proc] = {}
    for process in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "create_time", "cpu_percent"]):
        info = process.info
        if (info.get("name") or "").lower() not in PYTHON:
            continue
        cmdline = " ".join(info.get("cmdline") or [])
        label, known, protected = label_for(cmdline)
        memory = info.get("memory_info")
        found[info["pid"]] = Proc(info["pid"], info["name"], cmdline, memory.rss / 2 ** 20 if memory else 0.0,
                                  info.get("cpu_percent") or 0.0, info.get("create_time") or 0.0, label, known,
                                  protected or info["pid"] == os.getpid())
    return found


def family(pid: int | None) -> set[int]:
    """A process and everything it started (a job's real size: PowerShell scripts start python children),
    from the last snapshot's parent links (no extra call to Windows)."""
    if not pid:
        return set()
    if not _children:
        try:
            return {pid} | {c.pid for c in psutil.Process(pid).children(recursive=True)}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {pid}
    out, todo = set(), [pid]
    while todo:
        current = todo.pop()
        if current in out:
            continue
        out.add(current)
        todo.extend(_children.get(current, []))
    return out


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
