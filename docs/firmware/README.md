# firmware/ : documentation du micrologiciel ESP32

Le code est à la racine du dépôt (PlatformIO l'exige) : `src/` (découpé en couches), `include/`, `lib/`, `test/`, `platformio.ini`.
**Ne pas le modifier sans demande explicite** : l'endpoint `/api/sensors/zmct/` et son format sont un contrat.

| Page | Contenu |
|---|---|
| [architecture-firmware.md](architecture-firmware.md) | **comment le code est organisé** : couches, modules, trajet d'une mesure, où changer quoi, où est passé l'ancien `main.cpp` |
| [firmware-esp32.md](firmware-esp32.md) | **le firmware tel qu'il est** : brochage, Wi-Fi multi-réseaux, détection par fréquences, tampon, relais, OTA |
| [guide-test-bout-en-bout.md](guide-test-bout-en-bout.md) | configurer, flasher, vérifier les capteurs, lancer le serveur, voir les données |
| [detection-onoff-zmct103c.md](detection-onoff-zmct103c.md) | méthode d'origine (RMS, Arduino Uno) : historique et principes |

Les mots de passe Wi-Fi, la clé du boîtier et le mot de passe OTA sont dans `include/secrets.h`, **ignoré par Git** : ne jamais le
committer (le modèle `include/secrets.example.h`, lui, est versionné). Tests du domaine, sur PC : `pio test -e native`.
