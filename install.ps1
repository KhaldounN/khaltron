# Sets up the Job Monitor (safe to run again):
#  1. its own Python environment (.venv) with psutil, pystray, pillow, pytest
#  2. a desktop shortcut "Job Monitor" with the hotkey Ctrl+Alt+J
#  3. a scheduled task "Job Monitor" that starts it hidden in the tray when you log in
# Undo: delete the shortcut, and  Unregister-ScheduledTask -TaskName "Job Monitor" -Confirm:$false
$here = $PSScriptRoot
$venv = Join-Path $here ".venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) { python -m venv $venv }
& "$venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check psutil pystray pillow pytest
$pythonw = "$venv\Scripts\pythonw.exe"
$app = Join-Path $here "monitor.pyw"

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Job Monitor.lnk"))
$link.TargetPath = $pythonw
$link.Arguments = "`"$app`""
$link.WorkingDirectory = $here
$link.Hotkey = "CTRL+ALT+J"
$link.Description = "Background jobs: what runs now and what is queued next"
$link.Save()
"Desktop shortcut made (Ctrl+Alt+J)."

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$app`" --tray" -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT20S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "Job Monitor" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Starts the Job Monitor in the tray at logon (job monitor\install.ps1)" -Force | Out-Null
"Scheduled task 'Job Monitor' made (starts in the tray at logon)."
