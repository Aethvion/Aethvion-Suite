@echo off
:: ============================================================
::  AETHVION SUITE — Directory Setup Helper
::  Creates all necessary data subfolders for the suite.
:: ============================================================

set PROJECT_DIR=%~dp0..
cd /d "%PROJECT_DIR%"

echo.
echo [1/3] VERIFYING DIRECTORY STRUCTURE...

:: ── Apps ─────────────────────────────────────────────────────
echo [SETUP] Configuring application storage...
if not exist "data\apps"                   mkdir "data\apps"
if not exist "data\apps\arena"             mkdir "data\apps\arena"
if not exist "data\apps\audio"             mkdir "data\apps\audio"
if not exist "data\apps\code"              mkdir "data\apps\code"
if not exist "data\apps\code\projects"     mkdir "data\apps\code\projects"
if not exist "data\apps\driveinfo"         mkdir "data\apps\driveinfo"
if not exist "data\apps\finance"           mkdir "data\apps\finance"
if not exist "data\apps\games"             mkdir "data\apps\games"
if not exist "data\apps\hardwareinfo"      mkdir "data\apps\hardwareinfo"
if not exist "data\apps\nexus"             mkdir "data\apps\nexus"
if not exist "data\apps\photo"             mkdir "data\apps\photo"
if not exist "data\apps\tracking"          mkdir "data\apps\tracking"
if not exist "data\apps\vtuber"            mkdir "data\apps\vtuber"
if not exist "data\apps\vtuber\models"     mkdir "data\apps\vtuber\models"
if not exist "data\apps\vtuber\files"      mkdir "data\apps\vtuber\files"

:: ── Config ───────────────────────────────────────────────────
echo [SETUP] Configuring system config...
if not exist "data\config"                 mkdir "data\config"

:: ── History ──────────────────────────────────────────────────
echo [SETUP] Configuring conversation history...
if not exist "data\history"                    mkdir "data\history"
if not exist "data\history\chat"               mkdir "data\history\chat"
if not exist "data\history\ai_conversations"   mkdir "data\history\ai_conversations"
if not exist "data\history\advanced"           mkdir "data\history\advanced"

:: ── Logs ─────────────────────────────────────────────────────
echo [SETUP] Configuring unified logging...
if not exist "data\logs"                   mkdir "data\logs"
if not exist "data\logs\usage"             mkdir "data\logs\usage"
if not exist "data\logs\system"            mkdir "data\logs\system"

:: ── System ───────────────────────────────────────────────────
echo [SETUP] Configuring runtime system state...
if not exist "data\system"                 mkdir "data\system"

:: ── Vault ────────────────────────────────────────────────────
echo [SETUP] Configuring persistent vault...
if not exist "data\vault"                                    mkdir "data\vault"
if not exist "data\vault\personas"                           mkdir "data\vault\personas"
if not exist "data\vault\personas\misakacipher"              mkdir "data\vault\personas\misakacipher"
if not exist "data\vault\personas\misakacipher\threads"      mkdir "data\vault\personas\misakacipher\threads"
if not exist "data\vault\knowledge"                          mkdir "data\vault\knowledge"
if not exist "data\vault\search"                             mkdir "data\vault\search"
if not exist "data\vault\episodic"                           mkdir "data\vault\episodic"

:: ── Workspaces ───────────────────────────────────────────────
echo [SETUP] Configuring workspaces...
if not exist "data\workspaces"             mkdir "data\workspaces"
if not exist "data\workspaces\outputs"     mkdir "data\workspaces\outputs"
if not exist "data\workspaces\tools"       mkdir "data\workspaces\tools"
if not exist "data\workspaces\media"       mkdir "data\workspaces\media"
if not exist "data\workspaces\uploads"     mkdir "data\workspaces\uploads"
if not exist "data\workspaces\projects"    mkdir "data\workspaces\projects"

echo [OK]    Directory structure ready.
echo.
