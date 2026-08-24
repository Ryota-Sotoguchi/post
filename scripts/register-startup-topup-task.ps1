param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$ProjectDir = (Join-Path $PSScriptRoot ".."),
    [string]$TaskName = "MBTI Startup Top Up",
    [int]$TargetCount = 0,
    [int]$DelayMinutes = 1
)

$ErrorActionPreference = "Stop"

$resolvedProjectDir = (Resolve-Path $ProjectDir).Path
$resolvedPython = if ([System.IO.Path]::IsPathRooted($PythonExe)) {
    $PythonExe
} else {
    (Resolve-Path (Join-Path $resolvedProjectDir $PythonExe)).Path
}
$runnerScript = (Resolve-Path (Join-Path $PSScriptRoot "run-startup-topup.ps1")).Path
$powershellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
$userId = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet
$settings.StartWhenAvailable = $true
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries = $false
$settings.MultipleInstances = "IgnoreNew"

$actionArgs = @(
    "-NoProfile"
    "-WindowStyle"
    "Hidden"
    "-ExecutionPolicy"
    "Bypass"
    "-File"
    ('"{0}"' -f $runnerScript)
    "-PythonExe"
    ('"{0}"' -f $resolvedPython)
    "-TargetCount"
    $TargetCount
) -join " "

$action = New-ScheduledTaskAction -Execute $powershellExe -Argument $actionArgs -WorkingDirectory $resolvedProjectDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
if ($DelayMinutes -gt 0) {
    $trigger.Delay = "PT${DelayMinutes}M"
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
Write-Host "Registered startup top-up task '$TaskName' for $userId with delay ${DelayMinutes}m"
