@echo off
setlocal EnableExtensions
title AOCEDA - Lancement complet
cd /d "%~dp0"

rem ==========================================================================
rem  AOCEDA - lancement complet du prototype en UN seul clic
rem
rem    lancer_tout.bat                 demarre Django + le pont USB de l'ESP32
rem    lancer_tout.bat tout            idem, le pont affiche TOUS les messages de l'ESP32
rem    lancer_tout.bat navigateur      idem, puis ouvre le site dans le navigateur
rem    lancer_tout.bat etat            dit ce qui tourne (ne lance rien)
rem    lancer_tout.bat arreter         arrete Django et le pont
rem
rem  Le pont USB est le moniteur serie de la carte : il montre ses messages utiles ET fait
rem  passer ses mesures a Django par le cable (sans Wi-Fi). Un seul programme peut utiliser
rem  le port USB : ce script ferme le moniteur serie de PlatformIO s'il tourne.
rem  Ce qui tourne deja n'est jamais relance en double.
rem ==========================================================================

set "PY=.venv_local\Scripts\python.exe"
set "PORT_DJANGO=8003"
set "OPT_TOUT="
set "OUVRIR=0"

if not exist "%PY%" (
    echo.
    echo AOCEDA n'est pas encore installe sur ce PC : lancez d'abord installer.bat
    echo.
    pause
    exit /b 1
)

if /i "%~1"=="arreter" goto :arreter
if /i "%~1"=="etat" goto :etat

for %%A in (%*) do (
    if /i "%%A"=="tout" set "OPT_TOUT=--tout"
    if /i "%%A"=="navigateur" set "OUVRIR=1"
)

echo.
echo === AOCEDA - Lancement complet ===
echo.

rem --- 1. Django ---------------------------------------------------------------
call :django_actif
if "%DJANGO%"=="1" goto :django_deja
echo [1/3] Lancement de Django (port %PORT_DJANGO%, HTTP + WebSocket)...
start "AOCEDA - Django" /min cmd /k "cd /d "%~dp0" && %PY% manage.py runserver 0.0.0.0:%PORT_DJANGO%"
goto :django_attente
:django_deja
echo [1/3] Django tourne deja (port %PORT_DJANGO%) : on le garde.
goto :django_fin
:django_attente
echo       attente du serveur (60 s au plus)...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 60 -and -not $ok;$i++){ try{ Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT_DJANGO%/api/sensors/zmct/' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop | Out-Null; $ok=$true }catch{ if($_.Exception.Response){ $ok=$true } else { Start-Sleep -Seconds 1 } } }; if($ok){ exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo.
    echo ERREUR : Django ne repond pas apres 60 s. Regardez la fenetre "AOCEDA - Django" dans
    echo la barre des taches : le message d'erreur y est affiche.
    echo.
    pause
    exit /b 1
)
echo       Django repond.
:django_fin

rem --- 2. Port USB libre ---------------------------------------------------------
rem Le moniteur serie de PlatformIO garderait le port : le pont ne pourrait pas s'y connecter.
powershell -NoProfile -Command "$p = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'device monitor' }); $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; if($p.Count -gt 0){ exit 3 } else { exit 0 }"
if errorlevel 3 echo [2/3] Moniteur serie de PlatformIO ferme : le pont reprend le port USB.
if not errorlevel 3 echo [2/3] Port USB libre.

rem --- 3. Pont USB = moniteur serie --------------------------------------------------
call :pont_actif
if "%PONT%"=="1" goto :pont_deja
echo [3/3] Lancement du pont USB (moniteur serie de la carte)...
start "AOCEDA - Pont USB (moniteur serie)" cmd /k "cd /d "%~dp0" && %PY% outils\pont_usb_esp32.py %OPT_TOUT%"
goto :pont_fin
:pont_deja
echo [3/3] Le pont USB tourne deja : on le garde.
:pont_fin

rem --- Resume ----------------------------------------------------------------------
set "IP="
for /f %%a in ('%PY% -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0])" 2^>nul') do set "IP=%%a"

echo.
echo ------------------------------------------------------------------------
echo  Site, sur ce PC :  http://127.0.0.1:%PORT_DJANGO%
if defined IP echo  Depuis un telephone (meme Wi-Fi) :  http://%IP%:%PORT_DJANGO%
echo.
echo  Deux fenetres tournent : "AOCEDA - Django" (reduite dans la barre des taches)
echo  et "AOCEDA - Pont USB" (les messages de la carte). Ne les fermez pas :
echo  fermer l'une coupe le flux des mesures. Pour tout arreter :
echo      lancer_tout.bat arreter
echo ------------------------------------------------------------------------
echo.
if "%OUVRIR%"=="1" start "" "http://127.0.0.1:%PORT_DJANGO%"
pause
exit /b 0


rem ==========================================================================
:etat
echo.
echo === AOCEDA - Etat ===
echo.
call :django_actif
if "%DJANGO%"=="1" (echo  Django    : en marche, port %PORT_DJANGO%) else (echo  Django    : arrete)
call :pont_actif
if "%PONT%"=="1" (echo  Pont USB  : en marche) else (echo  Pont USB  : arrete)
powershell -NoProfile -Command "$m = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'device monitor' }); if($m.Count -gt 0){ Write-Host ' Moniteur PlatformIO : ouvert (il garde le port USB)' } else { Write-Host ' Moniteur PlatformIO : ferme' }"
echo.
pause
exit /b 0


rem ==========================================================================
:arreter
echo.
echo === AOCEDA - Arret ===
echo.
rem Les motifs sont coupes en deux morceaux pour que cette commande ne se reconnaisse pas elle-meme
powershell -NoProfile -Command "$n=0; Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'cmd.exe') -and $_.CommandLine -match ('manage' + '.py runserver|pont_usb' + '_esp32') -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $n++ }; Write-Host (' ' + $n + ' processus arretes (Django et pont USB).')"
echo.
pause
exit /b 0


rem ==========================================================================
rem  Sous-programmes : positionnent DJANGO / PONT a 1 si le programme tourne
rem ==========================================================================
:django_actif
set "DJANGO=0"
netstat -ano | findstr /R /C:":%PORT_DJANGO% .*LISTENING" >nul 2>&1
if not errorlevel 1 set "DJANGO=1"
exit /b 0

:pont_actif
set "PONT=0"
for /f %%N in ('powershell -NoProfile -Command "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match ('pont_usb' + '_esp32') }).Count"') do set "PONT=%%N"
if not "%PONT%"=="0" set "PONT=1"
exit /b 0
