# ZMCT103C — Firmware IoT AOCEDA (ESP32)

Firmware PlatformIO pour ESP32 qui lit deux capteurs de courant ZMCT103C
(détection allumé/éteint + courant/puissance), envoie les mesures en Wi-Fi
vers le serveur Django AOCEDA, et met en tampon (LittleFS) si le réseau ou
le serveur est indisponible. Ce document décrit **le test complet, de bout
en bout** : compiler/flasher le code dans VS Code, vérifier que les
capteurs sont bien lus, démarrer le serveur, se connecter, et visualiser
les données reçues.

---

## 1. Prérequis

- **VS Code** + l'extension **PlatformIO IDE** (icône fourmi dans la barre
  latérale). Ce dépôt est déjà un projet PlatformIO (`platformio.ini`).
- Un **ESP32** relié en USB, avec deux capteurs **ZMCT103C** branchés sur
  les broches analogiques `34` et `35` (voir `capteurs[]` dans
  [src/main.cpp](src/main.cpp)).
- Un réseau **Wi-Fi 2,4 GHz** (l'ESP32 ne voit pas le 5 GHz) sur lequel le
  PC qui fait tourner Django est aussi connecté.
- Le serveur Django du dossier [AOCEDA/](AOCEDA/), installé une fois avec
  `AOCEDA\installer.bat` (bibliothèques, `.env`, base, modèles de l'assistant IA) :
  voir [AOCEDA/INSTALLATION.md](AOCEDA/INSTALLATION.md).

Vous travaillez avec un agent IA (Claude Code, Codex, Cursor…) ? Ses consignes sont dans [AGENTS.md](AGENTS.md) :
branche à utiliser, installation après un clone, structure de l'assistant IA, interdits.

## 2. Configurer le firmware avant de flasher

Tout est en haut de [src/main.cpp](src/main.cpp) :

```cpp
const char* ssid       = "...";   // nom de ton réseau Wi-Fi 2,4 GHz
const char* password   = "...";   // mot de passe de ce réseau
const char* serverName = "http://<IP_DU_PC>:8003/api/sensors/zmct/";
const char* apiKeyDevice = "..."; // doit correspondre au Dispositif créé côté Django
```

L'IP du PC (serveur Django) **change à chaque changement de réseau**
(DHCP). Avant de flasher, récupère-la avec `ipconfig` (adaptateur Wi-Fi,
"Adresse IPv4") et mets-la à jour dans `serverName`.

Dans [platformio.ini](platformio.ini), vérifie `upload_port` (le port COM
de l'ESP32, visible dans le Gestionnaire de périphériques Windows si
`COM4` ne correspond plus).

## 3. Compiler et flasher depuis VS Code

Avec l'extension PlatformIO, en bas de VS Code (barre bleue) :

| Icône | Action | Équivalent CLI |
| :--- | :--- | :--- |
| ✔️ (coche) | Compiler (Build) | `pio run` |
| → (flèche) | Flasher (Upload) | `pio run -t upload` |
| 🔌 (prise) | Moniteur série | `pio device monitor` |

Ou tout d'un coup : ouvre le terminal PlatformIO (icône fourmi → "PIO
Home" ou terminal intégré) et lance :

```
pio run -t upload -t monitor
```

Le moniteur s'ouvre à **9600 bauds** (réglé dans `platformio.ini`).

## 4. Vérifier que les capteurs sont bien lus (moniteur série)

Au démarrage, tu dois voir dans l'ordre :

1. `=== ZMCT103C - AOCEDA IOT (Wi-Fi) ===` puis le serveur configuré et le
   SSID ciblé.
2. `[SCAN] Reseaux Wi-Fi 2,4 GHz visibles :` — la liste des réseaux vus par
   l'ESP32. **Si ton réseau n'apparaît pas ici**, il émet en 5 GHz
   (invisible pour l'ESP32) ou est hors de portée : le firmware te le dit
   explicitement (`ABSENT (=> probablement en 5 GHz)`).
3. `WiFi connecte ! Adresse IP de l'ESP32 : ...`
4. `[Serveur] Joignable a http://...` (code HTTP) — confirme que l'IP/port
   du serveur Django sont corrects. Si tu vois `[Serveur] INJOIGNABLE`,
   l'IP du PC a changé : mets à jour `serverName` (étape 2) et reflashe.
5. `Stabilisation offset...` puis `Pret a mesurer !`

Ensuite, **teste chaque capteur en branchant/débranchant un appareil** sur
la prise/lampe reliée au ZMCT103C correspondant. Tu dois voir :

```
+++ Capteur_1 ALLUME
[HTTP] Envoi OK : {"capteur_index":1,"etat":"ON","courant":0.523,"puissance":115.1,"timestamp_unix":...}
```

puis, à l'extinction :

```
--- Capteur_1 ETEINT
[HTTP] Envoi OK : {"capteur_index":1,"etat":"OFF","courant":0.000,"puissance":0.0,...}
```

Si tu vois `[HTTP] Hors-ligne, mis en tampon : ...` au lieu de `Envoi OK`,
le Wi-Fi est bon mais le serveur Django n'est pas joignable (pas démarré,
mauvaise IP, ou pare-feu) — les mesures ne sont pas perdues, elles seront
rejouées automatiquement dès que le serveur répond (`[Tampon] N
mesure(s) rejouee(s)`).

## 5. Démarrer le serveur Django

Depuis [AOCEDA/](AOCEDA/), le plus simple est le script fourni :

```
AOCEDA\lancer_aoceda.bat
```

Il lance `manage.py runserver 0.0.0.0:8003` avec le Python du projet (`.venv_local`) : serveur
Daphne (pages, API et WebSocket de l'appel Live de l'assistant). Le
`0.0.0.0` est important : il permet à l'ESP32 (et à un téléphone sur le
même réseau) d'atteindre le serveur, pas seulement `127.0.0.1`.

Une fois lancé, le terminal affiche l'IP à utiliser côté ESP32/téléphone
(à revérifier à chaque changement de réseau, comme à l'étape 2).

## 6. Se connecter / créer un compte

Il n'y a **pas d'auto-inscription publique** côté client : un compte
client est créé soit par un **technicien** (depuis son espace, "Créer un
client"), soit par un **administrateur** (console Django Admin). C'est un
choix produit délibéré (parc de capteurs géré par AOCEDA, pas de
self-service).

- **Espace client / technicien** : `http://<IP_DU_PC>:8003/auth/`
- **Admin Django** (créer des comptes, dispositifs, capteurs) :
  `http://<IP_DU_PC>:8003/admin/`

Des comptes de test déjà en base (admin/technicien/clients) sont listés
dans [AOCEDA/COMPTES.md](AOCEDA/COMPTES.md). Pour qu'un nouveau dispositif
ESP32 soit accepté, sa clé (`apiKeyDevice` dans `main.cpp`) doit
correspondre à un **Dispositif** créé et assigné à un client (Admin ou
espace technicien → Dispositifs), et un capteur doit être assigné à ce
dispositif pour que `capteur_index` (1 ou 2) soit rattaché à un
utilisateur.

## 7. Visualiser les données reçues

Une fois connecté (client) :

- **Tableau de bord** — `/dashboard/` : état en direct des capteurs
  (allumé/éteint), courant/puissance, graphe de consommation.
- **Historique** — `/historique/` : consommation par période, coût à ce
  jour, répartition par appareil.
- **Alertes** — `/alertes/` : déclenchées par les règles de détection
  (surintensité, disjoncteur, etc.).

Ces pages consomment les mêmes mesures que celles injectées par le
firmware sur `POST /api/sensors/zmct/` — donc si les événements
`ALLUME`/`ETEINT` s'affichent dans le moniteur série avec `Envoi OK`, ils
doivent apparaître dans la minute sur le tableau de bord (rafraîchi
automatiquement).

## 8. Dépannage rapide

| Symptôme | Cause probable | Solution |
| :--- | :--- | :--- |
| Réseau absent du `[SCAN]` | Réseau en 5 GHz, ou hors de portée | Utiliser/forcer la bande 2,4 GHz du routeur |
| `[Serveur] INJOIGNABLE` | IP du PC a changé (DHCP) | `ipconfig`, mettre à jour `serverName`, reflasher |
| `[HTTP] Hors-ligne, mis en tampon` en continu | Django pas démarré, ou pare-feu Windows bloque le port 8003 | Démarrer `lancer_aoceda.bat`, autoriser le port dans le pare-feu |
| Rien dans le tableau de bord malgré `Envoi OK` | `apiKeyDevice` ne correspond à aucun Dispositif, ou capteur non assigné | Vérifier dans Admin Django / espace technicien |
| Compte "email/mot de passe incorrect" | Compte pas encore créé côté client | Faire créer le compte par un technicien/admin (voir §6) |
