# Guide de test de bout en bout : de l'ESP32 au tableau de bord

Compiler et flasher le firmware, vérifier que les capteurs sont lus, démarrer le serveur, se connecter et voir les données.
Pour comprendre ce que fait le programme : [firmware-esp32.md](firmware-esp32.md).

## 1. Prérequis

- **VS Code** + l'extension **PlatformIO IDE** (ce dépôt est déjà un projet PlatformIO : `platformio.ini` à la racine).
- Un **ESP32** relié en USB, deux capteurs **ZMCT103C** sur les broches `34` et `35`, et si vous testez la coupure à distance, deux
  modules relais sur `26` et `27` (câblage détaillé dans [firmware-esp32.md](firmware-esp32.md) §1).
- Un réseau **Wi-Fi 2,4 GHz** (l'ESP32 ne voit pas le 5 GHz) sur lequel le PC qui fait tourner Django est aussi connecté.
- Le serveur installé une fois : [AOCEDA/INSTALLATION.md](../../AOCEDA/INSTALLATION.md).

Vous travaillez avec un agent IA ? Ses consignes sont dans [AGENTS.md](../../AGENTS.md).

## 2. Configurer le firmware avant de flasher

Tout est en haut de [src/main.cpp](../../src/main.cpp) : la liste `RESEAUX_WIFI` (réseau, mot de passe, **adresse du serveur sur ce
réseau**), `apiKeyDevice` et `MOT_DE_PASSE_OTA`. Le détail est dans [firmware-esp32.md](firmware-esp32.md) §2.

- L'IP du PC **change à chaque changement de réseau** (DHCP) : `ipconfig` → adaptateur Wi-Fi → « Adresse IPv4 », puis mettre
  `http://<cette IP>:8003/api/sensors/zmct/` sur la ligne du réseau concerné.
- `apiKeyDevice` doit correspondre à un **Dispositif** en base, assigné à un client, avec un capteur par `capteur_index` (1 ou 2).
- **Ne commitez jamais** ce fichier avec de vrais mots de passe Wi-Fi.
- Dans [platformio.ini](../../platformio.ini), vérifiez `upload_port` (actuellement `COM4`).

## 3. Compiler et flasher

| Icône PlatformIO | Action | Équivalent CLI |
|---|---|---|
| ✔️ | Compiler | `pio run` |
| → | Flasher | `pio run -t upload` |
| 🔌 | Moniteur série (9 600 bauds) | `pio device monitor` |

Tout d'un coup : `pio run -t upload -t monitor`. Ensuite, les mises à jour peuvent se faire **par Wi-Fi** (OTA, voir
[firmware-esp32.md](firmware-esp32.md) §6).

## 4. Vérifier au démarrage (moniteur série)

Dans l'ordre :
1. `=== ZMCT103C - AOCEDA IOT (Wi-Fi) ===`, puis la liste des réseaux configurés et leur serveur.
2. `[SCAN]` : réseaux 2,4 GHz visibles. Si le vôtre manque : il émet en 5 GHz ou est hors de portée.
3. `[RELAIS] … ordre enregistré = …` : l'ordre de coupure gardé en mémoire est réappliqué.
4. `[WiFi] Essai de "…"` puis `[WiFi] Connecte a "…" ! IP de l'ESP32 = …`.
5. `[Serveur] Joignable à …` (code HTTP). `INJOIGNABLE` = mauvaise IP ou serveur arrêté : corriger l'adresse de ce réseau et reflasher.
6. `[OTA] Mise a jour par Wi-Fi possible a l'adresse …` : flashage sans câble disponible.
7. Mesure du bruit de fond (appareils **coupés**), puis les capteurs sont prêts.

Ensuite, branchez/débranchez un appareil sur chaque capteur :

```
[Capteur_1] ETAT : LAMPE ALLUMEE (secteur lisse=…, bruit=…)
[Capteur_2] ETAT : PRISE LIBRE (secteur lisse=…, bruit=…)
[DEBUG-SIGNAL] Capteur_1 | Secteur: … | Bruit: … | Seuils: …/… | I: 0.523 A | Etat: ON
```

Si les envois échouent, le message `[HTTP] [Capteur_x] ECHEC D'ENVOI (Hors-ligne), TRAME MISE EN TAMPON` apparaît : le Wi-Fi est bon mais le
serveur n'est pas joignable (arrêté, mauvaise IP, pare-feu). Les mesures sont gardées puis rejouées (`[TAMPON] PURGE PARTIELLE : N mesure(s) rejouee(s)`,
puis `PURGE TERMINEE`). Attention : un redémarrage de la carte **efface** le tampon (« Ancien tampon sature efface »). Le firmware écrit ses messages sans accent.

Tester la **coupure à distance** : sur la page du client, couper un appareil (carte Oui / Non) ; le journal affiche
`[RELAIS] Capteur_x : COUPE à distance`, puis `courant RETABLI` au rétablissement.

## 5. Démarrer le serveur

```
AOCEDA\lancer_aoceda.bat
```

Il lance `manage.py runserver 0.0.0.0:8003` avec le Python du projet (`.venv_local`) : Daphne, pour les pages, l'API et le WebSocket
de l'appel Live. Le `0.0.0.0` est indispensable : il permet à l'ESP32 et à un téléphone du même réseau d'atteindre le serveur.
Pour suivre le journal UDP de l'ESP32, écouter le port UDP **5005** sur le PC.

## 6. Se connecter / créer un compte

Pas d'inscription publique : un compte client est créé par un **technicien** (« Créer un client ») ou par un **administrateur**
(`/admin/`). Pour essayer sans matériel : `manage.py setup_demo` (comptes de démonstration, mot de passe `Password123!`, mesures simulées).

- Espace client / technicien : `http://<IP_DU_PC>:8003/auth/`
- Administration : `http://<IP_DU_PC>:8003/admin/`

## 7. Voir les données

Une fois connecté : **Tableau de bord** `/dashboard/` (état en direct, courant, puissance, graphe), **Historique** `/historique/`,
**Alertes** `/alertes/`, **Facturation** `/previsions/`. Ces pages lisent les mesures envoyées sur `POST /api/sensors/zmct/` : un
« ALLUMÉ » dans le moniteur avec envoi réussi doit apparaître dans la minute (rafraîchissement automatique).

## 8. Dépannage rapide

| Symptôme | Cause probable | Solution |
|---|---|---|
| Réseau absent du `[SCAN]` | réseau en 5 GHz ou hors de portée | utiliser la bande 2,4 GHz |
| `[Serveur] INJOIGNABLE` | IP du PC changée (DHCP) | `ipconfig`, corriger l'adresse **de ce réseau** dans `RESEAUX_WIFI`, reflasher |
| `ECHEC D'ENVOI … MIS EN TAMPON` en continu | Django arrêté, ou pare-feu Windows bloque le port 8003 | lancer `lancer_aoceda.bat`, autoriser le port |
| Rien dans le tableau de bord malgré l'envoi | `apiKeyDevice` sans Dispositif, ou capteur non assigné | vérifier dans l'admin ou l'espace technicien |
| Faux « allumé » ou « éteint » | bruit mal appris (appareil allumé au démarrage), alimentation bruyante | redémarrer appareils **coupés** ; voir [firmware-esp32.md](firmware-esp32.md) §3 |
| Compte « email/mot de passe incorrect » | compte pas encore créé | le faire créer par un technicien ou l'administrateur |
