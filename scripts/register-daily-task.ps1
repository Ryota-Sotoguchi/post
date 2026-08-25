<#
    Registers the daily MBTI generation with Windows Task Scheduler.

    Generation lives in WSL, but WSL's own cron only runs while a WSL session
    happens to be up. Task Scheduler starts WSL on demand, so the schedule
    survives a reboot and a machine that is only switched on intermittently.

    --no-reconcile makes the run follow state/phone_export_daemon_state.json
    rather than counting what is already in out/. Reconciling by file count
    ignores the slots the state records as done and regenerates them.

    Run from an ordinary PowerShell prompt:
        ./scripts/register-daily-task.ps1
#>
param(
    [string]   $Distro     = "Ubuntu-24.04",
    [string]   $ProjectDir = "/home/alr_k/work/tiktok",
    [string]   $TaskName   = "MBTI Daily Generate",
    [string[]] $Times      = @("08:00", "12:00", "18:00")
)

$ErrorActionPreference = "Stop"

$command  = "cd '$ProjectDir' && .venv-linux/bin/python -m mbti_tiktok_bot run-daemon --run-once --no-reconcile >> logs/task.log 2>&1"
$argument = "-d $Distro -e bash -lc `"$command`""
$action   = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\wsl.exe" -Argument $argument

$triggers = foreach ($time in $Times) { New-ScheduledTaskTrigger -Daily -At $time }

# StartWhenAvailable catches up a slot the machine slept through; IgnoreNew
# keeps a slow run from overlapping the next trigger.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Description "Generates the day's MBTI slides in WSL and writes them to the OneDrive folder." | Out-Null

Write-Host "Registered '$TaskName' for $($Times -join ', ')."
