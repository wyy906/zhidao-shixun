# Starts the standalone Docker executor service (V2-04B).
# The executor service is the ONLY process that may talk to Docker daemon.
# The FastAPI business process never loads Docker SDK (V2-04A architecture).
#
# Requires ZD_EXECUTOR_TOKEN to be set; refuses to start otherwise (fail-closed).
# Refuses execution entirely until ZD_EXECUTOR_IMAGE_DIGEST is approved
# (executor_image_lock.json approval_status=pending).

param(
  [switch]$Check
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
  Write-Host "Virtualenv not found; run scripts/setup-dev.ps1 first."
  exit 1
}

if ($Check) {
  Push-Location (Join-Path $repoRoot "server")
  try {
    & $python -c "import urllib.request, json; print(json.loads(urllib.request.urlopen('http://127.0.0.1:8101/healthz', timeout=3).read()).get('status'))"
  } finally { Pop-Location }
  exit $LASTEXITCODE
}

if (-not $env:ZD_EXECUTOR_TOKEN) {
  Write-Host "ZD_EXECUTOR_TOKEN is not set; refusing to start (fail-closed)."
  exit 1
}

Push-Location (Join-Path $repoRoot "server")
try {
  & $python -m app.services.executor.service_app
} finally { Pop-Location }
