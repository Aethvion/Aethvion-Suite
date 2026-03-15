@echo off
SETLOCAL EnableDelayedExpansion

:: Window always-open guarantee
if not defined AETHVION_FINANCE_LAUNCHED (
    set AETHVION_FINANCE_LAUNCHED=1
    cmd /k ""%~f0""
    exit
)
TITLE Aethvion Finance

:: Root of the repository (two levels up from apps\finance\)
for %%I in ("%~dp0..\..") do set "ROOT_DIR=%%~fI"

:: Switch working directory to project root
cd /d "%ROOT_DIR%"
SET PYTHONPATH=%ROOT_DIR%

echo.
echo          AETHVION FINANCE
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

:: --- 3. Core dependencies (fastapi) ---------------------------
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] Installing fastapi...
    pip install fastapi
    if %errorlevel% neq 0 (
        echo [WARN]  fastapi install reported an issue.
    ) else (
        echo [OK]  fastapi installed.
    )
) else (
    echo [OK]  fastapi verified.
)

:: --- 4. uvicorn -----------------------------------------------
python -c "import uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] Installing uvicorn...
    pip install uvicorn
    if %errorlevel% neq 0 (
        echo [WARN]  uvicorn install reported an issue.
    ) else (
        echo [OK]  uvicorn installed.
    )
) else (
    echo [OK]  uvicorn verified.
)

:: --- 5. yfinance (live market prices) ---------------------------
python -c "import yfinance" >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] Installing yfinance...
    pip install yfinance
    if %errorlevel% neq 0 (
        echo [WARN]  yfinance install reported an issue. Live price refresh may not work.
    ) else (
        echo [OK]  yfinance installed.
    )
) else (
    echo [OK]  yfinance verified.
)

:: --- 6. Create data directory ---------------------------------
if not exist "data\finance\projects" (
    mkdir "data\finance\projects"
    echo [SETUP] Created data\finance\projects directory.
) else (
    echo [OK]  data\finance directory found.
)

:: --- 7. Launch -----------------------------------------------
echo [START] Launching Aethvion Finance...
echo         Viewer -^> http://localhost:8085
echo         Data   -^> data\finance\
echo         Press CTRL+C to stop.
echo.

"%ROOT_DIR%\.venv\Scripts\python.exe" apps\finance\finance_server.py
set MAIN_EXIT=%errorlevel%

:: --- 8. Result -----------------------------------------------
if %MAIN_EXIT% neq 0 (
    echo.
    echo [ERROR] Finance server crashed (exit code %MAIN_EXIT%).
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
