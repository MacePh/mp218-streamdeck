param(
    [string]$Config = "config.json"
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$controllerPath = Join-Path $repoRoot "controller.py"
$configPath = Join-Path $repoRoot $Config

if (-not (Test-Path $controllerPath)) {
    throw "controller.py not found at: $controllerPath"
}
if (-not (Test-Path $configPath)) {
    throw "Config not found at: $configPath"
}

$escapedController = [Regex]::Escape($controllerPath)
$escapedConfig = [Regex]::Escape($configPath)
$matches = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and
        $_.CommandLine -match $escapedController -and
        $_.CommandLine -match $escapedConfig
    })

foreach ($p in $matches) {
    Write-Host "[restart] stopping PID $($p.ProcessId)"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

if ($matches.Count -eq 0) {
    Write-Host "[restart] no matching controller process found"
} else {
    Start-Sleep -Milliseconds 400
}

$runScript = Join-Path $repoRoot "run.ps1"
& $runScript -Config $Config -Force
