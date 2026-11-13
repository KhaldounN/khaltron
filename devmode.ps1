# Development mode: your work (Claude, terminal, editor, Stable Diffusion) gets the PC first (see monitor\devmode.py).
#   devmode.ps1 on | off | toggle | status
# Used by the Ctrl+Alt+D shortcut (toggle), the "dev mode on/off" phrase in Claude, and the /devmode skill.
param([Parameter(Position = 0)][string]$Command = 'status')

$here = $PSScriptRoot
$python = Join-Path $here '.venv\Scripts\python.exe'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Push-Location $here
try {
    $out = & $python -m monitor.devmode $Command 2>&1 | Out-String
} finally { Pop-Location }
$out = $out.Trim()
Add-Content -Path (Join-Path $here 'state\devmode.log') -Value ("{0}  {1}`n{2}`n" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Command, $out) -Encoding UTF8
Write-Output $out
