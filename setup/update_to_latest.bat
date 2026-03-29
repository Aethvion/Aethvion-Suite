@echo off
TITLE Aethvion Suite — Update to Latest
color 0B

echo.
echo  =====================================================
echo    Aethvion Suite — Update to Latest Version
echo  =====================================================
echo.

:: Navigate to the repo root (this file lives one level below)
cd /d "%~dp0.."

echo  Working directory: %CD%
echo.

:: ── Check Git ────────────────────────────────────────────────────────────
git --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Git is not installed or not in PATH.
    echo  Install Git for Windows: https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

:: ── Check Python ─────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not in PATH.
    echo.
    pause
    exit /b 1
)

:: ── Step 1: Fetch ─────────────────────────────────────────────────────────
echo  [1/4] Fetching latest changes from remote...
git fetch origin main 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] git fetch failed. Check your network connection.
    pause
    exit /b 1
)

:: ── Step 2: Stash ─────────────────────────────────────────────────────────
echo  [2/4] Stashing any local changes...
git stash 2>&1

:: ── Step 3: Pull ──────────────────────────────────────────────────────────
echo  [3/4] Pulling latest version...
git pull origin main 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] git pull failed. Restoring stash before aborting...
    git stash pop 2>&1
    pause
    exit /b 1
)

:: ── Step 4: Dependencies ──────────────────────────────────────────────────
echo  [4/4] Updating Python dependencies...
python -m pip install -e . --quiet 2>&1
if errorlevel 1 (
    echo.
    echo  [WARNING] pip install reported an issue. The suite may still work.
    echo  Run manually: python -m pip install -e .
    echo.
)

:: ── Done ──────────────────────────────────────────────────────────────────
echo.
echo  =====================================================
echo    Update complete!
echo.
echo    Start Aethvion Suite with: Start_Aethvion.bat
echo  =====================================================
echo.
pause
