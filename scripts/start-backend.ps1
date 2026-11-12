"""启动后端开发服务器（PowerShell 友好）"""
Write-Host "=== 智导实训 · 后端启动 ===" -ForegroundColor Cyan
Set-Location "$PSScriptRoot\..\backend"

if (-not (Test-Path ".env")) {
    Write-Host "📄 创建 .env ..." -ForegroundColor Yellow
    Copy-Item .env.example .env
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 未检测到 python，请先安装 Python 3.10+" -ForegroundColor Red
    exit 1
}

Write-Host "📦 安装依赖 ..." -ForegroundColor Yellow
pip install -r requirements.txt

Write-Host "🚀 启动 FastAPI（http://localhost:8000）..." -ForegroundColor Green
python -m app.main
