param([string]$Python = 'python', [string]$MakeNSIS = 'makensis')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Creating Python environment failed.' }
$BuildPython = Join-Path $PWD '.venv\Scripts\python.exe'
& $BuildPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Installing dependencies failed.' }
& $BuildPython packaging/build_locales.py
if ($LASTEXITCODE -ne 0) { throw 'Building translation catalog failed.' }
& $BuildPython -m PyInstaller --noconfirm --windowed --onedir --name 拾光图库 --icon shiguang.ico --version-file packaging/version_info.txt --add-data 'web;web' --distpath release-1.0.5 app.py
if ($LASTEXITCODE -ne 0) { throw 'Building executable failed.' }
& $BuildPython packaging/assemble_release.py
if ($LASTEXITCODE -ne 0) { throw 'Assembling release failed.' }
& $MakeNSIS packaging/setup.nsi
if ($LASTEXITCODE -ne 0) { throw 'Building installer failed.' }
$ReleaseDir = Join-Path $PWD '发布包\1.0.5'
$Lines = Get-ChildItem -LiteralPath $ReleaseDir -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | ForEach-Object {
    '{0}  {1}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
}
$Lines | Set-Content -LiteralPath (Join-Path $ReleaseDir 'SHA256SUMS.txt') -Encoding utf8
