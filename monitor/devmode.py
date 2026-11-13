"""Development mode: the PC's CPU and memory go to what you are working on now - Claude and everything it runs,
your terminal and editor, and Stable Diffusion (image generation).

ON:  pauses the planned queue and FREEZES the background jobs gaming mode freezes (book analyses, stage 2, the
     library job, planned jobs, cloud sync, Widgets...), but never the Book Analyzer website or the read-aloud voice;
     gives your work HIGH priority: every Claude process and everything it started (node, python, bash, dev servers,
     test browsers), Windows Terminal, VS Code, git, ComfyUI / Stable Diffusion and what they start;
     LOWERS the other programs that have a window (browsers, chat...) to "below normal": they keep working, they
     just always give way (nothing with a window is frozen, so nothing looks crashed);
     sets Windows' power mode to "Best performance". Everything it changed is written to the switch file
     (config "dev_flag", by default state/dev-mode.json).
OFF: reads that file and undoes exactly that: frozen jobs carry on, every priority it changed goes back.

While it is on, the Job Monitor calls enforce() on every refresh: new jobs are frozen, whatever Claude or ComfyUI
started since is boosted, newly opened programs are lowered. Gaming mode and development mode never run together:
switching one on switches the other off first. Run:  python -m monitor.devmode on | off | toggle | status"""

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

import psutil

from . import gaming, mywork, planned
from .appcontrol import NEVER_NAMES, WINDOWS_DIR
from .config import CONFIG, STATE
from .util import read_json, write_json

FLAG = Path(CONFIG.get("dev_flag", str(STATE / "dev-mode.json"))).expanduser()  # exists = development mode on
NAME = "Development mode"

# Windows priority classes (psutil's constants exist only on Windows; the numbers are Windows' own)
NORMAL, ABOVE, BELOW, HIGH = 0x20, 0x8000, 0x4000, 0x80
PRIORITY_NAMES = {0x40: "idle", BELOW: "below normal", NORMAL: "normal", ABOVE: "above normal", HIGH: "high",
                  0x100: "realtime"}
# above normal by default: "high" let a busy ComfyUI crowd out typing (2026-11-13)
PRIORITIES = bool(CONFIG.get("dev_priorities", False))  # boost your work / lower other apps (off: see _adjust)
BOOST = {"high": HIGH, "above_normal": ABOVE}.get(str(CONFIG.get("dev_boost", "above_normal")).lower(), ABOVE)
# Windows' typing helpers: boosted with your work, so keys reach your app even when the CPU is full
INPUT_HELPERS = {"ctfmon.exe": "Typing (Windows)", "textinputhost.exe": "Typing (Windows)"}

# your work: these programs and everything they start (config "dev_keep" adds program names)
WORK_NAMES = {n.lower() for n in ["claude.exe", "windowsterminal.exe", "code.exe", "git.exe"]
              + list(CONFIG.get("dev_keep", []))}
# ... and anything run from these folders (Stable Diffusion; config "dev_keep_folders" replaces the list)
WORK_FOLDERS = [f.lower() for f in CONFIG.get("dev_keep_folders", ["stablediffusion", "comfyui",
                                                                   "stable-diffusion-webui"])]
SCRIPT_HOSTS = ("python", "pythonw", "cmd.exe", "powershell", "pwsh")  # their command line says what they run
# browsers: never lowered (artifacts, docs and test pages open there: lowered, they opened slowly, 2026-11-13); a
# browser started from your terminal is not boosted either, only the ones Claude started
BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe", "iexplore.exe"}
NEVER_LOWER = NEVER_NAMES | {"explorer.exe", "dwm.exe", "taskmgr.exe", "searchhost.exe", "startmenuexperiencehost.exe",
                             "shellexperiencehost.exe", "textinputhost.exe", "lockapp.exe", "systemsettings.exe",
                             "applicationframehost.exe"}


def is_on() -> bool:
    return FLAG.exists()


# --- the process snapshot --------------------------------------------------------------------------------------
_cmdlines: dict[tuple[int, float], str] = {}
_exes: dict[tuple[int, float], str] = {}


class Snapshot:
    """Every process once: parent, name, program path, start time (command lines only when needed, cached)."""

    def __init__(self, samples: dict | None = None):
        """samples: the Job Monitor's own process sample of this refresh (programs.sample(): one quick Windows call
        with name, parent and start time), so nothing is scanned twice. Without it (the command line), psutil."""
        self.info: dict[int, dict] = {}
        if samples:
            for pid, item in samples.items():
                self.info[pid] = {"name": (item.name or "").lower(), "ppid": item.ppid, "create_time": item.started}
        else:
            # no program paths here: asking for every process's path takes seconds (Windows refuses many slowly)
            for process in psutil.process_iter(["ppid", "name", "create_time"]):
                info = process.info
                info["name"] = (info.get("name") or "").lower()
                info["create_time"] = info.get("create_time") or 0.0
                self.info[process.pid] = info
        self.children: dict[int, list[int]] = {}
        for pid, info in self.info.items():
            parent = self.info.get(info.get("ppid"))
            # a parent number reused by a newer program is not the real parent
            if parent and parent["create_time"] <= info["create_time"] and info.get("ppid") != pid:
                self.children.setdefault(info["ppid"], []).append(pid)
        global _cmdlines
        live = {(pid, i["create_time"]) for pid, i in self.info.items()}
        if len(_cmdlines) > 2 * max(1, len(live)):
            _cmdlines = {k: v for k, v in _cmdlines.items() if k in live}
        global _exes
        if len(_exes) > 2 * max(1, len(live)):
            _exes = {k: v for k, v in _exes.items() if k in live}

    def exe(self, pid: int) -> str:
        """The program's path, lower case ("" if Windows won't say). Only asked for when needed."""
        info = self.info.get(pid, {})
        if "exe" not in info:
            key = (pid, info.get("create_time", 0.0))
            if key not in _exes:  # kept between refreshes: a program's path never changes
                try:
                    _exes[key] = (psutil.Process(pid).exe() or "").lower()
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    _exes[key] = ""
            info["exe"] = _exes[key]
        return info.get("exe", "")

    def cmdline(self, pid: int) -> str:
        key = (pid, self.info.get(pid, {}).get("create_time", 0.0))
        if key not in _cmdlines:
            try:
                _cmdlines[key] = " ".join(psutil.Process(pid).cmdline())
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                _cmdlines[key] = ""
        return _cmdlines[key]

    def descendants(self, pid: int, stop) -> list[int]:
        out, todo = [], list(self.children.get(pid, []))
        while todo:
            child = todo.pop()
            if stop(child):
                continue
            out.append(child)
            todo.extend(self.children.get(child, []))
        return out


def _planned_pids() -> set[int]:
    return {e["pid"] for e in planned.load() if e.get("state") in (planned.RUNNING, planned.STOPPING) and e.get("pid")}


def work_pids(snap: Snapshot) -> dict[int, str]:
    """Your work right now: pid -> why. Claude's tree, terminal, editor, git, Stable Diffusion and their children.
    The walk stops at Khaltron's own processes (its queue runner, the website, the voice) and at planned jobs:
    queued work is background work, even when Claude queued it."""
    queued = _planned_pids()

    def stop(pid: int) -> bool:
        info = snap.info[pid]
        if pid in queued:
            return True
        if info["name"].startswith(SCRIPT_HOSTS):
            return any(n in snap.cmdline(pid) for n in gaming.NEVER)
        return False

    def is_sd(pid: int, info: dict) -> bool:
        if any(f in info["name"] for f in WORK_FOLDERS):  # e.g. a ComfyUI desktop app
            return True
        return info["name"].startswith(SCRIPT_HOSTS) and any(
            f in snap.exe(pid) or f in snap.cmdline(pid).lower() for f in WORK_FOLDERS)

    def stop_browsers(pid: int) -> bool:
        return stop(pid) or snap.info[pid]["name"] in BROWSERS

    roots: dict[int, str] = {}
    yours = mywork.names()  # your work list (Programs tab)
    for pid, info in snap.info.items():
        if info["name"] in yours and info["name"] not in WORK_NAMES:
            roots[pid] = os.path.splitext(info["name"])[0]
        elif info["name"] in WORK_NAMES:
            roots[pid] = {"claude.exe": "Claude", "windowsterminal.exe": "Terminal", "code.exe": "VS Code"}.get(
                info["name"], os.path.splitext(info["name"])[0])
        elif is_sd(pid, info) and not stop(pid):
            roots[pid] = "Stable Diffusion"
    found: dict[int, str] = {}
    # Claude first (its label wins inside the terminal it runs in), and only Claude's walk includes browsers
    for pid, why in sorted(roots.items(), key=lambda kv: kv[1] != "Claude"):
        found.setdefault(pid, why)
        for child in snap.descendants(pid, stop if why == "Claude" else stop_browsers):
            found.setdefault(child, why)
    return found


def window_pids() -> set[int]:
    """Programs with a visible, titled top-level window."""
    if sys.platform != "win32":
        return set()
    user32 = ctypes.windll.user32
    found: set[int] = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                found.add(pid.value)
        return True

    user32.EnumWindows(each, 0)
    return found


def lower_pids(snap: Snapshot, work: dict[int, str], windows: set[int] | None = None) -> dict[int, str]:
    """The other programs with a window, and what they started: pid -> program name. Never your work, Windows'
    own parts, Khaltron and its helpers, antivirus, drivers, sound, terminals, or this process."""
    windows = window_pids() if windows is None else windows
    me = os.getpid()

    def stop(pid: int) -> bool:
        info = snap.info[pid]
        return pid in work or pid == me or (info["name"].startswith(SCRIPT_HOSTS)
                                            and any(n in snap.cmdline(pid) for n in gaming.NEVER))

    found: dict[int, str] = {}
    for pid in windows:
        info = snap.info.get(pid)
        if not info or stop(pid) or info["name"] in NEVER_LOWER or info["name"] in BROWSERS or not snap.exe(pid) \
                or snap.exe(pid).startswith(WINDOWS_DIR.lower()):
            continue
        label = os.path.splitext(info["name"])[0]
        found[pid] = label
        for child in snap.descendants(pid, stop):
            found.setdefault(child, label)
    return found


# --- priorities -------------------------------------------------------------------------------------------------
def _set(state: dict, key: str, pid: int, created: float, label: str, before: int, now: int) -> bool:
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - created) > 1:
            return False
        process.nice(now)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False
    state[key].append({"pid": pid, "created": created, "label": label, "before": before, "now": now})
    return True


def _priority(pid: int) -> int | None:
    try:
        return int(psutil.Process(pid).nice())
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None


def foreground_pid() -> int | None:
    """The program whose window is in front (the one you are typing in)."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


def _adjust(state: dict, snap: Snapshot | None = None, windows: set[int] | None = None,
            front: int | None = -1) -> tuple[list, list]:
    """Boost new work processes, lower new windowed programs; record both in `state`. Returns their labels.
    The program in front (the one you are using) is never lowered: if it was, it is set back to normal now, and
    lowered again once you leave it.
    Off unless config "dev_priorities" is true (2026-11-13): this PC's limit is memory, which priorities don't free,
    and the juggling itself made typing and opening pages slower. Development mode is about memory now."""
    state.setdefault("boosted", [])
    state.setdefault("lowered", [])
    if not PRIORITIES:
        return [], []
    snap = snap or Snapshot()
    state.setdefault("lowered", [])
    front = foreground_pid() if front == -1 else front
    in_front = set()
    if front and front in snap.info:
        in_front = {front, *snap.descendants(front, lambda p: False)}
        back = [i for i in state["lowered"] if i["pid"] in in_front]
        if back:
            _restore(back)
            state["lowered"] = [i for i in state["lowered"] if i["pid"] not in in_front]
    done = {(i["pid"], i["created"]) for i in state["boosted"] + state["lowered"]}
    frozen = {i["pid"] for i in state.get("frozen", [])}
    work = work_pids(snap)
    helpers = {pid: INPUT_HELPERS[i["name"]] for pid, i in snap.info.items() if i["name"] in INPUT_HELPERS}
    boosted, lowered = [], []
    for pid, why in {**helpers, **work}.items():
        # boost only the main programs (Claude, terminal, editor, ComfyUI and its workers), not every short command
        # Claude runs: those were dozens of priority changes a minute for no gain (they are still never frozen)
        if why != "Stable Diffusion" and snap.info[pid]["name"] not in WORK_NAMES | set(INPUT_HELPERS):
            continue
        created = snap.info[pid]["create_time"]
        if (pid, created) in done or pid in frozen:
            continue
        now = _priority(pid)
        # only normal / above normal: something set lower on purpose (a long job at below normal) stays so
        if now not in (NORMAL, ABOVE) or now == BOOST:
            continue
        if _set(state, "boosted", pid, created, why, now, BOOST):
            boosted.append(why)
    for pid, label in lower_pids(snap, work, windows).items():
        created = snap.info[pid]["create_time"]
        if (pid, created) in done or pid in frozen or pid in in_front:
            continue
        now = _priority(pid)
        if now == NORMAL:
            if _set(state, "lowered", pid, created, label, NORMAL, BELOW):
                lowered.append(label)
        elif now == BELOW:  # started by a lowered program while lowered (Windows passed "below normal" on)
            parent = snap.info[pid].get("ppid")
            if any(i["pid"] == parent for i in state["lowered"]):
                state["lowered"].append({"pid": pid, "created": created, "label": label, "before": NORMAL,
                                         "now": BELOW})
    return boosted, lowered


def _restore(items: list[dict]) -> int:
    done = 0
    for item in items:
        try:
            process = psutil.Process(item["pid"])
            if abs(process.create_time() - item["created"]) > 1 or int(process.nice()) != item["now"]:
                continue  # gone, or someone changed it since: leave it as it is now
            process.nice(item["before"])
            done += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass
    return done


def _counts(labels: list[str]) -> str:
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return ", ".join(f"{k} ({v})" if v > 1 else k for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))


def _skip_work(snap: Snapshot):
    work = work_pids(snap)
    return lambda process: process.pid in work


# --- the switch -------------------------------------------------------------------------------------------------
def _turn_on() -> str:
    if is_on():
        return "Development mode is already ON.\n" + status()
    lines = ["Development mode ON."]
    if gaming.is_on():  # never both
        gaming._turn_off()
        lines.append("- Gaming mode switched off first.")
    before = gaming.free_memory_gb()
    state = {"since": time.time(), "frozen": [], "boosted": [], "lowered": [],
             "queue_was_paused": planned.queue_paused(), "power_before": None}
    write_json(FLAG, state)  # first, so the monitor's enforce() sees it at once
    if not state["queue_was_paused"]:
        planned.pause_queue(True)
        lines.append("- Planned queue paused (no new job starts).")
    snap = Snapshot()
    slowed = []
    frozen = gaming._freeze_new(state, website_too=False, skip=_skip_work(snap), slowed=slowed)
    lines += [f"- Frozen: {f}" for f in frozen] or ["- No background job needed freezing."]
    lines += [f"- Efficiency mode (still running, slowly): {s}" for s in slowed]
    lines += [f"- Left running: {n} (it watches the keyboard/mouse; frozen, typing would lag)"
              for n in sorted(set(state.get("input_spared", [])))]
    boosted, lowered = _adjust(state, snap)
    if boosted:
        lines.append(f"- Boosted to {PRIORITY_NAMES[BOOST]} priority: {_counts(boosted)}.")
    if lowered:
        lines.append(f"- Lowered to below normal (still running): {_counts(lowered)}.")
    mode = gaming.power_mode()
    if mode and mode != gaming.BEST_PERFORMANCE and gaming.set_power_mode(gaming.BEST_PERFORMANCE):
        state["power_before"] = mode
        lines.append(f"- Power mode: {gaming.POWER_MODES.get(mode, mode)} -> Best performance.")
    write_json(FLAG, state)
    time.sleep(1)  # let Windows hand the trimmed memory back before measuring
    lines.append(f"Free memory: {before:.1f} GB -> {gaming.free_memory_gb():.1f} GB. Website and voice keep running.")
    return "\n".join(lines)


def _turn_off() -> str:
    if not is_on():
        return "Development mode is already OFF."
    state = read_json(FLAG, {}) or {}
    lines = ["Development mode OFF."]
    resumed, gone = gaming.wake_frozen(state.get("frozen", []))
    if resumed:
        lines.append(f"- {resumed} frozen job process(es) carry on where they stopped.")
    if gaming.eco.restore(state.get("eco", [])):
        lines.append("- Background apps are out of efficiency mode.")
    if gone:
        lines.append(f"- {gone} frozen process(es) were gone (e.g. after a restart); start those jobs again if needed.")
    back = _restore(state.get("boosted", [])) + _restore(state.get("lowered", []))
    if back:
        lines.append(f"- {back} program priorities set back to what they were.")
    if not state.get("queue_was_paused"):
        planned.pause_queue(False)
        try:
            from . import runner
            runner.wake()
        except Exception:  # noqa: BLE001 - the runner starts by itself with the next job anyway
            pass
        lines.append("- Planned queue resumed.")
    if state.get("power_before") and gaming.set_power_mode(state["power_before"]):
        lines.append(f"- Power mode back to {gaming.POWER_MODES.get(state['power_before'], state['power_before'])}.")
    FLAG.unlink(missing_ok=True)
    if state.get("since"):
        lines.append(f"Development mode was on for {(time.time() - state['since']) / 60:.0f} min.")
    return "\n".join(lines)


def _busy() -> str:
    return "Development mode is busy switching; try again in a moment."


def toggle() -> str:
    with gaming._locked() as got:
        return (_turn_off() if is_on() else _turn_on()) if got else _busy()


def turn_on() -> str:
    with gaming._locked() as got:
        return _turn_on() if got else _busy()


def turn_off() -> str:
    with gaming._locked() as got:
        return _turn_off() if got else _busy()


def recover() -> str | None:
    """A mode switched on before the PC last started (a crash, a restart) is not really on any more: everything it
    froze is gone. Switch it off properly (queue, power mode, the switch file). Returns what was done, or None."""
    state = read_json(FLAG, None)
    if not isinstance(state, dict):
        return None
    try:
        booted = psutil.boot_time()
    except Exception:  # noqa: BLE001
        return None
    if state.get("since", booted) >= booted:
        return None
    with gaming._locked(wait=10) as got:
        if not got or not is_on():
            return None
        return "Found on after a restart, switched off.\n" + _turn_off()


def enforce(samples: dict | None = None) -> list[str]:
    """While development mode is on: freeze jobs that started since, boost what Claude / ComfyUI started since,
    lower programs opened since. Returns the newly frozen jobs (the only ones worth a notification).
    samples: the Job Monitor's process sample of this refresh (no second scan). It calls this every
    config "mode_check_seconds" (15 s), not every refresh: every 2 s was a constant load on a busy PC."""
    if not is_on():
        return []
    with gaming._locked(wait=0) as got:
        state = read_json(FLAG, None) if got and is_on() else None
        if not isinstance(state, dict):
            return []
        state.setdefault("frozen", [])
        snap = Snapshot(samples)
        frozen = gaming._freeze_new(state, website_too=False, skip=_skip_work(snap))
        boosted, lowered = _adjust(state, snap)
        # forget what has ended, so the file doesn't grow all day (Claude starts many short commands)
        before = len(state["boosted"]) + len(state["lowered"])
        for key in ("boosted", "lowered"):
            state[key] = [i for i in state[key]
                          if abs(snap.info.get(i["pid"], {}).get("create_time", -9) - i["created"]) <= 1]
        if frozen or boosted or lowered or before != len(state["boosted"]) + len(state["lowered"]):
            write_json(FLAG, state)
        return frozen


def status() -> str:
    mode = gaming.power_mode()
    lines = [f"Development mode is {'ON' if is_on() else 'OFF'}.", f"Free memory: {gaming.free_memory_gb():.1f} GB.",
             f"Power mode: {gaming.POWER_MODES.get(mode, mode) if mode else 'unknown'}."]
    if is_on():
        state = read_json(FLAG, {}) or {}
        lines.insert(1, f"On since {time.strftime('%H:%M', time.localtime(state.get('since', time.time())))}; "
                        f"{len(state.get('frozen', []))} job process(es) frozen, "
                        f"{len(state.get('boosted', []))} boosted, {len(state.get('lowered', []))} lowered.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    command = (argv[0] if argv else "status").lower()
    cleaned = recover()
    if cleaned:
        print(cleaned + "\n")
    actions = {"on": turn_on, "off": turn_off, "toggle": toggle, "status": status}
    if command not in actions:
        print("Use: devmode on | off | toggle | status")
        return 2
    print(actions[command]())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
