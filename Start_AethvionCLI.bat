@echo off
setlocal EnableDelayedExpansion

:: ── 1. Configuration ────────────────────────────────────────
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"
TITLE Aethvion Suite - CLI

:: ── 2. Installation Check ──────────────────────────────────
set "ALREADY_INSTALLED=1"
if not exist ".venv\Scripts\python.exe" set "ALREADY_INSTALLED=0"
if not exist "core\main.py" set "ALREADY_INSTALLED=0"

if "!ALREADY_INSTALLED!"=="1" (
    ".venv\Scripts\python.exe" -c "import fastapi" >nul 2>&1
    if !errorlevel! neq 0 set "ALREADY_INSTALLED=0"
)

:: ── 3. Execution Path ──────────────────────────────────────
if "!ALREADY_INSTALLED!"=="1" (
    echo Starting Aethvion CLI...
    ".venv\Scripts\python.exe" core\main.py --cli
    pause
) else (
    echo [INFO] System not fully installed. Launching installer...
    start "" setup\installer\installer.bat
    exit
)
