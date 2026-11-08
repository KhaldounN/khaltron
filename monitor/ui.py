"""The window (tkinter). Reading happens in a background thread every few seconds, and so do the actions, so the
window never freezes; results come back through a queue that the window checks 5 times a second."""

import queue
import shlex
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import actions, alerts, gaming, planned, runner, theme
from .collect import State, collect
from .config import BOOK, CONFIG
from .model import DONE, FAILED, RUNNING, STOPPED, WAITING, Job
from .util import duration, when

GREEN, AMBER, RED, GREY = theme.GREEN, theme.AMBER, theme.RED, theme.MUTED
SEGMENTS = 24  # the memory gauge is drawn as a row of segments


def bar(progress: float | None, width: int = 10) -> str:
    if progress is None:
        return ""
    progress = max(0.0, min(1.0, progress))
    full = round(progress * width)
    return "▰" * full + "▱" * (width - full) + f" {progress * 100:.0f}%"


def gb(mb: float | None) -> str:
    if mb is None:
        return ""
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


class Table(ttk.Frame):
    """A list (ttk.Treeview) with a row of buttons under it; each button is enabled when the selected row allows
    that action. Rows are matched by job id between refreshes, so the selection stays put."""

    def __init__(self, parent, app, columns: list[tuple[str, str, int]], buttons: list[str], height: int = 5):
        super().__init__(parent)
        self.app, self.jobs = app, {}
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings", height=height,
                                 selectmode="browse")
        for key, title, width in columns:
            self.tree.heading(key, text=title, anchor="w")
            self.tree.column(key, width=width, minwidth=40, stretch=key in ("name", "step"), anchor="w")
        for state, colour in ((RUNNING, GREEN), (FAILED, RED), ("ended", AMBER), (STOPPED, AMBER),
                              (WAITING, theme.TEXT), (DONE, GREY), ("protected", GREY)):
            self.tree.tag_configure(state, foreground=colour)
        self.tree.tag_configure("odd", background="#0d1320")  # every other row a shade darker
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        row = ttk.Frame(self)
        row.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.buttons = {}
        for action in buttons:
            button = ttk.Button(row, text=actions.LABELS[action], command=lambda a=action: self.press(a))
            button.pack(side="left", padx=(0, 4))
            self.buttons[action] = button
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.enable())
        self.tree.bind("<Double-1>", lambda _: self.press("log"))
        self.enable()

    def selected(self) -> Job | None:
        chosen = self.tree.selection()
        return self.jobs.get(chosen[0]) if chosen else None

    def enable(self):
        job = self.selected()
        for action, button in self.buttons.items():
            button.state(["!disabled"] if job and action in job.actions else ["disabled"])

    def press(self, action: str):
        job = self.selected()
        if job and action in job.actions:
            self.app.act(job, action)

    def show(self, jobs: list[Job], values):
        flat = values
        values = lambda i, j: tuple(" ".join(str(v).split()) if isinstance(v, str) else v for v in flat(i, j))
        self.jobs = {job.id: job for job in jobs}
        present = set(self.tree.get_children())
        for gone in present - set(self.jobs):
            self.tree.delete(gone)
        for index, job in enumerate(jobs):
            tag = "protected" if job.ref.get("protected") else job.state
            if job.id in present:
                self.tree.item(job.id, values=values(index, job), tags=(tag, "odd") if index % 2 else (tag,))
                self.tree.move(job.id, "", index)
            else:
                self.tree.insert("", index, iid=job.id, values=values(index, job),
                                 tags=(tag, "odd") if index % 2 else (tag,))
        self.enable()


class App:
    def __init__(self, root: tk.Tk, tray=None, start_hidden: bool = False):
        self.root, self.tray = root, tray
        self.results: queue.Queue = queue.Queue()
        self.wake = threading.Event()
        self.watcher = alerts.Watcher()
        self.alerts_on = True
        self.hidden_once = False
        self.gaming_was = None  # gaming mode at the last refresh (a change pops up a notification)
        root.title(theme.NAME)
        root.geometry("1080x760")
        root.minsize(760, 520)
        root.protocol("WM_DELETE_WINDOW", self.hide)
        theme.apply(root)
        self.build()
        theme.dark_title_bar(root)
        if start_hidden:
            root.withdraw()
        threading.Thread(target=self.reader, daemon=True).start()
        root.after(200, self.poll)

    # --- layout ---------------------------------------------------------------------------------------------
    def build(self):
        self.brand()
        outer = ttk.Frame(self.root, padding=(14, 10, 14, 10))
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text="MEMORY FREE", style="Small.TLabel").pack(side="left")
        self.memory_bar = tk.Canvas(top, width=SEGMENTS * 10, height=16, highlightthickness=0, bg=theme.BG)
        self.memory_bar.pack(side="left", padx=8)
        self.memory_text = ttk.Label(top, text="...", style="Stat.TLabel")
        self.memory_text.pack(side="left")
        ttk.Label(top, text="CPU", style="Small.TLabel").pack(side="left", padx=(22, 6))
        self.cpu_text = ttk.Label(top, text="", style="Stat.TLabel")
        self.cpu_text.pack(side="left")
        start = ttk.Menubutton(top, text="Start / control")
        menu = tk.Menu(start, tearoff=False)
        menu.add_command(label="Add a job to the planned queue...", command=self.add_dialog)
        menu.add_separator()
        menu.add_command(label="Start the library pre-analysis", command=lambda: self.global_action(
            "Start the library pre-analysis?\n\nIt analyzes every library book without a saved result, shortest "
            "first, in the background (books already done are skipped).", actions.start_library))
        menu.add_command(label="Resume stage 2", command=lambda: self.global_action(
            actions.question(Job("", "", "", ""), "resume2"), actions.resume_stage2))
        menu.add_command(label="Pause stage 2", command=lambda: self.global_action(
            actions.question(Job("", "", "", ""), "pause2"), actions.pause_stage2))
        menu.add_separator()
        menu.add_command(label="Pause the planned queue", command=lambda: self.global_action(
            "Pause the planned queue?\n\nJobs already running go on; no new planned job starts until you resume.",
            lambda: actions.set_queue_paused(True)))
        menu.add_command(label="Resume the planned queue", command=lambda: self.global_action(
            "Resume the planned queue?", lambda: actions.set_queue_paused(False)))
        menu.add_separator()
        menu.add_command(label="Gaming mode on / off (Ctrl+Alt+G)", command=self.toggle_gaming)
        menu.add_separator()
        menu.add_command(label="Open the Book Analyzer results folder", command=lambda: self.open_path(BOOK / "results"))
        menu.add_command(label="Refresh now", command=self.wake.set)
        start["menu"] = menu
        start.pack(side="right")
        ttk.Button(top, text="Hide to tray", command=self.hide).pack(side="right", padx=6)

        self.flags = ttk.Label(outer, text="", style="Flag.TLabel")
        self.flags.pack(fill="x", pady=(4, 0))

        panes = ttk.PanedWindow(outer, orient="vertical")
        panes.pack(fill="both", expand=True, pady=(6, 0))

        box = ttk.Frame(panes)
        ttk.Label(box, text="Now running", style="Section.TLabel").pack(anchor="w")
        self.running = Table(box, self, [("name", "Job", 220), ("source", "From", 95), ("step", "Doing now", 290),
                                         ("progress", "Progress", 110), ("time", "Running for", 85),
                                         ("left", "Time left", 75), ("memory", "Memory", 70)],
                             ["stop", "pause2", "log", "folder"], height=4)
        self.running.pack(fill="both", expand=True)
        panes.add(box, weight=2)

        box = ttk.Frame(panes)
        ttk.Label(box, text="Up next", style="Section.TLabel").pack(anchor="w", pady=(8, 0))
        self.waiting = Table(box, self, [("pos", "#", 36), ("name", "Job", 270), ("source", "Queue", 110),
                                         ("step", "Waiting for", 380), ("added", "Added", 90)],
                             ["up", "down", "runnow", "remove", "stop", "log"], height=6)
        self.waiting.pack(fill="both", expand=True)
        panes.add(box, weight=3)

        tabs = ttk.Notebook(panes)
        self.finished = Table(tabs, self, [("name", "Job", 270), ("source", "From", 110), ("state", "Result", 80),
                                           ("step", "Details", 380), ("when", "Ended", 90)], ["log"], height=6)
        self.tasks = Table(tabs, self, [("name", "Task", 250), ("state", "State", 80), ("step", "Status", 330),
                                        ("last", "Last run", 100), ("next", "Next run", 100)], ["runtask"], height=6)
        self.procs = Table(tabs, self, [("name", "Process", 250), ("pid", "PID", 70), ("memory", "Memory", 80),
                                        ("cpu", "CPU", 60), ("time", "Running for", 90), ("step", "Command", 380)],
                           ["stop"], height=6)
        self.problems = tk.Text(tabs, height=6, wrap="word", font=(theme.MONO, 9), relief="flat", bg=theme.PANEL,
                                fg=theme.MUTED, insertbackground=theme.CYAN, padx=10, pady=8, highlightthickness=0)
        tabs.add(self.finished, text="Finished")
        tabs.add(self.tasks, text="Scheduled tasks")
        tabs.add(self.procs, text="Python processes")
        tabs.add(self.problems, text="Problems")
        panes.add(tabs, weight=3)

        self.status = ttk.Label(outer, text="Starting...", style="Small.TLabel")
        self.status.pack(fill="x", pady=(6, 0))

    def brand(self):
        """The header: logo, name, tagline, a live dot that blinks on every refresh, and the clock."""
        from PIL import ImageTk
        header = tk.Frame(self.root, bg=theme.PANEL)
        header.pack(fill="x")
        self.logo_image = ImageTk.PhotoImage(theme.logo(44))
        tk.Label(header, image=self.logo_image, bg=theme.PANEL).pack(side="left", padx=(14, 10), pady=10)
        words = tk.Frame(header, bg=theme.PANEL)
        words.pack(side="left")
        tk.Label(words, text=theme.NAME.upper(), font=(theme.FONT, 19, "bold"), fg=theme.TEXT,
                 bg=theme.PANEL).pack(anchor="w")
        tk.Label(words, text=theme.TAGLINE.upper(), font=(theme.FONT, 8, "bold"), fg=theme.CYAN,
                 bg=theme.PANEL).pack(anchor="w")
        self.clock = tk.Label(header, text="", font=(theme.MONO, 11), fg=theme.MUTED, bg=theme.PANEL)
        self.clock.pack(side="right", padx=(6, 16))
        self.live = tk.Label(header, text="\u25cf LIVE", font=(theme.FONT, 9, "bold"), fg=theme.GREEN, bg=theme.PANEL)
        self.live.pack(side="right")
        glow = tk.Canvas(self.root, height=2, highlightthickness=0, bg=theme.BG)
        glow.pack(fill="x")
        glow.bind("<Configure>", lambda event: self.glow_line(glow, event.width))

    @staticmethod
    def glow_line(canvas: tk.Canvas, width: int):
        """A thin cyan-to-violet line under the header."""
        canvas.delete("all")
        start, end = theme._rgb(theme.CYAN), theme._rgb(theme.VIOLET)
        steps = 60
        for i in range(steps):
            t = i / (steps - 1)
            colour = "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(start, end))
            canvas.create_rectangle(width * i / steps, 0, width * (i + 1) / steps + 1, 2, fill=colour, width=0)

    # --- reading in the background --------------------------------------------------------------------------
    def reader(self):
        last_slow = 0.0
        while True:
            slow = time.time() - last_slow >= CONFIG["slow_refresh_seconds"]
            if slow:
                last_slow = time.time()
            try:
                for frozen in gaming.enforce():  # gaming mode: a job that started anyway is frozen too
                    self.results.put(("notify", ("Gaming mode: job frozen", frozen)))
            except Exception as error:  # noqa: BLE001
                self.results.put(("message", f"Gaming mode check failed: {error}"))
            try:
                self.results.put(("state", collect(slow)))
            except Exception as error:  # noqa: BLE001
                self.results.put(("message", f"Reading failed: {error}"))
            self.wake.wait(CONFIG["refresh_seconds"])
            self.wake.clear()

    def poll(self):
        try:
            while True:
                kind, value = self.results.get_nowait()
                if kind == "state":
                    self.draw(value)
                elif kind == "message":
                    self.status.configure(text=value)
                elif kind == "error":
                    messagebox.showerror(theme.NAME, value, parent=self.root)
                elif kind == "notify":
                    if self.tray:
                        self.tray.notify(*value)
                elif kind == "gaming":
                    self.toggle_gaming()
                elif kind == "show":
                    self.show()
                elif kind == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(200, self.poll)

    # --- drawing ---------------------------------------------------------------------------------------------
    def draw(self, state: State):
        now = time.time()
        h = state.health
        if h:
            limit = CONFIG["low_memory_mb"]
            colour = RED if h.free_mb < limit else AMBER if h.free_mb < 2 * limit else GREEN
            share = h.free_mb / h.total_mb if h.total_mb else 0
            self.memory_bar.delete("all")
            lit = round(SEGMENTS * min(1, share))
            for i in range(SEGMENTS):
                self.memory_bar.create_rectangle(i * 10, 2, i * 10 + 7, 14, width=0,
                                                 fill=colour if i < lit else theme.RAISED)
            self.memory_text.configure(text=f"{gb(h.free_mb)} / {gb(h.total_mb)}", foreground=colour)
            self.cpu_text.configure(text=f"{h.cpu:.0f}%",
                                    foreground=RED if h.cpu > 85 else AMBER if h.cpu > 60 else theme.TEXT)
        self.clock.configure(text=time.strftime("%H:%M:%S"))
        self.live.configure(fg=theme.GREEN if self.live.cget("fg") != theme.GREEN else theme.CYAN_DARK)
        flags = []
        playing = gaming.is_on()
        if playing:
            flags.append("GAMING MODE is on: background jobs are frozen (Start / control > Gaming mode off).")
        if playing != self.gaming_was and self.gaming_was is not None and self.tray:
            self.tray.notify("Gaming mode " + ("ON" if playing else "OFF"),
                             "Background jobs frozen, voice off. Have fun!" if playing else "Background jobs carry on.")
        self.gaming_was = playing
        if state.stage2_paused and any(j.source == "Stage 2" for j in state.waiting):
            flags.append("Stage 2 is paused (Start / control > Resume stage 2).")
        if state.queue_paused:
            flags.append("The planned queue is paused (Start / control > Resume the planned queue).")
        if h and h.free_mb < CONFIG["low_memory_mb"]:
            flags.append("Memory is low: a new job may be ended by Windows.")
        self.flags.configure(text="   ".join(flags))

        self.running.show(state.running, lambda i, j: (
            j.name, j.source, j.step, bar(j.progress), duration(now - j.started) if j.started else "",
            f"~{duration(j.eta_minutes * 60)}" if j.eta_minutes else "", gb(j.memory_mb)))
        self.waiting.show(state.waiting, lambda i, j: (
            i + 1, j.name, j.source, j.step, when(j.started)))
        history = sorted(state.finished + alerts.history(), key=lambda j: j.finished or 0, reverse=True)[:40]
        self.finished.show(history, lambda i, j: (j.name, j.source, j.state, j.step, when(j.finished)))
        self.tasks.show(state.tasks, lambda i, j: (j.name, j.state, j.step, when(j.started), when(j.finished)))
        self.procs.show(state.processes, lambda i, j: (
            j.name + ("  (protected)" if j.ref.get("protected") else ""), j.pid, gb(j.memory_mb),
            f"{j.ref.get('cpu', 0):.0f}%", duration(now - j.started) if j.started else "", j.step))
        self.problems.delete("1.0", "end")
        self.problems.insert("end", "\n".join(state.errors) or "No problems reading the jobs.")

        idle = not state.running
        self.status.configure(text=f"Updated {time.strftime('%H:%M:%S')} ({state.taken:.1f} s).  "
                                   + ("Nothing is running." if idle else f"{len(state.running)} running, "
                                      f"{len(state.waiting)} waiting.")
                                   + f"  Planned queue runner: {'on' if runner.is_running() else 'off'}.")
        if self.tray:
            self.tray.set_tooltip(f"{theme.NAME}: {len(state.running)} running, {len(state.waiting)} waiting")
        for title, message in self.watcher.changes(state):
            if self.alerts_on and self.tray:
                self.tray.notify(title, message)

    # --- actions ---------------------------------------------------------------------------------------------
    def act(self, job: Job, action: str):
        if action not in actions.HARMLESS:
            if not messagebox.askyesno("Are you sure?", actions.question(job, action), parent=self.root):
                return
        self.run_in_background(lambda: actions.do(job, action))

    def toggle_gaming(self):
        """No "are you sure?": it is meant to be quick, and switching it back undoes everything it did."""
        def do():
            message = gaming.toggle()
            self.wake.set()
            return message.splitlines()[0]
        self.run_in_background(do)

    def global_action(self, text: str, do):
        if messagebox.askyesno("Are you sure?", text, parent=self.root):
            self.run_in_background(do)

    def run_in_background(self, do):
        def work():
            try:
                self.results.put(("message", do()))
            except Exception as error:  # noqa: BLE001
                self.results.put(("error", str(error)))
            self.wake.set()
        threading.Thread(target=work, daemon=True).start()

    def open_path(self, path):
        import os
        os.startfile(str(path))

    def add_dialog(self):
        AddDialog(self)

    # --- window and tray -------------------------------------------------------------------------------------
    def hide(self):
        if not self.tray:
            self.quit()
            return
        self.root.withdraw()
        if not self.hidden_once:
            self.hidden_once = True
            self.tray.notify(f"{theme.NAME} is still watching", "It's in the tray by the clock. Right-click it to quit.")

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit(self):
        if self.tray:
            self.tray.stop()
        self.root.destroy()


class AddDialog(tk.Toplevel):
    """Queue a command: it runs when its turn comes (one planned job at a time)."""

    def __init__(self, app: App):
        super().__init__(app.root)
        self.app = app
        self.title("Add a job to the planned queue")
        self.configure(bg=theme.BG)
        self.transient(app.root)
        self.resizable(True, False)
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self.name = tk.StringVar(value="My job")
        self.command = tk.StringVar(value='.venv\\Scripts\\python.exe -u scripts\\deep_analysis.py')
        self.cwd = tk.StringVar(value=str(BOOK))
        self.after = tk.StringVar(value="nothing (next in line)")
        self.normal = tk.BooleanVar(value=False)
        rows = [("Name", ttk.Entry(frame, textvariable=self.name, width=60)),
                ("Command", ttk.Entry(frame, textvariable=self.command, width=60)),
                ("Run in folder", ttk.Entry(frame, textvariable=self.cwd, width=60)),
                ("Also wait for", ttk.Combobox(frame, textvariable=self.after, state="readonly", width=40, values=[
                    "nothing (next in line)", "library", "stage2", "main", "previous"]))]
        for i, (label, widget) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 8))
            widget.grid(row=i, column=1, sticky="we", pady=3)
        ttk.Button(frame, text="Browse...", command=self.browse).grid(row=2, column=2, padx=(6, 0))
        ttk.Checkbutton(frame, text="Normal priority (default: below normal, so the PC stays quick)",
                        variable=self.normal).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Label(frame, text="A .ps1 file is run with PowerShell. Quote paths with spaces. Output goes to its log.",
                  style="Small.TLabel").grid(row=5, column=1, sticky="w")
        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=1, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Add to queue", command=self.add).pack(side="right", padx=6)
        frame.columnconfigure(1, weight=1)
        theme.dark_title_bar(self)
        self.grab_set()

    def browse(self):
        chosen = filedialog.askdirectory(initialdir=self.cwd.get(), parent=self)
        if chosen:
            self.cwd.set(chosen)

    def add(self):
        command = [part.strip('"') for part in shlex.split(self.command.get(), posix=False)]
        if not command or not self.name.get().strip():
            messagebox.showerror(theme.NAME, "Give it a name and a command.", parent=self)
            return
        after = [] if self.after.get().startswith("nothing") else [self.after.get()]
        text = (f"Add '{self.name.get()}' to the planned queue?\n\n{' '.join(command)}\nin {self.cwd.get()}"
                + (f"\nafter: {after[0]}" if after else ""))
        if not messagebox.askyesno("Are you sure?", text, parent=self):
            return
        name, cwd, normal = self.name.get().strip(), self.cwd.get(), self.normal.get()

        def do():
            job_id = planned.add(name, command, cwd, after, priority="normal" if normal else "below")
            runner.wake()
            return f"Added '{name}' (id {job_id})."
        self.app.run_in_background(do)
        self.destroy()
