"""The animated header: Khaltron as a sentinel drone watching your jobs.

A tkinter Canvas redrawn 25 times a second (only moving or recolouring a few shapes, so it costs almost nothing):
- the drone's red eye drifts left and right behind two armour plates, as if scanning;
- a see-through red laser cone sweeps from the eye across the header, with a bright line at its centre;
- a faint scan line rolls down, like an old security monitor;
- the glow pulses. On an alert (a job failed lately, or memory is low) it pulses faster and redder, the plates
  close in (a narrower, angrier eye) and the status says ALERT.
It stops animating while the window is hidden in the tray."""

import math
import time
import tkinter as tk
import tkinter.font as tkfont

from . import theme

HEIGHT = 96
FPS = 25
EYE_X, EYE_Y = 60, 48
VISOR = 22          # the dark visor's radius
SCAN = 7            # how far the pupil drifts left and right
VOID = "#050608"    # the inside of the visor


def _arc(cx, cy, r, start, end, steps=14):
    """Points along a circle, angles in degrees (0 = right, 90 = down: screen coordinates)."""
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in (start + (end - start) * i / steps for i in range(steps + 1))]


class SentinelHeader(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, height=HEIGHT, bg=theme.PANEL, highlightthickness=0)
        self.started = time.time()
        self.alert = False
        self.width = 900
        self.letters: list[int] = []
        self.draw_static()
        self.bind("<Configure>", self.resized)
        self.after(1000 // FPS, self.tick)

    # --- shapes that only move when the window is resized -------------------------------------------------------
    def draw_static(self):
        self.delete("all")
        w = self.width
        for x in range(0, w, 24):  # a faint HUD grid
            self.create_line(x, 0, x, HEIGHT, fill="#11141a")
        for y in range(0, HEIGHT, 24):
            self.create_line(0, y, w, y, fill="#11141a")
        # the laser cone (below the text, so the name stays readable) and its bright centre line
        self.beam = self.create_polygon(0, 0, 0, 0, 0, 0, fill=theme.LASER, outline="", stipple="gray12")
        self.ray = self.create_line(0, 0, 0, 0, fill=theme.LASER, width=1)
        self.dot = self.create_oval(0, 0, 0, 0, fill=theme.LASER_HOT, outline="")
        self.scanline = self.create_line(0, 0, w, 0, fill=theme.mix(theme.PANEL, theme.LASER, 0.28))

        # HUD corner brackets around the drone
        x0, y0, x1, y1, k = EYE_X - 44, 6, EYE_X + 44, HEIGHT - 6, 10
        for (ax, ay, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            self.create_line(ax, ay + dy * k, ax, ay, ax + dx * k, ay, fill=theme.LASER_DARK, width=2)

        # the drone: side fins with lights, armoured body, dark visor
        for side in (-1, 1):
            a, b = EYE_X + side * 28, EYE_X + side * 40
            self.create_polygon(a, EYE_Y - 9, b, EYE_Y - 4, b, EYE_Y + 4, a, EYE_Y + 9, fill=theme.RAISED,
                                outline=theme.METAL)
        self.fin_lights = [self.create_oval(EYE_X + side * 35 - 2, EYE_Y - 2, EYE_X + side * 35 + 2, EYE_Y + 2,
                                            fill=theme.LASER, outline="") for side in (-1, 1)]
        self.create_oval(EYE_X - 31, EYE_Y - 31, EYE_X + 31, EYE_Y + 31, fill=theme.RAISED, outline=theme.METAL,
                         width=2)
        self.create_oval(EYE_X - VISOR, EYE_Y - VISOR, EYE_X + VISOR, EYE_Y + VISOR, fill=VOID, outline="")
        # the eye: glow rings (no see-through colours on a Canvas, so darker reds fake the glow), iris, hot centre
        self.glow = [self.create_oval(0, 0, 0, 0, fill=VOID, outline="") for _ in range(3)]
        self.iris = self.create_oval(0, 0, 0, 0, fill=theme.LASER, outline="")
        self.core = self.create_oval(0, 0, 0, 0, fill=theme.LASER_HOT, outline="")
        self.spark = self.create_oval(0, 0, 0, 0, fill="#ffffff", outline="")
        # armour plates: circle segments with a V edge, over the eye; they close in on an alert
        self.upper = self.create_polygon(0, 0, 0, 0, 0, 0, fill=VOID, outline="")
        self.lower = self.create_polygon(0, 0, 0, 0, 0, 0, fill=VOID, outline="")
        self.upper_edge = self.create_line(0, 0, 0, 0, 0, 0, fill=theme.METAL, width=2)
        self.create_oval(EYE_X - VISOR, EYE_Y - VISOR, EYE_X + VISOR, EYE_Y + VISOR, outline=theme.METAL, width=2)

        # the name, letter by letter (wide spacing), and the tagline
        big = tkfont.Font(family=theme.FONT, size=22, weight="bold")
        x = 124
        self.letters = []
        for letter in theme.NAME.upper():
            self.letters.append(self.create_text(x, 38, text=letter, anchor="w", font=big, fill=theme.TEXT))
            x += big.measure(letter) + 5
        self.create_text(126, 66, text=theme.TAGLINE.upper(), anchor="w", font=(theme.FONT, 8, "bold"),
                         fill=theme.LASER)

        # the status corner
        self.state_text = self.create_text(w - 18, 26, text="◉ WATCHING", anchor="e",
                                           font=(theme.FONT, 10, "bold"), fill=theme.LASER)
        self.clock = self.create_text(w - 18, 48, text="", anchor="e", font=(theme.MONO, 13), fill=theme.TEXT)
        self.counts = self.create_text(w - 18, 70, text="", anchor="e", font=(theme.MONO, 9), fill=theme.MUTED)

    def resized(self, event):
        if event.width != self.width:
            texts = (self.itemcget(self.counts, "text"),) if self.letters else ("",)
            self.width = event.width
            self.draw_static()
            self.itemconfigure(self.counts, text=texts[0])

    # --- what the window tells it -------------------------------------------------------------------------------
    def status(self, running: int, waiting: int, alert: bool):
        self.alert = alert
        self.itemconfigure(self.counts, text=f"{running} RUNNING · {waiting} QUEUED")

    # --- the animation ------------------------------------------------------------------------------------------
    def tick(self):
        try:
            if self.winfo_viewable():
                self.frame(time.time() - self.started)
        except tk.TclError:
            return  # the window was closed
        self.after(1000 // FPS if self.winfo_viewable() else 500, self.tick)

    def frame(self, t: float):
        alert = self.alert
        speed = 2.6 if alert else 1.0
        pulse = 0.5 + 0.5 * math.sin(t * 2.2 * speed)          # 0..1
        # the pupil scans left and right (with a short pause at each side), and bobs a little
        look = math.sin(t * 0.7 * speed)
        look = math.copysign(abs(look) ** 0.6, look)
        ex, ey = EYE_X + SCAN * look, EYE_Y + 1.2 * math.sin(t * 1.3)

        strength = 0.55 + 0.45 * pulse if not alert else 0.75 + 0.25 * pulse
        for ring, (r, share) in zip(self.glow, ((19, 0.22), (16, 0.42), (13, 0.68))):
            self.coords(ring, ex - r, ey - r * 0.8, ex + r, ey + r * 0.8)
            self.itemconfigure(ring, fill=theme.mix(VOID, theme.LASER, share * strength))
        self.coords(self.iris, ex - 10, ey - 10, ex + 10, ey + 10)
        hot = 4 + 1.2 * pulse
        self.coords(self.core, ex - hot, ey - hot, ex + hot, ey + hot)
        self.coords(self.spark, ex - 1.8, ey - 1.8, ex + 1.8, ey + 1.8)
        self.itemconfigure(self.iris, fill=theme.mix(theme.LASER_DARK, theme.LASER, 0.6 + 0.4 * strength))

        # armour plates: an angry V; they close in on an alert
        gap_top, gap_bottom = (4, 5) if not alert else (2, 3)
        rim = VISOR + 1
        top = _arc(EYE_X, EYE_Y, rim, 200, 340)
        self.coords(self.upper, *[v for p in top for v in p],
                    EYE_X + rim * 0.94, EYE_Y - 8 + (2 if alert else 0), EYE_X, EYE_Y - gap_top,
                    EYE_X - rim * 0.94, EYE_Y - 8 + (2 if alert else 0))
        self.coords(self.upper_edge, EYE_X - rim * 0.94, EYE_Y - 8 + (2 if alert else 0), EYE_X, EYE_Y - gap_top,
                    EYE_X + rim * 0.94, EYE_Y - 8 + (2 if alert else 0))
        bottom = _arc(EYE_X, EYE_Y, rim, 20, 160)
        self.coords(self.lower, *[v for p in bottom for v in p],
                    EYE_X - rim * 0.94, EYE_Y + 7 - (2 if alert else 0), EYE_X, EYE_Y + gap_bottom,
                    EYE_X + rim * 0.94, EYE_Y + 7 - (2 if alert else 0))

        # the laser: a cone from the eye sweeping across the header (and back), with a bright centre line
        span = max(200, self.width - 330)
        sweep = 0.5 + 0.5 * math.sin(t * 0.45 * speed)
        target = 120 + span * sweep
        half = 34 + 10 * pulse
        self.coords(self.beam, ex + 9, ey, target - half, HEIGHT, target + half, HEIGHT)
        self.coords(self.ray, ex + 9, ey, target, HEIGHT)
        self.coords(self.dot, target - 3, HEIGHT - 3, target + 3, HEIGHT + 3)
        # a letter of the name lights up red while the laser crosses it
        for letter in self.letters:
            x0, _, x1, _ = self.bbox(letter)
            near = abs((x0 + x1) / 2 - target) < 26
            self.itemconfigure(letter, fill=theme.LASER_HOT if near else theme.TEXT)

        # the scan line rolls down every 3 seconds
        y = (t % 3) / 3 * HEIGHT
        self.coords(self.scanline, 0, y, self.width, y)
        # status corner and fin lights blink
        on = (t * (2.5 if alert else 1.0)) % 1 < 0.6
        self.itemconfigure(self.state_text, text="◉ ALERT" if alert else "◉ WATCHING",
                           fill=(theme.LASER if on else theme.LASER_DARK) if alert else
                           theme.mix(theme.LASER_DARK, theme.LASER, 0.4 + 0.6 * pulse))
        for light in self.fin_lights:
            self.itemconfigure(light, fill=theme.LASER if on else theme.LASER_DARK)
        self.itemconfigure(self.clock, text=time.strftime("%H:%M:%S"))
