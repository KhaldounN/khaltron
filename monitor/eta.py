"""Time left for a running job, worked out from how fast it has gone so far.

- The library pre-analysis: its log says each book's size and how long it took ("reading x.txt (1986 KB)" ...
  "done in 19.0 min"), and it goes shortest first, so the recent books' minutes per KB, times the KB still to read,
  is a good guess (much better than "books done / books left": the last books are the longest).
- Any other job that reports its progress (0..1): the time so far, stretched to the whole."""

import re
import time

READING = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d)\s+reading (\S+\.txt) \((\d+) KB\)")
DONE = re.compile(r"done in ([\d.]+) min")
RECENT = 8  # books the speed is taken from


def library_minutes(log_lines: list[str], left_kb: list[float], now: float | None = None) -> float | None:
    """Minutes until the library job is done. log_lines: its log (oldest first); left_kb: the sizes of the books
    still without a result (including the one being read now)."""
    now = time.time() if now is None else now
    pairs, reading = [], None
    for line in log_lines:
        hit = READING.match(line)
        if hit:
            reading = (hit.group(1), float(hit.group(3)))
            continue
        hit = DONE.search(line)
        if hit and reading:
            pairs.append((reading[1], float(hit.group(1))))
            reading = None
    pairs = pairs[-RECENT:]
    if not pairs or not left_kb:
        return None
    per_kb = sum(m for _, m in pairs) / max(1.0, sum(kb for kb, _ in pairs))
    total = per_kb * sum(left_kb)
    if reading:  # the book being read now: part of it is already done
        started = time.mktime(time.strptime(reading[0], "%Y-%m-%d %H:%M"))
        total -= min(per_kb * reading[1], max(0.0, (now - started) / 60))
    return max(1.0, total)


def from_progress(progress: float | None, started: float | None, now: float | None = None) -> float | None:
    """Minutes left for a job that says how far it is (None when it is too early to tell)."""
    now = time.time() if now is None else now
    if progress is None or not started or not 0.03 <= progress < 1:
        return None
    elapsed = now - started
    if elapsed < 60:
        return None
    return elapsed * (1 - progress) / progress / 60
