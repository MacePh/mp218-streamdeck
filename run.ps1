param(
    [string]$Config = "config.json"
)

$ErrorActionPreference = "Stop"

$venvActivate = Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1"
if (-not $env:VIRTUAL_ENV -and (Test-Path $venvActivate)) {
    . $venvActivate
    Write-Host "[run] activated virtual environment"
}

python "$PSScriptRoot\controller.py" --config "$PSScriptRoot\$Config"