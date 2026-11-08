# Sets up Khaltron, the Job Monitor (safe to run again):
#  1. its own Python environment (.venv) with psutil, pystray, pillow, pytest
#  2. a desktop shortcut "Khaltron" (its logo as the icon) with the hotkey Ctrl+Alt+J
#  3. a scheduled task "Khaltron" that starts it hidden in the tray when you log in
# (the older "Job Monitor" shortcut and task, from before the rename, are removed)
# Undo: delete the shortcut, and  Unregister-ScheduledTask -TaskName "Khaltron" -Confirm:$false
$here = $PSScriptRoot
$venv = Join-Path $here ".venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) { python -m venv $venv }
& "$venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check psutil pystray pillow pytest
$pythonw = "$venv\Scripts\pythonw.exe"
$app = Join-Path $here "monitor.pyw"

$desktop = [Environment]::GetFolderPath("Desktop")
Remove-Item (Join-Path $desktop "Job Monitor.lnk") -ErrorAction SilentlyContinue
if (Get-ScheduledTask -TaskName "Job Monitor" -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName "Job Monitor" -Confirm:$false }
$icon = Join-Path $here "assets\khaltron.ico"
if (-not (Test-Path $icon)) { & "$venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'$here'); from monitor import theme; theme.save_icon(r'$icon')" }
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $desktop "Khaltron.lnk"))
$link.TargetPath = $pythonw
$link.Arguments = "`"$app`""
$link.WorkingDirectory = $here
$link.Hotkey = "CTRL+ALT+J"
$link.IconLocation = "$icon,0"
$link.Description = "Background jobs: what runs now and what is queued next"
$link.Save()
"Desktop shortcut Khaltron made (Ctrl+Alt+J)."

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$app`" --tray" -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT20S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "Khaltron" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Starts Khaltron (the Job Monitor) in the tray at logon (job monitor\install.ps1)" -Force | Out-Null
"Scheduled task 'Khaltron' made (starts in the tray at logon)."
