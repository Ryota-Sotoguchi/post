param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$ProjectDir = (Join-Path $PSScriptRoot ".."),
    [string[]]$Times = @("08:00", "12:00", "18:00"),
    [string]$TaskPrefix = "MBTI Phone Export",
    [datetime]$StartDate = (Get-Date).Date,
    [switch]$RunWhenLoggedOut
)

$ErrorActionPreference = "Stop"

$resolvedProjectDir = (Resolve-Path $ProjectDir).Path
$resolvedPython = (Resolve-Path $PythonExe).Path
$runnerScript = (Resolve-Path (Join-Path $PSScriptRoot 'run_daily.ps1')).Path
$powershellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
$userId = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
$logonType = if ($RunWhenLoggedOut) { "S4U" } else { "Interactive" }
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType $logonType -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet
$settings.WakeToRun = $true
$settings.StartWhenAvailable = $true
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries = $false

$normalizedTimes = @(
    $Times |
        ForEach-Object {
            try {
                (Get-Date $_ -ErrorAction Stop).ToString("HH:mm")
            } catch {
                throw "Invalid time '$_'. Use HH:mm format."
            }
        } |
        Select-Object -Unique
)

$desiredTaskNames = $normalizedTimes | ForEach-Object { "$TaskPrefix $($_.Replace(':', ''))" }
$taskNamePattern = '^{0} \d{{4}}$' -f [regex]::Escape($TaskPrefix)

Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -match $taskNamePattern -and $desiredTaskNames -notcontains $_.TaskName } |
    ForEach-Object {
        Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "Removed stale task '$($_.TaskName)'"
    }

foreach ($time in $normalizedTimes) {
    $safeTime = $time.Replace(":", "")
    $taskName = "$TaskPrefix $safeTime"
    $actionArgs = @(
        '-NoProfile'
        '-WindowStyle'
        'Hidden'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        ('"{0}"' -f $runnerScript)
        '-PythonExe'
        ('"{0}"' -f $resolvedPython)
        '-Slot'
    ) -join ' '
    $action = New-ScheduledTaskAction -Execute $powershellExe -Argument $actionArgs -WorkingDirectory $resolvedProjectDir
    $trigger = New-ScheduledTaskTrigger -Daily -At $time
    $startAt = Get-Date ("{0} {1}" -f $StartDate.ToString("yyyy-MM-dd"), $time)
    $trigger.StartBoundary = $startAt.ToString("s")
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
    Write-Host "Registered task '$taskName' at $time starting $($StartDate.ToString('yyyy-MM-dd')) with logon type $logonType"
}