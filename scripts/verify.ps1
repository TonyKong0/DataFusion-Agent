<#
.SYNOPSIS
Local CI gate for DataFusion Agent.

.DESCRIPTION
Runs the same checks a CI job would run, on the developer machine:
  1. backend pytest (full regression)
  2. frontend production build
  3. version single-source consistency (version.py / package.json / package-lock.json)
  4. cv2 import check (implicit dependency of the OCR/quality modules)
  5. optional live DeepSeek connectivity (-CheckLLM, one billed request)

The current git remote is gitee, so .github/workflows/ci.yml is only a
forward-looking configuration. This script is the gate that actually runs.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -CheckLLM -SkipFrontend
#>
[CmdletBinding()]
param(
    [switch]$CheckLLM,
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [string]$Python = '',
    [string]$Npm = 'npm'
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'

if (-not $Python) {
    $venvPython = Join-Path $backend '.venv\Scripts\python.exe'
    if (Test-Path $venvPython) { $Python = $venvPython } else { $Python = 'python' }
}

$checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param([string]$Name, [string]$Result, [double]$Seconds, [string]$Detail)
    $checks.Add([pscustomobject]@{
        Check = $Name
        Result = $Result
        Seconds = [math]::Round($Seconds, 2)
        Detail = $Detail
    })
}

function Invoke-Native {
    param(
        [string]$Name,
        [string]$Exe,
        [string[]]$Arguments,
        [string]$WorkingDir
    )
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $ok = $false
    $detail = ''
    Push-Location $WorkingDir
    try {
        $output = & $Exe @Arguments 2>&1 | Out-String
        $code = $LASTEXITCODE
        $ok = ($code -eq 0)
        $lines = @($output -split "`r?`n" | Where-Object { $_.Trim() })
        if ($lines.Count -gt 0) { $detail = $lines[-1].Trim() } else { $detail = "exit=$code" }
        if (-not $ok) {
            Write-Host "--- $Name output (exit $code) ---" -ForegroundColor Red
            Write-Host $output -ForegroundColor Red
            Write-Host "--- end $Name output ---" -ForegroundColor Red
        }
    } catch {
        $detail = "launch failed: $($_.Exception.Message)"
    } finally {
        Pop-Location
    }
    $stopwatch.Stop()
    Add-Check -Name $Name -Result $(if ($ok) { 'PASS' } else { 'FAIL' }) `
        -Seconds $stopwatch.Elapsed.TotalSeconds -Detail $detail
    return $ok
}

# 1. Full backend regression. pytest must run with backend as CWD so app/ is importable.
if ($SkipBackend) {
    Add-Check -Name 'backend.pytest' -Result 'SKIP' -Seconds 0 -Detail '-SkipBackend'
} else {
    $null = Invoke-Native -Name 'backend.pytest' -Exe $Python `
        -Arguments @('-m', 'pytest', '-q') -WorkingDir $backend
}

# 2. Frontend production build.
if ($SkipFrontend) {
    Add-Check -Name 'frontend.build' -Result 'SKIP' -Seconds 0 -Detail '-SkipFrontend'
} else {
    $null = Invoke-Native -Name 'frontend.build' -Exe $Npm `
        -Arguments @('run', 'build') -WorkingDir $root
}

# 3. Version single-source consistency (independent of the pytest suite).
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $versionFile = Get-Content (Join-Path $backend 'app\core\version.py') -Raw
    if ($versionFile -notmatch "APP_VERSION\s*=\s*'([^']+)'") {
        throw 'APP_VERSION not found in backend/app/core/version.py'
    }
    $appVersion = $Matches[1]
    # Read the version fields as text: ConvertFrom-Json on a large lock file and
    # the empty-named packages[""] entry are unreliable on Windows PowerShell 5.1.
    $packageText = Get-Content (Join-Path $root 'package.json') -Raw
    $lockText = Get-Content (Join-Path $root 'package-lock.json') -Raw
    $packageMatch = [regex]::Match($packageText, '"version"\s*:\s*"([^"]+)"')
    $lockMatches = [regex]::Matches($lockText, '"version"\s*:\s*"([^"]+)"')
    if (-not $packageMatch.Success -or $lockMatches.Count -lt 2) {
        throw 'could not read version fields from package.json / package-lock.json'
    }
    $packageVersion = $packageMatch.Groups[1].Value
    $lockVersion = $lockMatches[0].Groups[1].Value
    $lockRootVersion = $lockMatches[1].Groups[1].Value
    $mismatch = @()
    if ($packageVersion -ne $appVersion) { $mismatch += "package.json=$packageVersion" }
    if ($lockVersion -ne $appVersion) { $mismatch += "package-lock.json=$lockVersion" }
    if ($lockRootVersion -ne $appVersion) { $mismatch += "package-lock.root=$lockRootVersion" }
    if ($mismatch.Count -gt 0) { throw ($mismatch -join ', ') }
    Add-Check -Name 'version.consistency' -Result 'PASS' `
        -Seconds $stopwatch.Elapsed.TotalSeconds -Detail "all sources = $appVersion"
} catch {
    Add-Check -Name 'version.consistency' -Result 'FAIL' `
        -Seconds $stopwatch.Elapsed.TotalSeconds -Detail $_.Exception.Message
}
$stopwatch.Stop()

# 4. cv2 is an implicit dependency; make the failure explicit instead of an ImportError.
$null = Invoke-Native -Name 'dependencies.cv2' -Exe $Python `
    -Arguments @('-c', 'import cv2; print("cv2", cv2.__version__)') -WorkingDir $backend

# 5. Optional live LLM check (one billed API request).
if ($CheckLLM) {
    $null = Invoke-Native -Name 'llm.connectivity' -Exe $Python `
        -Arguments @('scripts/check_llm.py') -WorkingDir $backend
} else {
    Add-Check -Name 'llm.connectivity' -Result 'SKIP' -Seconds 0 -Detail 'use -CheckLLM to enable'
}

Write-Host ''
Write-Host '=== Local CI gate summary ===' -ForegroundColor Cyan
$checks | Format-Table -AutoSize | Out-Host

$failed = @($checks | Where-Object { $_.Result -eq 'FAIL' })
if ($failed.Count -gt 0) {
    Write-Host "GATE FAILED: $($failed.Count) check(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host 'GATE PASSED: all executed checks are green.' -ForegroundColor Green
exit 0
