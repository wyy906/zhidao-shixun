# Portable Windows build for the desktop assistant.
# Uses a copied signed Python runtime so the app can start on machines
# where Smart App Control blocks unsigned PyInstaller executables.
# Usage:
#   powershell -ExecutionPolicy Bypass -File desktop\build_portable.ps1
#   powershell -ExecutionPolicy Bypass -File desktop\build_portable.ps1 -Zip
param(
    [switch]$Zip,
    [string]$PythonHome = ""
)

$ErrorActionPreference = 'Stop'

$desktop = $PSScriptRoot
if (-not $PythonHome) {
    $PythonHome = Split-Path (Get-Command python).Source
}

$pythonExe = Join-Path $PythonHome 'python.exe'
$pythonwExe = Join-Path $PythonHome 'pythonw.exe'
$libDir = Join-Path $PythonHome 'Lib'
$dllDir = Join-Path $PythonHome 'DLLs'
if (-not (Test-Path $pythonExe)) { throw "python.exe not found: $PythonHome" }
if (-not (Test-Path $libDir)) { throw "Lib not found: $PythonHome" }
if (-not (Test-Path $dllDir)) { throw "DLLs not found: $PythonHome" }
if (-not (Test-Path $pythonwExe)) { throw "pythonw.exe not found: $PythonHome" }

$dist = Join-Path $desktop 'dist\ZhidaoPortable'
$runtime = Join-Path $dist 'runtime'

Write-Host "[1/5] Clean old portable output"
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
New-Item -ItemType Directory -Force $runtime | Out-Null

Write-Host "[2/5] Copy signed Python runtime from $PythonHome"
foreach ($name in @('python.exe', 'pythonw.exe', 'python3.dll', 'python313.dll',
                    'vcruntime140.dll', 'vcruntime140_1.dll')) {
    $src = Join-Path $PythonHome $name
    if (Test-Path $src) { Copy-Item $src $runtime }
}
Copy-Item $dllDir (Join-Path $runtime 'DLLs') -Recurse
Copy-Item $libDir (Join-Path $runtime 'Lib') -Recurse

foreach ($name in @('site-packages', 'test', 'idlelib', 'tkinter',
                    'ensurepip', 'lib2to3', 'pydoc_data', 'turtledemo')) {
    $path = Join-Path $runtime "Lib\$name"
    if (Test-Path $path) { Remove-Item $path -Recurse -Force }
}
Get-ChildItem $runtime -Recurse -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force

Write-Host "[3/5] Install desktop dependencies into the portable runtime"
$target = Join-Path $runtime 'Lib\site-packages'
python -m pip install --disable-pip-version-check -q --no-warn-script-location `
    --target $target -r (Join-Path $desktop 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE" }

Write-Host "[4/5] Copy app sources and launchers"
Copy-Item (Join-Path $desktop 'src') (Join-Path $dist 'app') -Recurse
Get-ChildItem (Join-Path $dist 'app') -Recurse -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force
Copy-Item (Join-Path $desktop 'packaging\run.py') $dist
Copy-Item (Join-Path $desktop 'packaging\start.bat') $dist

Write-Host "[5/5] Verify imports with the portable runtime"
$check = @"
import sys
sys.path.insert(0, r'$dist\app')
import PySide6, pywinauto, comtypes, mss, PIL, httpx
import ui.main_window
print('portable-import-ok')
"@
& (Join-Path $runtime 'python.exe') -c $check
if ($LASTEXITCODE -ne 0) { throw "portable import check failed" }

$sizeMb = [math]::Round((Get-ChildItem $dist -Recurse -File |
    Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "Done: $dist ($sizeMb MB)"
Write-Host "Launch: $dist\start.bat"

if ($Zip) {
    $zipPath = Join-Path $desktop 'dist\ZhidaoPortable-win64.zip'
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    Compress-Archive -Path (Join-Path $dist '*') -DestinationPath $zipPath
    Write-Host "Zip: $zipPath"
}
