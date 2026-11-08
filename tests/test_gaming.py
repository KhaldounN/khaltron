"""Gaming mode on a stand-in job: a sleeping python whose command line looks like a Book Analyzer worker.
The real switch file, voice server, power mode and Book Analyzer folder are never touched."""

import json
import subprocess
import sys
import time

import psutil
import pytest

from monitor import gaming, planned


@pytest.fixture
def game(state_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(gaming, "FLAG", tmp_path / "gaming.json")
    monkeypatch.setattr(gaming, "LOCK", tmp_path / "gaming.lock")
    monkeypatch.setattr(gaming, "BOOK", tmp_path / "book")
    monkeypatch.setattr(gaming, "_stop_voice", lambda: False)
    modes = {"now": "00000000-0000-0000-0000-000000000000"}
    monkeypatch.setattr(gaming, "power_mode", lambda: modes["now"])
    monkeypatch.setattr(gaming, "set_power_mode", lambda m: modes.update(now=m) or True)
    monkeypatch.setattr(gaming.time, "sleep", lambda s: None)
    # SAFETY: the tests may only ever see processes they started themselves, never the PC's real jobs
    def only_mine(*args, **kwargs):
        found = []
        for process in psutil.Process().children(recursive=True):
            try:
                process.info = {"name": process.name()}  # what process_iter(["name"]) would fill in
                found.append(process)
            except psutil.NoSuchProcess:
                pass
        return found
    monkeypatch.setattr(gaming.psutil, "process_iter", only_mine)
    yield modes
    if gaming.is_on():  # a failed test must not leave anything frozen
        gaming.turn_off()


def started(process) -> None:
    """Wait until a new process has really started (its command line readable, a venv launcher's child there):
    on a busy PC that takes longer than a fixed half second."""
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            me = psutil.Process(process.pid)
            family = [me] + me.children(recursive=True)
            if all("analyzer.worker" in " ".join(p.cmdline()) for p in family) and (
                    len(family) > 1 or "Scripts" not in sys.executable):
                return
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        time.sleep(0.1)


@pytest.fixture
def fake_worker(tmp_path):
    # "-m analyzer.worker" can't be used (no such module here), so the needle rides along as an argument
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "analyzer.worker"])
    started(process)
    yield process
    process.kill()


def test_the_tests_only_see_their_own_processes(game, fake_worker):
    seen = {p.pid for p in gaming._job_processes()}
    assert fake_worker.pid in seen
    assert all(psutil.Process(pid).ppid() in (fake_worker.pid,) or pid == fake_worker.pid for pid in seen)


def state_of(process) -> str:
    return psutil.Process(process.pid).status()


def test_on_freezes_jobs_and_off_resumes_them(game, fake_worker):
    message = gaming.turn_on()
    assert gaming.is_on()
    assert "Frozen: Book analysis worker" in message
    assert state_of(fake_worker) == psutil.STATUS_STOPPED
    assert planned.queue_paused()
    assert game["now"] == gaming.BEST_PERFORMANCE

    message = gaming.turn_off()
    assert not gaming.is_on()
    assert state_of(fake_worker) != psutil.STATUS_STOPPED
    assert not planned.queue_paused()
    assert game["now"] == "00000000-0000-0000-0000-000000000000"  # the power mode comes back
    assert "frozen job process(es) carry on" in message


def test_a_queue_paused_before_stays_paused(game):
    planned.pause_queue(True)
    gaming.turn_on()
    gaming.turn_off()
    assert planned.queue_paused()


def test_enforce_freezes_a_job_that_starts_later(game, fake_worker):
    fake_worker.kill()
    gaming.turn_on()
    late = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "analyzer.worker"])
    try:
        started(late)
        assert gaming.enforce()
        gaming.enforce()  # (a venv's python.exe is a launcher with the real python as its child)
        assert state_of(late) == psutil.STATUS_STOPPED
        assert gaming.enforce() == []  # never the same process twice
        pids = [f["pid"] for f in json.loads(gaming.FLAG.read_text(encoding="utf-8"))["frozen"]]
        assert len(pids) == len(set(pids))
        gaming.turn_off()
        assert state_of(late) != psutil.STATUS_STOPPED
    finally:
        late.kill()


def test_off_refreshes_the_status_file_of_a_frozen_worker(game, fake_worker, tmp_path):
    jobs = tmp_path / "book" / "results" / "jobs"
    jobs.mkdir(parents=True)
    status = jobs / "abc.json"
    status.write_text(json.dumps({"state": "running", "pid": fake_worker.pid, "updated": 1}), encoding="utf-8")
    gaming.turn_on()
    gaming.turn_off()
    assert json.loads(status.read_text(encoding="utf-8"))["updated"] > time.time() - 60


def test_protected_programs_are_never_frozen(game):
    website = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "streamlit", "analyzer.worker"])
    try:
        started(website)
        gaming.turn_on()
        assert state_of(website) != psutil.STATUS_STOPPED
    finally:
        gaming.turn_off()
        website.kill()


def test_a_reused_process_number_is_not_resumed(game, fake_worker):
    gaming.turn_on()
    found = json.loads(gaming.FLAG.read_text(encoding="utf-8"))
    found["frozen"][0]["created"] -= 1000  # as if the number now belonged to another program
    gaming.FLAG.write_text(json.dumps(found), encoding="utf-8")
    assert "were gone" in gaming.turn_off()
    psutil.Process(fake_worker.pid).resume()


def test_switching_twice_is_harmless(game):
    gaming.turn_on()
    assert "already ON" in gaming.turn_on()
    gaming.turn_off()
    assert "already OFF" in gaming.turn_off()


def test_other_heavy_python_scripts_are_frozen_too_but_small_ones_are_not(game, monkeypatch):
    """Gaming mode frees as much as it safely can: any other Python script of yours over gaming_python_mb."""
    script = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "my_experiment"])
    try:
        deadline = time.time() + 15
        while time.time() < deadline and "my_experiment" not in " ".join(psutil.Process(script.pid).cmdline()):
            time.sleep(0.1)
        monkeypatch.setitem(gaming.CONFIG, "gaming_python_mb", 100_000)  # far more than a sleeping python holds
        gaming.turn_on()
        assert state_of(script) != psutil.STATUS_STOPPED
        gaming.turn_off()
        monkeypatch.setitem(gaming.CONFIG, "gaming_python_mb", 1)  # every python counts as heavy
        message = gaming.turn_on()
        assert state_of(script) == psutil.STATUS_STOPPED
        assert "Python:" in message
        gaming.turn_off()
        assert state_of(script) != psutil.STATUS_STOPPED
    finally:
        script.kill()
