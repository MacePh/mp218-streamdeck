$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$controllerPath = Join-Path $root "controller.py"
$configPath = Join-Path $root "config.json"
$escapedController = [Regex]::Escape($controllerPath)
$escapedConfig = [Regex]::Escape($configPath)

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and
        $_.CommandLine -match $escapedController -and
        $_.CommandLine -match $escapedConfig
    } |
    ForEach-Object {
        Write-Host "[mpd218] stopping PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

& (Join-Path $root "run.ps1")
