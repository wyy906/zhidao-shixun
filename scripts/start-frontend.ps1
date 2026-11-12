"""启动前端开发服务器（PowerShell 友好）"""
Write-Host "=== 智导实训 · 前端启动 ===" -ForegroundColor Cyan
Set-Location "$PSScriptRoot\..\frontend"

if (-not (Test-Path "node_modules")) {
    Write-Host "📦 首次运行，安装依赖（可能较慢）..." -ForegroundColor Yellow
    npm.cmd install
}

Write-Host "🚀 启动 Vite（http://localhost:5173）..." -ForegroundColor Green
npm.cmd run dev
