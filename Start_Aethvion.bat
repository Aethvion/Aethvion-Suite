@echo off
SETLOCAL EnableDelayedExpansion
:: ============================================================
::  AETHVION SUITE - Consumer Launcher
::  Standard background mode: auto-install + auto-browser.
:: ============================================================
SET PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"
TITLE Aethvion Suite - Initializing...

echo.
echo ============================================================
echo   AETHVION SUITE  ^|  CONSUMER MODE
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
echo [INFO] Dashboards will open in your app-mode browser shortly.
echo [INFO] You can close this window once the server starts.
echo.

start "" ".venv\Scripts\pythonw.exe" core\launcher.py --consumer --browser app %*

:: Small delay to ensure process spawns correctly before closing BAT
timeout /t 3 /nobreak >nul
exit
