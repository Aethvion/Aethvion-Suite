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
TITLE Aethvion Suite - Developer Portal

:: ── 1. Setup / Environment check ────────────────────
if not exist .venv (
    echo [ERROR] Virtual environment not found.
    echo Running installer...
    start /wait setup\installer.exe
    if not exist .venv (
        echo [ERROR] Installer failed to create .venv. 
        pause & exit /b 1
    )
)

:: ── 2. Launch (dev mode - visible consoles, web browser tab) ─
echo.
echo [1/1] LAUNCHING CORE ENGINE (DEV MODE)...
echo [INFO] Dashboard  -> http://localhost:8080
echo [INFO] Press Ctrl+C here to stop the entire suite.
echo.

.venv\Scripts\python.exe core\launcher.py --dev --browser web %*
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
