"""The window (tkinter). Reading happens in a background thread every few seconds, and so do the actions, so the
window never freezes; results come back through a queue that the window checks 5 times a second."""

import queue
import shlex
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import actions, alerts, autogame, devmode, gaming, planned, runner, startup, theme
from .hud import Briefing, NextList, RunningPanel, Section, StatCard, ViewSwitch
from .about import AboutPage
from .hunter import KhaltronHeader, card_for
from .collect import State, collect
from .sources import gpu as gpu_source
from .config import BOOK, CONFIG, HAS_BOOK, STATE
from .model import DONE, FAILED, PAUSED, RUNNING, STOPPED, WAITING, Job
from .util import duration, read_json, when, write_json

GREEN, AMBER, RED, GREY = theme.GREEN, theme.AMBER, theme.RED, theme.MUTED
SEGMENTS = 20  # the RAM and CPU gauges are drawn as rows of segments


def bar(progress: float | None, width: int = 10) -> str:
    if progress is None:
        return ""
    progress = max(0.0, min(1.0, progress))
    full = round(progress * width)
    return "▰" * full + "▱" * (width - full) + f" {progress * 100:.0f}%"


def briefing(state: State, playing: bool) -> tuple[str, str, str]:
    """(chip, colour, sentence): the whole picture in one plain sentence."""
    h = state.health
    running, waiting = len(state.running), len(state.waiting)
    jobs = (f"{running} job{'s' if running != 1 else ''} running" if running else "No jobs running") + \
        (f", {waiting} waiting." if waiting else ", nothing waiting.")
    if playing:
        return "GAMING", theme.LASER, "Gaming mode is on: background jobs are frozen so your game gets the PC."
    if not h:
        return "SCANNING", theme.MUTED, jobs
    pc = f"CPU {h.cpu:.0f}%, {gb(h.free_mb)} of memory free."
    if h.free_mb < CONFIG["low_memory_mb"]:
        return "LOW MEMORY", theme.RED, f"{jobs} Memory is running out: {pc}"
    if h.cpu > 85:
        return "BUSY", theme.AMBER, f"{jobs} Your PC is very busy: {pc}"
    if running:
        return "WORKING", theme.GREEN, f"{jobs} Your PC has room to spare: {pc}"
    return "CALM", theme.GREEN, f"{jobs} Your PC is calm: {pc}"


def share_bar(share: float, width: int = 10) -> str:
    """A text bar for a table cell: how big a share of the whole this is."""
    share = max(0.0, min(1.0, share))
    full = round(share * width)
    return f"{share * 100:4.1f}%  " + "\u25ae" * full + "\u25af" * (width - full)


def program_row(program, control=None) -> Job:
    """A Programs-section row (sources/programs.py) in the shape the tables show, with the buttons it allows
    (monitor/appcontrol.py decides: never Windows' own parts, Claude, or Khaltron's protected programs)."""
    windows = not program.yours
    allowed = control.allowed if control else []
    paused = bool(control and control.paused)
    actions_ = (["resume_app", "end_app"] if paused else ["pause_app", "close_app", "end_app"]) if allowed else []
    if allowed:  # your work list (monitor/mywork.py): gaming and development mode leave these programs alone
        actions_ = actions_ + (["unkeep_app"] if control and control.mine else ["keep_app"])
    return Job(id=f"app:{program.name}", name=program.name, source="Windows" if windows else "You",
               state=PAUSED if paused else DONE if windows else WAITING, cpu=program.cpu, memory_mb=program.memory_mb,
               actions=actions_, step="" if allowed or windows else (control.reason if control else ""),
               ref={"count": program.processes or "", "allowed": allowed})


def startup_row(app, memory_mb) -> Job:
    """A Startup-apps row (monitor/startup.py): on (green) or off (grey), and the button that switches it."""
    return Job(id=f"start:{app.hive}:{app.approved}:{app.name}", name=startup.label(app), source=app.where,
               state=RUNNING if app.on else DONE, memory_mb=memory_mb, step=app.command,
               actions=["startup_off"] if app.on else ["startup_on"], ref={"app": app})


def pct(value: float | None) -> str:
    return "" if value is None else f"{value:.0f}%"


def gauge(canvas: tk.Canvas, share: float, colour: str) -> None:
    """A row of SEGMENTS segments; the first `share` of them lit."""
    canvas.delete("all")
    lit = round(SEGMENTS * max(0.0, min(1.0, share)))
    for i in range(SEGMENTS):
        canvas.create_rectangle(i * 9, 2, i * 9 + 6, 14, width=0, fill=colour if i < lit else theme.RAISED)


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
        self.shown: dict[str, tuple] = {}  # row id -> (values, tags) last written
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings", height=height,
                                 selectmode="browse")
        for key, title, width in columns:
            self.tree.heading(key, text=title, anchor="w")
            self.tree.column(key, width=width, minwidth=40, stretch=key in ("name", "step"), anchor="w")
        for state, colour in ((RUNNING, GREEN), (FAILED, RED), ("ended", AMBER), (STOPPED, AMBER), (PAUSED, AMBER),
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
        present = list(self.tree.get_children())
        for gone in set(present) - set(self.jobs):
            self.tree.delete(gone)
            self.shown.pop(gone, None)
        order = [row for row in present if row in self.jobs]
        for index, job in enumerate(jobs):
            tag = "protected" if job.ref.get("protected") else job.state
            row = (values(index, job), (tag, "odd") if index % 2 else (tag,))
            if job.id not in self.shown:
                self.tree.insert("", index, iid=job.id, values=row[0], tags=row[1])
                order.insert(index, job.id)
            else:
                # only rows that changed are touched: rewriting ~80 unchanged rows every 2 s cost real CPU
                if self.shown[job.id] != row:
                    self.tree.item(job.id, values=row[0], tags=row[1])
                if index >= len(order) or order[index] != job.id:
                    self.tree.move(job.id, "", index)
                    order.remove(job.id)
                    order.insert(index, job.id)
            self.shown[job.id] = row
        self.enable()


LITE = STATE / "lite.json"  # the lite look (a still header) you chose


class App:
    def __init__(self, root: tk.Tk, tray=None, start_hidden: bool = False):
        self.root, self.tray = root, tray
        self.results: queue.Queue = queue.Queue()
        self.wake = threading.Event()
        self.watcher = alerts.Watcher()
        self.alerts_on = True
        self.hidden_once = False
        self.gaming_was = None  # gaming mode at the last refresh (a change pops up a notification)
        self.switched_at = 0.0  # when Khaltron itself last switched gaming mode (it says so in its own pop-up)
        self.dev_was = None     # development mode at the last refresh
        self.dev_busy = False   # development mode is switching in the background
        self.visible = not start_hidden  # hidden in the tray: no redrawing, slower refresh
        self.pending = None              # the newest state, drawn when the window is shown again
        self.lite_on = bool((read_json(LITE, {}) or {}).get("on", False))  # the still header, chosen by you
        self.busy_count = 0              # refreshes in a row with the CPU over 85% (the header goes still)
        root.bind("<Unmap>", self.minimised, add="+")  # minimised counts as hidden too
        root.bind("<Map>", self.shown, add="+")
        self.autogame = autogame.Watcher()
        root.title(theme.NAME)
        # tall enough for the header; never taller than the screen (a laptop's is ~1080 px with the taskbar)
        root.geometry(f"1180x{min(1010, root.winfo_screenheight() - 70)}+40+10")
        root.minsize(760, 520)
        root.protocol("WM_DELETE_WINDOW", self.hide)
        theme.apply(root)
        self.build()
        theme.dark_title_bar(root)
        if start_hidden:
            root.withdraw()
        threading.Thread(target=self.recover_modes, daemon=True).start()
        threading.Thread(target=self.reader, daemon=True).start()
        root.after(200, self.poll)

    # --- layout ---------------------------------------------------------------------------------------------
    def build(self):
        self.brand()
        outer = ttk.Frame(self.root, padding=(14, 10, 14, 10))
        outer.pack(fill="both", expand=True)

        # the toolbar: which view (left); gaming mode, hide, the control menu (right)
        top = ttk.Frame(outer)
        top.pack(fill="x")
        self.view_switch = ViewSwitch(top, ["Overview", "Details", "About"], self.show_view)
        self.view_switch.pack(side="left")
        start = ttk.Menubutton(top, text="Start / control")
        menu = tk.Menu(start, tearoff=False)
        menu.add_command(label="Add a job to the planned queue...", command=self.add_dialog)
        if HAS_BOOK:  # the Book Analyzer's own jobs
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
        menu.add_command(label="Development mode on / off (Ctrl+Alt+D)", command=self.toggle_dev)
        menu.add_command(label="Lite look on / off (a still header)", command=lambda: self.set_lite(not self.lite_on))
        menu.add_separator()
        if HAS_BOOK:
            menu.add_command(label="Open the Book Analyzer results folder",
                             command=lambda: self.open_path(BOOK / "results"))
        menu.add_command(label="Refresh now", command=self.wake.set)
        start["menu"] = menu
        start.pack(side="right")
        ttk.Button(top, text="Hide to tray", command=self.hide).pack(side="right", padx=6)
        # auto gaming mode: gaming mode switches itself on when a game starts, off when it closes
        self.auto_var = tk.BooleanVar(value=autogame.enabled())
        ttk.Checkbutton(top, text="Auto gaming mode", variable=self.auto_var,
                        command=lambda: self.set_auto_gaming(self.auto_var.get())).pack(side="right", padx=(6, 0))
        # the one-sentence briefing shares this row (one row less under the header)
        self.briefing = Briefing(top, compact=True)
        self.briefing.pack(side="left", fill="x", expand=True, padx=(14, 8))
        self.gaming_switch = self.header  # the header's toggle pill is the gaming mode switch

        # the one-sentence briefing, and warnings under it
        self.flags = ttk.Label(outer, text="", style="Flag.TLabel")
        self.flags.pack(fill="x", pady=(4, 0))

        # the status line first, at the bottom: packed after the views it got no room left
        self.status = ttk.Label(outer, text="Starting...", style="Small.TLabel")
        self.status.pack(side="bottom", fill="x", pady=(6, 0))
        views = ttk.Frame(outer)
        views.pack(fill="both", expand=True, pady=(8, 0))

        # OVERVIEW: what matters at a glance
        overview = self.overview = ttk.Frame(views)
        cards = ttk.Frame(overview)
        cards.pack(fill="x")
        self.ram_card = StatCard(cards, "RAM in use")
        self.cpu_card = StatCard(cards, "CPU")
        self.gpu_card = StatCard(cards, "GPU")
        self.jobs_card = StatCard(cards, "Your background jobs")
        for column, card in enumerate((self.ram_card, self.cpu_card, self.gpu_card, self.jobs_card)):
            card.grid(row=0, column=column, sticky="we", padx=(0 if column == 0 else 10, 0))
            cards.columnconfigure(column, weight=1, uniform="cards")
        self.running_title = Section(overview, "Now running")
        self.running_title.pack(fill="x", pady=(10, 6))
        self.running = RunningPanel(overview, self)
        self.running.pack(fill="x")
        bottom = ttk.Frame(overview)
        bottom.pack(fill="both", expand=True, pady=(6, 0))
        left = ttk.Frame(bottom)
        left.pack(fill="both", expand=True)
        self.next_title = Section(left, "Next up")
        self.next_title.pack(fill="x", pady=(0, 6))
        self.next_list = NextList(left, lambda: self.show_view("Details"))
        self.next_list.pack(fill="x")

        # DETAILS: every table, as before
        details = self.details = ttk.Frame(views)
        panes = ttk.PanedWindow(details, orient="vertical")
        panes.pack(fill="both", expand=True)

        box = ttk.Frame(panes)
        self.waiting_title = Section(box, "Up next")
        self.waiting_title.pack(fill="x", pady=(0, 6))
        self.waiting = Table(box, self, [("pos", "#", 36), ("name", "Job", 270), ("source", "Queue", 110),
                                         ("step", "Waiting for", 380), ("added", "Added", 90)],
                             ["up", "down", "runnow", "remove", "stop", "log"], height=6)
        self.waiting.pack(fill="both", expand=True)
        panes.add(box, weight=2)

        tabs = ttk.Notebook(panes)
        self.apps = Table(tabs, self, [("name", "Program", 300), ("who", "Started by", 90), ("count", "Processes", 80),
                                       ("cpu", "CPU", 60), ("share", "Share of the CPU", 170), ("memory", "RAM", 80),
                                       ("rshare", "Share of the RAM", 170), ("step", "Note", 200)],
                          ["pause_app", "resume_app", "close_app", "end_app", "keep_app", "unkeep_app"], height=8)
        self.finished = Table(tabs, self, [("name", "Job", 270), ("source", "From", 110), ("state", "Result", 80),
                                           ("step", "Details", 380), ("when", "Ended", 90)], ["log"], height=8)
        self.tasks = Table(tabs, self, [("name", "Task", 250), ("state", "State", 80), ("step", "Status", 330),
                                        ("last", "Last run", 100), ("next", "Next run", 100)], ["runtask"], height=8)
        self.procs = Table(tabs, self, [("name", "Process", 250), ("pid", "PID", 70), ("memory", "Memory", 80),
                                        ("cpu", "CPU", 60), ("time", "Running for", 90), ("step", "Command", 380)],
                           ["stop"], height=8)
        self.startup = Table(tabs, self, [("name", "App", 250), ("state", "At login", 90), ("where", "Set in", 190),
                                          ("memory", "Running now", 100), ("step", "Starts", 420)],
                             ["startup_off", "startup_on"], height=8)
        self.problems = tk.Text(tabs, height=6, wrap="word", font=(theme.MONO, 9), relief="flat", bg=theme.PANEL,
                                fg=theme.MUTED, insertbackground=theme.LASER, padx=10, pady=8, highlightthickness=0)
        tabs.add(self.apps, text="Programs on this PC")
        tabs.add(self.startup, text="Startup apps")
        tabs.add(self.finished, text="Finished")
        tabs.add(self.tasks, text="Scheduled tasks")
        tabs.add(self.procs, text="Python processes")
        tabs.add(self.problems, text="Problems")
        panes.add(tabs, weight=3)
        # ABOUT: who made it and why
        self.about = AboutPage(views)
        self.show_view("Overview")


    def show_view(self, view: str):
        """Overview (simple, the default), Details (every table) or About (who made it and why)."""
        self.view_switch.select(view)
        pages = {"Overview": self.overview, "Details": self.details, "About": self.about}
        for page in pages.values():
            page.pack_forget()
        pages[view].pack(fill="both", expand=True)

    def brand(self):
        """The header, after the owner's design (khaltron-header.css): the robot watching the six busiest programs
        on its ledge, cyan while monitoring, red when gaming mode hunts (monitor/hunter.py)."""
        self.programs = []  # the latest Programs-on-this-PC rows (for the cards gaming mode will pause)
        self.header = KhaltronHeader(self.root, on_locked=self.freeze_for_game, on_exit=self.leave_game,
                                     targets=self.gaming_targets, on_dev=self.toggle_dev)
        self.header.pack(fill="x")
        tk.Frame(self.root, height=1, bg=theme.LINE).pack(fill="x")

    # --- reading in the background --------------------------------------------------------------------------
    def reader(self):
        last_slow = 0.0
        while True:
            slow = time.time() - last_slow >= CONFIG["slow_refresh_seconds"]
            if slow:
                last_slow = time.time()
            try:
                state = collect(slow)
            except Exception as error:  # noqa: BLE001
                self.results.put(("message", f"Reading failed: {error}"))
            else:
                self.check_modes(state.samples)
                try:  # auto gaming mode: a game started or closed?
                    for note in self.autogame.tick(state.samples):
                        self.switched_at = time.time()
                        self.results.put(("notify", note))
                except Exception as error:  # noqa: BLE001
                    self.results.put(("message", f"Auto gaming mode check failed: {error}"))
                self.results.put(("state", state))
            self.wake.wait(CONFIG["refresh_seconds"] if self.visible else CONFIG.get("hidden_refresh_seconds", 6))
            self.wake.clear()

    def recover_modes(self):
        """At start: a gaming or development mode left 'on' by a crash or restart is switched off properly."""
        for name, module in (("Gaming mode", gaming), ("Development mode", devmode)):
            try:
                done = module.recover()
            except Exception as error:  # noqa: BLE001
                done = None
                self.results.put(("message", f"{name} clean-up failed: {error}"))
            if done:
                self.results.put(("notify", (f"{name} was left on by a restart",
                                             "Switched off properly: the queue and power mode are back.")))

    def check_modes(self, samples: dict):
        """While gaming or development mode is on: freeze jobs that started anyway, and (development mode) boost or
        lower what is new. Every config "mode_check_seconds" (15 s), with this refresh's process sample: checking
        every 2 s with a scan of its own was a constant load on an already busy PC (2026-11-13)."""
        if not (gaming.is_on() or devmode.is_on()):
            self.modes_checked = 0.0  # the first check after a switch happens at once
            return
        if time.time() - getattr(self, "modes_checked", 0.0) < CONFIG.get("mode_check_seconds", 15):
            return
        self.modes_checked = time.time()
        try:
            for frozen in gaming.enforce():  # gaming mode: a job that started anyway is frozen too
                self.results.put(("notify", ("Gaming mode: job frozen", frozen)))
        except Exception as error:  # noqa: BLE001
            self.results.put(("message", f"Gaming mode check failed: {error}"))
        try:
            for frozen in devmode.enforce(samples):  # development mode: new jobs frozen, new work boosted
                self.results.put(("notify", ("Development mode: job frozen", frozen)))
        except Exception as error:  # noqa: BLE001
            self.results.put(("message", f"Development mode check failed: {error}"))

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
                elif kind == "gaming_done":
                    self.gaming_switch.set_state(gaming.is_on(), busy=False)
                elif kind == "gaming":
                    self.toggle_gaming()
                elif kind == "dev_done":
                    self.dev_busy = False
                    self.show_dev(devmode.is_on())
                elif kind == "lite":
                    self.set_lite(not self.lite_on)
                elif kind == "devmode":
                    self.toggle_dev()
                elif kind == "auto_gaming":
                    self.set_auto_gaming(not autogame.enabled())
                elif kind == "show":
                    self.show()
                elif kind == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(200, self.poll)

    # --- drawing ---------------------------------------------------------------------------------------------
    def set_lite(self, on: bool):
        """The lite look: a still header (remembered in state/lite.json). It also comes on by itself while the PC is
        very busy; this is your own choice on top of that."""
        self.lite_on = on
        write_json(LITE, {"on": on})
        self.header.set_lite(on or self.busy_count >= 3)
        self.status.configure(text="Lite look ON: the header stays still (less CPU)." if on
                              else "Lite look OFF: the header moves again (it still goes still when the PC is very busy).")

    def show_gpu(self):
        """The GPU card: how busy the graphics card is, its video memory and temperature (sources/gpu.py, ~1 ms).
        Read here, so only while the window is visible: asking a laptop's sleeping graphics card wakes it."""
        g = gpu_source.read()
        if g is None:
            self.gpu_card.update_value(0, "-", "no NVIDIA graphics card\nfound", theme.MUTED)
            return
        colour = RED if g.load > 90 else AMBER if g.load > 60 else GREEN
        memory = f"{gb(g.used_mb)} / {gb(g.total_mb)} VRAM" if g.total_mb else "VRAM unknown"  # short: it shares the card with the graph
        heat = f"  {g.temp_c}°C" if g.temp_c is not None else ""
        self.gpu_card.update_value(g.load / 100, f"{g.load:.0f}%", f"{memory}\n{g.name}{heat}", colour)

    def background(self, state: State) -> tuple[bool, bool]:
        """What must happen on every refresh even with the window hidden: pop-ups when a mode was switched elsewhere,
        the tray tooltip, job started / finished / failed alerts. Returns (gaming on, development on)."""
        playing, developing = gaming.is_on(), devmode.is_on()
        recent = time.time() - self.switched_at <= 20  # Khaltron switched it itself: its own pop-up says so
        if playing != self.gaming_was and self.gaming_was is not None and self.tray and not recent:
            self.tray.notify("Gaming mode " + ("ON" if playing else "OFF"),
                             "Background jobs frozen, voice off. Have fun!" if playing else "Background jobs carry on.")
        if developing != self.dev_was and self.dev_was is not None and self.tray and not recent:
            self.tray.notify("Development mode " + ("ON" if developing else "OFF"),
                             "Your work comes first; background jobs frozen." if developing
                             else "Everything is back as it was.")
        self.gaming_was, self.dev_was = playing, developing
        if self.tray:
            self.tray.set_tooltip(f"{theme.NAME}: {len(state.running)} running, {len(state.waiting)} waiting")
        for title, message in self.watcher.changes(state):
            if self.alerts_on and self.tray:
                self.tray.notify(title, message)
        return playing, developing

    def draw(self, state: State):
        """One refresh. Hidden in the tray, only background() runs and the newest state waits for show(): redrawing
        every table and graph nobody could see was most of Khaltron's CPU use (2026-11-13)."""
        playing, developing = self.background(state)
        if not self.visible:
            self.pending = state
            return
        self.pending = None
        now = time.time()
        h = state.health
        if h:
            limit = CONFIG["low_memory_mb"]
            colour = RED if h.free_mb < limit else AMBER if h.free_mb < 2 * limit else GREEN
            # RAM: what is IN USE, like Task Manager; the colour warns when little is left
            used_share = h.used_mb / h.total_mb if h.total_mb else 0
            self.ram_card.update_value(used_share, f"{gb(h.used_mb)} / {gb(h.total_mb)}",
                                       f"{used_share * 100:.0f}% in use\n{gb(h.free_mb)} free for new work", colour)
            cpu_colour = RED if h.cpu > 85 else AMBER if h.cpu > 60 else GREEN
            top_app = next((a for a in state.programs if a.cpu >= 1 and not a.name.startswith("Windows:")), None)
            busiest = top_app.name.split(" (")[0] if top_app else ""
            self.cpu_card.update_value(h.cpu / 100, f"{h.cpu:.0f}%", f"of {h.cores} threads"
                                       + (f"\nbusiest: {busiest} {top_app.cpu:.0f}%" if top_app else ""),
                                       cpu_colour)
            self.show_gpu()
            # very busy (CPU over 85% three refreshes running): the header goes still until it calms down (<70%)
            self.busy_count = self.busy_count + 1 if h.cpu > 85 else 0 if h.cpu < 70 else self.busy_count
            self.header.set_lite(self.lite_on or self.busy_count >= 3)
            others = max(0, h.used_mb - state.jobs_mb)
            self.jobs_card.update_value(state.jobs_cpu / 100, f"{state.jobs_cpu:.0f}%  {gb(state.jobs_mb) or '0 MB'}",
                                        f"CPU and RAM of {len(state.running)} running\nall else: {gb(others)} RAM",
                                        theme.LASER)
        alert = bool(h and h.free_mb < CONFIG["low_memory_mb"]) or any(
            j.state == FAILED and j.finished and now - j.finished < 600 for j in state.finished)
        flags = []
        if not self.gaming_switch.busy:
            self.gaming_switch.set_state(playing)
        if playing:
            flags.append("GAMING MODE is on: background jobs are frozen (Start / control > Gaming mode off).")
        if not self.dev_busy:
            self.show_dev(developing)
        if developing:
            flags.append("DEVELOPMENT MODE is on: background jobs frozen, background apps in efficiency mode, the "
                         "memory goes to your work (the header's DEV MODE button switches it off).")
        if state.stage2_paused and any(j.source == "Stage 2" for j in state.waiting):
            flags.append("Stage 2 is paused (Start / control > Resume stage 2).")
        if state.queue_paused:
            flags.append("The planned queue is paused (Start / control > Resume the planned queue).")
        paused_apps = [name for name, c in state.controls.items() if c.paused]
        if paused_apps:
            flags.append(f"Paused by you: {', '.join(paused_apps)} (Details > Programs on this PC > Resume).")
        if h and h.free_mb < CONFIG["low_memory_mb"]:
            flags.append("Memory is low: a new job may be ended by Windows.")
        self.flags.configure(text="   ".join(flags))

        self.running.show(state.running, now)
        self.next_list.show(state.waiting)
        self.next_title.count(len(state.waiting))
        held = (read_json(gaming.FLAG, {}) or {}) if playing else {}
        frozen = {item["pid"] for item in held.get("frozen", []) + held.get("eco", [])}  # frozen or slowed down
        self.programs = state.programs
        apps = [a for a in state.programs if a.yours and not a.name.startswith("Windows")]
        apps.sort(key=lambda a: (-round(a.cpu), -a.memory_mb))
        self.header.set_programs([card_for(a) for a in apps[:6]])
        if playing:
            self.header.mark_frozen(frozen)
        self.briefing.show(*briefing(state, playing))
        self.running_title.count(len(state.running))
        self.waiting_title.count(len(state.waiting))
        total_mb = h.total_mb if h else 1
        self.apps.show([program_row(a, state.controls.get(a.name)) for a in state.programs], lambda i, j: (
            j.name + ("  (PAUSED)" if j.state == PAUSED else ""), j.source, j.ref["count"], pct(j.cpu),
            share_bar(j.cpu / 100), gb(j.memory_mb), share_bar(j.memory_mb / total_mb),
            "paused by you" if j.state == PAUSED else ("can't touch: " + j.step if j.step else "")))
        self.startup.show([startup_row(app, mb) for app, mb in state.startup], lambda i, j: (
            j.name, "starts" if j.state == RUNNING else "off", j.source,
            gb(j.memory_mb) if j.memory_mb is not None else "not running", j.step))
        self.waiting.show(state.waiting, lambda i, j: (
            i + 1, j.name, j.source, j.step, when(j.started)))
        history = sorted(state.finished + alerts.history(), key=lambda j: j.finished or 0, reverse=True)[:40]
        self.finished.show(history, lambda i, j: (j.name, j.source, j.state, j.step, when(j.finished)))
        self.tasks.show(state.tasks, lambda i, j: (j.name, j.state, j.step, when(j.started), when(j.finished)))
        self.procs.show(state.processes, lambda i, j: (
            j.name + ("  (protected)" if j.ref.get("protected") else ""), j.pid, gb(j.memory_mb),
            pct(j.cpu), duration(now - j.started) if j.started else "", j.step))
        self.problems.delete("1.0", "end")
        self.problems.insert("end", "\n".join(state.errors) or "No problems reading the jobs.")

        idle = not state.running
        self.status.configure(text=f"Updated {time.strftime('%H:%M:%S')} ({state.taken:.1f} s).  "
                                   + ("Nothing is running." if idle else f"{len(state.running)} running, "
                                      f"{len(state.waiting)} waiting.")
                                   + f"  Planned queue runner: {'on' if runner.is_running() else 'off'}.")

    # --- actions ---------------------------------------------------------------------------------------------
    def act(self, job: Job, action: str):
        if action not in actions.HARMLESS:
            if not messagebox.askyesno("Are you sure?", actions.question(job, action), parent=self.root):
                return
        self.run_in_background(lambda: actions.do(job, action))

    def gaming_targets(self):
        """The cards for gaming mode's sequence: the programs it will really pause (your background jobs and the
        safe background apps), so what the robot locks onto is the truth."""
        from .sources import programs as program_source
        pausable = {"python (incl. your background jobs)"} | {
            program_source.FRIENDLY.get(exe, exe.rsplit(".", 1)[0]).lower() for exe in gaming.EXTRA_APPS}
        cards = [card_for(a) for a in self.programs if a.name.lower() in pausable]
        for card in cards:
            card.pausable = True
        return cards

    def freeze_for_game(self, _cards):
        """The header's gaming sequence locked: now really freeze the jobs (the design: 'onLocked')."""
        if gaming.is_on() or self.header.busy:
            return
        self._switch_gaming(gaming.turn_on)

    def leave_game(self):
        """EXIT GAMING MODE clicked: let everything carry on."""
        if gaming.is_on():
            self._switch_gaming(gaming.turn_off)

    def set_auto_gaming(self, on: bool):
        """The toolbar's and the tray's switch for auto gaming mode (remembered in state/auto_gaming.json)."""
        autogame.set_enabled(on)
        self.auto_var.set(on)
        self.status.configure(text="Auto gaming mode ON: gaming mode switches on when a game starts, off when it "
                                   "closes." if on else "Auto gaming mode OFF: gaming mode only when you switch it.")

    def _switch_gaming(self, switch):
        self.switched_at = time.time()
        self.header.set_state(gaming.is_on(), busy=True)

        def do():
            try:
                message = switch()
            finally:
                self.results.put(("gaming_done", None))
                self.wake.set()
            lines = message.splitlines()
            frozen = [line for line in lines if line.startswith(("- Frozen:", "- Efficiency mode"))]
            if lines[0].startswith("Gaming mode ON") and not frozen:
                body = "Nothing to pause: no background jobs are running. Your apps and Windows are left alone."
            else:
                body = (f"{len(frozen)} job(s) or app(s) paused. " if frozen else "") + lines[-1]
            self.results.put(("notify", (lines[0], body)))
            return lines[0] + "  " + lines[-1]
        self.run_in_background(do)

    def toggle_gaming(self):
        """No "are you sure?": it is meant to be quick, and switching it back undoes everything it did.
        The switch shows SWITCHING... meanwhile; afterwards a pop-up says what was frozen and what it freed."""
        if self.gaming_switch.busy:
            return
        self.switched_at = time.time()
        self.gaming_switch.set_state(gaming.is_on(), busy=True)

        def do():
            try:
                message = gaming.toggle()
            finally:
                self.results.put(("gaming_done", None))
                self.wake.set()
            lines = message.splitlines()
            frozen = [line for line in lines if line.startswith(("- Frozen:", "- Efficiency mode"))]
            if lines[0].startswith("Gaming mode ON") and not frozen:
                body = "Nothing to pause: no background jobs are running. Your apps and Windows are left alone."
            else:
                body = (f"{len(frozen)} job(s) or app(s) paused. " if frozen else "") + lines[-1]
            self.results.put(("notify", (lines[0], body)))
            return lines[0] + "  " + lines[-1]
        self.run_in_background(do)

    def show_dev(self, on: bool):
        """The header's DEV MODE pill (left of GAMING MODE) shows development mode's state."""
        self.header.set_dev(on, busy=False)

    def toggle_dev(self):
        """Like gaming mode: no "are you sure?" (switching it back undoes everything); a pop-up says what it did."""
        if self.dev_busy:
            return
        self.dev_busy = True
        self.switched_at = time.time()
        self.header.set_dev(devmode.is_on(), busy=True)
        gaming_before = gaming.is_on()

        def do():
            try:
                message = devmode.toggle()
            finally:
                self.results.put(("dev_done", None))
                if gaming_before:
                    self.results.put(("gaming_done", None))
                self.wake.set()
            lines = message.splitlines()
            frozen = sum(1 for line in lines if line.startswith("- Frozen:"))
            boosted = next((line[2:] for line in lines if line.startswith("- Boosted")), "")
            body = (f"{frozen} job(s) frozen. " if frozen else "") + (boosted + " " if boosted else "") + lines[-1]
            self.results.put(("notify", (lines[0], body)))
            return lines[0] + "  " + lines[-1]
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
        self.visible = False
        if not self.hidden_once:
            self.hidden_once = True
            self.tray.notify(f"{theme.NAME} is still watching", "It's in the tray by the clock. Right-click it to quit.")

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.shown()

    def shown(self, _event=None):
        """Visible again (shown from the tray, or restored after minimising): draw what waited, then fresh data."""
        if _event is not None and _event.widget is not self.root:
            return
        was = self.visible
        self.visible = True
        if self.pending is not None:
            self.draw(self.pending)
        if not was:
            self.wake.set()

    def minimised(self, event):
        if event.widget is self.root:
            self.visible = False

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
