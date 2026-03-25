@echo off
SETLOCAL EnableDelayedExpansion

:: Window always-open guarantee
if not defined AETHVION_LAUNCHED (
    set AETHVION_LAUNCHED=1
    cmd /k ""%~f0""
    exit
)

SET PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"
TITLE Aethvion Suite — Developer Portal

echo.
echo ============================================================
echo   AETHVION SUITE  ^|  DEVELOPER MODE
echo ============================================================
echo.

:: ── 1. Python check ─────────────────────────────────────────
echo [1/5] VERIFYING PYTHON...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    goto :FAIL
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK]   Python %PY_VER% verified.

:: ── 2. Virtual environment ───────────────────────────────────
echo.
echo [2/5] SYNCING VIRTUAL ENVIRONMENT...
if not exist ".venv\Scripts\activate.bat" (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        goto :FAIL
    )
    echo [OK]   Virtual environment created.
) else (
    echo [OK]   Virtual environment found.
)
call ".venv\Scripts\activate.bat"

:: ── 3. Dependencies ──────────────────────────────────────────
echo.
echo [3/5] VERIFYING DEPENDENCIES...
python -c "import fastapi" >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK]   Dependencies verified.
    goto :FINALIZING
)

echo [SETUP] Installing dependencies from pyproject.toml...
python -m pip install --upgrade pip
pip install -e ".[memory]"
if !errorlevel! equ 0 (
    echo [OK]   Dependencies installed.
    goto :FINALIZING
)

echo.
echo [WARNING] Extended dependency installation failed.
echo [SETUP] Attempting minimal core installation...
pip install -e "."
if !errorlevel! neq 0 (
    echo [ERROR] Dependency installation failed.
    echo [TIP] If you are on an older PC, ensure you have a stable Python version (e.g. 3.12).
    goto :FAIL
)
echo [OK]   Core suite installed. Some optional local AI features were skipped.

:FINALIZING

:: ── 4. Configuration ─────────────────────────────────────────
echo.
echo [4/5] FINALIZING CONFIGURATION...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [SETUP] Created .env from template.
    ) else (
        echo [WARN]  No .env file found.
    )
) else (
    echo [OK]   .env found.
)
if not exist "core\config\security.yaml" (
    if exist "core\config\security.yaml.example" (
        copy "core\config\security.yaml.example" "core\config\security.yaml" >nul
        echo [SETUP] Created security.yaml from template.
    )
)

:: ── 5. Required directories ──────────────────────────────────
call core\setup_directories.bat

:: ── 6. Launch (dev mode — visible consoles, web browser tab) ─
echo.
echo [5/5] LAUNCHING CORE ENGINE...
echo [INFO] Dashboard  -^> http://localhost:8080
echo [INFO] Press Ctrl+C here to stop the entire suite.
echo.

python core\launcher.py --dev --browser web %*
set MAIN_EXIT=%errorlevel%

if %MAIN_EXIT% neq 0 (
    echo.
    echo [ERROR] Launcher exited with code %MAIN_EXIT%.
    goto :FAIL
)
goto :END

:FAIL
echo.
echo ============================================================
echo  Something went wrong — read the error above, then close.
echo ============================================================
echo.
pause
exit /b 1

:END
pause
