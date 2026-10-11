$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $PythonExe)) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 with the Windows py launcher first.' }
}
& $PythonExe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $PythonExe -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
& $PythonExe -m material_agent.login
if ($LASTEXITCODE -ne 0) { throw 'Browser stopped; check network access and close any existing agent browser.' }
