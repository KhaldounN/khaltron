"""The HUD parts of the window: stat cards with live graphs, running-job cards with glowing progress bars, and
section headers. Plain tkinter (Canvas and Frame), coloured by theme.py.

Everything here is redrawn from data the window passes in (never read by itself), and the only animation (the
progress bars' glow and the "scanning" bar of a job without a known progress) runs 20 times a second, and stops
while the window is hidden."""

import math
import time
import tkinter as tk
from collections import deque
from tkinter import ttk

from . import actions, theme
from .model import Job
from .util import duration

HISTORY = 90  # samples kept per graph: 3 minutes at one refresh every 2 seconds
SOURCE_COLOURS = {"Book Analyzer": theme.GREEN, "Library": "#38bdf8", "Stage 2": "#c084fc", "Planned": theme.AMBER}


def gb(mb):
    if mb is None:
        return "-"
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


# --- section headers --------------------------------------------------------------------------------------------
class Section(tk.Frame):
    """'▍NOW RUNNING  [3] ──────────' : a HUD heading with a count badge and a rule line."""

    def __init__(self, parent, title: str):
        super().__init__(parent, bg=theme.BG)
        tk.Frame(self, bg=theme.LASER, width=3, height=16).pack(side="left", padx=(0, 8))
        tk.Label(self, text=title.upper(), font=(theme.FONT, 10, "bold"), fg=theme.TEXT, bg=theme.BG).pack(side="left")
        self.badge = tk.Label(self, text="0", font=(theme.MONO, 9, "bold"), fg=theme.LASER, bg=theme.SELECT, padx=6)
        self.badge.pack(side="left", padx=8)
        self.rule = tk.Canvas(self, height=10, bg=theme.BG, highlightthickness=0)
        self.rule.pack(side="left", fill="x", expand=True)
        self.rule.bind("<Configure>", self._draw_rule)

    def _draw_rule(self, event):
        self.rule.delete("all")
        self.rule.create_line(0, 5, event.width - 30, 5, fill=theme.LINE)
        for i in range(3):  # three small ticks at the end, like a HUD
            x = event.width - 22 + i * 8
            self.rule.create_line(x, 2, x, 8, fill=theme.LASER_DARK, width=2)

    def count(self, n: int):
        self.badge.configure(text=str(n), fg=theme.LASER if n else theme.MUTED,
                             bg=theme.SELECT if n else theme.RAISED)


# --- stat cards ---------------------------------------------------------------------------------------------------
class StatCard(tk.Canvas):
    """A HUD panel: a small label, a big number, a line under it, and a live graph of the last 3 minutes."""

    def __init__(self, parent, label: str):
        super().__init__(parent, height=96, bg=theme.PANEL, highlightthickness=0)
        self.label = label
        self.history: deque[float] = deque(maxlen=HISTORY)
        self.value, self.sub, self.colour, self.share = "-", "", theme.TEXT, 0.0
        self.bind("<Configure>", lambda e: self.redraw())

    def update_value(self, share: float, value: str, sub: str, colour: str):
        """share: 0..1, where the graph draws this sample."""
        self.history.append(max(0.0, min(1.0, share)))
        self.value, self.sub, self.colour, self.share = value, sub, colour, share
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        # frame: hairline border and red HUD corners
        self.create_rectangle(0, 0, w - 1, h - 1, outline=theme.LINE)
        k = 8
        for (x, y, dx, dy) in ((0, 0, 1, 1), (w - 1, 0, -1, 1), (0, h - 1, 1, -1), (w - 1, h - 1, -1, -1)):
            self.create_line(x, y + dy * k, x, y, x + dx * k, y, fill=theme.LASER_DARK, width=2)
        # the graph: right 55% of the card, filled under the line
        gx0, gx1, gy0, gy1 = w * 0.52, w - 10, 12, h - 12
        for frac in (0.25, 0.5, 0.75):
            y = gy1 - (gy1 - gy0) * frac
            self.create_line(gx0, y, gx1, y, fill="#151820", dash=(2, 3))
        points = list(self.history)
        if len(points) >= 2:
            step = (gx1 - gx0) / (HISTORY - 1)
            start = gx1 - step * (len(points) - 1)
            xy = [(start + i * step, gy1 - (gy1 - gy0) * v) for i, v in enumerate(points)]
            self.create_polygon(xy[0][0], gy1, *[c for p in xy for c in p], xy[-1][0], gy1,
                                fill=self.colour, outline="", stipple="gray25")
            self.create_line(*[c for p in xy for c in p], fill=self.colour, width=2, smooth=True)
            x, y = xy[-1]
            self.create_oval(x - 3, y - 3, x + 3, y + 3, fill=theme.TEXT, outline=self.colour, width=2)
        # the words
        self.create_text(14, 14, text=self.label.upper(), anchor="w", font=(theme.FONT, 8, "bold"), fill=theme.MUTED)
        size = 17 if w * 0.5 > 230 else 14  # a narrow window: a smaller number, so it never runs into the graph
        self.create_text(14, 38, text=self.value, anchor="w", font=(theme.MONO, size, "bold"), fill=self.colour)
        self.create_text(14, 58, text=self.sub, anchor="nw", font=(theme.FONT, 8), fill=theme.MUTED)


# --- running-job cards ----------------------------------------------------------------------------------------------
class JobCard(tk.Frame):
    """One running job: coloured edge, name and source, what it is doing, a glowing progress bar, its RAM and CPU,
    and its own buttons."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.LINE)
        self.app, self.job = app, None
        self.edge = tk.Frame(self, width=4, bg=theme.GREEN)
        self.edge.pack(side="left", fill="y")
        body = tk.Frame(self, bg=theme.PANEL)
        body.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        top = tk.Frame(body, bg=theme.PANEL)
        top.pack(fill="x")
        self.name = tk.Label(top, font=(theme.FONT, 11, "bold"), fg=theme.TEXT, bg=theme.PANEL, anchor="w")
        self.name.pack(side="left")
        self.source = tk.Label(top, font=(theme.FONT, 8, "bold"), fg=theme.BG, bg=theme.GREEN, padx=6)
        self.source.pack(side="left", padx=10)
        self.times = tk.Label(top, font=(theme.MONO, 9), fg=theme.MUTED, bg=theme.PANEL, anchor="e")
        self.times.pack(side="right")
        self.step = tk.Label(body, font=(theme.FONT, 9), fg=theme.MUTED, bg=theme.PANEL, anchor="w")
        self.step.pack(fill="x", pady=(2, 6))
        self.bar = tk.Canvas(body, height=12, bg=theme.PANEL, highlightthickness=0)
        self.bar.pack(fill="x")

        side = tk.Frame(self, bg=theme.PANEL)
        side.pack(side="right", padx=(0, 12), pady=8)
        self.stats = tk.Label(side, font=(theme.MONO, 10), fg=theme.TEXT, bg=theme.PANEL, justify="right")
        self.stats.pack(anchor="e")
        buttons = tk.Frame(side, bg=theme.PANEL)
        buttons.pack(anchor="e", pady=(6, 0))
        self.buttons = {}
        for action in ("stop", "pause2", "log", "folder"):
            button = ttk.Button(buttons, text=actions.LABELS[action], style="Card.TButton",
                                command=lambda a=action: self.press(a))
            self.buttons[action] = button

    def press(self, action):
        if self.job and action in self.job.actions:
            self.app.act(self.job, action)

    def show(self, job: Job, now: float):
        self.job = job
        colour = SOURCE_COLOURS.get(job.source, theme.GREEN)
        self.edge.configure(bg=colour)
        self.source.configure(text=job.source.upper(), bg=colour)
        self.name.configure(text=job.name)
        self.step.configure(text=" ".join(str(job.step).split())[:160] or "working...")
        ran = duration(now - job.started) if job.started else ""
        left = f"  ·  ~{duration(job.eta_minutes * 60)} left" if job.eta_minutes else ""
        self.times.configure(text=f"{ran}{left}")
        cpu = f"{job.cpu:.0f}%" if job.cpu is not None else "-"
        self.stats.configure(text=f"RAM {gb(job.memory_mb):>7}\nCPU {cpu:>7}")
        for action, button in self.buttons.items():
            if action in job.actions:
                button.pack(side="left", padx=(4, 0))
            else:
                button.pack_forget()
        self.colour = colour

    def animate(self, t: float):
        """The progress bar: a glowing fill with a bright head; a scanning segment when progress is unknown."""
        bar = self.bar
        bar.delete("all")
        w = bar.winfo_width()
        if w < 10 or self.job is None:
            return
        bar.create_rectangle(0, 3, w, 9, fill=theme.RAISED, width=0)
        progress = self.job.progress
        colour = getattr(self, "colour", theme.GREEN)
        if progress is None:
            x = (math.sin(t * 1.6) * 0.5 + 0.5) * (w - 80)
            for i in range(8):  # a short comet that fades behind it
                bar.create_rectangle(x + i * 10, 3, x + i * 10 + 8, 9, width=0,
                                     fill=theme.mix(theme.RAISED, colour, (i + 1) / 8))
            return
        fill = max(2, w * max(0.0, min(1.0, progress)))
        glow = 0.55 + 0.45 * math.sin(t * 3)
        bar.create_rectangle(0, 1, fill, 11, fill=theme.mix(theme.PANEL, colour, 0.25 * glow), width=0)
        bar.create_rectangle(0, 3, fill, 9, fill=theme.mix(theme.mix(theme.BG, colour, 0.55), colour, glow), width=0)
        bar.create_rectangle(fill - 3, 0, fill, 12, fill=theme.TEXT, width=0)  # the bright head
        bar.create_text(min(fill + 6, w - 4), 6, text=f"{progress * 100:.0f}%", anchor="w" if fill + 40 < w else "e",
                        font=(theme.MONO, 8, "bold"), fill=theme.TEXT)


class RunningPanel(tk.Frame):
    """The running jobs as cards (one per job, reused between refreshes), or a calm message when none run."""

    MAX_HEIGHT = 290  # about three cards; more scroll (mouse wheel), so the queue and tabs keep their room

    def __init__(self, parent, app):
        super().__init__(parent, bg=theme.BG)
        self.app = app
        self.cards: dict[str, JobCard] = {}
        # a scrolling area: a Canvas holding a frame with the cards
        self.canvas = tk.Canvas(self, bg=theme.BG, highlightthickness=0, height=60)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=theme.BG)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._fit)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.empty = tk.Label(self.inner, text="◉  No active targets.  K-9000 is watching.", font=(theme.FONT, 10),
                              fg=theme.DIM, bg=theme.BG, pady=18)
        self.started = time.time()
        self.after(50, self.tick)

    def show(self, jobs: list[Job], now: float):
        for job_id in list(self.cards):
            if job_id not in {j.id for j in jobs}:
                self.cards.pop(job_id).destroy()
        for card in self.cards.values():
            card.pack_forget()
        self.empty.pack_forget()
        if not jobs:
            self.empty.pack(fill="x")
        for job in jobs:
            card = self.cards.get(job.id)
            if card is None:
                card = self.cards[job.id] = JobCard(self.inner, self.app)
            card.show(job, now)
            card.pack(fill="x", pady=(0, 6))

    def _fit(self, _event=None):
        """As tall as the cards, up to MAX_HEIGHT; the scrollbar only when they don't fit."""
        needed = self.inner.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, 0, needed), height=min(needed, self.MAX_HEIGHT))
        if needed > self.MAX_HEIGHT:
            self.scroll.pack(side="right", fill="y")
        else:
            self.scroll.pack_forget()
            self.canvas.yview_moveto(0)

    def _wheel(self, event):
        """Scroll the cards with the mouse wheel while the pointer is over them."""
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None and widget is not self:
            widget = widget.master
        if widget is self and self.inner.winfo_reqheight() > self.MAX_HEIGHT:
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def tick(self):
        try:
            if self.winfo_viewable():
                t = time.time() - self.started
                for card in self.cards.values():
                    card.animate(t)
            self.after(50 if self.winfo_viewable() else 500, self.tick)
        except tk.TclError:
            pass


# --- the gaming mode switch ---------------------------------------------------------------------------------------
class GamingSwitch(tk.Canvas):
    """A big sliding switch: 'GAMING MODE' with OFF/ON. Off: grey. On: laser red, the knob glows and pulses.
    While switching: 'SWITCHING...'. A click calls `on_click` (the window does the switching in the background)."""

    W, H = 196, 34

    def __init__(self, parent, on_click):
        super().__init__(parent, width=self.W, height=self.H, bg=theme.BG, highlightthickness=0, cursor="hand2")
        self.on, self.busy, self.hover = False, False, False
        self.started = time.time()
        self.bind("<Button-1>", lambda e: None if self.busy else on_click())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.draw()
        self.after(60, self.tick)

    def _hover(self, inside: bool):
        self.hover = inside
        self.draw()

    def set_state(self, on: bool, busy: bool | None = None):
        changed = on != self.on or (busy is not None and busy != self.busy)
        self.on = on
        if busy is not None:
            self.busy = busy
        if changed:
            self.draw()

    def draw(self, glow: float = 0.0):
        self.delete("all")
        w, h = self.W, self.H
        live = self.on and not self.busy
        edge = theme.LASER if live else (theme.LASER_DARK if self.hover or self.busy else theme.LINE)
        fill = theme.mix(theme.PANEL, theme.LASER_DARK, 0.5 + 0.3 * glow) if live else theme.PANEL
        self.create_rectangle(1, 1, w - 2, h - 2, outline=edge, width=2, fill=fill)
        for x, dx in ((1, 1), (w - 2, -1)):  # HUD notches on the short sides
            self.create_line(x, h / 2 - 6, x + dx * 5, h / 2, x, h / 2 + 6, fill=edge, width=2)
        label = "SWITCHING..." if self.busy else "GAMING MODE"
        self.create_text(14, h / 2, text=label, anchor="w", font=(theme.FONT, 9, "bold"),
                         fill=theme.TEXT if live or self.hover else theme.MUTED)
        # the pill switch on the right
        x0, x1, y0, y1 = w - 74, w - 12, 8, h - 8
        r = (y1 - y0) / 2
        track = theme.LASER if live else theme.RAISED
        self.create_oval(x0, y0, x0 + 2 * r, y1, fill=track, outline="")
        self.create_oval(x1 - 2 * r, y0, x1, y1, fill=track, outline="")
        self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=track, outline="")
        knob = x1 - r if live else x0 + r
        if live:
            halo = 3 + 3 * glow
            self.create_oval(knob - r - halo, y0 - halo, knob + r + halo, y1 + halo, outline=theme.LASER_HOT, width=1)
        self.create_oval(knob - r + 2, y0 + 2, knob + r - 2, y1 - 2, fill=theme.TEXT if live else theme.MUTED, outline="")
        self.create_text(x0 + r + 18 if live else x1 - r - 16, h / 2, text="ON" if live else "OFF",
                         font=(theme.FONT, 7, "bold"), fill="#ffffff" if live else theme.DIM)

    def tick(self):
        """While on (or switching), pulse; otherwise idle."""
        try:
            if (self.on or self.busy) and self.winfo_viewable():
                self.draw(0.5 + 0.5 * math.sin((time.time() - self.started) * 4))
            self.after(80 if self.on or self.busy else 400, self.tick)
        except tk.TclError:
            pass
