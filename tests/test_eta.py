"""Time left: the library job's speed per KB, and the simple stretch for jobs that report progress."""

import time

from monitor import eta

LOG = [
    "2026-11-10 10:00  reading a.txt (1000 KB), try 1",
    "2026-11-10 10:10    done in 10.0 min",
    "2026-11-10 10:10  reading b.txt (2000 KB), try 1",
    "2026-11-10 10:30    done in 20.0 min",
    "2026-11-10 10:30  reading c.txt (3000 KB), try 1",
]


def at(stamp: str) -> float:
    return time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M"))


def test_library_speed_times_what_is_left():
    # 0.01 min per KB; c (3000 KB, 10 min in) and d (4000 KB) left: 30 - 10 + 40 = 60 min
    assert eta.library_minutes(LOG, [3000, 4000], now=at("2026-11-10 10:40")) == 60


def test_library_without_a_finished_book_yet_is_unknown():
    assert eta.library_minutes(LOG[:1], [1000, 2000]) is None
    assert eta.library_minutes(LOG, []) is None


def test_progress_stretch():
    now = 10_000.0
    assert eta.from_progress(0.25, now - 600, now) == 30          # 10 min for a quarter: 30 more
    assert eta.from_progress(0.01, now - 600, now) is None        # too early to tell
    assert eta.from_progress(0.5, now - 30, now) is None          # under a minute in
    assert eta.from_progress(None, now - 600, now) is None
