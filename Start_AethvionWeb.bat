@echo off
SETLOCAL EnableDelayedExpansion
:: ============================================================
::  AETHVION SUITE — Web Launcher (silent background)
::  Opens in a standard browser tab, no CMD windows visible.
::  Double-click to start; this window closes by itself.
:: ============================================================
SET PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"

:: ── 1. Python check ─────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: ── 2. Virtual environment ───────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo [SETUP] Creating virtual environment…
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)
call ".venv\Scripts\activate.bat"

:: ── 3. Core dependencies ─────────────────────────────────────
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] Installing dependencies…
    pip install -e ".[memory]" >nul 2>&1
)

:: ── 4. .env file ─────────────────────────────────────────────
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
    )
)

:: ── 5. Required directories ──────────────────────────────────
call core\setup_directories.bat

:: ── 6. Launch via pythonw + standard browser tab ─────────────
::  Uses --browser web so the dashboard opens in a normal tab
::  (not --app= mode) — useful if you prefer the browser chrome.
start "" /b ".venv\Scripts\pythonw.exe" core\launcher.py --consumer --browser web %*

:: This window can close immediately — everything is in the background.
exit
