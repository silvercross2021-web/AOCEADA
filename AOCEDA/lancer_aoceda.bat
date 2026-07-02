@echo off
title AOCEDA - Lancement
echo.
echo === AOCEDA - Demarrage ===
echo.

cd /d "%~dp0"

echo [1/2] Lancement du serveur Django (port 8003)...
start "AOCEDA - Django" cmd /k "cd /d %~dp0 && venv\Scripts\activate && python manage.py runserver 8003"

echo Attente 4 secondes pour que Django demarre...
timeout /t 4 /nobreak >nul

echo [2/2] Lancement du bridge Arduino (COM7)...
start "AOCEDA - Bridge Arduino" cmd /k "cd /d %~dp0 && venv\Scripts\activate && python zmct_bridge.py COM7"

echo.
echo Les deux fenetres sont ouvertes.
echo Connecte-toi sur : http://127.0.0.1:8003
echo.
pause
