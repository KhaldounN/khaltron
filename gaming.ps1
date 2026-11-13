# Gaming mode: frees the PC's CPU and memory for a game (see monitor\gaming.py).
#   gaming.ps1 on | off | toggle | status
# Used by the Ctrl+Alt+G shortcut (toggle), the "gaming mode on/off" phrase in Claude, and the /gaming skill.
param([Parameter(Position = 0)][string]$Command = 'status')
. (Join-Path $PSScriptRoot 'modeswitch.ps1')
Write-Output (Invoke-ModeSwitch -Word 'gaming' -Module 'monitor.gaming' -Command $Command.ToLower() -LogName 'gaming.log')
