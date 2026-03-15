@echo off
SETLOCAL EnableDelayedExpansion

:: Window always-open guarantee:
:: When double-clicked, AETHVION_LAUNCHED is undefined.
:: We re-launch this same script inside `cmd /k` which holds the window open
:: until the user explicitly closes it - regardless of errors or crashes.
if not defined AETHVION_LAUNCHED (
    set AETHVION_LAUNCHED=1
    cmd /k ""%~f0""
    exit
)
TITLE Aethvion Suite - Aethvion Systems
SET PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"

echo.
echo ============================================================
echo                AETHVION SUITE
echo ============================================================
echo.

:: --------------------------------------------------------------
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

:: --- 3. Install / verify dependencies -------------------------
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] Installing dependencies from pyproject.toml...
    python -m pip install --upgrade pip
    pip install -e ".[memory]"
    if %errorlevel% neq 0 (
        echo.
        echo [WARN]  Dependency installation reported an issue. 
        echo         Checking if core packages are available...
        :: Run the check and capture any error message if it fails
        python -c "import fastapi; import pydantic; import google.genai" >clog.tmp 2>&1
        if !errorlevel! neq 0 (
            echo [ERROR] Core dependencies check failed.
            echo         Details:
            type clog.tmp
            del clog.tmp
            echo.
            echo         Try running: pip install -e ".[memory]"
            goto :FAIL
        )
        del clog.tmp
        echo [OK]    Core dependencies verified despite pip warnings.
    ) else (
        echo [OK]  Dependencies installed.
    )
) else (
    echo [OK]  Dependencies verified.
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

:: --- 5. Required directories -----------------------------------
:: Core Nervous System
if not exist "data\core"                       mkdir data\core
if not exist "data\core\logs"                  mkdir data\core\logs
if not exist "data\core\config"                mkdir data\core\config
if not exist "data\core\system"                mkdir data\core\system

:: AI Brain
if not exist "data\ai"                         mkdir data\ai
if not exist "data\ai\history"                 mkdir data\ai\history
if not exist "data\ai\memory"                  mkdir data\ai\memory
if not exist "data\ai\memory\storage"          mkdir data\ai\memory\storage
if not exist "data\ai\outputfiles"             mkdir data\ai\outputfiles
if not exist "data\ai\workspace"               mkdir data\ai\workspace
if not exist "data\ai\workspace\media"         mkdir data\ai\workspace\media
if not exist "data\ai\workspace\uploads"       mkdir data\ai\workspace\uploads
if not exist "data\ai\tools"                   mkdir data\ai\tools
if not exist "data\ai\tools\generated"         mkdir data\ai\tools\generated

:: App Data
if not exist "data\vtuber"                     mkdir data\vtuber
if not exist "data\tracking"                   mkdir data\tracking
if not exist "data\photo"                      mkdir data\photo
if not exist "data\audio"                      mkdir data\audio

:: --- 5.1 Configuration Setup ----------------------------------
if not exist "core\config\security.yaml" (
    if exist "core\config\security.yaml.example" (
        copy "core\config\security.yaml.example" "core\config\security.yaml" >nul
        echo [OK]    Created security.yaml from template.
    )
)

:: --- 6. Launch -------------------------------------------------
echo.
echo [START] Launching Aethvion Suite...
echo         Dashboard -^> http://localhost:8080 (or your configured PORT)
echo         Press CTRL+C to stop.
echo.

python -m core.main %*
set MAIN_EXIT=%errorlevel%

:: --- 7. Result ------------------------------------------------
if %MAIN_EXIT% neq 0 (
    echo.
    echo [ERROR] Aethvion Suite crashed (exit code %MAIN_EXIT%).
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
