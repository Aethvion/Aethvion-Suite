@echo off
SETLOCAL EnableDelayedExpansion

:: Window always-open guarantee
if not defined MISAKA_LAUNCHED (
    set MISAKA_LAUNCHED=1
    cmd /k ""%~f0""
    exit
)
TITLE Specter Rigging Engine - Aethvion Systems

:: Figure out the directory where this script actually lives
SET SPECTER_MODULE_DIR=%~dp0

:: Figure out the root MISAKA CIPHER directory relative to the new module location
:: The script is in C:\Aethvion\Misaka-Cipher\modules\aethvion\specter\
:: To get to the root, we go up exactly 3 levels: ..\..\.. -> aethvion -> modules -> Misaka-Cipher
for %%I in ("%~dp0..\..\..") do set "ROOT_DIR=%%~fI"

:: Switch working directory to the project Root
cd /d "%ROOT_DIR%"
SET PYTHONPATH=%ROOT_DIR%

echo.
echo ============================================================
echo          AETHVION - SPECTER RIGGING ENGINE
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

:: --- 4. Install Optional Specter Dependencies ------------------
python -c "import rembg" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [INFO]  The 'rembg' package for automatic background removal is not installed.
    echo         This is optional, but recommended for clean VTuber rig generation.
    set /p INSTALL_REMBG="Do you want to install rembg now? (Y/N): "
    if /I "!INSTALL_REMBG!"=="Y" (
        echo [SETUP] Installing rembg and onnxruntime...
        pip install rembg onnxruntime
        if !errorlevel! neq 0 (
            echo [WARN] Failed to install optional dependencies. Specter will run without background removal.
        ) else (
            echo [OK]   Optional dependencies installed successfully.
        )
    ) else (
        echo [INFO] Skipping optional background removal setup.
    )
    echo.
) else (
    echo [OK]  Background removal dependencies verified.
)

:: --- 5. Environment file ---------------------------------------
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

:: --- 6. Launch -------------------------------------------------
echo.
echo [START] Launching Specter Engine...
echo         Viewer -^> http://localhost:8001
echo         Press CTRL+C to stop.
echo.

:: We launch it using the Python environment targeting the module relative to our Root
python modules\aethvion\specter\specter_server.py
set MAIN_EXIT=%errorlevel%

:: --- 7. Result ------------------------------------------------
if %MAIN_EXIT% neq 0 (
    echo.
    echo [ERROR] Specter Engine crashed (exit code %MAIN_EXIT%).
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
