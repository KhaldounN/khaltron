# jobq for PowerShell scripts: the same commands as jobq.py (see its help: .\jobq.ps1 -h).
# Called with & from a script, it runs inside that script's process, so "begin" fills in the script's own
# process id ($PID) by itself:   $id = & $jobq begin --name "My chain" --after library
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$rest = @($args)
if ($rest.Count -gt 0 -and $rest[0] -eq "begin" -and ($rest -notcontains "--pid")) { $rest += @("--pid", "$PID") }
& $py (Join-Path $PSScriptRoot "jobq.py") @rest
