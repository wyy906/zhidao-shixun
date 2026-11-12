# V2 dev environment one-shot setup (Windows PowerShell)
# Usage: ./scripts/setup-dev.ps1 [-Proxy "http://127.0.0.1:10808"]
# Requires: Python 3.11+ (verified on 3.13), Node.js 20+ (verified on 26)
param(
    [string]$Proxy = ""
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if ($Proxy -ne "") {
    $env:HTTP_PROXY = $Proxy
    $env:HTTPS_PROXY = $Proxy
}

Write-Host "==> [1/3] Create Python venv .venv"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    python -m venv (Join-Path $repoRoot ".venv")
}
& $venvPython -m pip install --upgrade pip --quiet

Write-Host "==> [2/3] Install Python deps (contracts editable + server + desktop)"
& $venvPython -m pip install -e (Join-Path $repoRoot "contracts") `
    -r (Join-Path $repoRoot "server\requirements-dev.txt") `
    -r (Join-Path $repoRoot "desktop\requirements.txt") --progress-bar off

Write-Host "==> [3/3] Install web deps"
Push-Location (Join-Path $repoRoot "web")
try { npm install --no-fund --no-audit } finally { Pop-Location }

Write-Host "Done. Start with: scripts/start-server.ps1 / start-web.ps1 / start-desktop.ps1"
