# Creates "Restart MPD Streamdeck.lnk" on the current user's Desktop.
param(
    [string]$DesktopPath = (Join-Path $env:USERPROFILE "Desktop")
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$restartScript = Join-Path $repoRoot "restart.ps1"

if (-not (Test-Path $restartScript)) {
    throw "restart.ps1 not found at: $restartScript"
}

if (-not (Test-Path $DesktopPath)) {
    New-Item -ItemType Directory -Path $DesktopPath -Force | Out-Null
}

$lnkPath = Join-Path $DesktopPath "Restart MPD Streamdeck.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnkPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Normal -File `"$restartScript`""
$shortcut.WorkingDirectory = $repoRoot
$shortcut.Description = "Stop and start the MPD Streamdeck controller (same as pad 48 restart)."
$shortcut.IconLocation = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe,0"
$shortcut.Save()

Write-Host "[desktop] shortcut created: $lnkPath"
