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

    def __init__(self, parent, title: str, badge: bool = True):
        super().__init__(parent, bg=theme.BG)
        tk.Frame(self, bg=theme.LASER, width=3, height=16).pack(side="left", padx=(0, 8))
        tk.Label(self, text=title.upper(), font=(theme.FONT, 9, "bold"), fg=theme.TEXT, bg=theme.BG).pack(side="left")
        self.badge = tk.Label(self, text="0", font=(theme.MONO, 9, "bold"), fg=theme.LASER, bg=theme.SELECT, padx=6)
        if badge:
            self.badge.pack(side="left", padx=8)
        else:
            tk.Frame(self, width=8, bg=theme.BG).pack(side="left")
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
        super().__init__(parent, height=92, bg=theme.PANEL, highlightthickness=0)
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
        self.create_text(14, 35, text=self.value, anchor="w", font=(theme.MONO, size, "bold"), fill=self.colour)
        self.create_text(14, 52, text=self.sub, anchor="nw", font=(theme.FONT, 8), fill=theme.MUTED)


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
        self.name = tk.Label(top, font=(theme.FONT, 10, "bold"), fg=theme.TEXT, bg=theme.PANEL, anchor="w")
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

    def _set(self, widget, **options):
        """Change a label only when something changed: every change makes Tk lay out and repaint the window."""
        key = (id(widget), tuple(sorted(options.items())))
        if self._last.get(id(widget)) != key:
            self._last[id(widget)] = key
            widget.configure(**options)

    def show(self, job: Job, now: float):
        self.job = job
        if not hasattr(self, "_last"):
            self._last, self._buttons = {}, None
        colour = SOURCE_COLOURS.get(job.source, theme.GREEN)
        self._set(self.edge, bg=colour)
        self._set(self.source, text=job.source.upper(), bg=colour)
        self._set(self.name, text=job.name)
        self._set(self.step, text=" ".join(str(job.step).split())[:160] or "working...")
        ran = duration(now - job.started) if job.started else ""
        left = f"  ·  ~{duration(job.eta_minutes * 60)} left" if job.eta_minutes else ""
        self._set(self.times, text=f"{ran}{left}")
        cpu = f"{job.cpu:.0f}%" if job.cpu is not None else "-"
        self._set(self.stats, text=f"RAM {gb(job.memory_mb):>7}\nCPU {cpu:>7}")
        wanted = [a for a in self.buttons if a in job.actions]
        if wanted != self._buttons:  # buttons are re-packed only when the job's actions change
            self._buttons = wanted
            for button in self.buttons.values():
                button.pack_forget()
            for action in wanted:
                self.buttons[action].pack(side="left", padx=(4, 0))
        self.colour = colour

    def _bar_items(self):
        """The bar's shapes, made once: each frame only moves and recolours them (deleting and re-making every
        shape 20 times a second was most of the window's own CPU)."""
        bar = self.bar
        self.items = {
            "track": bar.create_rectangle(0, 3, 0, 9, fill=theme.RAISED, width=0),
            "halo": bar.create_rectangle(0, 1, 0, 11, width=0),
            "fill": bar.create_rectangle(0, 3, 0, 9, width=0),
            "head": bar.create_rectangle(0, 0, 0, 12, fill=theme.TEXT, width=0),
            "pct": bar.create_text(0, 6, text="", font=(theme.MONO, 8, "bold"), fill=theme.TEXT),
        }
        self.shown_pct = None

    def animate(self, t: float):
        """The progress bar: a glowing fill with a bright head. When progress is unknown (a planned job, say) only
        the still, empty track shows (the owner found a moving bar there distracting)."""
        bar = self.bar
        w = bar.winfo_width()
        if w < 10 or self.job is None:
            return
        if not hasattr(self, "items"):
            self._bar_items()
        items = self.items
        bar.coords(items["track"], 0, 3, w, 9)
        progress = self.job.progress
        colour = getattr(self, "colour", theme.GREEN)
        unknown = progress is None
        for key in ("halo", "fill", "head", "pct"):
            bar.itemconfigure(items[key], state="hidden" if unknown else "normal")
        if unknown:
            return
        fill = max(2, w * max(0.0, min(1.0, progress)))
        glow = 0.55 + 0.45 * math.sin(t * 3)
        bar.coords(items["halo"], 0, 1, fill, 11)
        bar.itemconfigure(items["halo"], fill=theme.mix(theme.PANEL, colour, 0.25 * glow))
        bar.coords(items["fill"], 0, 3, fill, 9)
        bar.itemconfigure(items["fill"], fill=theme.mix(theme.mix(theme.BG, colour, 0.55), colour, glow))
        bar.coords(items["head"], fill - 3, 0, fill, 12)
        text = f"{progress * 100:.0f}%"
        if text != self.shown_pct:
            self.shown_pct = text
            bar.itemconfigure(items["pct"], text=text)
        bar.coords(items["pct"], min(fill + 6, w - 4), 6)
        bar.itemconfigure(items["pct"], anchor="w" if fill + 40 < w else "e")


class RunningPanel(tk.Frame):
    """The running jobs as cards (one per job, reused between refreshes), or a calm message when none run."""

    MAX_HEIGHT = 250  # about two and a half cards; more scroll (mouse wheel), so the queue and tabs keep their room

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
        order = [j.id for j in jobs]
        for job_id in list(self.cards):
            if job_id not in order:
                self.cards.pop(job_id).destroy()
        for job in jobs:
            card = self.cards.get(job.id)
            if card is None:
                card = self.cards[job.id] = JobCard(self.inner, self.app)
            card.show(job, now)
        if order != getattr(self, "order", None):  # re-arranged only when the jobs (or their order) change
            self.order = order
            for card in self.cards.values():
                card.pack_forget()
            self.empty.pack_forget()
            if not jobs:
                self.empty.pack(fill="x")
            for job_id in order:
                self.cards[job_id].pack(fill="x", pady=(0, 6))

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
            self.after(theme.pace(self, 66), self.tick)  # 15 frames a second while you look at it
        except tk.TclError:
            pass


# --- the simple overview ------------------------------------------------------------------------------------------
class ViewSwitch(tk.Frame):
    """[ OVERVIEW | DETAILS ]: two tabs drawn as one segmented control; the chosen one is lit."""

    def __init__(self, parent, views: list[str], on_change):
        super().__init__(parent, bg=theme.LINE, padx=1, pady=1)
        self.on_change, self.labels, self.current = on_change, {}, None
        for view in views:
            label = tk.Label(self, text=view.upper(), font=(theme.FONT, 9, "bold"), padx=16, pady=5, cursor="hand2")
            label.pack(side="left", padx=(0 if not self.labels else 1, 0))
            label.bind("<Button-1>", lambda e, v=view: self.on_change(v))
            self.labels[view] = label
        self.select(views[0])

    def select(self, view: str):
        self.current = view
        for name, label in self.labels.items():
            on = name == view
            label.configure(bg=theme.SELECT if on else theme.PANEL, fg=theme.TEXT if on else theme.MUTED)


class Briefing(tk.Frame):
    """The one-sentence summary at the top: a status chip (CALM, WORKING, BUSY, LOW MEMORY, GAMING) and what is
    going on in plain words, with a machine-style prompt above it."""

    def __init__(self, parent):
        super().__init__(parent, bg=theme.BG)
        tk.Label(self, text="> SYSTEM BRIEFING", font=(theme.MONO, 8), fg=theme.LASER_DARK, bg=theme.BG).pack(anchor="w")
        row = tk.Frame(self, bg=theme.BG)
        row.pack(fill="x", pady=(2, 0))
        self.chip = tk.Label(row, font=(theme.FONT, 9, "bold"), padx=10, pady=2)
        self.chip.pack(side="left")
        self.sentence = tk.Label(row, font=(theme.FONT, 10), fg=theme.TEXT, bg=theme.BG, anchor="w", justify="left")
        self.sentence.pack(side="left", padx=12, fill="x", expand=True)
        self.shown = None

    def show(self, chip: str, colour: str, sentence: str):
        if (chip, colour, sentence) == self.shown:
            return
        self.shown = (chip, colour, sentence)
        self.chip.configure(text=chip, bg=colour, fg=theme.BG)
        self.sentence.configure(text=sentence)
        self.sentence.configure(wraplength=max(300, self.winfo_width() - 160))


class NextList(tk.Frame):
    """The next few waiting jobs, in plain words; '+N more' opens the Details view."""

    SHOWN = 3

    def __init__(self, parent, on_more):
        super().__init__(parent, bg=theme.BG)
        self.on_more, self.shown = on_more, None
        self.rows = tk.Frame(self, bg=theme.BG)
        self.rows.pack(fill="x")

    def show(self, jobs: list[Job]):
        key = tuple((j.id, j.name, j.step) for j in jobs[:self.SHOWN]) + (len(jobs),)
        if key == self.shown:
            return
        self.shown = key
        for child in self.rows.winfo_children():
            child.destroy()
        if not jobs:
            tk.Label(self.rows, text="Nothing waiting.", font=(theme.FONT, 10), fg=theme.DIM, bg=theme.BG,
                     anchor="w").pack(fill="x", pady=4)
            return
        for number, job in enumerate(jobs[:self.SHOWN], 1):
            row = tk.Frame(self.rows, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.LINE)
            row.pack(fill="x", pady=(0, 3))
            tk.Label(row, text=str(number), font=(theme.MONO, 10, "bold"), fg=theme.LASER, bg=theme.PANEL,
                     width=3).pack(side="left", padx=(4, 2), pady=4)
            words = tk.Frame(row, bg=theme.PANEL)
            words.pack(side="left", fill="x", expand=True, pady=3)
            tk.Label(words, text=job.name, font=(theme.FONT, 9, "bold"), fg=theme.TEXT, bg=theme.PANEL,
                     anchor="w").pack(fill="x")
            step = " ".join(str(job.step).split())
            tk.Label(words, text=step[:90] + ("..." if len(step) > 90 else ""), font=(theme.FONT, 8),
                     fg=theme.MUTED, bg=theme.PANEL, anchor="w").pack(fill="x")
        more = len(jobs) - self.SHOWN
        if more > 0:
            link = tk.Label(self.rows, text=f"+ {more} more  ▸  see Details", font=(theme.FONT, 9, "bold"),
                            fg=theme.LASER, bg=theme.BG, cursor="hand2", anchor="w")
            link.pack(fill="x", pady=(2, 0))
            link.bind("<Button-1>", lambda e: self.on_more())
