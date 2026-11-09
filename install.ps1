# Sets up Khaltron 9000 on this PC (safe to run again). From this folder:
#   powershell -ExecutionPolicy Bypass -File install.ps1               (everything)
#   powershell -ExecutionPolicy Bypass -File install.ps1 -NoStartup    (don't start it when you log in)
#   powershell -ExecutionPolicy Bypass -File install.ps1 -NoShortcuts  (no desktop shortcuts)
# It makes:
#  1. its own Python environment (.venv) with the packages in requirements.txt
#  2. desktop shortcuts: "Khaltron 9000" (Ctrl+Alt+J) and "Khaltron Gaming Mode" (Ctrl+Alt+G, switches gaming mode)
#  3. a scheduled task "Khaltron 9000" that starts it hidden in the tray when you log in (current user only)
# Undo: delete the shortcuts, and  Unregister-ScheduledTask -TaskName "Khaltron 9000" -Confirm:$false
param([switch]$NoShortcuts, [switch]$NoStartup)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$venv = Join-Path $here ".venv"

# --- Python 3.11 or newer (the "py" launcher first: it finds the newest Python even when it isn't on PATH) ---------
function Find-Python {
    foreach ($candidate in @(@("py", "-3"), @("python"))) {
        try {
            $exe, $rest = $candidate
            $version = & $exe @rest -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$version -ge [version]"3.11") { return , $candidate }
        } catch { }
    }
    return $null
}
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    $python = Find-Python
    if (-not $python) {
        Write-Host "Khaltron needs Python 3.11 or newer (with tkinter, which the standard installer includes)." -ForegroundColor Red
        Write-Host "Get it from https://www.python.org/downloads/windows/ , then run this script again."
        exit 1
    }
    $exe, $rest = $python
    & $exe @rest -m venv $venv
}
& "$venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r (Join-Path $here "requirements.txt")
New-Item -ItemType Directory -Force (Join-Path $here "state") | Out-Null
"Python environment ready."

$pythonw = "$venv\Scripts\pythonw.exe"
$app = Join-Path $here "monitor.pyw"
$icon = Join-Path $here "assets\khaltron.ico"
if (-not (Test-Path $icon)) { & "$venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'$here'); from monitor import theme; theme.save_icon(r'$icon')" }

if (-not $NoShortcuts) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    foreach ($old in "Job Monitor", "Khaltron") {  # names from before the renames
        Remove-Item (Join-Path $desktop "$old.lnk") -ErrorAction SilentlyContinue
    }
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $desktop "Khaltron 9000.lnk"))
    $link.TargetPath = $pythonw
    $link.Arguments = "`"$app`""
    $link.WorkingDirectory = $here
    $link.Hotkey = "CTRL+ALT+J"
    $link.IconLocation = "$icon,0"
    $link.Description = "Background jobs: what runs now and what is queued next"
    $link.Save()
    "Desktop shortcut 'Khaltron 9000' made (Ctrl+Alt+J)."
    # gaming mode on/off from anywhere (skipped if a "Gaming Mode" shortcut already has that hotkey)
    if (-not (Test-Path (Join-Path $desktop "Gaming Mode.lnk"))) {
        $link = $shell.CreateShortcut((Join-Path $desktop "Khaltron Gaming Mode.lnk"))
        $link.TargetPath = "powershell.exe"
        $link.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $here 'gaming.ps1')`" toggle"
        $link.WorkingDirectory = $here
        $link.Hotkey = "CTRL+ALT+G"
        $link.WindowStyle = 7
        $link.IconLocation = "$icon,0"
        $link.Description = "Gaming mode on/off: freezes background jobs so a game gets the PC"
        $link.Save()
        "Desktop shortcut 'Khaltron Gaming Mode' made (Ctrl+Alt+G)."
    }
}

if (-not $NoStartup) {
    foreach ($old in "Job Monitor", "Khaltron") {
        if (Get-ScheduledTask -TaskName $old -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $old -Confirm:$false }
    }
    $action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$app`" --tray" -WorkingDirectory $here
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger.Delay = "PT20S"
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName "Khaltron 9000" -Action $action -Trigger $trigger -Settings $settings `
        -Description "Starts Khaltron 9000 in the tray at logon ($here)" -Force | Out-Null
    "Scheduled task 'Khaltron 9000' made (starts in the tray when you log in)."
}
"Done. Start it with the desktop shortcut, Ctrl+Alt+J, or: .venv\Scripts\pythonw.exe monitor.pyw"
