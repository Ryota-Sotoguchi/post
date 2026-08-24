param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$ProjectDir = (Join-Path $PSScriptRoot ".."),
    [string]$Date = "",
    [int]$TargetCount = 0
)

$ErrorActionPreference = "Stop"

function Write-StartupLog {
    param(
        [string]$ProjectRoot,
        [string]$Message
    )

    $logDir = Join-Path $ProjectRoot "logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path (Join-Path $logDir "startup_topup.log") -Value "[$timestamp] $Message" -Encoding utf8
}

function Resolve-PythonPath {
    param(
        [string]$ProjectRoot,
        [string]$PythonExeArg
    )

    if ([System.IO.Path]::IsPathRooted($PythonExeArg)) {
        return $PythonExeArg
    }
    return (Join-Path $ProjectRoot $PythonExeArg)
}

function Get-DailyStatus {
    param(
        [string]$ProjectRoot,
        [string]$PythonPath,
        [string]$TargetDate,
        [int]$RequestedTargetCount
    )

    $statusScript = @'
import json
import sys
from pathlib import Path

from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.pipeline import load_daily_results
from mbti_tiktok_bot.planner import resolve_target_date

target_arg = sys.argv[1] or None
if target_arg == '__AUTO__':
    target_arg = None
requested_target = int(sys.argv[2])
config = load_config(Path.cwd())
target_date = resolve_target_date(target_arg)
target_count = requested_target if requested_target > 0 else config.daily_posts
results = load_daily_results(target_date, config)
print(json.dumps({
    'date': target_date.isoformat(),
    'count': len(results),
    'target_count': target_count,
}, ensure_ascii=False))
'@

    Push-Location $ProjectRoot
    try {
        $dateArg = if ([string]::IsNullOrWhiteSpace($TargetDate)) { "__AUTO__" } else { $TargetDate }
        $raw = & $PythonPath -X utf8 -c $statusScript $dateArg $RequestedTargetCount
        if ($LASTEXITCODE -ne 0) {
            throw "Status check failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    return ($raw | Select-Object -Last 1 | ConvertFrom-Json)
}

$resolvedProjectDir = (Resolve-Path $ProjectDir).Path
$pythonPath = Resolve-PythonPath -ProjectRoot $resolvedProjectDir -PythonExeArg $PythonExe
$runnerScript = (Resolve-Path (Join-Path $PSScriptRoot "run_daily.ps1")).Path

Write-StartupLog -ProjectRoot $resolvedProjectDir -Message "START target_count=$TargetCount date_arg=$Date"

$status = Get-DailyStatus -ProjectRoot $resolvedProjectDir -PythonPath $pythonPath -TargetDate $Date -RequestedTargetCount $TargetCount
$targetDate = [string]$status.date
$previousCount = [int]$status.count
$limit = [int]$status.target_count

Write-StartupLog -ProjectRoot $resolvedProjectDir -Message "STATUS date=$targetDate count=$previousCount target=$limit"

while ($previousCount -lt $limit) {
    $nextNumber = $previousCount + 1
    Write-StartupLog -ProjectRoot $resolvedProjectDir -Message "RUN_SLOT date=$targetDate next=$nextNumber target=$limit"

    & $runnerScript -PythonExe $pythonPath -Date $targetDate -Slot
    if ($LASTEXITCODE -ne 0) {
        Write-StartupLog -ProjectRoot $resolvedProjectDir -Message "FAIL date=$targetDate exit_code=$LASTEXITCODE"
        exit $LASTEXITCODE
    }

    $status = Get-DailyStatus -ProjectRoot $resolvedProjectDir -PythonPath $pythonPath -TargetDate $targetDate -RequestedTargetCount $TargetCount
    $currentCount = [int]$status.count
    Write-StartupLog -ProjectRoot $resolvedProjectDir -Message "AFTER_SLOT date=$targetDate count=$currentCount target=$limit"

    if ($currentCount -le $previousCount) {
        Write-StartupLog -ProjectRoot $resolvedProjectDir -Message "STOP_NO_PROGRESS date=$targetDate count=$currentCount"
        throw "Startup top-up did not increase the daily output count."
    }

    $previousCount = $currentCount
}

Write-StartupLog -ProjectRoot $resolvedProjectDir -Message "DONE date=$targetDate count=$previousCount target=$limit"
Write-Host "Startup top-up complete: $targetDate count=$previousCount target=$limit"
