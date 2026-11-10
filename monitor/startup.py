"""The apps that start when you log in, and switching them on or off: exactly what Task Manager's "Startup apps"
page does, so the two always agree and either can undo the other.

Where Windows keeps them:
- the Run keys in the registry: yours (HKCU) and the PC's (HKLM, also its 32-bit WOW6432Node copy);
- the Startup folders: yours and the PC's (all users).
Whether each is on: the matching "StartupApproved" key holds 12 bytes per entry. The first byte even (02, 06) = on,
odd (03, 07) = off; no entry = on. Switching off writes 03 + the time (as Task Manager does); on writes 02.
Nothing is deleted, so switching back on always works. The PC-wide entries need administrator rights: Windows asks
(a UAC prompt) when you switch one of those."""

import os
import re
import struct
import subprocess
import time
import winreg
from dataclasses import dataclass
from pathlib import Path

from .util import NO_WINDOW

RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN32 = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
USER_FOLDER = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
ALL_FOLDER = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs\StartUp"
HIVES = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}


@dataclass
class StartupApp:
    name: str        # the entry's name (a registry value name, or a shortcut's file name)
    command: str     # what it runs
    hive: str        # "HKCU" (yours) or "HKLM" (the whole PC: needs administrator to switch)
    approved: str    # the StartupApproved subkey that holds its on/off: "Run", "Run32" or "StartupFolder"
    on: bool
    where: str       # for the window: "Registry (you)", "Startup folder (all users)"...

    @property
    def needs_admin(self) -> bool:
        return self.hive == "HKLM"

    @property
    def exe(self) -> str:
        """The program it starts (from the command line; a shortcut's own path for the Startup folder)."""
        return program_of(self.command)


def program_of(command: str) -> str:
    command = os.path.expandvars(command.strip())
    if os.path.exists(command):  # a whole path with spaces (a shortcut whose target couldn't be read)
        return command
    if command.startswith('"'):
        return command[1:].split('"', 1)[0]
    lower = command.lower()
    end = lower.find(".exe")
    return command[:end + 4] if end >= 0 else command.split(" ", 1)[0]


def _values(hive: str, path: str) -> dict[str, object]:
    try:
        with winreg.OpenKey(HIVES[hive], path) as key:
            out, i = {}, 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    return out
                out[name] = value
                i += 1
    except OSError:
        return {}


def _is_on(flags: dict, name: str) -> bool:
    value = flags.get(name)
    return not (isinstance(value, bytes) and value and value[0] % 2 == 1)


def read() -> list[StartupApp]:
    found = []
    for hive, path, approved, where in (("HKCU", RUN, "Run", "Registry (you)"),
                                        ("HKLM", RUN, "Run", "Registry (all users)"),
                                        ("HKLM", RUN32, "Run32", "Registry (all users, 32-bit)")):
        flags = _values(hive, APPROVED + "\\" + approved)
        for name, command in _values(hive, path).items():
            if name and isinstance(command, str):
                found.append(StartupApp(name, command, hive, approved, _is_on(flags, name), where))
    for hive, folder, where in (("HKCU", USER_FOLDER, "Startup folder (you)"),
                                ("HKLM", ALL_FOLDER, "Startup folder (all users)")):
        flags = _values(hive, APPROVED + "\\StartupFolder")
        try:
            files = [f for f in folder.iterdir() if f.is_file() and f.name.lower() != "desktop.ini"]
        except OSError:
            files = []
        for file in files:
            found.append(StartupApp(file.name, _shortcut_target(file), hive, "StartupFolder",
                                    _is_on(flags, file.name), where))
    return sorted(found, key=lambda a: (not a.on, a.name.lower()))


def _shortcut_target(file: Path) -> str:
    """Where a Startup-folder shortcut points (read from the .lnk without starting anything); else the file."""
    if file.suffix.lower() != ".lnk":
        return str(file)
    try:
        data = file.read_bytes()
    except OSError:
        return str(file)
    for text in (data.decode("latin-1"), data.decode("utf-16-le", errors="ignore"),
                 data[1:].decode("utf-16-le", errors="ignore")):
        found = re.search(r"[A-Za-z]:\\[^\x00-\x1f\"*?<>|]*?\.exe", text, re.IGNORECASE)
        if found:
            return _long(found.group(0))
    return str(file)


def _long(path: str) -> str:
    """An old short path (C:/PROGRA~1/TAILSC~1/...) as its full one (C:/Program Files/Tailscale/...)."""
    if "~" not in path:
        return path
    import ctypes
    buffer = ctypes.create_unicode_buffer(1024)
    return buffer.value if ctypes.windll.kernel32.GetLongPathNameW(path, buffer, 1024) else path


def label(app: "StartupApp") -> str:
    """A readable name: no ".lnk", no long code at the end (MicrosoftEdgeAutoLaunch_DDC746D6C976DB45...)."""
    name = re.sub(r"[_-][0-9A-F]{12,}$", "", os.path.splitext(app.name)[0] if app.approved == "StartupFolder"
                  else app.name)
    known = {"MicrosoftEdgeAutoLaunch": "Microsoft Edge", "Mozilla-Firefox": "Firefox",
             "com.squirrel.Teams.Teams": "Microsoft Teams (classic)", "SecurityHealth": "Windows Security (tray icon)",
             "RtkAudUService": "Realtek Audio", "WDDiscovery": "WD Discovery", "GoogleDriveFS": "Google Drive",
             "GoogleDriveSync": "Google Backup and Sync (old)", "AdobeAAMUpdater-1.0": "Adobe updater"}
    return known.get(name, name)


def _flag_bytes(on: bool) -> bytes:
    if on:
        return bytes([2]) + bytes(11)
    filetime = int((time.time() + 11644473600) * 10 ** 7)  # now, as Windows counts time
    return bytes([3, 0, 0, 0]) + struct.pack("<Q", filetime)


def set_on(app: StartupApp, on: bool) -> str:
    """Switch an entry on or off for the next login (what is running now keeps running)."""
    key_path = APPROVED + "\\" + app.approved
    value = _flag_bytes(on)
    if app.hive == "HKCU":
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, app.name, 0, winreg.REG_BINARY, value)
    else:
        # the PC's entries: reg.exe, run as administrator (Windows shows its UAC prompt)
        args = f'add "HKLM\\{key_path}" /v "{app.name}" /t REG_BINARY /d {value.hex()} /f'
        ps = ("$p = Start-Process reg.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ArgumentList $args[0]; "
              "exit $p.ExitCode")
        result = subprocess.run(["powershell", "-NoProfile", "-Command", ps, args], capture_output=True,
                                creationflags=NO_WINDOW)
        if result.returncode != 0 or _is_on(_values("HKLM", key_path), app.name) != on:
            raise RuntimeError(f"{app.name} was not changed (administrator permission was refused or failed).")
    return (f"{app.name} will start when you log in." if on else
            f"{app.name} won't start at login any more (it stays installed; switch it back on any time).")


def running_mb(apps: list[StartupApp], samples: dict, exe_of) -> dict[str, float | None]:
    """Entry name -> RAM its program uses right now (None = not running). A program counts when it IS the entry's
    program or lives in the same folder (Discord's Update.exe starts Discord.exe next to it), except games in
    Steam's library and Windows' own folders (there only the exact program counts)."""
    windows = os.path.normcase(os.environ.get("SystemRoot", r"C:\Windows"))
    paths = {pid: exe_of(pid, item.started) for pid, item in samples.items()}
    out = {}
    for app in apps:
        exe = os.path.normcase(app.exe)
        folder = os.path.dirname(exe) + os.sep if exe.endswith(".exe") else None
        if folder and (folder.startswith(windows) or folder.count(os.sep) < 3):
            folder = None
        total, seen = 0.0, False
        for pid, path in paths.items():
            if not path:
                continue
            if path == exe or (folder and path.startswith(folder) and "\\steamapps\\" not in path):
                total += samples[pid].private_mb
                seen = True
        out[app.name] = total if seen else None
    return out
