import os
import sys

from monitor import planned, runner

PY = sys.executable


def names(entries):
    return [e["name"] for e in entries]


def test_add_keeps_order_and_previous_means_the_last_queued(state_dir):
    a = planned.add("A", [PY, "-c", "pass"], cwd=str(state_dir))
    planned.add("B", [PY, "-c", "pass"], cwd=str(state_dir), waits_for=["previous"])
    entries = planned.load()
    assert names(entries) == ["A", "B"]
    assert entries[1]["waits_for"] == [f"job:{a}"]
    assert planned.blocked_by(entries[1], entries) == "waiting for 'A'"
    assert planned.blocked_by(entries[0], entries) is None


def test_move_run_now_and_remove(state_dir):
    ids = [planned.add(n, [PY], cwd=str(state_dir), waits_for=["library"]) for n in "ABC"]
    planned.move(ids[2], -1)
    assert names(planned.load()) == ["A", "C", "B"]
    planned.move(ids[0], -1)  # already first: nothing happens
    assert names(planned.load()) == ["A", "C", "B"]
    planned.run_now(ids[1])
    entries = planned.load()
    assert names(entries) == ["B", "A", "C"] and entries[0]["waits_for"] == []
    planned.remove(ids[0])
    assert names(planned.load()) == ["B", "C"]


def test_a_tracked_script_that_vanished_is_marked_failed(state_dir):
    job = planned.begin("chain", pid=999_999_9)
    with planned.edit() as entries:
        planned.check_tracked(entries)
    entry = planned.load()[0]
    assert entry["id"] == job and entry["state"] == "failed"


def test_tracked_script_reports_begin_running_finish(state_dir):
    job = planned.begin("chain", pid=os.getpid(), waits_for=["pid:999999"])
    assert planned.load()[0]["state"] == "waiting"
    planned.running(job)
    planned.finish(job, 0)
    running, waiting, finished = planned.jobs_from(planned.load())
    assert not running and not waiting and finished[0].state == "done"


def test_runner_runs_jobs_in_order_and_records_exit_codes(state_dir):
    out = state_dir / "order.txt"
    first = planned.add("first", [PY, "-c", f"open(r'{out}', 'a').write('1')"], cwd=str(state_dir))
    planned.add("second", [PY, "-c", f"open(r'{out}', 'a').write('2'); raise SystemExit(3)"], cwd=str(state_dir),
                waits_for=[f"job:{first}"])
    runner.main()
    entries = planned.load()
    assert out.read_text() == "12"
    assert [e["state"] for e in entries] == ["done", "failed"]
    assert entries[1]["exit_code"] == 3
    assert "first" in (state_dir / "logs" / f"{first}.log").read_text(encoding="utf-8")
    assert not runner.LOCK.exists()


def test_a_paused_queue_starts_nothing(state_dir, monkeypatch):
    planned.add("A", [PY, "-c", "pass"], cwd=str(state_dir))
    planned.pause_queue(True)
    calls = []
    monkeypatch.setattr(runner, "run", lambda entry: calls.append(entry))
    monkeypatch.setattr(runner.time, "sleep", lambda s: planned.pause_queue(False) or planned.remove(planned.load()[0]["id"]))
    runner.main()
    assert calls == []


def test_jobq_cli_add_and_list(state_dir, capsys):
    import jobq
    jobq.main(["add", "--name", "From Claude", "--after", "library", "--", PY, "-c", "pass"])
    job_id = capsys.readouterr().out.strip()
    jobq.main(["list"])
    listed = capsys.readouterr().out
    assert job_id in listed and "From Claude" in listed
    _, waiting, _ = planned.jobs_from(planned.load())
    assert waiting[0].step == "waits for the library pre-analysis"


def test_jobq_add_works_without_the_double_dash(state_dir, capsys):
    """PowerShell drops '--' when it runs jobq.ps1: the command starts at the first word that isn't an option."""
    import jobq
    jobq.main(["add", "--name", "No dash", "--after", "previous", PY, "-u", "script.py", "--style", "x"])
    assert planned.load()[0]["command"] == [PY, "-u", "script.py", "--style", "x"]
