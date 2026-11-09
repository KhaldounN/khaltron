"""config.json: plain settings replace the default; a list of apps (a dict) adds to it, and null takes one off."""

import json

from monitor import config


def test_your_apps_add_to_the_default_list(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    (tmp_path / "config.json").write_text(json.dumps({
        "low_memory_mb": 2000,
        "gaming_also_freeze": {"Plex Media Server.exe": "Plex", "WidgetBoard.exe": None},
    }), encoding="utf-8")
    found = config.load()
    assert found["low_memory_mb"] == 2000
    apps = found["gaming_also_freeze"]
    assert apps["Plex Media Server.exe"] == "Plex"      # added
    assert apps["OneDrive.exe"] == "OneDrive sync"       # the defaults stay
    assert "WidgetBoard.exe" not in apps                 # null = taken off


def test_the_default_list_never_holds_what_a_gamer_needs():
    never = ("steam", "epic", "overwolf", "discord", "chrome", "firefox", "msedge", "claude", "msmpeng",
             "audiodg", "tailscale", "explorer", "dwm", "nvcontainer")
    for exe in config.DEFAULTS["gaming_also_freeze"]:
        assert not any(word in exe.lower() for word in never), exe
