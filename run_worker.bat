@echo off
title SHORTZ Worker [gpu-worker-1]
color 0B

echo.
echo ========================================================
echo    SHORTZ — GPU Worker (standalone)
echo ========================================================
echo    Worker:  gpu-worker-1
echo    Queue:   shortz_jobs
echo    GPU:     1
echo ========================================================
echo.

set "PYTHON=d:\tts\venv\Scripts\python.exe"
set "PROJECT=D:\Projects\Shortz"

:: Duplicate check
wmic process where "name='python.exe'" get CommandLine 2>nul | findstr /i "worker.py" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [WARN] Worker already running. Aborting.
    pause
    exit /b 1
)

:: Redis check
echo [....] Checking Redis ...
wsl redis-cli ping 2>nul | findstr /i "PONG" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Redis not running. Use launch_shortz_system.bat instead.
    pause
    exit /b 1
)
echo [OK]   Redis running
echo.

echo [OK]   Starting worker ...
echo.
cd /d "%PROJECT%"
"%PYTHON%" worker.py

echo.
echo [....] Worker exited.
pause
