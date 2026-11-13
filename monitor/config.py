"""Settings: defaults here, overridden by config.json in the project folder (only the keys you put there).

The defaults work on any Windows PC. config.json is your own (it is not in the repository), for example:
    {"scheduled_tasks": ["Khaltron 9000", "My nightly backup"], "low_memory_mb": 2000}"""

import json
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent  # the "job monitor" folder
STATE = HOME / "state"  # planned.json, history, logs of planned jobs, runner lock

DEFAULTS = {
    # the Book Analyzer project, if you have it (its views switch themselves off when the folder isn't there)
    "book_analyzer": str(HOME.parent / "book analyzer v2"),
    "refresh_seconds": 2,           # how often the window re-reads everything
    "slow_refresh_seconds": 60,     # scheduled tasks and the library count (slower to read)
    "low_memory_mb": 1500,          # below this the memory bar turns red and a warning pops up (stage 2's own limit)
    "heavy_process_mb": 300,        # a python process using more memory than this is listed
    "heavy_process_cpu": 20,        # ... or more CPU (percent of one core) than this
    "scheduled_tasks": ["Khaltron 9000"],  # Windows scheduled tasks to show (add your own)
    # processes to recognise, as [text in the command line, name to show, protected (never stopped or frozen)]
    "known_processes": [],
    # gaming mode's switch file: while it exists, gaming mode is on (other tools can check it)
    "gaming_flag": str(STATE / "gaming.json"),
    # gaming mode also freezes these background apps (process name -> what the window calls it), and any other
    # Python script of yours holding more RAM than gaming_python_mb. Only apps that run unseen and simply carry on
    # afterwards: never a game, launcher, overlay, browser, chat, Claude, antivirus, audio or network. Apps that
    # aren't installed are ignored. Your config.json ADDS to this list; give a name null to take it off.
    "gaming_also_freeze": {
        "OneDrive.exe": "OneDrive sync", "OneDrive.Sync.Service.exe": "OneDrive sync",
        "Dropbox.exe": "Dropbox sync", "GoogleDriveFS.exe": "Google Drive sync", "iCloudDrive.exe": "iCloud sync",
        "AdobeCollabSync.exe": "Adobe Acrobat sync", "CCXProcess.exe": "Adobe Creative Cloud",
        "WidgetBoard.exe": "Windows Widgets", "WidgetService.exe": "Windows Widgets",
        "MicrosoftStartFeedProvider.exe": "Windows Widgets (news feed)",
        "CrossDeviceService.exe": "Phone Link", "CrossDeviceResume.exe": "Phone Link",
        "PhoneExperienceHost.exe": "Phone Link",
    },
    "gaming_python_mb": 200,
    # auto gaming mode (its switch is in the toolbar and the tray; this is only its first setting) and extra game
    # programs to recognise by name, for games outside the usual game folders (Steam, Epic, Xbox, GOG...)
    "auto_gaming": True,
    "games": [],
    "not_games": [],  # program or folder names that look like games but are not (never switch for these)
    # gaming mode also pauses (freezes) the Book Analyzer website; it carries on when gaming mode ends
    "gaming_pause_website": True,
    # the activation sound when gaming mode turns on (assets/khaltron-gaming-mode.wav) and its volume (0-1)
    "gaming_sound": True,
    "gaming_sound_volume": 0.8,
    # development mode (monitor/devmode.py): its switch file, extra programs counted as your work (with everything
    # they start; Claude, Windows Terminal, VS Code and git always are), folders whose programs are your work too
    # (Stable Diffusion), and the priority your work gets ("high" or "above_normal")
    "dev_flag": str(STATE / "dev-mode.json"),
    "dev_keep": [],
    "dev_keep_folders": ["stablediffusion", "comfyui", "stable-diffusion-webui"],
    "dev_boost": "high",
    "port": 59126,                 # a second launch tells the first window to show itself through this port
}


def load() -> dict:
    found = dict(DEFAULTS)
    try:
        for key, value in json.loads((HOME / "config.json").read_text(encoding="utf-8")).items():
            if isinstance(value, dict) and isinstance(found.get(key), dict):  # a list of apps: add to it
                value = {k: v for k, v in {**found[key], **value}.items() if v is not None}
            found[key] = value
    except (OSError, ValueError):
        pass
    return found


CONFIG = load()
BOOK = Path(CONFIG["book_analyzer"]).expanduser()
HAS_BOOK = (BOOK / "analyzer").exists()  # the Book Analyzer integration is on only when that project is there
