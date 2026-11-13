@echo off
title Tunnel ngrok - AOCEDA
cd /d "%~dp0"
echo ========================================================
echo   Lancement du tunnel public ngrok vers Django (port 8003)
echo ========================================================
echo.
ngrok http 8003
pause
