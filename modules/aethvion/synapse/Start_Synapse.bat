@echo off
SETLOCAL EnableDelayedExpansion

:: Window always-open guarantee
if not defined MISAKA_LAUNCHED (
    set MISAKA_LAUNCHED=1
    cmd /k ""%~f0""
    exit
)
TITLE Synapse Tracking Engine - Aethvion Systems

:: Figure out the directory where this script actually lives
SET SYNAPSE_MODULE_DIR=%~dp0

:: Figure out the root MISAKA CIPHER directory relative to the new module location
:: The script is in C:\Aethvion\Misaka-Cipher\modules\aethvion\synapse\
for %%I in ("%~dp0..\..\..") do set "ROOT_DIR=%%~fI"

:: Switch working directory to the project Root
cd /d "%ROOT_DIR%"
SET PYTHONPATH=%ROOT_DIR%

echo.
echo ============================================================
echo          AETHVION - SYNAPSE TRACKING ENGINE
echo ============================================================
echo.
echo [INFO] Running under Misaka Cipher root: %ROOT_DIR%
echo.

:: --- 1. Python Check ------------------------------------------
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Install Python 3.10+ from https://python.org
    goto :FAIL
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK]  Python %PY_VER% detected.

:: --- 2. Virtual environment ------------------------------------
if not exist ".venv\Scripts\activate.bat" (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        goto :FAIL
    )
    echo [OK]  Virtual environment created.
) else (
    echo [OK]  Virtual environment found.
)

call ".venv\Scripts\activate.bat"

:: --- 3. Install Core Dependencies ------------------------------
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] Installing core dependencies from pyproject.toml...
    python -m pip install --upgrade pip
    pip install -e ".[memory]"
    if %errorlevel% neq 0 (
        echo [WARN]  Core dependency installation reported an issue. 
    ) else (
        echo [OK]  Core dependencies installed.
    )
) else (
    echo [OK]  Core dependencies verified.
)

:: --- 4. Environment file ---------------------------------------
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [SETUP] Created .env from .env.example - add your API keys in the dashboard.
        echo.
    ) else (
        echo [WARN]  No .env file found. Create one with your API keys.
    )
) else (
    echo [OK]  .env found.
)

:: --- 5. Launch -------------------------------------------------
echo.
echo [START] Launching Synapse Tracking Engine...
echo         Viewer -^> http://localhost:8002
echo         Press CTRL+C to stop.
echo.

:: We launch it using the Python environment targeting the module relative to our Root
python modules\aethvion\synapse\synapse_server.py
set MAIN_EXIT=%errorlevel%

:: --- 6. Result ------------------------------------------------
if %MAIN_EXIT% neq 0 (
    echo.
    echo [ERROR] Synapse Server crashed (exit code %MAIN_EXIT%).
    echo         Scroll up to find the error, then fix it and re-run.
    goto :FAIL
)
goto :END

:FAIL
echo.
echo ============================================================
echo  Something went wrong. Read the error above, then close.
echo ============================================================
echo.
pause
EXIT /B 1

:END
pause
