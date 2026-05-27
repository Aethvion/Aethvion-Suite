@echo off
title Aethvion DevTool - Automate Editor
echo.
echo ============================================================
echo   Aethvion Dev Tool - Automate Workflow Editor
echo   URL : http://localhost:8002
echo   Dir : core/automate/config/
echo   Saves go directly to shipped defaults
echo ============================================================
echo.
cd /d "%~dp0..\.."
.venv\Scripts\python.exe -m core.devtools.automate_editor.server
pause
