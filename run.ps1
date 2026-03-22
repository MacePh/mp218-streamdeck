param(
    [string]$Config = "config.json",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$controllerPath = Join-Path $PSScriptRoot "controller.py"
$configPath = Join-Path $PSScriptRoot $Config

if (-not $Force) {
    $escapedController = [Regex]::Escape($controllerPath)
    $escapedConfig = [Regex]::Escape($configPath)
    $existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^python(w)?\.exe$' -and
            $_.CommandLine -match $escapedController -and
            $_.CommandLine -match $escapedConfig
        } |
        Select-Object -First 1

    if ($null -ne $existing) {
        Write-Host "[run] controller already running (PID $($existing.ProcessId)); use -Force to bypass"
        exit 0
    }
}

$venvActivate = Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1"
if (-not $env:VIRTUAL_ENV -and (Test-Path $venvActivate)) {
    . $venvActivate
    Write-Host "[run] activated virtual environment"
}

python "$controllerPath" --config "$configPath"