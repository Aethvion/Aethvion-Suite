@echo off
SETLOCAL EnableDelayedExpansion
:: ============================================================
::  AETHVION SUITE - Web Launcher
::  Standard background mode: auto-install + standard browser.
:: ============================================================
SET PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"
TITLE Aethvion Suite - Initializing Web Mode...

echo.
echo ============================================================
echo   AETHVION SUITE  ^|  WEB MODE
echo ============================================================
echo.

call setup\setup_environment.bat
if %errorlevel% neq 0 (
    pause
    exit /b 1
)


:: ── 6. Launch via pythonw (no console window) ────────────────
echo.
echo [5/5] LAUNCHING CORE ENGINE...
echo [INFO] Dashboards will open in a standard browser tab shortly.
echo [INFO] You can close this window once the server starts.
echo.

start "" ".venv\Scripts\pythonw.exe" core\launcher.py --consumer --browser web %*

:: Small delay to ensure process spawns correctly before closing BAT
timeout /t 3 /nobreak >nul
exit
