# SYSTEM — OBS Broadcast Templates Launcher (PowerShell)
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "    SYSTEM — OBS Broadcast Templates Launcher     " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Check Python
$PythonCmd = if (Get-Command "python" -ErrorAction SilentlyContinue) { "python" }
             elseif (Get-Command "py" -ErrorAction SilentlyContinue) { "py" }
             else {
                 Write-Host "[!] Python 3 not found. Please install Python 3.10+ from python.org" -ForegroundColor Red
                 Write-Host "    (Make sure to check 'Add python.exe to PATH' during installation)" -ForegroundColor Yellow
                 Read-Host "Press Enter to exit..."
                 exit 1
             }

# 2. Check virtualenv
$VenvPython = Join-Path $ScriptDir "bridge\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[*] Initializing virtual environment in bridge\.venv..." -ForegroundColor Yellow
    & $PythonCmd -m venv "bridge\.venv"
    & (Join-Path $ScriptDir "bridge\.venv\Scripts\pip.exe") install --upgrade pip
    & (Join-Path $ScriptDir "bridge\.venv\Scripts\pip.exe") install -r "bridge\requirements.txt"
}

# 3. Check config.toml
$ConfigFile = Join-Path $ScriptDir "bridge\config.toml"
if (-not (Test-Path $ConfigFile)) {
    Write-Host "[*] Creating bridge\config.toml from template..." -ForegroundColor Yellow
    Copy-Item "bridge\config.example.toml" $ConfigFile
}

# 4. Safe scene collection handling
$ObsScenesDir = Join-Path $env:APPDATA "obs-studio\basic\scenes"
if (Test-Path $ObsScenesDir) {
    $DestFile = Join-Path $ObsScenesDir "SYSTEM.json"
    if (-not (Test-Path $DestFile)) {
        Write-Host "[*] First run: importing SYSTEM scene collection to OBS..." -ForegroundColor Yellow
        & $VenvPython "obs\generate_collection.py" | Out-Null
        Copy-Item "obs\SYSTEM_Scene_Collection.json" $DestFile -ErrorAction SilentlyContinue
        Write-Host "    [✓] Created $DestFile" -ForegroundColor Green
    } elseif ($args -contains "--reset-scenes") {
        Write-Host "[!] Backing up existing scenes and restoring template defaults..." -ForegroundColor Yellow
        Copy-Item $DestFile "$DestFile.bak" -Force
        & $VenvPython "obs\generate_collection.py" | Out-Null
        Copy-Item "obs\SYSTEM_Scene_Collection.json" $DestFile -Force
        Write-Host "    [✓] Reset $DestFile to template defaults." -ForegroundColor Green
    } else {
        & $VenvPython "obs\sync_scenes.py" --target $DestFile | Out-Null
        Write-Host "    [✓] OBS scene collection synchronized: custom sources preserved." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "  [✓] Unified Server:   http://localhost:8787/" -ForegroundColor Green
Write-Host "  [✓] Control Dock:     http://localhost:8787/dock" -ForegroundColor Green
Write-Host "  [✓] Event WebSocket:  ws://localhost:8787/events" -ForegroundColor Green
if ($args -contains "--settings") {
    Write-Host "  [✓] Settings Panel:   http://localhost:8787/settings" -ForegroundColor Green
}
if ($args -contains "--obs") {
    Write-Host "[*] Launching OBS Studio..." -ForegroundColor Cyan
    $ObsExe = "$env:ProgramFiles\obs-studio\bin\64bit\obs64.exe"
    if (Test-Path $ObsExe) {
        Start-Process -FilePath $ObsExe -WorkingDirectory (Split-Path $ObsExe)
        Write-Host "    [✓] OBS Studio launched." -ForegroundColor Green
    } else {
        Write-Host "    [!] OBS Studio not found in $ObsExe. Please launch OBS manually." -ForegroundColor Yellow
    }
}

$PyArgs = @()
if ($args -contains "--settings") { $PyArgs += "--settings" }
for ($i = 0; $i -lt $args.Count; $i++) {
    if ($args[$i] -eq "--config" -and ($i + 1) -lt $args.Count) {
        $PyArgs += "--config"
        $PyArgs += $args[$i + 1]
    }
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "[*] Starting SYSTEM server... (Press Ctrl+C to stop)"
Write-Host ""

& $VenvPython "bridge\alerts_bridge.py" $PyArgs
