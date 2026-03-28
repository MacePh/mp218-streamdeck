param(
    [switch]$Once,
    [double]$PollSeconds = 0.5,
    [string]$SessionHint = "agent:main:main",
    [ValidateSet("full", "summary")]
    [string]$SpeechMode = "full",
    [string]$Voice = ""
)

$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Write-Host "[boris-voice] loading environment from $Path"
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

$root = $PSScriptRoot
$dotenvPath = Join-Path $root ".env"
Import-DotEnv -Path $dotenvPath

$venvActivate = Join-Path $root "venv\Scripts\Activate.ps1"
if (-not $env:VIRTUAL_ENV -and (Test-Path $venvActivate)) {
    . $venvActivate
    Write-Host "[boris-voice] activated virtual environment"
}

$argsList = @(
    (Join-Path $root "boris_voice_sidecar.py"),
    "--poll-seconds", "$PollSeconds",
    "--session-hint", $SessionHint,
    "--speech-mode", $SpeechMode
)

if ($Voice) {
    $argsList += @("--voice", $Voice)
}
if ($Once) {
    $argsList += "--once"
}

python @argsList
