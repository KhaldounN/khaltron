"""Pausing / resuming / ending a program from the Programs tab, on stand-in processes the test starts itself.
Real programs are never touched: the "program" here is a sleeping python we started."""

import subprocess
import sys
import time
from collections import namedtuple

import psutil
import pytest

from monitor import appcontrol
from monitor.sources import programs

Sample = namedtuple("Sample", "name cpu private_mb session ppid started")
Program = programs.Program


@pytest.fixture
def paused_file(tmp_path, monkeypatch):
    monkeypatch.setattr(appcontrol, "PAUSED", tmp_path / "paused.json")


@pytest.fixture
def sleeper():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    deadline = time.time() + 10
    while time.time() < deadline and not psutil.pid_exists(process.pid):
        time.sleep(0.05)
    yield process
    try:
        psutil.Process(process.pid).resume()
    except psutil.Error:
        pass
    process.kill()


def test_windows_parts_claude_and_services_are_never_offered(monkeypatch):
    mine = 1
    samples = {10: Sample("explorer.exe", 0, 100, mine, 0, 1.0), 11: Sample("claude.exe", 0, 900, mine, 0, 2.0),
               12: Sample("svchost.exe", 0, 50, 0, 0, 3.0), 13: Sample("Overwolf.exe", 0, 90, mine, 0, 4.0)}
    paths = {10: r"C:\Windows\explorer.exe", 11: r"C:\Users\x\AppData\Local\AnthropicClaude\claude.exe",
             12: r"C:\Windows\System32\svchost.exe", 13: r"C:\Program Files (x86)\Overwolf\Overwolf.exe"}
    monkeypatch.setattr(appcontrol, "_exe", lambda pid, started: paths[pid].lower())
    monkeypatch.setattr(appcontrol, "WINDOWS_DIR", "c:\\windows\\")
    groups = [Program("File Explorer", 1, 0, 0, True, [10]), Program("Claude", 1, 0, 0, True, [11]),
              Program("Windows & services", 1, 0, 0, False, [12]), Program("Overwolf", 1, 0, 0, True, [13])]
    found = appcontrol.controls(groups, samples, mine)
    assert not found["File Explorer"].allowed and "Windows" in found["File Explorer"].reason
    assert not found["Claude"].allowed and "Claude" in found["Claude"].reason
    assert not found["Windows & services"].allowed
    assert found["Overwolf"].allowed == [13]


def test_pause_then_resume(paused_file, sleeper):
    message = appcontrol.pause("Sleeper", [sleeper.pid])
    assert "Paused Sleeper" in message
    assert psutil.Process(sleeper.pid).status() == psutil.STATUS_STOPPED
    assert [p["pid"] for p in appcontrol.paused_list()] == [sleeper.pid]
    assert appcontrol.pause("Sleeper", [sleeper.pid]).startswith("Nothing paused")  # never twice
    assert appcontrol.resume("Sleeper") == "Resumed Sleeper."
    assert psutil.Process(sleeper.pid).status() != psutil.STATUS_STOPPED
    assert appcontrol.paused_list() == []


def test_a_reused_process_number_is_not_resumed(paused_file, sleeper):
    appcontrol.pause("Sleeper", [sleeper.pid])
    found = appcontrol.paused_list()
    found[0]["created"] -= 1000  # as if the number now belonged to another program
    appcontrol.write_json(appcontrol.PAUSED, found)
    assert "wasn't paused" in appcontrol.resume("Sleeper")
    assert psutil.Process(sleeper.pid).status() == psutil.STATUS_STOPPED  # left alone (the fixture resumes it)


def test_end_now_ends_even_a_paused_program(paused_file, sleeper):
    appcontrol.pause("Sleeper", [sleeper.pid])
    assert appcontrol.end("Sleeper", [sleeper.pid]) == "Ended Sleeper."
    sleeper.wait(timeout=10)
    assert not psutil.pid_exists(sleeper.pid) or psutil.Process(sleeper.pid).status() == psutil.STATUS_ZOMBIE


def test_protected_programs_are_skipped_at_the_last_moment(paused_file):
    runner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "monitor.runner"])
    try:
        deadline = time.time() + 10
        while time.time() < deadline and "monitor.runner" not in " ".join(psutil.Process(runner.pid).cmdline()):
            time.sleep(0.05)
        assert appcontrol.pause("Python", [runner.pid]).startswith("Nothing paused")
        assert psutil.Process(runner.pid).status() != psutil.STATUS_STOPPED
    finally:
        runner.kill()
