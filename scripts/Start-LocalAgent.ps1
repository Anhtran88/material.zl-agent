$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$AgentRoot = Join-Path $env:LOCALAPPDATA 'ZaloMaterialAgent'
$ToolsRoot = Join-Path $AgentRoot 'tools'
New-Item -ItemType Directory -Path $ToolsRoot -Force | Out-Null
$UserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $AgentRoot /inheritance:r /grant:r "*${UserSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot secure the local Agent directory.' }
# Refuse port conflicts; never terminate or adopt unrelated applications.
foreach ($AgentPort in @(8765, 20128)) {
    $Probe = New-Object System.Net.Sockets.TcpClient
    try {
        $Connected = $Probe.ConnectAsync('127.0.0.1', $AgentPort)
        if ($Connected.Wait(500) -and $Probe.Connected) { throw "Port $AgentPort is busy. Close the previous Agent/router first." }
    } catch [System.AggregateException] { } finally { $Probe.Dispose() }
}
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $PythonExe)) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 with the Windows py launcher is required.' }
}
& $PythonExe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $PythonExe -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
# Use a pinned portable x64 Node build; no administrator/MSI/PATH modifications.
$MachineArch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
if ($MachineArch -ne 'AMD64') { throw 'This bootstrap supports Windows x64. ARM64 requires a separately validated build.' }
$NodeVersion = '24.19.0'
$NodeFolder = Join-Path $ToolsRoot "node\node-v$NodeVersion-win-x64"
$NodeExe = Join-Path $NodeFolder 'node.exe'
$NodeHash = '57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73'
if (-not (Test-Path $NodeExe)) {
    $NodeArchive = Join-Path $ToolsRoot "node-v$NodeVersion-win-x64.zip"
    Invoke-WebRequest -Uri "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip" -OutFile $NodeArchive
    if ((Get-FileHash $NodeArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $NodeHash) { throw 'Node archive checksum mismatch.' }
    Expand-Archive -Path $NodeArchive -DestinationPath (Join-Path $ToolsRoot 'node') -Force
    Remove-Item $NodeArchive
}
$NpmExe = Join-Path $NodeFolder 'npm.cmd'
$RouterFolder = Join-Path $ToolsRoot '9router'
New-Item -ItemType Directory -Path $RouterFolder -Force | Out-Null
Copy-Item (Join-Path $ProjectRoot 'installer\9router\package.json') $RouterFolder -Force
Copy-Item (Join-Path $ProjectRoot 'installer\9router\package-lock.json') $RouterFolder -Force
$OriginalPath = $env:PATH
try {
    $env:PATH = "$NodeFolder;$OriginalPath"
    # Lockfile verifies package integrity. Suppress upstream install hooks; direct server
    # uses Node built-in SQLite, avoids automatic installers/tray/process termination.
    & $NpmExe ci --prefix $RouterFolder --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Pinned 9Router installation failed.' }
    & $PythonExe -m material_agent.local_agent
    if ($LASTEXITCODE -ne 0) { throw 'Local Agent stopped with an error.' }
} finally { $env:PATH = $OriginalPath }
