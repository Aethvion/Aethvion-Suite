@echo off
title Aethvion DevTool - Companion Editor
echo.
echo ============================================================
echo   Aethvion Dev Tool - Companion Editor
echo   URL : http://localhost:8003
echo   Dir : core/companions/configs/
echo   Saves go directly to shipped defaults
echo ============================================================
echo.
cd /d "%~dp0..\.."
.venv\Scripts\python.exe -m core.devtools.companion_editor.server
pause
