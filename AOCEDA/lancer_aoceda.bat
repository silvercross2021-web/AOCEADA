@echo off
title AOCEDA - Lancement
echo.
echo === AOCEDA - Demarrage ===
echo.

cd /d "%~dp0"

echo [1/2] Lancement du serveur Django (port 8003, HTTP + WebSocket de l'appel Live)...
:: .venv_local = le Python du projet (l'ancien dossier venv pointe vers une autre machine)
start "AOCEDA - Django" cmd /k "cd /d %~dp0 && .venv_local\Scripts\python.exe manage.py runserver 0.0.0.0:8003"

echo Attente 4 secondes pour que Django demarre...
timeout /t 4 /nobreak >nul

echo [2/2] Le pont série n'est plus nécessaire (L'ESP32 envoie en Wi-Fi)
:: start "AOCEDA - Bridge Arduino" cmd /k "cd /d %~dp0 && venv\Scripts\activate && python serial_bridge.py COM7"

echo.
echo Le serveur Django est ouvert.
echo Connecte-toi sur le PC : http://127.0.0.1:8003
echo Ou depuis un téléphone/ESP32 : http://10.11.255.194:8003
echo.
pause
