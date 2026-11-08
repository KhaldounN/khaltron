import json
import os
import subprocess
import sys
import time

import psutil
import pytest

from monitor import actions, alerts, protect
from monitor.collect import State
from monitor.model import Job
from monitor.sources import book_stage2
from monitor.sources.health import Health


def stage2_queue(tmp_path, monkeypatch, working: bool):
    monkeypatch.setattr(actions, "BOOK", tmp_path)
    here = book_stage2.folder(tmp_path)
    here.mkdir(parents=True)
    (here / "queue.json").write_text(json.dumps([{"key": k} for k in "ABCD"]), encoding="utf-8")
    status = {"state": "running", "pid": os.getpid(), "updated": time.time(), "key": "A"} if working else {"state": "idle"}
    (here / "status.json").write_text(json.dumps(status), encoding="utf-8")
    return lambda: [q["key"] for q in json.loads((here / "queue.json").read_text(encoding="utf-8"))]


def row(key):
    return Job(id=f"s2:{key}", name=key, source="Stage 2", state="waiting", ref={"key": key})


def test_stage2_queue_edits_keep_the_working_book_first(tmp_path, monkeypatch):
    keys = stage2_queue(tmp_path, monkeypatch, working=True)
    actions.do(row("B"), "up")
    assert keys() == ["A", "B", "C", "D"]  # can't jump over the book being worked on
    actions.do(row("D"), "runnow")
    assert keys() == ["A", "D", "B", "C"]
    actions.do(row("B"), "down")
    assert keys() == ["A", "D", "C", "B"]
    actions.do(row("C"), "remove")
    assert keys() == ["A", "D", "B"]


def test_stage2_run_now_when_idle_wakes_it(tmp_path, monkeypatch):
    keys = stage2_queue(tmp_path, monkeypatch, working=False)
    woken = []
    monkeypatch.setattr(actions, "resume_stage2", lambda: woken.append(1) or "ok")
    actions.do(row("C"), "runnow")
    assert keys()[0] == "C" and woken == [1]


def sleeper(*marker):
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", *marker])
    time.sleep(0.5)
    return process


def test_protected_processes_are_never_stopped():
    process = sleeper("piper_server.py")
    try:
        assert "Voice server" in protect.why_protected(process.pid)
        with pytest.raises(protect.Protected):
            protect.stop_tree(process.pid)
        assert process.poll() is None
        assert protect.why_protected(os.getpid())
    finally:
        process.kill()


def test_an_ordinary_job_is_stopped_with_its_children():
    process = sleeper()
    protect.stop_tree(process.pid)
    process.wait(timeout=10)
    assert not psutil.pid_exists(process.pid) or process.poll() is not None


def test_every_control_action_has_a_question():
    job = Job("x", "Thing", "Planned", "waiting")
    for action in set(actions.LABELS) - actions.HARMLESS:
        assert actions.question(job, action).strip()


def test_alerts_started_finished_and_low_memory(state_dir):
    watch = alerts.Watcher()
    job = Job("plan:1", "Deep analysis", "Planned", "running")
    healthy = Health(8000, 16000, 8000, 8000, 9000, 10, 12)
    assert watch.changes(State(health=healthy, running=[job])) == []  # first look: nothing is "new"
    done = Job("plan:1", "Deep analysis", "Planned", "done", step="exit code 0")
    low = Health(900, 16000, 15100, 900, 1000, 10, 12)
    told = watch.changes(State(health=low, finished=[done]))
    assert ("Job finished", "Deep analysis\nexit code 0") in told
    assert any(title == "Memory is low" for title, _ in told)
    assert watch.changes(State(health=low)) == []  # told once
    gone = Job("lib:run", "Library pre-analysis", "Library", "running")
    watch.changes(State(health=healthy, running=[gone]))
    assert watch.changes(State(health=healthy))[0][0] == "Job finished"
    assert alerts.history()[0].name == "Library pre-analysis"  # kept for the Finished tab
