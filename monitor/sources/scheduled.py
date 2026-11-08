"""Windows scheduled tasks (the website watchdog at logon, the 3 am library run...): state, last and next run."""

import json
import subprocess
from datetime import datetime

from ..model import FAILED, RUNNING, Job
from ..util import NO_WINDOW

SCRIPT = r"""
$out = foreach ($n in @(__NAMES__)) {
  $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
  if ($t) {
    $i = $t | Get-ScheduledTaskInfo
    [pscustomobject]@{ name = $n; state = "$($t.State)"; result = $i.LastTaskResult;
      last = if ($i.LastRunTime -and $i.LastRunTime.Year -gt 2000) { $i.LastRunTime.ToString('s') } else { '' };
      next = if ($i.NextRunTime) { $i.NextRunTime.ToString('s') } else { '' } }
  }
}
ConvertTo-Json @($out) -Compress
"""
RESULTS = {0: "OK", 267009: "still running", 267011: "never run", 267014: "stopped by you", 2147946720: "not running (logon trigger)"}


def query(names: list[str]) -> list[dict]:
    try:
        quoted = ", ".join("'" + n.replace("'", "''") + "'" for n in names)
        done = subprocess.run(["powershell", "-NoProfile", "-Command", SCRIPT.replace("__NAMES__", quoted)], capture_output=True,
                              text=True, timeout=30, creationflags=NO_WINDOW)
        found = json.loads(done.stdout or "[]")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    return found if isinstance(found, list) else [found]


def _stamp(text: str) -> float | None:
    try:
        return datetime.fromisoformat(text).timestamp() if text else None
    except ValueError:
        return None


def read(names: list[str]) -> list[Job]:
    out = []
    for task in query(names):
        result = task.get("result")
        meaning = RESULTS.get(result, f"code {result}") if result is not None else ""
        state = {"Running": RUNNING, "Disabled": FAILED}.get(task.get("state"), (task.get("state") or "").lower())
        last = _stamp(task.get("last", ""))
        out.append(Job(id=f"task:{task['name']}", name=task["name"], source="Scheduled task", state=state,
                       step=f"last result: {meaning}" if last else "not run since it was made (or since the PC started)",
                       started=last, finished=_stamp(task.get("next", "")),  # 'finished' holds the NEXT run here
                       actions=["runtask"], ref={"task": task["name"]}))
    return out
