param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$ProjectDir = (Join-Path $PSScriptRoot ".."),
    [string[]]$Times = @("08:00", "12:00", "18:00"),
    [int]$PollSeconds = 30
)

$ErrorActionPreference = "Stop"

function Write-LoopLog {
    param(
        [string]$ProjectRoot,
        [string]$Message
    )

    $logDir = Join-Path $ProjectRoot "logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path (Join-Path $logDir "phone_export_loop.log") -Value "[$timestamp] $Message" -Encoding utf8
}

function Normalize-Times {
    param(
        [string[]]$RawTimes
    )

    return @(
        $RawTimes |
            ForEach-Object {
                try {
                    (Get-Date $_ -ErrorAction Stop).ToString("HH:mm")
                }
                catch {
                    throw "Invalid time '$_'. Use HH:mm format."
                }
            } |
            Sort-Object |
            Select-Object -Unique
    )
}

function Get-StatePath {
    param(
        [string]$ProjectRoot
    )

    $stateDir = Join-Path $ProjectRoot "state"
    if (-not (Test-Path $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir | Out-Null
    }
    return Join-Path $stateDir "phone_export_loop_state.json"
}

function Load-LoopState {
    param(
        [string]$ProjectRoot
    )

    $statePath = Get-StatePath -ProjectRoot $ProjectRoot
    if (-not (Test-Path $statePath)) {
        return @{ date = ""; completed_slots = @() }
    }

    try {
        $raw = Get-Content $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $stateDate = ""
        if ($null -ne $raw -and $null -ne $raw.date) {
            $stateDate = [string]$raw.date
        }
        $completedSlots = @()
        if ($null -ne $raw -and $null -ne $raw.completed_slots) {
            $completedSlots = @($raw.completed_slots)
        }
        return @{
            date = $stateDate
            completed_slots = $completedSlots
        }
    }
    catch {
        return @{ date = ""; completed_slots = @() }
    }
}

function Save-LoopState {
    param(
        [string]$ProjectRoot,
        [hashtable]$State
    )

    $statePath = Get-StatePath -ProjectRoot $ProjectRoot
    $payload = @{
        date = [string]$State.date
        completed_slots = @($State.completed_slots)
    } | ConvertTo-Json
    Set-Content -Path $statePath -Value $payload -Encoding utf8
}

$resolvedProjectDir = (Resolve-Path $ProjectDir).Path
$normalizedTimes = Normalize-Times -RawTimes $Times

Write-Host "Starting phone export loop for times: $($normalizedTimes -join ', ')"
Write-Host "Press Ctrl+C to stop."
Write-LoopLog -ProjectRoot $resolvedProjectDir -Message "START times=$($normalizedTimes -join ',') poll_seconds=$PollSeconds"

while ($true) {
    $now = Get-Date
    $today = $now.ToString("yyyy-MM-dd")
    $state = Load-LoopState -ProjectRoot $resolvedProjectDir

    if ($state.date -ne $today) {
        $state = @{ date = $today; completed_slots = @() }
        Save-LoopState -ProjectRoot $resolvedProjectDir -State $state
        Write-LoopLog -ProjectRoot $resolvedProjectDir -Message "RESET date=$today"
    }

    foreach ($time in $normalizedTimes) {
        if ($state.completed_slots -contains $time) {
            continue
        }

        $scheduledAt = Get-Date ("{0} {1}" -f $today, $time)
        if ($now -lt $scheduledAt) {
            continue
        }

        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Running slot for $today $time"
        Write-LoopLog -ProjectRoot $resolvedProjectDir -Message "RUN date=$today slot=$time"

        try {
            & (Join-Path $PSScriptRoot "run_daily.ps1") -PythonExe $PythonExe -Date $today -Slot
            if ($LASTEXITCODE -eq 0) {
                $state.completed_slots = @($state.completed_slots + $time)
                Save-LoopState -ProjectRoot $resolvedProjectDir -State $state
                Write-LoopLog -ProjectRoot $resolvedProjectDir -Message "SUCCESS date=$today slot=$time"
            }
            else {
                Write-LoopLog -ProjectRoot $resolvedProjectDir -Message "FAIL date=$today slot=$time exit_code=$LASTEXITCODE"
            }
        }
        catch {
            Write-LoopLog -ProjectRoot $resolvedProjectDir -Message "ERROR date=$today slot=$time message=$($_.Exception.Message)"
        }
    }

    Start-Sleep -Seconds $PollSeconds
}