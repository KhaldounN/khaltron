"""Auto gaming mode, with stand-ins: the real gaming mode switch and real processes are never touched."""

import json
from collections import namedtuple

import pytest

from monitor import autogame

Sample = namedtuple("Sample", "name cpu private_mb session ppid started")
STEAM = "c:\\program files (x86)\\steam\\steamapps\\common\\"


def test_games_are_recognised_by_their_folder():
    assert autogame.is_game_path(STEAM + "aoe2de\\aoe2de_s.exe", "AoE2DE_s.exe")
    assert autogame.is_game_path("c:\\program files\\epic games\\fortnite\\fortniteclient-win64-shipping.exe",
                                 "FortniteClient-Win64-Shipping.exe")
    assert autogame.is_game_path("c:\\xboxgames\\halo\\content\\halo.exe", "halo.exe")


@pytest.mark.parametrize("path,name", [
    ("c:\\program files (x86)\\steam\\steam.exe", "steam.exe"),                       # the launcher
    (STEAM + "aoe2de\\crashreporter.exe", "CrashReporter.exe"),                     # a helper in a game folder
    (STEAM + "wallpaper_engine\\wallpaper64.exe", "wallpaper64.exe"),               # runs all day
    (STEAM + "steamvr\\bin\\win64\\vrserver.exe", "vrserver.exe"),
    ("c:\\program files\\google\\chrome\\application\\chrome.exe", "chrome.exe"),
])
def test_launchers_helpers_and_tools_are_not_games(path, name):
    assert not autogame.is_game_path(path, name)


class Fake:
    """Gaming mode as a file in tmp_path, and a process list we write ourselves."""

    def __init__(self, tmp_path, monkeypatch):
        self.flag = tmp_path / "gaming.json"
        self.calls = []
        self.paths = {}
        monkeypatch.setattr(autogame, "SETTING", tmp_path / "auto.json")
        monkeypatch.setattr(autogame, "_exe", lambda pid, started: self.paths.get(pid, ""))
        self.front = None
        self.watcher = autogame.Watcher(turn_on=self.on, turn_off=self.off, is_on=self.flag.exists,
                                        flag=lambda: self.flag, front=lambda: self.front)

    def on(self, auto=None):
        self.calls.append("on")
        self.flag.write_text(json.dumps({"auto": auto} if auto else {}), encoding="utf-8")
        return "Gaming mode ON.\n- Frozen: a job\nHave fun!"

    def off(self):
        self.calls.append("off")
        self.flag.unlink()
        return "Gaming mode OFF.\nGaming mode was on for 5 min."


@pytest.fixture
def fake(tmp_path, monkeypatch):
    return Fake(tmp_path, monkeypatch)


EDGE = {1: Sample("msedge.exe", 0, 100, 1, 0, 100.0)}
GAME = {**EDGE, 7: Sample("AoE2DE_s.exe", 30, 2000, 1, 0, 200.0)}


def test_a_game_switches_gaming_mode_on_and_its_end_switches_it_off(fake):
    fake.paths[7] = STEAM + "aoe2de\\aoe2de_s.exe"
    assert fake.watcher.tick(EDGE) == []
    notes = fake.watcher.tick(GAME)
    assert fake.calls == ["on"] and "AoE2DE_s started" in notes[0][0]
    assert fake.watcher.tick(GAME) == []          # still playing: nothing changes
    notes = fake.watcher.tick(EDGE)
    assert fake.calls == ["on", "off"] and "closed" in notes[0][0]


def test_turned_off_by_hand_mid_game_it_stays_off(fake):
    fake.paths[7] = STEAM + "aoe2de\\aoe2de_s.exe"
    fake.watcher.tick(GAME)
    fake.off()                                     # you switched it off yourself
    fake.watcher.tick(GAME)
    fake.watcher.tick(GAME)
    assert fake.calls == ["on", "off"]             # not switched on again for the same game


def test_gaming_mode_you_turned_on_is_never_turned_off(fake):
    fake.paths[7] = STEAM + "aoe2de\\aoe2de_s.exe"
    fake.on()                                      # by hand, before the game
    fake.watcher.tick(GAME)
    fake.watcher.tick(EDGE)                        # the game closed
    assert fake.calls == ["on"] and fake.flag.exists()


def test_the_switch_off_means_no_auto_mode(fake):
    fake.paths[7] = STEAM + "aoe2de\\aoe2de_s.exe"
    autogame.set_enabled(False)
    assert not autogame.enabled()
    assert fake.watcher.tick(GAME) == [] and fake.calls == []
    autogame.set_enabled(True)
    assert fake.watcher.tick(GAME) == []           # already running when you switched it on: yours to decide
    assert fake.calls == []


def test_a_full_screen_program_counts_after_a_few_seconds(fake, monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(autogame.time, "time", lambda: clock["now"])
    other = {**EDGE, 9: Sample("SomeIndieGame.exe", 20, 900, 1, 0, 300.0)}
    fake.front = 9
    assert fake.watcher.tick(other) == []          # just went full screen
    clock["now"] += autogame.FULLSCREEN_SECONDS + 1
    assert fake.watcher.tick(other) and fake.calls == ["on"]


def test_a_full_screen_browser_or_video_is_not_a_game(fake, monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(autogame.time, "time", lambda: clock["now"])
    fake.front = 1                                 # Edge, full screen (a video)
    fake.watcher.tick(EDGE)
    clock["now"] += 60
    assert fake.watcher.tick(EDGE) == [] and fake.calls == []
