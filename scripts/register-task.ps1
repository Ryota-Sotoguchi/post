<#
    Registers the TikTok draft sender with Windows Task Scheduler.

    The job runs inside WSL, but WSL's own cron only fires while a WSL session
    happens to be up. Task Scheduler starts one on demand, so the schedule
    survives a reboot and a machine that is only switched on intermittently.

    Run from an ordinary PowerShell prompt:
        ./scripts/register-task.ps1
#>
param(
    [string]   $Distro     = "Ubuntu",
    [string]   $ProjectDir = "/home/n049395/work/tiktok",
    [string]   $TaskName   = "TikTok Draft Sender",
    [string[]] $Times      = @("08:00", "12:00", "18:00", "20:00", "22:00")
)

$ErrorActionPreference = "Stop"

# One carousel per firing, so the five triggers spread the day's posts out
# instead of dropping five drafts into the inbox at once.
$command  = "cd '$ProjectDir' && .venv/bin/python -m tiktok_poster post --count 1 >> logs/post.log 2>&1"
$argument = "-d $Distro -e bash -lc `"$command`""
$action   = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\wsl.exe" -Argument $argument

$triggers = foreach ($time in $Times) { New-ScheduledTaskTrigger -Daily -At $time }

# StartWhenAvailable catches up a slot the machine slept through; IgnoreNew
# stops a slow upload from overlapping the next trigger.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Description "Converts the next MBTI carousel, publishes it to GitHub Pages and sends it to TikTok drafts." | Out-Null

Write-Host "Registered '$TaskName' for $($Times -join ', ')."
