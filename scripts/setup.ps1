$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js/npm missing; install Node.js 20.19+ or 22.12+.' }
$nodeVersion = (& node --version)
Write-Host "Node $nodeVersion"
if (-not (Test-Path 'backend/.env')) {
  Copy-Item 'backend/.env.example' 'backend/.env'
  Write-Warning 'Created backend/.env; fill in MySQL credentials and DeepSeek API key.'
}
# Prefer backend/.venv when present; otherwise keep the repository-root .venv for existing setups.
$venvDir = if (Test-Path 'backend/.venv/Scripts/python.exe') { 'backend/.venv' } else { '.venv' }
$venvPython = Join-Path $venvDir 'Scripts/python.exe'
if (-not (Test-Path $venvPython)) {
  $venvCreated = $false
  if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 -m venv $venvDir
    $venvCreated = $LASTEXITCODE -eq 0 -and (Test-Path $venvPython)
  }
  if (-not $venvCreated -and (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host 'Python 3.12 was not available through the py launcher; trying python from PATH.' -ForegroundColor Yellow
    & python -m venv $venvDir
    $venvCreated = $LASTEXITCODE -eq 0 -and (Test-Path $venvPython)
  }
  if (-not $venvCreated) { throw "Could not create $venvDir. Install Python 3.11-3.13 and ensure python or py is on PATH." }
}
$python = Join-Path $root $venvPython
$pythonVersionText = & $python --version
if ($pythonVersionText -notmatch '^Python (\d+\.\d+)') { throw "Cannot determine Python version: $pythonVersionText" }
$version = $Matches[1]
if ([version]$version -lt [version]'3.11' -or [version]$version -ge [version]'3.14') {
  throw "Python $version is outside tested range 3.11-3.13; use 3.12."
}
& $python -m ensurepip --upgrade | Out-Null
& $python -m pip install -r 'backend/requirements-dev.txt'
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
& npm ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
New-Item -ItemType Directory -Force 'backend/data/documents','backend/data/vector_store','backend/data/models','reports','logs' | Out-Null
Write-Host 'Dependencies ready. Fill backend/.env, import Chinook, and see docs/deployment.md for BGE-M3.'
