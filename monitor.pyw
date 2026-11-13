"""Khaltron 9000 (the Job Monitor): start with  .venv\\Scripts\\pythonw.exe monitor.pyw  (--tray: start hidden in the tray).

Only one copy runs: a second launch tells the first one (through a local port) to show its window, then exits.
The same port takes 'gaming <on|off|toggle|status>' and 'dev ...' from gaming.ps1 / devmode.ps1 (fast hotkeys)."""

import socket
import sys
import threading
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitor import runner  # noqa: E402
from monitor.config import CONFIG  # noqa: E402


def already_running(port: int) -> bool:
    """Ask a running copy to show itself. True when there is one."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1) as connection:
            connection.sendall(b"show\n")
        return True
    except OSError:
        return False


def mode_command(word: str, command: str) -> str:
    """'gaming toggle', 'dev on'...: switch a mode in this running copy and say what was done. The hotkeys and the
    Claude phrases send these (gaming.ps1 / devmode.ps1): a fresh Python for each took ~5 s on a busy PC."""
    from monitor import devmode, gaming
    module = gaming if word == "gaming" else devmode
    actions = {"on": module.turn_on, "off": module.turn_off, "toggle": module.toggle, "status": module.status}
    if command not in actions:
        return "Use: on | off | toggle | status"
    cleaned = module.recover()
    return (cleaned + "\n\n" if cleaned else "") + actions[command]()


def listen(port: int, app) -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))  # only this PC can connect
    server.listen(4)

    def answer(connection):
        with connection:
            try:
                words = connection.recv(64).decode("utf-8", "replace").split()
                if words[:1] == ["show"]:
                    app.results.put(("show", None))
                elif len(words) == 2 and words[0] in ("gaming", "dev"):
                    reply = mode_command(words[0], words[1].lower())
                    app.wake.set()  # the window shows the new mode at once
                    connection.sendall(reply.encode("utf-8"))
            except Exception as error:  # noqa: BLE001 - a bad message must never stop the listener
                try:
                    connection.sendall(f"Khaltron could not do that: {error}".encode("utf-8"))
                except OSError:
                    pass

    def serve():
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=answer, args=(connection,), daemon=True).start()  # a switch takes seconds
    threading.Thread(target=serve, daemon=True).start()
    return server


def main():
    port = CONFIG["port"]
    if already_running(port):
        return
    from monitor import identity
    from monitor.tray import Tray, icon_image
    from monitor.ui import App
    from PIL import ImageTk

    identity.claim()  # notifications say "Khaltron 9000" with the raccoon, not "Python"

    root = tk.Tk()
    holder = {}
    app = App(root, tray=None, start_hidden="--tray" in sys.argv)
    holder["app"] = app
    try:
        app.tray = Tray(app.results, lambda: holder["app"])
    except Exception:  # noqa: BLE001 - no tray (pystray missing): closing the window quits
        app.tray = None
        root.deiconify()  # without a tray, a hidden window could never be shown again
    root.iconphoto(True, ImageTk.PhotoImage(icon_image(64)))
    listen(port, app)
    runner.wake()  # a planned queue left from before (the PC restarted) carries on
    root.mainloop()


if __name__ == "__main__":
    main()
