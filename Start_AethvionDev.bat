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

echo.
echo ============================================================
echo   AETHVION SUITE  ^|  DEVELOPER MODE
echo ============================================================
echo.

call setup\setup_environment.bat
if %errorlevel% neq 0 (
    goto :FAIL
)


:: ── 6. Launch (dev mode - visible consoles, web browser tab) ─
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
