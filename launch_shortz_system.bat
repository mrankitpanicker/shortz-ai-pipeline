@echo off
title SHORTZ — System Launcher
color 0A

echo.
echo ========================================================
echo    SHORTZ — System Launcher
echo ========================================================
echo.

set "PYTHON=d:\tts\venv\Scripts\python.exe"
set "PROJECT=D:\Projects\Shortz"

cd /d "%PROJECT%"
"%PYTHON%" shortz_supervisor.py

pause
