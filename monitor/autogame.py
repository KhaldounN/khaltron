"""Auto gaming mode: when a game starts, gaming mode switches itself on; when that game closes, off again.

A game is recognised in two ways, both cheap (Khaltron's one process snapshot per refresh is reused):
- its program lives in a game library: Steam's steamapps\\common, Epic Games, Xbox (XboxGames), GOG, Riot, EA,
  Ubisoft, Battle.net games... or its name is in config "games";
- or it fills the whole screen in front (full screen or borderless) for a few seconds, and it is not a browser, a
  video player, a slide show or one of Windows' own windows.

Your choice always wins: auto mode only switches OFF what it switched ON itself (gaming mode you turned on by hand
stays on), and if you turn gaming mode off while the game still runs, it leaves that game alone. The on/off switch
for auto mode itself is in the toolbar and the tray menu; it is remembered in state/auto_gaming.json."""

import ctypes
import os
import time
from ctypes import wintypes

import psutil

from . import gaming
from .config import CONFIG, STATE
from .util import read_json, write_json

SETTING = STATE / "auto_gaming.json"
LIBRARIES = ["\\steamapps\\common\\", "\\epic games\\", "\\xboxgames\\", "\\gog galaxy\\games\\", "\\gog games\\",
             "\\riot games\\", "\\ea games\\", "\\electronic arts\\", "\\ubisoft game launcher\\games\\",
             "\\battle.net\\games\\", "\\games\\"]
# never a game, even inside a game folder: launchers, helpers, installers, anti-cheat, crash reporters
NOT_GAMES = ("launcher", "crash", "helper", "updater", "update", "setup", "install", "redist", "unins", "anticheat",
             "easyanticheat", "beservice", "battleye", "report", "vc_redist", "dxsetup", "dotnet", "webhelper",
             "overlay", "service", "steamerrorreporter", "cefprocess", "browser")
# tools sold on Steam that run for hours beside (or without) a game: never a reason for gaming mode
NOT_GAME_FOLDERS = ["steamworks shared", "steamvr", "wallpaper_engine", "wallpaper engine", "soundpad",
                    "lossless scaling", "bongo cat", "desktop mate", "steam controller configs"]
# full-screen windows that are not games
NOT_FULLSCREEN_GAMES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe", "iexplore.exe",
    "vlc.exe", "mpc-hc64.exe", "mpc-hc.exe", "mpc-be64.exe", "potplayermini64.exe", "wmplayer.exe",
    "video.ui.exe", "microsoft.media.player.exe", "netflix.exe", "spotify.exe", "powerpnt.exe", "pptview.exe",
    "explorer.exe", "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe", "lockapp.exe",
    "applicationframehost.exe", "textinputhost.exe", "windowsterminal.exe", "code.exe", "claude.exe",
    "python.exe", "pythonw.exe", "obs64.exe", "zoom.exe", "ms-teams.exe", "teams.exe", "discord.exe",
    "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "overwolf.exe", "rundll32.exe", "dwm.exe",
    "screenclippinghost.exe", "snippingtool.exe", "taskmgr.exe", "mstsc.exe", "msrdc.exe", "acrord32.exe",
    "acrobat.exe", "photos.exe", "microsoft.photos.exe",
}
DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
FULLSCREEN_SECONDS = 8  # a window must stay full screen this long (not a video popping full screen for a moment)


# --- the switch for auto mode itself --------------------------------------------------------------------------------
def enabled() -> bool:
    found = read_json(SETTING, None)
    if isinstance(found, dict) and "on" in found:
        return bool(found["on"])
    return bool(CONFIG.get("auto_gaming", True))


def set_enabled(on: bool) -> None:
    write_json(SETTING, {"on": bool(on), "changed": time.time()})


# --- finding a game -------------------------------------------------------------------------------------------------
_exes: dict[tuple[int, float], str] = {}  # (pid, started) -> its program's path, lower case ("" = unknown)


def _exe(pid: int, started: float) -> str:
    key = (pid, started)
    if key not in _exes:
        try:
            _exes[key] = psutil.Process(pid).exe().lower()
        except (psutil.Error, OSError):
            _exes[key] = ""
    return _exes[key]


def is_game_path(path: str, name: str) -> bool:
    name = name.lower()
    if not path.endswith(".exe") or any(word in name for word in NOT_GAMES):
        return False
    if name in {g.lower() for g in CONFIG.get("games", [])}:
        return True
    path = path.replace("/", "\\")
    skip = NOT_GAME_FOLDERS + [n.lower() for n in CONFIG.get("not_games", [])]
    if name in skip or any(f"\\{folder}\\" in path for folder in skip):
        return False
    return any(folder in path for folder in LIBRARIES)


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _Rect), ("rcWork", _Rect), ("dwFlags", wintypes.DWORD)]


def fullscreen_pid() -> int | None:
    """The process whose window fills the whole screen in front right now (None if there is none)."""
    try:
        user32 = ctypes.windll.user32
    except AttributeError:
        return None
    hwnd = user32.GetForegroundWindow()
    if not hwnd or not user32.IsWindowVisible(hwnd):
        return None
    name = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, name, 64)
    if name.value in DESKTOP_CLASSES:
        return None
    window, info = _Rect(), _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    if not user32.GetWindowRect(hwnd, ctypes.byref(window)) or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    screen = info.rcMonitor
    if not (window.left <= screen.left and window.top <= screen.top and window.right >= screen.right
            and window.bottom >= screen.bottom):
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


class Watcher:
    """Called once per refresh with the refresh's process sample (programs.sample()). Returns the notifications
    to show, as (title, message)."""

    def __init__(self, turn_on=gaming.turn_on, turn_off=gaming.turn_off, is_on=gaming.is_on, flag=lambda: gaming.FLAG,
                 front=fullscreen_pid):
        self.turn_on, self.turn_off, self.is_on, self.flag, self.front = turn_on, turn_off, is_on, flag, front
        self.handled: set[tuple[int, float]] = set()  # games auto mode already switched for (never twice)
        self.front_since: dict[tuple[int, float], float] = {}

    def games(self, samples: dict) -> dict[tuple[int, float], str]:
        """Every game running now: (pid, started) -> its name."""
        found = {}
        for pid, item in samples.items():
            if item.name and item.name.lower().endswith(".exe") and is_game_path(_exe(pid, item.started), item.name):
                found[(pid, item.started)] = os.path.splitext(item.name)[0]
        front = self.front()
        if front and front in samples:
            item = samples[front]
            key = (front, item.started)
            if item.name.lower() not in NOT_FULLSCREEN_GAMES and front != os.getpid():
                since = self.front_since.setdefault(key, time.time())
                if time.time() - since >= FULLSCREEN_SECONDS:
                    found.setdefault(key, os.path.splitext(item.name)[0])
                self.front_since = {key: since}
            else:
                self.front_since = {}
        else:
            self.front_since = {}
        # forget what ended (a new process can reuse a number)
        live = {(pid, item.started) for pid, item in samples.items()}
        self.handled &= live
        global _exes
        if len(_exes) > 4 * max(1, len(live)):
            _exes = {key: path for key, path in _exes.items() if key in live}
        return found

    def tick(self, samples: dict) -> list[tuple[str, str]]:
        if not samples:
            return []
        games = self.games(samples)
        state = read_json(self.flag(), None) if self.is_on() else None
        auto = (state or {}).get("auto") if isinstance(state, dict) else None
        if auto:
            # on because of a game: off once no game is left
            if not games:
                message = self.turn_off()
                return [(f"{auto.get('game', 'Game')} closed: gaming mode OFF", _last_line(message))]
            return []
        if not enabled() or self.is_on():
            self.handled |= set(games)  # on by hand (or auto mode off): this game is yours to manage
            return []
        new = {key: name for key, name in games.items() if key not in self.handled}
        if not new:
            return []
        self.handled |= set(games)
        key, name = next(iter(new.items()))
        message = self.turn_on(auto={"game": name, "pid": key[0], "started": key[1]})
        frozen = sum(1 for line in message.splitlines() if line.startswith("- Frozen:"))
        return [(f"{name} started: gaming mode ON",
                 (f"{frozen} background job(s) frozen. " if frozen else "Nothing needed freezing. ")
                 + "It turns off when the game closes.")]


def _last_line(message: str) -> str:
    lines = message.splitlines()
    return lines[-1] if lines else message
