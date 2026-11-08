# Job Monitor

A small desktop window that shows the background jobs running on this PC, what is queued after them, and how much
memory is left, with buttons to control them.

- **Open it:** the desktop shortcut "Job Monitor" or **Ctrl+Alt+J**. It also starts in the tray at logon.
  Closing the window hides it to the tray (icon by the clock); right-click the icon > Quit to end it.
- **Set up / repair:** `powershell -ExecutionPolicy Bypass -File install.ps1`
- **Tests:** `.venv\Scripts\python.exe -m pytest`

## What it shows
| Part | Where it comes from |
|---|---|
| Memory free, CPU | Windows (the smaller of free RAM and remaining commit: the real limit for big models) |
| Book analyses | `book analyzer v2\results\jobs\<key>.json` (the website's worker) |
| Stage 2 | `results\jobs\second_stage\` status, queue, failed list and log |
| Library pre-analysis | the `analyze_library.py` process + `results\library_progress.log` |
| Planned jobs | `state\planned.json` (jobs queued with `jobq`) |
| Scheduled tasks | Windows Task Scheduler (names in `monitor\config.py`) |
| Python processes | every known python process, and unknown ones using > 300 MB or > 20% CPU |

Settings can be changed in a `config.json` next to this file (any keys of `DEFAULTS` in `monitor\config.py`).

## The planned queue (`jobq`)
Jobs queued here run **one at a time, in order**, each when what it waits for is over. A small runner process
(`python -m monitor.runner`) starts them; it runs on its own (the window can be closed) and stops when the queue
is empty.

```powershell
.\jobq.ps1 add --name "Deep analysis" --after library --cwd "..\book analyzer v2" -- .venv\Scripts\python.exe -u scripts\deep_analysis.py
.\jobq.ps1 add --name "Then this" --after previous -- some_script.ps1
.\jobq.ps1 list
```
`--after`: `library` (the library pre-analysis), `stage2`, `main` (a book analysis), `previous` (the last queued
job), a job id, or `pid:<number>`. Output goes to `state\logs\<id>.log`; the window shows its last line.

A script that runs itself can just report in (it shows as waiting / running / done):
```powershell
$jobq = "...\job monitor\jobq.ps1"
$job = & $jobq begin --name "My chain" --after library   # its own process id is filled in
& $jobq running $job
& $jobq finish $job --exit $LASTEXITCODE
```

## Safety
Every control button asks first. The read-aloud voice server, the Book Analyzer website (and its watchdog) and the
monitor itself are **never** stopped: they have no Stop button, and `monitor\protect.py` checks again (the process
and all its children) right before any stop. Stage 2 is paused with its own `second_stage.pause()`, so the book's
try is given back and it isn't marked as failed.
