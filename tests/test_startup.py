"""Startup apps: reading the on/off flags the way Task Manager writes them, and switching one.
The switch test writes only to a scratch registry key of its own (HKCU\\Software\\KhaltronTest), never the real list."""

import winreg
from collections import namedtuple

import pytest

from monitor import startup

Sample = namedtuple("Sample", "name cpu private_mb session ppid started")


def test_task_managers_flags():
    assert startup._is_on({}, "Steam")                                             # no flag = on
    assert startup._is_on({"Steam": bytes([2]) + bytes(11)}, "Steam")
    assert startup._is_on({"Steam": bytes([6]) + bytes(11)}, "Steam")
    assert not startup._is_on({"Steam": bytes.fromhex("0300000064881772ED21D601")}, "Steam")
    assert startup._flag_bytes(True) == bytes([2]) + bytes(11)
    off = startup._flag_bytes(False)
    assert off[0] == 3 and len(off) == 12


def test_the_program_of_a_command():
    assert startup.program_of('"C:\\Program Files (x86)\\Steam\\steam.exe" -silent') == \
        "C:\\Program Files (x86)\\Steam\\steam.exe"
    assert startup.program_of("C:\\Program Files (x86)\\Overwolf\\OverwolfLauncher.exe -overwolfsilent") == \
        "C:\\Program Files (x86)\\Overwolf\\OverwolfLauncher.exe"


def test_readable_names():
    app = lambda name, folder="Run": startup.StartupApp(name, "", "HKCU", folder, True, "")
    assert startup.label(app("MicrosoftEdgeAutoLaunch_DDC746D6C976DB459CA7A9C1565E3568")) == "Microsoft Edge"
    assert startup.label(app("Mozilla-Firefox-308046B0AF4A39CB")) == "Firefox"
    assert startup.label(app("Tailscale.lnk", "StartupFolder")) == "Tailscale"
    assert startup.label(app("Steam")) == "Steam"


def test_memory_of_what_an_entry_started():
    discord = startup.StartupApp("Discord", r"C:\Users\x\AppData\Local\Discord\Update.exe --processStart Discord.exe",
                                 "HKCU", "Run", True, "")
    steam = startup.StartupApp("Steam", r'"C:\Program Files (x86)\Steam\steam.exe" -silent', "HKCU", "Run", True, "")
    samples = {1: Sample("Discord.exe", 0, 300, 1, 0, 1.0), 2: Sample("steam.exe", 0, 40, 1, 0, 2.0),
               3: Sample("aoe2de_s.exe", 0, 2000, 1, 0, 3.0)}
    paths = {1: r"c:\users\x\appdata\local\discord\app-1.0\discord.exe", 2: r"c:\program files (x86)\steam\steam.exe",
             3: r"c:\program files (x86)\steam\steamapps\common\aoe2de\aoe2de_s.exe"}
    found = startup.running_mb([discord, steam], samples, lambda pid, started: paths[pid])
    assert found == {"Discord": 300, "Steam": 40}  # the game in Steam's library is not Steam's


@pytest.fixture
def scratch_key(monkeypatch):
    path = r"Software\KhaltronTest\StartupApproved"
    monkeypatch.setattr(startup, "APPROVED", path)
    yield path
    for key in (path + r"\Run", path, r"Software\KhaltronTest"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass


def test_switching_off_and_on_again(scratch_key):
    app = startup.StartupApp("Some app", "C:\\x\\app.exe", "HKCU", "Run", True, "Registry (you)")
    assert "won't start" in startup.set_on(app, False)
    assert not startup._is_on(startup._values("HKCU", scratch_key + r"\Run"), "Some app")
    assert "will start" in startup.set_on(app, True)
    assert startup._is_on(startup._values("HKCU", scratch_key + r"\Run"), "Some app")
