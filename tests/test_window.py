"""Smoke test of the window itself (2026-11-13): build Khaltron's whole window, read the PC once and draw everything,
hidden and shown. Catches what the logic tests can't, like a broken string that only fails when the window is built.
Read-only: no background threads, no auto gaming mode, no mode switch (the mode files are temporary, conftest.py)."""

import time
import tkinter as tk

import pytest

from monitor import autogame, ui
from monitor.collect import collect


@pytest.fixture
def window(monkeypatch, tmp_path):
    monkeypatch.setattr(ui.App, "reader", lambda self: None)          # no background refresh thread
    monkeypatch.setattr(ui.App, "recover_modes", lambda self: None)
    monkeypatch.setattr(autogame, "enabled", lambda: False)           # never switch gaming mode on
    monkeypatch.setattr(ui, "LITE", tmp_path / "lite.json")
    root = None
    for attempt in range(3):  # making a Tk window right after another one closed now and then fails for a moment
        try:
            root = tk.Tk()
            break
        except tk.TclError as error:
            last = error
            time.sleep(0.5)
    if root is None:
        pytest.fail(f"the window could not be made: {last}")
    root.geometry("1180x900+0+0")
    app = ui.App(root, tray=None)
    yield root, app
    root.destroy()


def test_the_window_builds_and_draws_a_real_refresh(window):
    root, app = window
    root.update()
    state = collect(True)
    app.visible = True
    app.draw(state)
    root.update()
    assert app.ram_card.value != "-" and app.cpu_card.value != "-"
    assert app.status.cget("text").startswith("Updated")


def test_hidden_it_only_does_the_background_duties(window):
    root, app = window
    app.visible = False
    state = collect(False)
    app.draw(state)
    assert app.pending is state             # kept for later, not drawn
    app.shown()
    root.update()
    assert app.pending is None and app.visible


def test_the_lite_look_and_every_view_switch(window):
    root, app = window
    app.set_lite(True)
    assert app.header.lite
    app.set_lite(False)
    for view in ("Details", "About", "Overview"):
        app.show_view(view)
        root.update()
