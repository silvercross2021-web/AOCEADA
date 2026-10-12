@echo off
title Tunnel ngrok - AOCEDA
cd /d "%~dp0"
echo ========================================================
echo   Lancement du tunnel public ngrok vers Django (port 8003)
echo ========================================================
echo Domaine public : https://vision-aerospace-operable.ngrok-free.dev
echo.
"%LOCALAPPDATA%\Programs\ngrok\ngrok.exe" http --url=https://vision-aerospace-operable.ngrok-free.dev 8003
if errorlevel 1 (
    echo.
    echo [ERREUR] ngrok s'est arrete avec une erreur.
)
pause
