@echo off
title SHORTZ GUI
color 0E

echo.
echo ========================================================
echo    SHORTZ — GUI (standalone)
echo ========================================================
echo.

set "PYTHON=d:\tts\venv\Scripts\python.exe"
set "PROJECT=D:\Projects\Shortz"

echo [OK]   Launching GUI ...
echo.
cd /d "%PROJECT%"
"%PYTHON%" main.pyw

echo.
echo [....] GUI exited.
pause
