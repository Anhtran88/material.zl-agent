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
# Match the compiled Python target; environment CPU variables may be absent/stale.
$NodeArch = (& $PythonExe -m material_agent.windows_runtime | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $NodeArch -notin @('x64', 'arm64')) { throw 'A supported 64-bit Windows Python runtime is required.' }
Write-Host "Detected Python runtime; portable Node architecture: $NodeArch"
$NodeVersion = '24.19.0'
$NodeFolder = Join-Path $ToolsRoot "node\node-v$NodeVersion-win-$NodeArch"
$NodeExe = Join-Path $NodeFolder 'node.exe'
$NodeHashes = @{
    x64 = '57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73'
    arm64 = '8502f4a50b458d4cc38ed8f2001556c2cd239d464920f74017926ccb1e1c157f'
}
$NodeHash = $NodeHashes[$NodeArch]
if (-not (Test-Path $NodeExe)) {
    $NodeArchive = Join-Path $ToolsRoot "node-v$NodeVersion-win-$NodeArch.zip"
    Invoke-WebRequest -Uri "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-$NodeArch.zip" -OutFile $NodeArchive
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
