param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$Date = "",
    [switch]$DryRun,
    [switch]$Slot
)

$ErrorActionPreference = "Stop"

function Write-RunLog {
    param(
        [string]$ProjectRoot,
        [string]$Message
    )

    $logDir = Join-Path $ProjectRoot "logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path (Join-Path $logDir "run_daily.log") -Value "[$timestamp] $Message" -Encoding utf8
}

function Get-VenvBasePython {
    param(
        [string]$PyVenvCfgPath
    )

    if (-not (Test-Path $PyVenvCfgPath)) {
        return $null
    }

    $cfg = Get-Content $PyVenvCfgPath
    $versionLine = $cfg | Where-Object { $_ -like 'version = *' } | Select-Object -First 1
    $version = if ($versionLine) { ($versionLine -replace '^version =\s*', '').Trim() } else { '' }
    $majorMinor = if ($version -match '^(\d+)\.(\d+)') { "$($Matches[1]).$($Matches[2])" } else { '' }
    $tag = if ($majorMinor) { 'Python' + ($majorMinor -replace '\.', '') } else { '' }

    $candidates = @()
    if ($tag) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\$tag\python.exe"
        $candidates += Join-Path $env:ProgramFiles "$tag\python.exe"
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $pyLauncher = Join-Path $env:WINDIR 'py.exe'
    if ((Test-Path $pyLauncher) -and $majorMinor) {
        try {
            $launcherResult = & $pyLauncher -$majorMinor -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $resolved = ($launcherResult | Select-Object -First 1).Trim()
                if ($resolved -and (Test-Path $resolved)) {
                    return $resolved
                }
            }
        } catch {
        }
    }

    return $null
}

function Repair-VenvLauncher {
    param(
        [string]$ProjectRoot,
        [string]$PythonPath
    )

    $venvScriptsDir = Split-Path -Parent $PythonPath
    $venvDir = Split-Path -Parent $venvScriptsDir
    $pyVenvCfgPath = Join-Path $venvDir 'pyvenv.cfg'
    $basePython = Get-VenvBasePython -PyVenvCfgPath $pyVenvCfgPath

    if (-not $basePython) {
        throw "Unable to locate a base Python interpreter to repair $pyVenvCfgPath"
    }

    $baseHome = Split-Path -Parent $basePython
    $commandLine = "$basePython -m venv $venvDir"
    $updated = @()

    foreach ($line in Get-Content $pyVenvCfgPath) {
        if ($line -like 'home = *') {
            $updated += "home = $baseHome"
        } elseif ($line -like 'executable = *') {
            $updated += "executable = $basePython"
        } elseif ($line -like 'command = *') {
            $updated += "command = $commandLine"
        } else {
            $updated += $line
        }
    }

    Set-Content -Path $pyVenvCfgPath -Value $updated -Encoding ascii
}

function Resolve-HealthyPython {
    param(
        [string]$ProjectRoot,
        [string]$PythonExeArg
    )

    $pythonCandidate = if ([System.IO.Path]::IsPathRooted($PythonExeArg)) {
        $PythonExeArg
    } else {
        Join-Path $ProjectRoot $PythonExeArg
    }

    if (-not (Test-Path $pythonCandidate)) {
        throw "Python executable not found: $pythonCandidate"
    }

    try {
        & $pythonCandidate -V *> $null
        if ($LASTEXITCODE -eq 0) {
            return $pythonCandidate
        }
    } catch {
    }

    Repair-VenvLauncher -ProjectRoot $ProjectRoot -PythonPath $pythonCandidate

    & $pythonCandidate -V *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Python executable is still unusable after repair: $pythonCandidate"
    }

    return $pythonCandidate
}


$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Resolve-HealthyPython -ProjectRoot $projectRoot -PythonExeArg $PythonExe

Push-Location $projectRoot

$commandName = if ($Slot) { "run-slot" } else { "run-daily" }
$arguments = @("-m", "mbti_tiktok_bot", $commandName)
if ($Date) {
    $arguments += @("--date", $Date)
}
if ($DryRun) {
    $arguments += "--dry-run"
}
if ($Slot) {
    $arguments += "--export-phone"
}

$argumentText = $arguments -join " "
Write-RunLog -ProjectRoot $projectRoot -Message "START python=$pythonPath args=$argumentText"

try {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pythonPath @arguments 2>&1 | Tee-Object -FilePath (Join-Path $projectRoot "logs\run_daily.log") -Append
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    Write-RunLog -ProjectRoot $projectRoot -Message "END exit_code=$exitCode"
}
catch {
    Write-RunLog -ProjectRoot $projectRoot -Message "ERROR $($_.Exception.Message)"
    throw
}
finally {
    $ErrorActionPreference = "Stop"
    Pop-Location
}

exit $exitCode
