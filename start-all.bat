@echo off
REM One-click launcher: V2RayN + Claude Code proxy
REM Auto-relaunches in Windows Terminal if not already in one.

setlocal
set "SCRIPT_DIR=%~dp0"
REM Strip trailing backslash to avoid wt.exe quote-escaping bug
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if not defined WT_SESSION (
    start "" wt.exe -d "%SCRIPT_DIR%" cmd /k "%~f0"
    exit /b
)

cd /d "%SCRIPT_DIR%"
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\start-all.ps1"
pause
