import json
import os
import time

from monitor.sources import book_library, book_main, book_stage2
from monitor.sources.processes import Proc, label_for


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_main_jobs_running_crashed_and_done(tmp_path):
    now = time.time()
    write(tmp_path / "aaa.json", {"state": "running", "step": "Linking pronouns", "fraction": 0.5, "pid": os.getpid(),
                                  "started": now - 600, "updated": now, "book": "war_and_peace.txt"})
    write(tmp_path / "bbb.json", {"state": "running", "step": "Emotions", "fraction": 0.2, "pid": 9_999_999,
                                  "started": now - 60, "updated": now})
    write(tmp_path / "ccc.json", {"state": "done", "minutes": 7.2, "pid": 1, "updated": now, "book": "emma.txt"})
    running, finished = book_main.read(tmp_path, {})
    assert [j.name for j in running] == ["Analyze War and peace"]
    assert running[0].progress == 0.5 and 9 < running[0].eta_minutes < 11
    assert {j.id: j.state for j in finished} == {"main:bbb": "failed", "main:ccc": "done"}


def test_stage2_running_queue_and_finished_lines(tmp_path):
    here = book_stage2.folder(tmp_path)
    write(here / "status.json", {"state": "running", "pid": os.getpid(), "updated": time.time(), "key": "k1",
                                 "stage": "surprise", "fraction": 0.4, "note": "1,200 of 3,000"})
    write(here / "queue.json", [{"key": "k1", "stem": "emma", "added": 1}, {"key": "k2", "stem": "dracula", "added": 2}])
    write(here / "failed.json", {"k9": 1794000000.0})
    (here / "log.txt").write_text("2026-11-08T18:19:52  emma: 19.0 min\nnoise\n", encoding="utf-8")
    running, waiting, finished = book_stage2.read(tmp_path, {})
    assert running[0].name == "Deeper analysis of Emma" and running[0].step.startswith("surprise (2 of 3)")
    assert [j.name for j in waiting] == ["Deeper analysis of Dracula"]
    assert {j.state for j in finished} == {"done", "failed"}


def test_library_job_counts_ready_books_and_lists_the_next(tmp_path, monkeypatch):
    (tmp_path / "analyzer").mkdir()
    (tmp_path / "analyzer" / "version.py").write_text("ANALYSIS_VERSION = 5\n", encoding="utf-8")
    data, results = tmp_path / "data", tmp_path / "results"
    data.mkdir()
    results.mkdir()
    for name, size in (("a.txt", 10), ("b.txt", 20), ("c.txt", 30)):
        (data / name).write_text("x" * size, encoding="utf-8")
    (results / f"v5-{book_library._sha(data / 'a.txt')}.pkl").write_bytes(b"")
    (results / "library_progress.log").write_text("2026-11-07 18:09  reading b.txt (1 KB), try 1\n", encoding="utf-8")
    monkeypatch.setattr(book_library, "_ready", (0.0, []))
    proc = Proc(42, "python.exe", "python scripts/analyze_library.py", 100, 5, time.time(), "Library", True, False)
    running, waiting = book_library.read(tmp_path, {42: proc}, slow=True)
    assert running[0].step.startswith("1 of 3 books ready")
    assert [j.name for j in waiting] == ["Analyze C"]  # b is being read now
    assert book_library.read(tmp_path, {}, slow=True) == ([], [])  # not running: nothing shown


def test_known_processes_and_protection_labels():
    assert label_for("pythonw.exe C:/x/tts/piper_server.py") == ("Voice server (read-aloud)", True, True)
    assert label_for("python -m streamlit run app/streamlit_app.py")[2] is True
    assert label_for("python -m analyzer.worker book.txt r.pkl s.json") == ("Book analysis worker", True, False)
    assert label_for("python something_else.py") == ("", False, False)


def test_job_cpu_is_a_share_of_the_whole_cpu_and_never_counted_twice(monkeypatch):
    """psutil gives a process's CPU as % of ONE core (a busy worker shows 180%); Task Manager shows % of all."""
    from monitor.sources import processes
    monkeypatch.setattr(processes, "CORES", 12)
    procs = {1: Proc(1, "python.exe", "x", 600, 180, 0, "", False, False),
             2: Proc(2, "python.exe", "y", 100, 60, 0, "", False, False)}
    monkeypatch.setattr(processes, "family", lambda pid: {1, 2} if pid == 1 else {pid} if pid else set())
    assert processes.tree_cpu(1, procs) == 20.0  # (180 + 60) / 12 cores
    assert processes.tree_memory(1, procs) == 700


def test_health_reports_ram_in_use_like_task_manager():
    from monitor.sources import health
    found = health.read()
    assert found.used_mb + found.ram_free_mb == found.total_mb
    assert found.cores >= 1 and 0 <= found.cpu <= 100


def test_programs_on_this_pc_are_read_in_one_quick_call():
    """Every process at once (NtQuerySystemInformation), grouped by program; CPU as a share of the whole CPU."""
    import sys
    import time as clock
    from monitor.sources import programs
    if sys.platform != "win32":
        assert programs.read() == []
        return
    programs.read()
    clock.sleep(0.5)
    started = clock.perf_counter()
    found = programs.read()
    assert clock.perf_counter() - started < 1.0  # asking process by process took 4-8 s
    names = [p.name for p in found]
    assert "Python (incl. your background jobs)" in names  # this test itself is a python process
    assert all(0 <= p.cpu <= 100.5 and p.memory_mb >= 0 for p in found)
    assert sum(p.processes for p in found) > 20
    assert any(not p.yours for p in found)  # Windows' own services are there too
