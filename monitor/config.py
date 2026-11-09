"""Settings: defaults here, overridden by config.json in the project folder (only the keys you put there)."""

import json
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent  # the "job monitor" folder
STATE = HOME / "state"  # planned.json, history, logs of planned jobs, runner lock

DEFAULTS = {
    "book_analyzer": str(HOME.parent / "book analyzer v2"),
    "refresh_seconds": 2,           # how often the window re-reads everything
    "slow_refresh_seconds": 60,     # scheduled tasks and the library count (slower to read)
    "low_memory_mb": 1500,          # below this the memory bar turns red and a warning pops up (stage 2's own limit)
    "heavy_process_mb": 300,        # a python process using more memory than this is listed
    "heavy_process_cpu": 20,        # ... or more CPU (percent of one core) than this
    "scheduled_tasks": ["Book Analyzer website", "Book Visualizer library (3 am)", "Khaltron 9000"],
    # gaming mode also freezes these background apps (process name -> what the window calls it), and any other
    # Python script of yours holding more RAM than gaming_python_mb; only things that are safe to freeze
    "gaming_also_freeze": {"OneDrive.exe": "OneDrive sync"},
    "gaming_python_mb": 200,
    # gaming mode also pauses (freezes) the Book Analyzer website; it carries on when gaming mode ends
    "gaming_pause_website": True,
    # the activation sound when gaming mode turns on (assets/khaltron-gaming-mode.wav) and its volume (0-1)
    "gaming_sound": True,
    "gaming_sound_volume": 0.8,
    "port": 59126,                  # a second launch tells the first window to show itself through this port
}


def load() -> dict:
    found = dict(DEFAULTS)
    try:
        found.update(json.loads((HOME / "config.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return found


CONFIG = load()
BOOK = Path(CONFIG["book_analyzer"])
