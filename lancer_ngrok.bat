@echo off
title Tunnel ngrok - AOCEDA
echo ========================================================
echo   Lancement du tunnel public ngrok vers Django (port 8003)
echo ========================================================
echo Domaine public : https://vision-aerospace-operable.ngrok-free.dev
echo.
"%LOCALAPPDATA%\Programs\ngrok\ngrok.exe" http --url=https://vision-aerospace-operable.ngrok-free.dev 8003
pause
