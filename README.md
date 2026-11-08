# Khaltron 9000

**A cybernetic sentinel for your background jobs.** Khaltron 9000 is a small Windows desktop app that watches the long-running jobs
on your PC, the ones that run for hours in the background (data processing, AI model runs, batch scripts), and
shows you in one dark window, watched over by a mechanical raccoon with glowing eyes:

- **what is running now**: what each job is doing, its progress, how long it has run, time left, and its RAM and CPU;
- **what is queued after it**, and what each waiting job is waiting for;
- **what finished or failed**, with its log one click away;
- **how much of your PC is free**: RAM in use (the same numbers as Task Manager), CPU, and how much of that your jobs take;
- **where all of your PC's power goes**: every program you run (apps, browsers, games) and Windows itself, grouped
  by program, with its share of the CPU and the RAM.

It also gives you a simple **job queue** (`jobq`): line jobs up and they run one at a time, each when the one it
waits for is done. So two heavy jobs never fight over your memory, and an AI assistant or a script can queue work you
can still see and control.

![Khaltron 9000's Overview: a one-line briefing, RAM / CPU / jobs cards, the running jobs, what is next, and where the PC's power goes](assets/screenshot.png)

## Features

- **Two views.** *Overview* (the default) is the whole picture at a glance: a one-sentence briefing with a status
  chip (CALM, WORKING, BUSY, LOW MEMORY, GAMING), the RAM / CPU / jobs cards, the running jobs, the next three
  jobs, and the five programs using the most CPU. *Details* has every table: the full queue with its buttons,
  every program on the PC, finished jobs, scheduled tasks, Python processes and problems.
- **HUD cards** for RAM, CPU and your jobs, each with a live graph of the last 3 minutes; running jobs as cards with
  glowing progress bars, their RAM and CPU, and their own buttons.
- **Programs on this PC**: everything running, grouped by program (Chrome's 30 processes are one row). It reads every
  process in one Windows call (as Task Manager does), so it costs a few milliseconds. What no program owns (drivers,
  interrupts, kernel and cache memory) gets its own row, so the totals add up. Watch-only: nothing there can be stopped.
- **Live view**, refreshed every 2 seconds. It only *reads* status files and process info, so it never slows a job down.
- **Planned queue**: `jobq add --name "..." --after previous -- python my_script.py`. A small runner process starts the
  jobs in order and keeps going when the window is closed.
- **Full control**: stop a job (and everything it started), reorder or remove waiting jobs, run one next, pause the
  queue. Every action asks "Are you sure?" first.
- **Protected processes**: things that must never be stopped (by default: a voice server, a website, Khaltron itself)
  have no Stop button, and are checked again right before any stop.
- **Notifications**: a Windows pop-up when a job starts, finishes or fails, and when free memory runs low.
- **A header that watches**: a mechanical raccoon grips a steel ledge where your six busiest apps stand as
  cards; in monitor mode (cyan) it looks from card to card. Click **GAMING MODE** and it plays the design's
  sequence once: red, it pushes in and glares at every card (TERMINATE?, WARNED), looks down as the beams flood
  the ledge (PAUSED), then locks still. At that moment the jobs are really frozen. Cards it doesn't pause
  (your browser...) honestly say SPARED. The design package it follows is in `design/khaltron-header/`.
- **Gaming mode**: one click on the header's GAMING MODE button (or Ctrl+Alt+G) freezes every background job, any other
  heavy Python script of yours and safe background apps (OneDrive by default) so a game gets the CPU and memory,
  and puts everything back when you switch it off. A pop-up says what was frozen and how much memory it freed.
- **Light on your PC**: one Windows call per refresh reads every process (~55 ms), and the animations slow down
  when another window has the focus and stop in the tray. The window itself uses about 1% of the CPU.
- **Tray icon**: closing the window hides it next to the clock. It can start with Windows.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer (with tkinter, which the standard Windows installer includes)

## Install

```powershell
git clone https://github.com/KhaldounN/khaltron.git
cd khaltron
powershell -ExecutionPolicy Bypass -File install.ps1
```

`install.ps1` makes a Python environment (`.venv`) with the four packages it needs (`psutil`, `pystray`, `pillow`,
`pytest`), a desktop shortcut **Khaltron 9000** (hotkey **Ctrl+Alt+J**), and a logon task that starts it in the tray.
Prefer to do it by hand?

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install psutil pystray pillow pytest
.venv\Scripts\pythonw.exe monitor.pyw
```

## Queue jobs with `jobq`

```powershell
# run a script now (or as soon as the queue is free)
.\jobq.ps1 add --name "Train the model" --cwd C:\work\project -- .venv\Scripts\python.exe -u train.py

# run another one after it
.\jobq.ps1 add --name "Evaluate" --after previous -- .venv\Scripts\python.exe -u evaluate.py

.\jobq.ps1 list        # what is queued, running and done
.\jobq.ps1 pause       # no new job starts (running ones go on);  .\jobq.ps1 resume
```

- `--after` can be `previous` (the last job in the queue), a job id, or `pid:<number>` (wait for a process to end),
  and you can give it more than once.
- The command starts at the first word that isn't an option, so the `--` is optional (PowerShell drops it anyway
  when it runs `jobq.ps1`).
- Each job's output goes to `state\logs\<id>.log`, and the window shows its last line as "Doing now".
- A `.ps1` command is run with PowerShell.

A script that runs on its own can also just **report in**, so it shows in the window:

```powershell
$job = & .\jobq.ps1 begin --name "Nightly export"      # it shows as running (its process id is filled in)
# ... the script's work ...
& .\jobq.ps1 finish $job --exit $LASTEXITCODE
```

## Gaming mode

`gaming.ps1 on | off | toggle | status`, or Ctrl+Alt+G, the tray menu, or *Start / control* in the window.
**On** pauses the planned queue, freezes (suspends) every running background job and asks Windows to move its memory
aside, stops the read-aloud voice server and sets the Windows power mode to Best performance. What it changed is
written to `~/.claude/gaming.json` (the file existing *is* the switch). **Off** undoes exactly that, and frozen jobs
carry on where they were. While it is on, a job that starts anyway is frozen too. Protected processes are never
frozen. Every switch is logged in `state\gaming.log`.

## Make it watch your own jobs

Khaltron was built to watch the jobs of one project (a book-analysis website). That project's readers sit in
`monitor\sources\` (`book_main.py`, `book_stage2.py`, `book_library.py`), and they switch themselves off when that
project isn't there. Without them you still get the queue, the Python processes, scheduled tasks and the PC's health.

To watch something of your own, add a reader to `monitor\sources\` that returns `Job` rows (see `monitor\model.py`)
and call it from `monitor\collect.py`. A reader only *reads* (status files, logs, processes), so the window stays quick.

Settings go in a `config.json` next to `monitor.pyw`; any key of `DEFAULTS` in `monitor\config.py` can be changed:

```json
{ "low_memory_mb": 2000, "scheduled_tasks": ["My nightly task"], "refresh_seconds": 3 }
```

Processes that must never be stopped are listed in `KNOWN` in `monitor\sources\processes.py` (the `True` ones).

## How it is built

| File | What it does |
|---|---|
| `monitor.pyw` | starts the window and the tray icon; a second launch just shows the first window |
| `monitor\ui.py` | the window (tkinter): tables, buttons, confirmations |
| `monitor\hunter.py` | the header, built to `design/khaltron-header/` (its README is the spec): the raccoon, its eyes and beams, the cards, the gaming-mode sequence |
| `monitor\hud.py` | the stat cards with live graphs, the job cards, the overview parts |
| `monitor\theme.py` | every colour and font, the logo, the dark title bar |
| `monitor\collect.py` | one refresh: asks every reader and adds up what the jobs use |
| `monitor\sources\` | the readers (jobs, processes, every program on the PC, PC health, scheduled tasks) |
| `monitor\planned.py`, `monitor\runner.py`, `jobq.py` | the planned queue, the process that runs it, and its command line |
| `monitor\actions.py`, `monitor\protect.py` | what the buttons do, and the never-stop list |
| `monitor\alerts.py`, `monitor\tray.py` | notifications, history, the tray icon |
| `monitor\gaming.py`, `gaming.ps1` | gaming mode |

Run the tests with `.venv\Scripts\python.exe -m pytest`.

## License

[MIT](LICENSE): free to use, copy, change and share.

The bundled fonts are under the SIL Open Font License: Orbitron (The Orbitron Project Authors) and
JetBrains Mono (The JetBrains Mono Project Authors); their licences are in `assets/fonts/`. They are
loaded privately when Khaltron starts; nothing is installed in Windows.
