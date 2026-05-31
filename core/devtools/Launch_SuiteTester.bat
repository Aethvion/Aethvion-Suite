@echo off
title Aethvion DevTool - Suite Tester
echo.
echo ============================================================
echo   Aethvion Dev Tool - Suite Tester (Auto Integration Tests)
echo   URL : http://localhost:8004
echo ============================================================
echo.
cd /d "%~dp0..\.."
.venv\Scripts\python.exe -m core.devtools.suite_tester.server
pause
