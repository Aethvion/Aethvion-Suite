@echo off
setlocal EnableDelayedExpansion

:: ---------------------------------------------------------------------------
::  Aethvion Suite - C# WebView2 Wrapper Build Script
::  Produces a single self-contained AethvionSuite.exe (no .NET runtime needed)
::
::  Source lives in:  core/devtools/csharpwrapper/
::  Output goes to:   dist/wrapper/AethvionSuite.exe  (project root)
:: ---------------------------------------------------------------------------

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\..\.."
set "OUT_DIR=%PROJECT_ROOT%\dist\wrapper"
set "EXE_NAME=AethvionSuite.exe"

echo.
echo  +------------------------------------------+
echo  ^|   Aethvion Suite - Build Wrapper (.exe)  ^|
echo  +------------------------------------------+
echo.

:: -- Check for dotnet --------------------------------------------------------
where dotnet >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] dotnet.exe not found on PATH.
    echo.
    echo  Please install the .NET 8 SDK from:
    echo    https://dotnet.microsoft.com/download/dotnet/8.0
    echo.
    echo  After installing, re-run this script.
    echo.
    pause
    exit /b 1
)

:: -- Check SDK version -------------------------------------------------------
for /f "tokens=1" %%v in ('dotnet --version 2^>nul') do set "DOTNET_VER=%%v"
echo  dotnet %DOTNET_VER% detected.

:: -- Restore packages --------------------------------------------------------
echo.
echo  [1/3] Restoring NuGet packages...
dotnet restore "%SCRIPT_DIR%AethvionSuite.csproj" --nologo -v quiet
if errorlevel 1 (
    echo  [ERROR] Package restore failed. Check your internet connection.
    pause
    exit /b 1
)

:: -- Publish (self-contained, single file, win-x64) -------------------------
echo  [2/3] Publishing (self-contained, single-file, win-x64)...
dotnet publish "%SCRIPT_DIR%AethvionSuite.csproj" ^
    -c Release ^
    -r win-x64 ^
    --self-contained true ^
    -p:PublishSingleFile=true ^
    -p:PublishTrimmed=false ^
    -p:IncludeNativeLibrariesForSelfExtract=true ^
    -o "%OUT_DIR%" ^
    --nologo ^
    -v quiet

if errorlevel 1 (
    echo  [ERROR] Build failed. See output above for details.
    pause
    exit /b 1
)

:: -- Copy icon next to exe (optional, for Start Menu / taskbar) -------------
if exist "%SCRIPT_DIR%icon.ico" (
    copy /y "%SCRIPT_DIR%icon.ico" "%OUT_DIR%\icon.ico" >nul
)

:: -- Report ------------------------------------------------------------------
echo  [3/3] Done!
echo.
echo  Output: %OUT_DIR%\%EXE_NAME%
echo.

:: Show file size
for %%F in ("%OUT_DIR%\%EXE_NAME%") do (
    set /a SIZE_MB=%%~zF / 1048576
    echo  Size  : !SIZE_MB! MB
)

echo.
echo  -- Next steps ------------------------------------------------------------
echo  Option A  Copy %EXE_NAME% to the Aethvion Suite project root and run it.
echo  Option B  Copy it anywhere; it walks up directories to find the project.
echo.
echo  Prerequisites on the target machine:
echo    * Windows 10 / 11 (WebView2 ships with Edge -- already present)
echo    * No .NET runtime needed (self-contained build)
echo    * Aethvion Suite venv must exist  (run Start_Aethvion.bat first)
echo.
pause
