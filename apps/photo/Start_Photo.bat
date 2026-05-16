@echo off
set TITLE=Aethvion Photo Service
title %TITLE%
echo Starting %TITLE%...

:: Root of the repository (two levels up from apps\photo\)
for %%I in ("%~dp0..\..") do set "ROOT_DIR=%%~fI"

:: Switch working directory to project root
cd /d "%ROOT_DIR%"
SET PYTHONPATH=%ROOT_DIR%

:: Check for environment variables or use defaults
if "%PHOTO_PORT%"=="" set PHOTO_PORT=8081

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

:: Run the server
"%ROOT_DIR%\.venv\Scripts\python.exe" apps\photo\photo_server.py
pause
