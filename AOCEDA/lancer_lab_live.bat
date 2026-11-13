@echo off
title AOCEDA - Laboratoire Live Multilingue
echo.
echo ======================================================================
echo    AOCEDA - Laboratoire Live Multilingue (Port 8775)
echo    Architecture Decouplee : Oreille / Cerveau / Bouche
echo ======================================================================
echo.

cd /d "%~dp0"

if not exist ".venv_local\Scripts\python.exe" (
    echo Erreur : .venv_local est introuvable. Lancez d'abord installer.bat.
    echo.
    pause
    exit /b 1
)

echo Demarrage du serveur de test sur http://127.0.0.1:8775/ ...
echo Ouvrez votre navigateur pour tester l'appel multilingue.
echo.
.venv_local\Scripts\python.exe lab_live\serveur_lab.py

pause
