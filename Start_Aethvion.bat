@echo off
SETLOCAL EnableDelayedExpansion
:: ============================================================
::  AETHVION SUITE — Consumer Launcher
::  Standard background mode: auto-install + auto-browser.
:: ============================================================
SET PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"
TITLE Aethvion Suite — Initializing...

echo.
echo  [94m   _____         __  .__              .__                [0m
echo  [94m  /  _  \  _____/  |_^|  ^|__ ___  __ ^|__| ____   ____    [0m
echo  [94m /  /_\  \/ __ \   __\  ^|  \\  \/ / ^|  ^|/  _ \ /    \   [0m
echo  [94m/    ^|    \  ___/^|  ^| ^|   Y  \   /  ^|  (  <_^> )   ^|  \  [0m
echo  [94m\____^|__  /\___  ^>__^| ^|___^|  /\_/   ^|__^|\____/^|___^|  /  [0m
echo  [94m        \/     \/          \/                    \/   [0m
echo.
echo ============================================================
echo   INITIALIZING AETHVION SUITE (CONSUMER MODE)
echo ============================================================
echo.

:: ── 1. Python check ─────────────────────────────────────────
echo [1/5] VERIFYING PYTHON...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK]   Python %PY_VER% verified.

:: ── 2. Virtual environment ───────────────────────────────────
echo.
echo [2/5] SYNCING VIRTUAL ENVIRONMENT...
if not exist ".venv\Scripts\activate.bat" (
    echo [SETUP] Creating fresh virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK]   Virtual environment created.
) else (
    echo [OK]   Virtual environment active.
)
call ".venv\Scripts\activate.bat"

:: ── 3. Core dependencies ─────────────────────────────────────
echo.
echo [3/5] VERIFYING DEPENDENCIES (THIS MAY TAKE A MOMENT)...
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] Installing required packages...
    python -m pip install --upgrade pip
    pip install -e ".[memory]"
    if !errorlevel! neq 0 (
        echo [ERROR] Dependency installation failed. Check your internet or logs.
        pause
        exit /b 1
    )
    echo [OK]   Installation complete.
) else (
    echo [OK]   All packages verified.
)

:: ── 4. Configuration ─────────────────────────────────────────
echo.
echo [4/5] FINALIZING CONFIGURATION...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [SETUP] Initialized .env from template.
    )
)

:: ── 5. Required directories ──────────────────────────────────
call core\setup_directories.bat

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
