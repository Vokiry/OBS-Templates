@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo ==================================================
echo     SYSTEM -- OBS Broadcast Templates Launcher
echo ==================================================

:: Parse arguments safely
set "SHOW_SETTINGS=0"
set "RESET_SCENES=0"
if not "%~1"=="" (
    for %%a in (%*) do (
        if /i "%%a"=="--settings" set "SHOW_SETTINGS=1"
        if /i "%%a"=="--reset-scenes" set "RESET_SCENES=1"
    )
)

:: 1. Check Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [!] Python 3 not found. Please install Python 3.10+ from python.org
        echo     (Make sure to check "Add python.exe to PATH" during installation)
        echo.
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
    if errorlevel 1 (
        echo [!] Failed to create virtualenv in bridge\.venv.
        pause
        exit /b 1
    )
    call bridge\.venv\Scripts\pip.exe install --upgrade pip
    call bridge\.venv\Scripts\pip.exe install -r bridge\requirements.txt
    if errorlevel 1 (
        echo [!] Failed to install dependencies from requirements.txt.
        pause
        exit /b 1
    )
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
    ) else if "%RESET_SCENES%"=="1" (
        echo [!] Backing up existing scenes and restoring template defaults...
        copy "%OBS_SCENES_DIR%\SYSTEM.json" "%OBS_SCENES_DIR%\SYSTEM.json.bak" >nul 2>nul
        bridge\.venv\Scripts\python.exe obs\generate_collection.py >nul 2>nul
        copy obs\SYSTEM_Scene_Collection.json "%OBS_SCENES_DIR%\SYSTEM.json" >nul 2>nul
        echo     [+] Reset %OBS_SCENES_DIR%\SYSTEM.json to template defaults.
    ) else (
        bridge\.venv\Scripts\python.exe obs\sync_scenes.py --target "%OBS_SCENES_DIR%\SYSTEM.json" >nul 2>nul
        echo     [+] OBS scene collection synchronized: custom sources preserved.
    )
)

echo.
echo   [+] Unified Server:   http://localhost:8787/
echo   [+] Control Dock:     http://localhost:8787/dock
echo   [+] Event WebSocket:  ws://localhost:8787/events
if "%SHOW_SETTINGS%"=="1" (
    echo   [+] Settings Panel:   http://localhost:8787/settings
)
echo.
echo   [!] In OBS Studio:
echo       1. Scene Collection -^> select 'SYSTEM Broadcast Templates'
echo       2. Docks -^> Custom Browser Docks:
echo          Name: SYSTEM Dock, URL: http://localhost:8787/dock
echo ==================================================
echo [*] Starting SYSTEM server... (Press Ctrl+C to stop)
echo.

bridge\.venv\Scripts\python.exe bridge\alerts_bridge.py %*
