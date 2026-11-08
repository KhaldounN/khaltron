"""The tray icon by the clock (pystray): Show window, Alerts on/off, Quit, and Windows notifications.
pystray runs in its own thread; its menu clicks are passed to the window through the window's queue."""

from PIL import Image, ImageDraw


def icon_image(size: int = 64) -> Image.Image:
    """A dark rounded square with three bars of a progress chart."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = size / 64
    draw.rounded_rectangle((2 * s, 2 * s, 62 * s, 62 * s), radius=12 * s, fill=(32, 41, 54, 255))
    for i, (height, colour) in enumerate(((40, (76, 175, 80)), (28, (129, 199, 132)), (16, (200, 230, 201)))):
        x = 12 * s + i * 15 * s
        draw.rounded_rectangle((x, (54 - height) * s, x + 11 * s, 54 * s), radius=3 * s, fill=colour)
    return image


class Tray:
    def __init__(self, results_queue, app_ref):
        import pystray
        self.results, self.app_ref = results_queue, app_ref
        menu = pystray.Menu(
            pystray.MenuItem("Show Job Monitor", lambda: self.results.put(("show", None)), default=True),
            pystray.MenuItem("Alerts", self.toggle_alerts, checked=lambda _: self.app_ref().alerts_on),
            pystray.MenuItem("Quit", lambda: self.results.put(("quit", None))),
        )
        self.icon = pystray.Icon("job_monitor", icon_image(), "Job Monitor", menu)
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
