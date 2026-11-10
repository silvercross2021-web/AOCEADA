@echo off
title Tunnel Cloudflare AOCEDA
color 0B
echo ====================================================
echo        LANCEMENT DU TUNNEL CLOUDFLARE AOCEDA
echo ====================================================
echo.
echo Connexion a Cloudflare...
echo Le lien commencant par https://....trycloudflare.com va apparaitre ci-dessous.
echo Donne ce lien a ton binome !
echo.
echo (Pour arreter le tunnel, ferme simplement cette fenetre)
echo ====================================================
echo.

"%~dp0cloudflared.exe" tunnel --protocol http2 --no-autoupdate --url http://127.0.0.1:8003

pause
