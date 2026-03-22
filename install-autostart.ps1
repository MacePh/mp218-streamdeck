param(
    [string]$TaskName = "mpd-streamdeck-autostart",
    [int]$DelaySeconds = 15
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript = Join-Path $repoRoot "run.ps1"

if (-not (Test-Path $runScript)) {
    throw "run.ps1 not found at: $runScript"
}

if ($DelaySeconds -lt 0) {
    throw "DelaySeconds must be 0 or greater."
}

$taskUser = if ($env:USERDOMAIN -and $env:USERNAME) {
    "$($env:USERDOMAIN)\$($env:USERNAME)"
} else {
    $env:USERNAME
}

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $existingTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$escapedRunScript = $runScript.Replace('"', '""')
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$escapedRunScript`"" `
    -WorkingDirectory $repoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
if ($DelaySeconds -gt 0) {
    $trigger.Delay = "PT$DelaySeconds`S"
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal `
    -UserId $taskUser `
    -LogonType Interactive `
    -RunLevel Limited

$description = "Autostart MPD Streamdeck controller at user logon."

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description $description | Out-Null

Write-Host "[autostart] installed task '$TaskName' for user '$taskUser'"
Write-Host "[autostart] target script: $runScript"
