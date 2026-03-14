@echo off
SETLOCAL EnableDelayedExpansion

:: Window always-open guarantee
if not defined AETHVION_AUDIO_LAUNCHED (
    set AETHVION_AUDIO_LAUNCHED=1
    cmd /k ""%~f0""
    exit
)
TITLE Aethvion Audio Editor

:: Figure out the directory where this script actually lives
SET AUDIO_MODULE_DIR=%~dp0

:: The script is in C:\Aethvion\Aethvion-Suite\apps\audio\
for %%I in ("%~dp0..\..") do set "ROOT_DIR=%%~fI"

:: Switch working directory to the project root
cd /d "%ROOT_DIR%"
SET PYTHONPATH=%ROOT_DIR%

echo.
echo          AETHVION AUDIO EDITOR
echo.
echo [INFO] Running under Aethvion Suite root: %ROOT_DIR%
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

:: --- 4. Install Audio Dependencies ----------------------------
python -c "import pydub" >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] Installing audio dependencies...
    pip install pydub numpy
    if %errorlevel% neq 0 (
        echo [WARN]  Audio dependency installation reported an issue.
    ) else (
        echo [OK]  Audio dependencies installed.
    )
) else (
    echo [OK]  Audio dependencies verified.
)

:: --- 5. FFmpeg notice ------------------------------------------
echo.
echo [NOTE] MP3 import/export requires FFmpeg to be installed.
echo        Download from: https://ffmpeg.org/download.html
echo        WAV, OGG, and FLAC work without FFmpeg.
echo.

:: --- 6. Environment file ---------------------------------------
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [SETUP] Created .env from .env.example
    )
) else (
    echo [OK]  .env found.
)

:: --- 7. Launch -------------------------------------------------
echo [START] Launching Aethvion Audio Editor...
echo         Viewer -^> http://localhost:8083
echo         Press CTRL+C to stop.
echo.

"%ROOT_DIR%\.venv\Scripts\python.exe" apps\audio\audio_server.py
set MAIN_EXIT=%errorlevel%

:: --- 8. Result ------------------------------------------------
if %MAIN_EXIT% neq 0 (
    echo.
    echo [ERROR] Audio Server crashed (exit code %MAIN_EXIT%).
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
