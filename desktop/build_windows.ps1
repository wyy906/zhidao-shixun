# 智导实训桌面助手 —— Windows 打包脚本
# 用法：powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1
# 可选：-Zip 同时生成 zip 分发包
param([switch]$Zip)

$ErrorActionPreference = 'Stop'

$desktop = $PSScriptRoot
$root = Split-Path -Parent $desktop
$dist = Join-Path $desktop 'dist'
$build = Join-Path $desktop 'build'
$exe = Join-Path $dist 'ZhidaoShixun\ZhidaoShixun.exe'

Write-Host "[1/3] 清理旧产物"
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
if (Test-Path $build) { Remove-Item -Recurse -Force $build }

Write-Host "[2/3] PyInstaller 构建（onedir / windowed）"
Push-Location $root
try {
    python -m PyInstaller `
        --noconfirm --clean --windowed `
        --name ZhidaoShixun `
        --distpath $dist `
        --workpath $build `
        --specpath $build `
        --paths (Join-Path $desktop 'src') `
        --collect-submodules pywinauto `
        --collect-submodules comtypes `
        (Join-Path $desktop 'src\main.py')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 退出码 $LASTEXITCODE" }
}
finally {
    Pop-Location
}

if (-not (Test-Path $exe)) { throw "未找到产物：$exe" }

$sizeMb = [math]::Round((Get-ChildItem (Split-Path $exe) -Recurse -File |
    Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "[3/3] 完成：$exe（目录合计 $sizeMb MB）"

if ($Zip) {
    $zipPath = Join-Path $dist 'ZhidaoShixun-win64.zip'
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    Compress-Archive -Path (Join-Path $dist 'ZhidaoShixun\*') -DestinationPath $zipPath
    Write-Host "分发包：$zipPath"
}
