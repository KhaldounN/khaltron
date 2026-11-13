"""The 2026-11-13 'make it practical' changes: memory guard, clean-up after a restart, efficiency mode for
background apps, your work list. Only processes the tests start themselves are touched."""

import subprocess
import sys
import time
from types import SimpleNamespace

import psutil
import pytest

from monitor import eco, gaming, mywork, planned, runner
from test_gaming import game, fake_worker, started  # noqa: F401 (fixtures)


@pytest.fixture
def sleeper():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    deadline = time.time() + 15
    while time.time() < deadline:
        family = [psutil.Process(process.pid)] + psutil.Process(process.pid).children(recursive=True)
        if len(family) > 1 or "Scripts" not in sys.executable:
            break
        time.sleep(0.05)
    yield process
    process.kill()


# --- the memory guard ------------------------------------------------------------------------------------------
def test_the_queue_waits_while_memory_is_short(monkeypatch):
    monkeypatch.setitem(runner.CONFIG, "memory_guard_mb", 2048)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=1.2 * 2 ** 30))
    assert "waiting for memory: 1.2 GB free" in runner.memory_short()
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=6 * 2 ** 30))
    assert runner.memory_short() is None


def test_the_memory_guard_can_be_switched_off(monkeypatch):
    monkeypatch.setitem(runner.CONFIG, "memory_guard_mb", 0)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=0))
    assert runner.memory_short() is None


# --- after a crash or restart ----------------------------------------------------------------------------------
def test_a_mode_left_on_by_a_restart_is_switched_off(game):
    gaming.turn_on()
    state = gaming.read_json(gaming.FLAG, {})
    state["since"] = psutil.boot_time() - 3600  # switched on before the PC last started
    gaming.write_json(gaming.FLAG, state)
    assert "after a restart" in gaming.recover()
    assert not gaming.is_on() and not planned.queue_paused()


def test_a_mode_switched_on_since_the_start_is_left_on(game):
    gaming.turn_on()
    assert gaming.recover() is None and gaming.is_on()


# --- efficiency mode instead of freezing for background apps -----------------------------------------------------
def test_efficiency_mode_slows_down_and_restores(sleeper):
    process = psutil.Process(sleeper.pid)
    before = eco.slow_down(process)
    assert before == 0x20 and int(process.nice()) == eco.IDLE
    assert process.status() != psutil.STATUS_STOPPED  # still running
    eco.restore([{"pid": process.pid, "created": process.create_time(), "before": before}])
    assert int(process.nice()) == 0x20


def test_background_apps_get_efficiency_mode_not_frozen(game, sleeper, monkeypatch):
    monkeypatch.setattr(gaming, "EXTRA_APPS", {"python.exe": "Test background app"})
    message = gaming.turn_on()
    assert "Efficiency mode (still running, slowly): Test background app" in message
    assert psutil.Process(sleeper.pid).status() != psutil.STATUS_STOPPED
    assert int(psutil.Process(sleeper.pid).nice()) == eco.IDLE
    assert "Background apps are out of efficiency mode" in gaming.turn_off()
    assert int(psutil.Process(sleeper.pid).nice()) == 0x20


# --- your work list ------------------------------------------------------------------------------------------------
def test_your_work_is_never_frozen(game, fake_worker):
    assert "is now your work" in mywork.mark("Python", [fake_worker.pid], True)
    gaming.turn_on()
    assert psutil.Process(fake_worker.pid).status() != psutil.STATUS_STOPPED
    gaming.turn_off()
    assert "no longer on your work list" in mywork.mark("Python", [fake_worker.pid], False)
    gaming.turn_on()
    assert psutil.Process(fake_worker.pid).status() == psutil.STATUS_STOPPED


# --- the memory guard for running jobs ------------------------------------------------------------------------------
@pytest.fixture
def guard(game, tmp_path, monkeypatch):
    from monitor import memguard
    monkeypatch.setattr(memguard, "FILE", tmp_path / "memguard.json")
    monkeypatch.setitem(memguard.CONFIG, "memory_pause_mb", 1024)
    monkeypatch.setitem(memguard.CONFIG, "memory_resume_mb", 3072)
    yield memguard
    memguard.release_all()


def stopped(process) -> bool:
    """Is the job frozen? (A venv's python.exe is a launcher; the guard freezes the bigger one, the real worker.)"""
    me = psutil.Process(process.pid)
    return any(p.status() == psutil.STATUS_STOPPED for p in [me] + me.children(recursive=True))


def test_low_memory_freezes_a_running_job_and_wakes_it_later(guard, fake_worker):
    notes = guard.check(free_mb=600)
    assert notes and "Memory low" in notes[0][0]
    assert stopped(fake_worker)
    assert guard.check(free_mb=2000) == []  # in between: wait
    notes = guard.check(free_mb=5000)
    assert notes and "carries on" in notes[0][1]
    assert not stopped(fake_worker)


def test_the_guard_leaves_jobs_alone_while_a_mode_is_on(guard, fake_worker):
    gaming.turn_on()
    assert guard.check(free_mb=100) == []
    gaming.turn_off()
    assert not stopped(fake_worker)


def test_quitting_wakes_what_the_guard_froze(guard, fake_worker):
    guard.check(free_mb=600)
    assert guard.release_all() >= 1
    assert not stopped(fake_worker)


def test_your_work_is_never_frozen_by_the_guard(guard, fake_worker):
    mywork.mark("Python", [fake_worker.pid], True)
    assert guard.check(free_mb=100) == []
    assert not stopped(fake_worker)
