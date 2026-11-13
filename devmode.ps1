# Development mode: the memory goes to your work (Claude, terminal, editor, Stable Diffusion); see monitor\devmode.py.
#   devmode.ps1 on | off | toggle | status
# Used by the Ctrl+Alt+D shortcut (toggle), the "dev mode on/off" phrase in Claude, and the /devmode skill.
param([Parameter(Position = 0)][string]$Command = 'status')
. (Join-Path $PSScriptRoot 'modeswitch.ps1')
Write-Output (Invoke-ModeSwitch -Word 'dev' -Module 'monitor.devmode' -Command $Command.ToLower() -LogName 'devmode.log')
