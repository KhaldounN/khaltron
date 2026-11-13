"""The tray icon by the clock (pystray): Show window, Alerts on/off, Quit, and Windows notifications.
pystray runs in its own thread; its menu clicks are passed to the window through the window's queue."""

from PIL import Image, ImageDraw

from . import autogame, devmode, gaming, theme


def icon_image(size: int = 64) -> Image.Image:
    """Khaltron 9000's logo (theme.logo): the sentinel drone's red eye."""
    return theme.logo(size)


class Tray:
    def __init__(self, results_queue, app_ref):
        import pystray
        self.results, self.app_ref = results_queue, app_ref
        menu = pystray.Menu(
            pystray.MenuItem(f"Show {theme.NAME}", lambda: self.results.put(("show", None)), default=True),
            pystray.MenuItem("Gaming mode", lambda: self.results.put(("gaming", None)),
                             checked=lambda _: gaming.is_on()),
            pystray.MenuItem("Development mode", lambda: self.results.put(("devmode", None)),
                             checked=lambda _: devmode.is_on()),
            pystray.MenuItem("Auto gaming mode (when a game starts)", lambda: self.results.put(("auto_gaming", None)),
                             checked=lambda _: autogame.enabled()),
            pystray.MenuItem("Alerts", self.toggle_alerts, checked=lambda _: self.app_ref().alerts_on),
            pystray.MenuItem("Quit", lambda: self.results.put(("quit", None))),
        )
        self.icon = pystray.Icon("khaltron", icon_image(), theme.NAME, menu)
        self.icon.run_detached()

    def toggle_alerts(self):
        app = self.app_ref()
        app.alerts_on = not app.alerts_on

    def notify(self, title: str, message: str):
        try:
            self.icon.notify(message[:250], title[:60])
        except Exception:  # noqa: BLE001 - a notification failing must not stop the window
            pass

    def set_tooltip(self, text: str):
        try:
            self.icon.title = text[:120]
        except Exception:  # noqa: BLE001
            pass

    def stop(self):
        try:
            self.icon.stop()
        except Exception:  # noqa: BLE001
            pass
