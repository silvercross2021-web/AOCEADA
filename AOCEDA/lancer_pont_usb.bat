@echo off
title AOCEDA - Pont USB de l'ESP32
echo.
echo === AOCEDA - Pont USB de l'ESP32 (canal de secours du Wi-Fi) ===
echo.

cd /d "%~dp0"

:: .venv_local = le Python du projet, cree par installer.bat
if not exist ".venv_local\Scripts\python.exe" (
    echo AOCEDA n'est pas encore installe sur ce PC : lancez d'abord installer.bat
    echo.
    pause
    exit /b 1
)

echo Le serveur Django doit deja tourner (lancer_aoceda.bat).
echo Fermez le moniteur serie de PlatformIO : un seul programme peut utiliser le port USB.
echo.
.venv_local\Scripts\python.exe outils\pont_usb_esp32.py %*
echo.
pause
