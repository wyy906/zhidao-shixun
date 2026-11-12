# Start web dev server (default http://localhost:5173, backend must be running first)
# Backend default http://127.0.0.1:8000; if backend uses another port, e.g.:
#   ./scripts/start-web.ps1 -ApiTarget http://127.0.0.1:8100
param(
    [string]$ApiTarget = "http://127.0.0.1:8000"
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$env:ZD_API_PROXY_TARGET = $ApiTarget
Push-Location (Join-Path $repoRoot "web")
try { npm run dev } finally { Pop-Location }
