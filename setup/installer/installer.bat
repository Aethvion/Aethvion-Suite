@echo off
setlocal
title Aethvion Suite Installer Launcher

:: Move to installer directory
cd /d "%~dp0"

echo [Installer] Initializing Aethvion Suite deployment...

:: Check if .venv exists
if not exist "..\..\.venv\Scripts\python.exe" (
    echo [Installer] Environment not found. Launching initial bootstrap...
    call "..\setup_environment.bat"
)

:: Re-verify .venv exists after setup attempt
if not exist "..\..\.venv\Scripts\python.exe" (
    echo [Error] Failed to create Python environment. Please check your Python installation.
    pause
    exit /b 1
)

:: Ensure customtkinter is available in the environment (should be if setup_environment ran with new pyproject.toml)
"..\..\.venv\Scripts\python.exe" -c "import customtkinter" 2>nul
if %errorlevel% neq 0 (
    echo [Installer] Syncing GUI dependencies...
    "..\..\.venv\Scripts\pip" install customtkinter
)

:: Launch the Graphical Installer
echo [Installer] Opening Graphical Interface...
start "" /b "..\..\.venv\Scripts\pythonw.exe" installer.py

exit /b 0
