"""Development mode on stand-in processes: sleeping pythons that play "your work", "a windowed app" and "a Book
Analyzer worker". The real switch files, power mode and the PC's own programs are never touched."""

import subprocess
import sys
import time

import psutil
import pytest

from monitor import devmode, gaming, planned
from test_gaming import started

SLEEP = [sys.executable, "-c", "import time; time.sleep(120)"]


def family(process) -> list[int]:
    """A process and its children (a venv's python.exe is a launcher with the real python as its child)."""
    me = psutil.Process(process.pid)
    return [me.pid] + [c.pid for c in me.children(recursive=True)]


def nice(pid: int) -> int:
    return int(psutil.Process(pid).nice())


@pytest.fixture
def dev(state_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(devmode, "FLAG", tmp_path / "dev-mode.json")
    monkeypatch.setattr(gaming, "FLAG", tmp_path / "gaming.json")
    monkeypatch.setattr(gaming, "LOCK", tmp_path / "modes.lock")
    monkeypatch.setattr(gaming, "BOOK", tmp_path / "book")
    monkeypatch.setattr(gaming, "_stop_voice", lambda: False)
    modes = {"now": "00000000-0000-0000-0000-000000000000"}
    monkeypatch.setattr(gaming, "power_mode", lambda: modes["now"])
    monkeypatch.setattr(gaming, "set_power_mode", lambda m: modes.update(now=m) or True)
    monkeypatch.setattr(gaming.time, "sleep", lambda s: None)

    # SAFETY: the tests may only ever see processes they started themselves, never the PC's real programs
    def only_mine(*args, **kwargs):
        found = []
        for process in psutil.Process().children(recursive=True):
            try:
                process.info = {"name": process.name(), "ppid": process.ppid(), "create_time": process.create_time()}
                found.append(process)
            except psutil.NoSuchProcess:
                pass
        return found
    monkeypatch.setattr(psutil, "process_iter", only_mine)
    roles = {"work": [], "windows": set()}
    # "your work" and "programs with a window" are the stand-ins the test names (not Claude or real windows)
    monkeypatch.setattr(devmode, "work_pids", lambda snap: {
        pid: "Claude" for root in roles["work"] for pid in [root] + snap.descendants(root, lambda p: False)})
    monkeypatch.setattr(devmode, "window_pids", lambda: set(roles["windows"]))
    yield modes, roles
    if devmode.is_on():  # a failed test must not leave anything frozen or changed
        devmode.turn_off()
    if gaming.is_on():
        gaming.turn_off()


@pytest.fixture
def procs():
    made = []

    def make(*extra):
        process = subprocess.Popen(SLEEP + list(extra))
        made.append(process)
        if "analyzer.worker" in extra:
            started(process)
        else:  # wait for a venv launcher's real python too, or a test could change only half the family
            deadline = time.time() + 15
            while "Scripts" in sys.executable and len(family(process)) < 2 and time.time() < deadline:
                time.sleep(0.05)
        return process
    yield make
    for process in made:
        process.kill()


# --- what counts as your work, and what is lowered (a made-up process table, nothing real) ---------------------
class FakeSnap(devmode.Snapshot):
    def __init__(self, table: dict, cmdlines: dict, exes: dict):
        self.info = {pid: {"name": name, "ppid": ppid, "create_time": float(pid), "exe": exes.get(pid, r"c:\apps\x.exe")}
                     for pid, (name, ppid) in table.items()}
        self.children = {}
        for pid, info in self.info.items():
            if info["ppid"] in self.info:
                self.children.setdefault(info["ppid"], []).append(pid)
        self._cmd = cmdlines

    def cmdline(self, pid):
        return self._cmd.get(pid, "")


def test_what_counts_as_work_and_what_is_lowered(monkeypatch):
    monkeypatch.setattr(devmode, "_planned_pids", lambda: {11})
    snap = FakeSnap({
        1: ("windowsterminal.exe", 0), 2: ("claude.exe", 1), 3: ("node.exe", 2),
        4: ("chrome.exe", 3),       # a test browser Claude started: work
        5: ("chrome.exe", 1),       # your everyday Chrome, started from the terminal: not work
        12: ("chrome.exe", 5),      # ... and its tabs
        6: ("python.exe", 2),       # Khaltron's queue runner (Claude woke it): the walk stops there
        7: ("python.exe", 6),       # a planned job under the runner: background work
        11: ("python.exe", 2),      # a planned job Claude started: background work too
        8: ("python.exe", 0), 9: ("python.exe", 8),  # ComfyUI and its child
        10: ("whatsapp.exe", 0),
    }, cmdlines={6: "python -m monitor.runner", 7: "python job.py", 8: "main.py --listen",
                 9: "worker", 11: "python job.py"},
        exes={8: r"f:\stablediffusion\comfyui_windows_portable\python_embeded\python.exe"})
    work = devmode.work_pids(snap)
    assert work[2] == "Claude" and work[3] == "Claude" and work[4] == "Claude"
    assert work[1] == "Terminal"
    assert work[8] == work[9] == "Stable Diffusion"
    assert not {5, 12, 6, 7, 11, 10} & set(work)
    lowered = devmode.lower_pids(snap, work, windows={2, 5, 8, 10})
    assert set(lowered) == {5, 12, 10}  # your work and Claude are never lowered


# --- the real switch on stand-in processes ---------------------------------------------------------------------
def test_on_freezes_boosts_lowers_and_off_puts_everything_back(dev, procs):
    modes, roles = dev
    worker, work, app = procs("analyzer.worker"), procs("work"), procs("app")
    roles["work"].append(work.pid)
    roles["windows"].add(app.pid)

    message = devmode.turn_on()
    assert devmode.is_on() and planned.queue_paused()
    assert "Frozen: Book analysis worker" in message
    assert psutil.Process(worker.pid).status() == psutil.STATUS_STOPPED
    assert all(nice(pid) == devmode.BOOST for pid in family(work))
    assert all(nice(pid) == devmode.BELOW for pid in family(app))
    assert modes["now"] == gaming.BEST_PERFORMANCE

    message = devmode.turn_off()
    assert not devmode.is_on() and not planned.queue_paused()
    assert psutil.Process(worker.pid).status() != psutil.STATUS_STOPPED
    assert all(nice(pid) == devmode.NORMAL for pid in family(work) + family(app))
    assert modes["now"] == "00000000-0000-0000-0000-000000000000"
    assert "priorities set back" in message


def test_your_work_is_never_frozen_even_if_it_looks_like_a_job(dev, procs):
    _, roles = dev
    mine = procs("analyzer.worker")  # e.g. Claude testing a book analysis right now
    roles["work"].append(mine.pid)
    devmode.turn_on()
    assert psutil.Process(mine.pid).status() != psutil.STATUS_STOPPED


def test_something_set_low_on_purpose_is_not_boosted(dev, procs):
    _, roles = dev
    slow = procs("work")
    for pid in family(slow):
        psutil.Process(pid).nice(devmode.BELOW)
    roles["work"].append(slow.pid)
    devmode.turn_on()
    assert all(nice(pid) == devmode.BELOW for pid in family(slow))


def test_a_priority_changed_meanwhile_is_left_alone(dev, procs):
    _, roles = dev
    app = procs("app")
    roles["windows"].add(app.pid)
    devmode.turn_on()
    psutil.Process(app.pid).nice(devmode.ABOVE)  # you changed it in Task Manager
    devmode.turn_off()
    assert nice(app.pid) == devmode.ABOVE


def test_enforce_boosts_and_lowers_what_starts_later(dev, procs):
    _, roles = dev
    devmode.turn_on()
    work, app = procs("work"), procs("app")
    roles["work"].append(work.pid)
    roles["windows"].add(app.pid)
    devmode.enforce()
    assert nice(work.pid) == devmode.BOOST and nice(app.pid) == devmode.BELOW
    devmode.turn_off()
    assert nice(work.pid) == nice(app.pid) == devmode.NORMAL


def test_gaming_and_development_mode_never_run_together(dev, procs):
    gaming.turn_on()
    assert "Gaming mode switched off first" in devmode.turn_on()
    assert devmode.is_on() and not gaming.is_on()
    assert "Development mode switched off first" in gaming.turn_on()
    assert gaming.is_on() and not devmode.is_on()
    gaming.turn_off()
    assert not planned.queue_paused()  # both switched off cleanly: the queue is back as it was


def test_the_app_in_front_is_never_lowered(dev, procs, monkeypatch):
    _, roles = dev
    app, other = procs("app"), procs("other")
    roles["windows"] |= {app.pid, other.pid}
    front = {"pid": app.pid}
    monkeypatch.setattr(devmode, "foreground_pid", lambda: front["pid"])
    devmode.turn_on()
    assert nice(app.pid) == devmode.NORMAL       # you are typing in it
    assert nice(other.pid) == devmode.BELOW
    front["pid"] = other.pid                     # you switch to the other one
    devmode.enforce()
    assert nice(other.pid) == devmode.NORMAL     # back to normal while in front
    assert nice(app.pid) == devmode.BELOW        # and the one you left gives way again
    devmode.turn_off()
    assert nice(app.pid) == nice(other.pid) == devmode.NORMAL


def test_the_boost_is_above_normal_by_default():
    assert devmode.BOOST == devmode.ABOVE
