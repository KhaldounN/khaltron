# Gaming mode: frees the PC's CPU and memory for a game (see monitor\gaming.py).
#   gaming.ps1 on | off | toggle | status
# Used by the Ctrl+Alt+G shortcut (toggle), the "gaming mode on/off" phrase in Claude, and the /gaming skill.
param([Parameter(Position = 0)][string]$Command = 'status')

$here = $PSScriptRoot
$python = Join-Path $here '.venv\Scripts\python.exe'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Push-Location $here
try {
    $out = & $python -m monitor.gaming $Command 2>&1 | Out-String
} finally { Pop-Location }
$out = $out.Trim()
Add-Content -Path (Join-Path $here 'state\gaming.log') -Value ("{0}  {1}`n{2}`n" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Command, $out) -Encoding UTF8
Write-Output $out
