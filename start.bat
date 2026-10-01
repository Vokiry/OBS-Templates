@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ==================================================
echo     SYSTEM -- OBS Broadcast Templates Launcher
echo ==================================================

:: 1. Check Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [!] Python 3 not found. Please install Python 3.10+ from python.org
        pause
        exit /b 1
    ) else (
        set "PY_CMD=py"
    )
) else (
    set "PY_CMD=python"
)

:: 2. Check virtualenv
if not exist "bridge\.venv" (
    echo [*] Initializing virtual environment in bridge\.venv...
    %PY_CMD% -m venv bridge\.venv
    call bridge\.venv\Scripts\pip.exe install --upgrade pip
    call bridge\.venv\Scripts\pip.exe install -r bridge\requirements.txt
)

:: 3. Check config.toml
if not exist "bridge\config.toml" (
    echo [*] Creating bridge\config.toml from template...
    copy bridge\config.example.toml bridge\config.toml >nul
)

:: 4. Safe scene collection handling for Windows OBS
set "OBS_SCENES_DIR=%APPDATA%\obs-studio\basic\scenes"
if exist "%OBS_SCENES_DIR%" (
    if not exist "%OBS_SCENES_DIR%\SYSTEM.json" (
        echo [*] First run: importing SYSTEM scene collection to OBS...
        bridge\.venv\Scripts\python.exe obs\generate_collection.py >nul 2>nul
        copy obs\SYSTEM_Scene_Collection.json "%OBS_SCENES_DIR%\SYSTEM.json" >nul 2>nul
        echo     [+] Created %OBS_SCENES_DIR%\SYSTEM.json
    ) else (
        echo [i] Existing OBS scene collection kept intact.
    )
)

echo.
echo   [+] Unified Server:   http://localhost:8787/
echo   [+] Control Dock:     http://localhost:8787/dock
echo   [+] Event WebSocket:  ws://localhost:8787/events
echo.
echo   [!] In OBS Studio:
echo       1. Scene Collection -^> select 'SYSTEM Broadcast Templates'
echo       2. Docks -^> Custom Browser Docks:
echo          Name: SYSTEM Dock, URL: http://localhost:8787/dock
echo ==================================================
echo [*] Starting SYSTEM server... (Press Ctrl+C to stop)
echo.

bridge\.venv\Scripts\python.exe bridge\alerts_bridge.py
