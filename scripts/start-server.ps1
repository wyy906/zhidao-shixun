# Start backend (default http://127.0.0.1:8000, health check at /health)
param(
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $repoRoot ".venv\Scripts\python.exe") -m uvicorn app.main:app --host 127.0.0.1 --port $Port --app-dir (Join-Path $repoRoot "server")
