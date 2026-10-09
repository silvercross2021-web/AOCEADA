@echo off
title AOCEDA - Lancement
echo.
echo === AOCEDA - Demarrage ===
echo.

cd /d "%~dp0"

:: .venv_local = le Python du projet, cree par installer.bat (l'ancien dossier venv pointe vers une autre machine)
if not exist ".venv_local\Scripts\python.exe" (
    echo AOCEDA n'est pas encore installe sur ce PC : lancez d'abord installer.bat
    echo.
    pause
    exit /b 1
)

echo Lancement du serveur Django (port 8003, HTTP + WebSocket de l'appel Live)...
start "AOCEDA - Django" cmd /k "cd /d %~dp0 && .venv_local\Scripts\python.exe manage.py runserver 0.0.0.0:8003"

:: Le pont serie n'est plus necessaire : l'ESP32 envoie ses mesures en Wi-Fi.

:: adresse de ce PC sur le reseau local (pour un telephone ou l'ESP32) : celle de la route reseau reelle, pas celle
:: d'une carte virtuelle (VirtualBox, VMware...) ; aucun paquet n'est envoye
set "IP="
for /f %%a in ('.venv_local\Scripts\python.exe -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0])" 2^>nul') do set "IP=%%a"

echo.
echo Le serveur Django demarre (quelques secondes).
echo Sur ce PC : http://127.0.0.1:8003
if defined IP echo Depuis un telephone ou l'ESP32 (meme Wi-Fi) : http://%IP%:8003
echo.
pause
