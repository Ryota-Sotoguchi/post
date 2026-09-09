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
    # Empty means the default distro. Naming one that does not exist fails the
    # task with 0xFFFFFFFF and writes no log, which is indistinguishable from
    # the task never having run - "Ubuntu" was wrong for Ubuntu-24.04.
    [string]   $Distro     = "",
    [string]   $ProjectDir = "/home/n049395/work/tiktok",
    [string]   $TaskName   = "TikTok Image Import",
    [string[]] $Times      = @("07:00")
)

$ErrorActionPreference = "Stop"

$command  = "cd '$ProjectDir' && mkdir -p logs && .venv/bin/python -m tiktok_poster sync >> logs/sync.log 2>&1"
$target   = if ($Distro) { "-d $Distro " } else { "" }
$argument = "$target-e bash -lc `"$command`""

# A distro that cannot be reached would leave the task failing silently every
# morning, so prove the command runs before registering it.
& "$env:SystemRoot\System32\wsl.exe" @($target.Trim() -split ' ' | Where-Object { $_ }) -e bash -lc "cd '$ProjectDir' && echo ok" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "wsl could not reach $ProjectDir$(if ($Distro) { " in $Distro" } else { " in the default distro" }). Check ``wsl -l -v``."
}
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
