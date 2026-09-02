<#
    Registers the image importer with Windows Task Scheduler.

    Sending runs on GitHub Actions and needs no PC, but importing does: the
    source carousels live on a OneDrive folder that only this machine can see.
    So this job converts whatever is new, publishes it, and pushes — after
    which Actions can post it without the machine being involved again.

    Running when nothing has changed is cheap and commits nothing.

    Run from an ordinary PowerShell prompt:
        ./scripts/register-sync-task.ps1
#>
param(
    [string]   $Distro     = "Ubuntu",
    [string]   $ProjectDir = "/home/n049395/work/tiktok",
    [string]   $TaskName   = "TikTok Image Import",
    [string[]] $Times      = @("07:00")
)

$ErrorActionPreference = "Stop"

$command  = "cd '$ProjectDir' && mkdir -p logs && .venv/bin/python -m tiktok_poster sync >> logs/sync.log 2>&1"
$argument = "-d $Distro -e bash -lc `"$command`""
$action   = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\wsl.exe" -Argument $argument

$triggers = foreach ($time in $Times) { New-ScheduledTaskTrigger -Daily -At $time }

# StartWhenAvailable catches up a slot the machine slept through. A full
# re-convert of the library takes about ten minutes, so the timeout is generous
# and overlapping runs are refused rather than queued.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName    $TaskName `
    -Action      $action `
    -Trigger     $triggers `
    -Settings    $settings `
    -Description "Converts new MBTI carousels from OneDrive and publishes them for TikTok to pull." `
    -Force | Out-Null

Write-Host "Registered '$TaskName' at $($Times -join ', ')."
Write-Host "Run it now with: Start-ScheduledTask -TaskName '$TaskName'"
