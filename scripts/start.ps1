param(
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $root 'backend'
$pythonCandidates = @(
  (Join-Path $backendDir '.venv\Scripts\python.exe'),
  (Join-Path $root '.venv\Scripts\python.exe')
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) { $python = $pythonCandidates[1] }
$envFile = Join-Path $backendDir '.env'
$logDir = Join-Path $root 'logs'
$frontendUrl = 'http://127.0.0.1:5173/'
$backendUrl = 'http://127.0.0.1:8000/openapi.json'

function Test-ProjectBackend {
  try {
    $spec = Invoke-RestMethod -Uri $backendUrl -TimeoutSec 3
    return $spec.info.title -eq 'DataFusion Agent'
  } catch {
    return $false
  }
}

function Test-ProjectFrontend {
  try {
    $page = Invoke-WebRequest -Uri $frontendUrl -TimeoutSec 3 -UseBasicParsing
    return $page.StatusCode -eq 200 -and $page.Content -match '<title>DataFusion Agent</title>'
  } catch {
    return $false
  }
}

function Test-PortInUse([int]$port) {
  $client = [System.Net.Sockets.TcpClient]::new()
  try {
    $task = $client.ConnectAsync('127.0.0.1', $port)
    return $task.Wait(500) -and $client.Connected
  } catch {
    return $false
  } finally {
    $client.Dispose()
  }
}

function Assert-BackendConfiguration {
  if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing Python environment. Run setup.bat first.'
  }
  if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Missing backend/.env. Run setup.bat and fill in the configuration.'
  }

  $settings = @{}
  foreach ($entry in Get-Content -LiteralPath $envFile) {
    if ($entry -match '^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
      $settings[$Matches[1]] = $Matches[2].Trim().Trim('"', "'")
    }
  }
  foreach ($name in @('MYSQL_USER', 'MYSQL_PASSWORD', 'DEEPSEEK_API_KEY')) {
    if (-not $settings.ContainsKey($name) -or [string]::IsNullOrWhiteSpace($settings[$name])) {
      throw "Missing $name in backend/.env. Fill it in before starting."
    }
  }
}

function Wait-ForService([scriptblock]$probe, [string]$name, [string]$errorLog, $process) {
  $timer = [System.Diagnostics.Stopwatch]::StartNew()
  while ($timer.Elapsed.TotalSeconds -lt 60) {
    if (& $probe) { return }
    if ($null -ne $process -and $process.HasExited) {
      throw "$name exited during startup. Check $errorLog."
    }
    Start-Sleep -Milliseconds 800
  }
  throw "$name did not become ready within 60 seconds. Check $errorLog."
}

Set-Location -LiteralPath $root
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$backendReady = Test-ProjectBackend
$frontendReady = Test-ProjectFrontend

if (-not $backendReady -and (Test-PortInUse 8000)) {
  throw 'Port 8000 is occupied by another service. Close it or change the project port.'
}
if (-not $frontendReady -and (Test-PortInUse 5173)) {
  throw 'Port 5173 is occupied by another service. Close it or change the project port.'
}

$backendProcess = $null
$frontendProcess = $null

if (-not $backendReady) {
  Assert-BackendConfiguration
  Write-Host 'Starting FastAPI backend...'
  $backendProcess = Start-Process -FilePath $python `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
    -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir 'backend.out.log') `
    -RedirectStandardError (Join-Path $logDir 'backend.err.log')
} else {
  Write-Host 'FastAPI backend is already running.'
}

if (-not $frontendReady) {
  if (-not (Test-Path -LiteralPath (Join-Path $root 'node_modules'))) {
    throw 'Missing frontend dependencies. Run setup.bat first.'
  }
  $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
  Write-Host 'Starting Vue frontend...'
  $frontendProcess = Start-Process -FilePath $npm `
    -ArgumentList @('run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173', '--strictPort') `
    -WorkingDirectory $root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir 'frontend.out.log') `
    -RedirectStandardError (Join-Path $logDir 'frontend.err.log')
} else {
  Write-Host 'Vue frontend is already running.'
}

Wait-ForService ${function:Test-ProjectBackend} 'FastAPI backend' 'logs/backend.err.log' $backendProcess
Wait-ForService ${function:Test-ProjectFrontend} 'Vue frontend' 'logs/frontend.err.log' $frontendProcess

Write-Host "Project is ready: $frontendUrl"
Write-Host 'Evaluation: http://127.0.0.1:5173/evaluation'
Write-Host 'API docs:   http://127.0.0.1:8000/docs'

if (-not $NoBrowser) {
  Start-Process -FilePath $frontendUrl | Out-Null
}
