@echo off
setlocal EnableExtensions
title Build Frosty EXE
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found on PATH.
    pause
    exit /b 1
)

echo Installing PyInstaller and app dependencies...
python -m pip install -U pip pyinstaller
python -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Install failed.
    pause
    exit /b 1
)

echo.
echo Building folder EXE. This can take several minutes.
echo Output: dist\Frosty\Frosty.exe
echo.

python -m PyInstaller --noconfirm --clean --onedir --console ^
  --name Frosty ^
  --collect-all paddleocr ^
  --collect-all paddle ^
  --collect-all cv2 ^
  --hidden-import edge_tts ^
  --hidden-import pygame ^
  --hidden-import pynput ^
  --hidden-import mss ^
  --hidden-import pycaw ^
  --hidden-import comtypes ^
  --hidden-import PIL ^
  --hidden-import psutil ^
  "%~dp0Frosty_v24_5_NATURAL_VOICE.py"

if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Done.
echo Double-click: dist\Frosty\Frosty.exe
echo Keep the whole dist\Frosty folder together. Do not move only the exe.
pause
