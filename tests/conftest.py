import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["JOB_MONITOR_NO_RUNNER"] = "1"  # tests never start the real background runner


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """The planned queue, its lock and the runner lock in a temporary folder."""
    from monitor import alerts, planned, runner
    monkeypatch.setattr(planned, "STATE", tmp_path)
    monkeypatch.setattr(planned, "FILE", tmp_path / "planned.json")
    monkeypatch.setattr(planned, "LOCK", tmp_path / "planned.lock")
    monkeypatch.setattr(planned, "PAUSED_FLAG", tmp_path / "queue_paused")
    monkeypatch.setattr(planned, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(runner, "STATE", tmp_path)
    monkeypatch.setattr(runner, "LOCK", tmp_path / "runner.lock")
    monkeypatch.setattr(alerts, "HISTORY", tmp_path / "history.json")
    return tmp_path
