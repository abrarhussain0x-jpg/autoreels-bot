@echo off
:: AUTO-REELS PRO v5.0 — Quick launcher for Windows
title AUTO-REELS PRO v5.0

cd /d "%~dp0cloud"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Download from https://python.org
    pause & exit /b 1
)

:: Check FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] FFmpeg not found.
    echo Download from https://ffmpeg.org/download.html and add to PATH.
    pause & exit /b 1
)

:: Install deps if needed
python -c "import flask, apscheduler, rich" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

:: Check .env
if not exist "%~dp0.env" (
    echo No .env found. Running setup wizard...
    python main.py --setup
    goto :end
)

echo.
echo  ^<^< AUTO-REELS PRO v5.0 ^>^>
echo  Dashboard: http://localhost:8888
echo.

python main.py %*

:end
pause
