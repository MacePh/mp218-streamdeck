param(
    [string]$Config = "config.json",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Write-Host "[run] loading environment from $Path"
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            return
        }
        $parts = $line -split '=', 2
        if ($parts.Count -ne 2) {
            return
        }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.Length -ge 2) {
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

$controllerPath = Join-Path $PSScriptRoot "controller.py"
$configPath = Join-Path $PSScriptRoot $Config
$dotenvPath = Join-Path $PSScriptRoot ".env"

Import-DotEnv -Path $dotenvPath

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
