@echo off
title AOCEDA - Installation
cd /d "%~dp0"
:: Installation complete (bibliotheques, .env, base, modeles de l'assistant IA) : voir installer.py
set "PY="
py -3.13 --version >nul 2>nul && set "PY=py -3.13"
if not defined PY py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY set "PY=python"
%PY% installer.py %*
echo.
pause
