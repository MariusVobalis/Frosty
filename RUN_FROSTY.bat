@echo off
setlocal EnableExtensions
title FROSTY v24.5 - Natural Voice
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found on PATH.
    echo Install Python 3.10+ and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Python 3.10 or newer is required.
    pause
    exit /b 1
)

echo Checking dependencies...
if exist "%~dp0requirements.txt" (
    python -m pip install -r "%~dp0requirements.txt"
) else (
    python -m pip install pycaw comtypes opencv-python psutil mss pillow pynput edge-tts pygame paddleocr numpy
)
if errorlevel 1 (
    echo.
    echo Dependency install failed.
    pause
    exit /b 1
)

echo.
echo Starting Frosty...
python "%~dp0Frosty_v24_5_NATURAL_VOICE.py"
if errorlevel 1 (
    echo.
    echo Frosty exited with an error.
)
pause
