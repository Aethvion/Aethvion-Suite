@echo off
:: ============================================================
::  AETHVION SUITE — Directory Setup Helper
::  Creates all necessary data/apps subfolders for the suite.
:: ============================================================

set PROJECT_DIR=%~dp0..
cd /d "%PROJECT_DIR%"

echo [SETUP] Verifying directory structure...

:: ── Root Data ────────────────────────────────────────────────
if not exist "data\apps"            mkdir "data\apps"

:: ── Core System ──────────────────────────────────────────────
if not exist "data\core"            mkdir "data\core"
if not exist "data\core\logs"       mkdir "data\core\logs"
if not exist "data\core\config"     mkdir "data\core\config"
if not exist "data\core\system"     mkdir "data\core\system"

:: ── AI & Memory ──────────────────────────────────────────────
if not exist "data\ai"              mkdir "data\ai"
if not exist "data\ai\history"      mkdir "data\ai\history"
if not exist "data\ai\memory"       mkdir "data\ai\memory"
if not exist "data\ai\outputfiles"  mkdir "data\ai\outputfiles"

:: ── App Specific ─────────────────────────────────────────────
if not exist "data\apps\audio"         mkdir "data\apps\audio"
if not exist "data\apps\code"          mkdir "data\apps\code"
if not exist "data\apps\code\projects" mkdir "data\apps\code\projects"
if not exist "data\apps\driveinfo"     mkdir "data\apps\driveinfo"
if not exist "data\apps\finance"       mkdir "data\apps\finance"
if not exist "data\apps\hardwareinfo"  mkdir "data\apps\hardwareinfo"
if not exist "data\apps\photo"         mkdir "data\apps\photo"
if not exist "data\apps\tracking"      mkdir "data\apps\tracking"
if not exist "data\apps\vtuber"        mkdir "data\apps\vtuber"
if not exist "data\apps\vtuber\models" mkdir "data\apps\vtuber\models"
if not exist "data\apps\vtuber\files"  mkdir "data\apps\vtuber\files"

echo [OK]    Directory structure verified.
