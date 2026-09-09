<#
    Registers the daily run with Windows Task Scheduler.

    Generation and publishing now live in one repo, so this is one task:
    generate the slot's carousels, then convert them and push to GitHub Pages.
    There used to be two tasks on two machines handing off through a OneDrive
    folder; the sync half ran on a work PC. Both halves run here now.

    Everything runs in WSL. WSL's own cron only runs while a WSL session
    happens to be up, so Task Scheduler starts it on demand and the schedule
    survives a reboot and a machine that is only switched on intermittently.

    --no-reconcile makes the run follow state/phone_export_daemon_state.json
    rather than counting what is already in out/. Reconciling by file count
    ignores the slots the state records as done and regenerates them.

    Run from an ordinary PowerShell prompt:
        ./scripts/register-daily-task.ps1
#>
param(
    [string]   $Distro     = "Ubuntu-24.04",
    [string]   $ProjectDir = "/home/alr_k/projects/tiktok",
    [string]   $TaskName   = "MBTI Daily",
    # Four slots of four carousels covers all 16 MBTI types in a day, so a
    # theme starts and finishes on the same date.
    [string[]] $Times      = @("08:00", "12:00", "16:00", "20:00")
)

$ErrorActionPreference = "Stop"

# A wrong path here is the failure that stopped generation for three days: the
# task pointed at a directory the package had been moved out of, and every run
# exited 1 into a log nobody was reading. Fail at registration instead.
$probe = & wsl.exe -d $Distro -e bash -lc "test -f '$ProjectDir/src/mbti_tiktok_bot/cli.py' && echo ok" 2>$null
if ($probe -ne "ok") {
    throw "Cannot see the project at $ProjectDir in $Distro. Fix the path before registering."
}

$generate = ".venv-linux/bin/python -m mbti_tiktok_bot run-daemon --run-once --no-reconcile"
$publish  = ".venv-linux/bin/python -m tiktok_poster sync"
$command  = "cd '$ProjectDir' && mkdir -p logs && $generate && $publish >> logs/task.log 2>&1"
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
    -Description "Generates the day's MBTI slides in WSL and publishes them to GitHub Pages." | Out-Null

Write-Host "Registered '$TaskName' for $($Times -join ', ')."
Write-Host "Retire the old tasks if they are still present:"
Write-Host "  Unregister-ScheduledTask -TaskName 'MBTI Daily Generate' -Confirm:`$false"
Write-Host "  Unregister-ScheduledTask -TaskName 'TikTok Image Import'  -Confirm:`$false"
