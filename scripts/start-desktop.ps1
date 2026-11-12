# Start Windows desktop assistant
# Usage: ./scripts/start-desktop.ps1 [-Smoke] [-Check] [-ApiTarget http://127.0.0.1:8000]
#   -Smoke : window auto-exits after 1.5s (for automated verification)
#   -Check : only probe backend /health, no window
param(
    [switch]$Smoke,
    [switch]$Check,
    [string]$ApiTarget = "http://127.0.0.1:8000"
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$extraArgs = @()
if ($Smoke) { $extraArgs += "--smoke" }
if ($Check) { $extraArgs += "--check" }
$env:ZD_API_BASE_URL = $ApiTarget
Push-Location (Join-Path $repoRoot "desktop")
try {
    & (Join-Path $repoRoot ".venv\Scripts\python.exe") -m zhidao_desktop.main @extraArgs
} finally { Pop-Location }
