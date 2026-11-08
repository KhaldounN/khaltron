"""Khaltron (the Job Monitor): start with  .venv\\Scripts\\pythonw.exe monitor.pyw  (--tray: start hidden in the tray).

Only one copy runs: a second launch tells the first one (through a local port) to show its window, then exits."""

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


def listen(port: int, results) -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))  # only this PC can connect
    server.listen(2)

    def serve():
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return
            with connection:
                if connection.recv(16).startswith(b"show"):
                    results.put(("show", None))
    threading.Thread(target=serve, daemon=True).start()
    return server


def main():
    port = CONFIG["port"]
    if already_running(port):
        return
    from monitor.tray import Tray, icon_image
    from monitor.ui import App
    from PIL import ImageTk

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
    listen(port, app.results)
    runner.wake()  # a planned queue left from before (the PC restarted) carries on
    root.mainloop()


if __name__ == "__main__":
    main()
