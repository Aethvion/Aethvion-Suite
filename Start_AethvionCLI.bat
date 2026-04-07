@echo off
SETLOCAL EnableDelayedExpansion
:: ============================================================
::  AETHVION SUITE - CLI Launcher
::  Opens an interactive terminal for direct system control.
:: ============================================================
SET PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"
TITLE Aethvion Suite - CLI

echo.
echo ============================================================
echo   AETHVION SUITE  ^|  COMMAND LINE INTERFACE
echo ============================================================
echo.

call setup\setup_environment.bat
if %errorlevel% neq 0 (
    echo [ERROR] Environment setup failed.
    pause
    exit /b 1
)

echo.
echo Starting CLI...
echo.

".venv\Scripts\python.exe" core\main.py --cli

echo.
echo CLI session ended.
pause
