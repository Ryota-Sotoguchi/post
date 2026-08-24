param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$ProjectDir = (Join-Path $PSScriptRoot ".."),
    [string]$Time = "19:00",
    [string]$TaskName = "MBTI Asset Bot"
)

$resolvedProjectDir = (Resolve-Path $ProjectDir).Path
$resolvedPython = (Resolve-Path $PythonExe).Path

$action = New-ScheduledTaskAction -Execute $resolvedPython -Argument "-m mbti_tiktok_bot run-daily" -WorkingDirectory $resolvedProjectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Write-Host "Registered task '$TaskName' at $Time"
