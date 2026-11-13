# Shared by gaming.ps1 and devmode.ps1: switch a mode, fast.
# First it asks the Khaltron 9000 that is already running (one line through its local port, answered in about a
# second); only when none answers does it start a new Python (~5 s on a busy PC). Every switch is logged.
function Invoke-ModeSwitch([string]$Word, [string]$Module, [string]$Command, [string]$LogName) {
    $here = $PSScriptRoot
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $port = 59126
    try {
        $cfg = Get-Content (Join-Path $here 'config.json') -Raw -ErrorAction Stop | ConvertFrom-Json
        if ($cfg.port) { $port = [int]$cfg.port }
    } catch {}
    $out = $null
    $key = ''
    try { $key = (Get-Content (Join-Path $here 'state\port.token') -Raw -ErrorAction Stop).Trim() } catch {}
    try {
        if (-not $key) { throw 'no key: Khaltron has not started yet' }
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect('127.0.0.1', $port)        # refused at once when Khaltron isn't running
        $client.ReceiveTimeout = 90000             # turning a mode on can take some seconds
        $stream = $client.GetStream()
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("$key $Word $Command`n")  # the key from state\port.token
        $stream.Write($bytes, 0, $bytes.Length)
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        $out = $reader.ReadToEnd().Trim()
        $client.Close()
    } catch { $out = $null }
    if (-not $out) {  # no Khaltron running (or an old one that doesn't know this message): the slow way
        $python = Join-Path $here '.venv\Scripts\python.exe'
        Push-Location $here
        try { $out = (& $python -m $Module $Command 2>&1 | Out-String).Trim() } finally { Pop-Location }
    }
    Add-Content -Path (Join-Path $here "state\$LogName") -Value ("{0}  {1}`n{2}`n" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Command, $out) -Encoding UTF8
    return $out
}
