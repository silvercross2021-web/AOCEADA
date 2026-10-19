# firmware/ : documentation du micrologiciel ESP32

Le code est à la racine du dépôt (PlatformIO l'exige) : `src/main.cpp`, `include/`, `lib/`, `test/`, `platformio.ini`.
**Ne pas le modifier sans demande explicite** : l'endpoint `/api/sensors/zmct/` et son format sont un contrat.

| Page | Contenu |
|---|---|
| [firmware-esp32.md](firmware-esp32.md) | **le firmware tel qu'il est** : brochage, Wi-Fi multi-réseaux, détection par fréquences, tampon, relais, OTA |
| [guide-test-bout-en-bout.md](guide-test-bout-en-bout.md) | configurer, flasher, vérifier les capteurs, lancer le serveur, voir les données |
| [detection-onoff-zmct103c.md](detection-onoff-zmct103c.md) | méthode d'origine (RMS, Arduino Uno) : historique et principes |

Attention : en local, `src/main.cpp` contient les mots de passe Wi-Fi de la machine. Ne jamais committer ce fichier avec
ces valeurs.
