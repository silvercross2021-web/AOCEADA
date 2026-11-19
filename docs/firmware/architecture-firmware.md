# Architecture du firmware ESP32

Le firmware était un seul fichier de 1 363 lignes (`src/main.cpp`) : une soixantaine de variables globales, la
détection, le Wi-Fi, le tampon et les relais mélangés. Depuis le 19/11/2026 il est découpé en **couches**. Le
comportement est le même (mêmes seuils, mêmes messages, même trame JSON) ; seule l'organisation a changé.
Ce qu'il fait, brochage compris : [firmware-esp32.md](firmware-esp32.md).

## 1. Les couches

```
include/secrets.h            Wi-Fi, clé du boîtier, mot de passe OTA (non versionné)
src/
├── main.cpp                 setup() et loop() : deux lignes
├── config/                  réglages : broches, seuils, rythmes ; accès aux secrets
├── domaine/                 logique PURE (aucun Arduino, testable sur PC)
├── systeme/                 services de la carte : journal, heure, mémoire, verrou de la radio
├── materiel/                capteurs ZMCT103C, relais, DHT11
├── reseau/                  Wi-Fi, envoi HTTP, canal USB, tampon hors ligne, OTA
└── application/             démarrage, boucle de mesure, tâches réseau : assemble le tout
test/test_domaine/           tests du domaine, sur PC
test/test_relais.cpp         banc d'essai des relais, sur la carte
```

**Règle de dépendance : une couche ne connaît que celles du dessous.** `application` utilise tout ; `reseau` et
`materiel` utilisent `systeme` et `domaine` ; `domaine` n'utilise que `config/Reglages.h`. Le domaine n'inclut jamais
`Arduino.h` : c'est ce qui permet de le tester sur le PC.

Un seul cas où la couche réseau doit « parler » aux relais : la réponse du serveur porte les ordres de coupure. Elle ne
les connaît pas : `reseau/ReponseServeur` expose un point de branchement, et `application/Demarrage.cpp` y branche
`Relais::appliquerReponseServeur`. Le même chemin sert au Wi-Fi et au câble USB.

## 2. Les modules

| Couche | Module | Rôle |
|---|---|---|
| config | `Reglages.h` | toutes les constantes (broches, électrique, fenêtres, seuils, délais, tailles) |
| config | `Identifiants.h` | lit `include/secrets.h` (ou le modèle `secrets.example.h` s'il manque) |
| domaine | `Capteur.h` | types : `EtatCapteur`, `Mesure`, `Lissage`, `ReleveAir` |
| domaine | `Detection` | lissage, bruit appris, seuils, **machine d'états allumé / éteint** (anti-rebond) |
| domaine | `Electrique` | tension estimée (220-230 V), courant et puissance déduits de la mesure |
| domaine | `Trame` | trame JSON d'une mesure, lecture des ordres de coupure, validité d'un relevé DHT11 |
| systeme | `Journal` | message sur le câble USB + copie UDP vers le PC |
| systeme | `Horloge` | heure UNIX réelle : NTP, ou heure du PC par le pont USB |
| systeme | `Stockage` | LittleFS et mémoire NVS (`Preferences`) |
| systeme | `VerrouRadio` | la mesure et la radio ne se chevauchent jamais (la radio brouille l'ADC) |
| materiel | `Capteurs` | table des deux capteurs ; numérotation locale / serveur |
| materiel | `AcquisitionZmct` | une fenêtre d'une seconde sur l'ADC, analysée à 50 / 150 / 250 Hz |
| materiel | `Relais` | coupure à distance, ordre gardé en NVS, retenue pendant la mesure du bruit |
| materiel | `Dht11` | température et humidité de l'air, relevé joint à une trame |
| reseau | `Reseau` | Wi-Fi multi-réseaux, reconnexion de fond, diagnostic |
| reseau | `ClientHttp` | `POST /api/sensors/zmct/`, comptage des envois sans réponse |
| reseau | `CanalUsb` | secours par le câble : `@USB`, `@HEURE`, `@ACK` |
| reseau | `Tampon` | mesures « allumé » gardées hors ligne (LittleFS + NVS), rejouées plus tard |
| reseau | `Ota` | mise à jour du programme par Wi-Fi |
| reseau | `ReponseServeur` | point de branchement de la réponse du serveur |
| application | `Demarrage` | démarrage en étapes (services, matériel, réseau, tâches, bruit de départ) |
| application | `BoucleMesure` | un tour : fenêtre, détection, événements, envoi, DHT11 |
| application | `FileEnvoi` | file entre la boucle de mesure et la tâche réseau |
| application | `TacheReseau` | tâche d'envoi (Wi-Fi, USB, tampon) et tâche de reconnexion Wi-Fi |

## 3. Le trajet d'une mesure

```
 coeur 1 (loop)                                   coeur 0 (tâches réseau)
 ──────────────                                   ───────────────────────
 AcquisitionZmct::fenetre   (1 s, radio verrouillée)
   → Detection::evaluer     (allumé / éteint)
   → FileEnvoi::deposer ───────────────────────►  tacheEnvoi
                                                   ├─ Wi-Fi OK  → ClientHttp::envoyer ─► Django
                                                   ├─ sinon     → CanalUsb::envoyer ──► pont PC ─► Django
                                                   └─ sinon     → Tampon::ajouter (mesures « allumé »)
 Dht11::lire (30 s) ─ relevé joint à UNE trame ──►  (puis marqué « parti »)
                                                  tacheWifi : reconnexion + NTP, en fond
```

Qui possède quel état partagé (jamais accédé directement par un autre module) :

| État | Propriétaire | Accès |
|---|---|---|
| ordres de coupure des relais | `Relais` | `estCoupe`, `appliquerReponseServeur` |
| dernier relevé DHT11 | `Dht11` | `releveAJoindre` / `releveParti`, sous verrou |
| réseau et serveur en cours | `Reseau` | `serveur()`, `connecte()` |
| compteur d'envois sans réponse | `ClientHttp` | `echecsSansReponse()` |
| contenu du tampon | `Tampon` | `ajouter`, `rejouer`, `enAttente` |
| file d'envoi | `FileEnvoi` | `deposer`, `recevoir` |

## 4. Secrets

Les mots de passe Wi-Fi, la clé du boîtier et le mot de passe OTA ne sont **plus dans le code** : ils sont dans
`include/secrets.h`, ignoré par Git. Pour une copie neuve : copier `include/secrets.example.h` en `include/secrets.h` et le
remplir. Sans ce fichier le firmware compile quand même (modèle d'exemple) : le Wi-Fi reste inactif et les mesures partent
par le câble USB. Le pont USB (`AOCEDA/outils/pont_usb_esp32.py`) lit la clé du boîtier dans ce même fichier.

## 5. Compiler, téléverser, tester

| Action | Commande |
|---|---|
| compiler | `pio run` |
| téléverser | `pio run -t upload` (le port USB doit être libre : fermer le pont, voir ci-dessous) |
| tester le domaine sur PC | `pio test -e native` (20 tests ; installe seul le compilateur MinGW sous Windows) |
| banc d'essai des relais | `pio run -e test_relais -t upload` |

Au quotidien, `AOCEDA\lancer_tout.bat` démarre Django et le pont USB (qui sert de moniteur série) : voir
[AOCEDA/outils/README.md](../../AOCEDA/outils/README.md). Un seul programme peut utiliser le port USB : pour téléverser,
fermer d'abord le pont (`lancer_tout.bat arreter`, ou fermer sa fenêtre).

## 6. Ajouter ou changer quelque chose

| Je veux… | Je touche… |
|---|---|
| changer un seuil, un délai, une broche | `config/Reglages.h` (les seuils de détection sont **mesurés** : voir [detection-onoff-zmct103c.md](detection-onoff-zmct103c.md)) |
| changer la règle allumé / éteint | `domaine/Detection.cpp`, puis `pio test -e native` |
| changer le format de la trame | `domaine/Trame.cpp` **et** le serveur (contrat `POST /api/sensors/zmct/`), puis les tests |
| ajouter un réseau Wi-Fi | `include/secrets.h` (`AOCEDA_RESEAUX_WIFI`) |
| ajouter un capteur de courant | `config/Reglages.h` (`NB_CAPTEURS`, broches), `materiel/Capteurs.cpp` (table), `materiel/Relais` (un relais par capteur : `static_assert`) |
| ajouter un capteur d'ambiance | un module dans `materiel/` sur le modèle de `Dht11`, appelé par `BoucleMesure::tour` |
| changer un message du journal | attention : le pont USB filtre les messages par `RE_UTILE` (`pont_usb_esp32.py`) |

Règles à garder : pas de `Arduino.h` dans `domaine/` ; pas d'état global partagé sans propriétaire ; les messages sont écrits
sans accent (le port série ne les affiche pas bien) ; **rien de secret dans le code**.

## 7. Où est passé le code de l'ancien `main.cpp`

| Ancien (`main.cpp`) | Nouveau |
|---|---|
| `setup()` / `loop()` | `Demarrage::executer()` / `BoucleMesure::tour()` |
| `traiterCapteur` | `BoucleMesure.cpp` + `Detection::evaluer` |
| `acquerir`, `initialiserTables` | `AcquisitionZmct::fenetre`, `initialiser` |
| `obtenirTensionSecteur` | `Electrique::tensionSecteurV` |
| `ajouterLissage`, `calculerSeuils`, `plancherBruit` | `Detection::lisser`, `calculerSeuils`, `borneBruit` |
| `construireJsonMesure` | `Trame::construireMesure` + `construireTrame` (`TacheReseau.cpp`) |
| `lireOrdresRelais`, `appliquerRelais` | `Relais::appliquerReponseServeur`, `Relais::appliquer` |
| `envoyerJson` | `ClientHttp::envoyer` |
| `envoyerParUsb` | `CanalUsb::envoyer` |
| `bufferiser`, `rejouerTampon` | `Tampon::ajouter`, `Tampon::rejouer` |
| `connecterReseaux`, `assurerWifi`, `verifierJoignabiliteServeur` | `Reseau::connecter`, `reconnecterSiBesoin` (la vérification est privée) |
| `synchroniserHeure`, `heureActuelleUnix` | `Horloge::synchroniser`, `heureUnix` |
| `journal`, `majIpJournal` | `Journal::ecrire`, `definirDestinataire` |
| `demarrerOta` | `Ota::suivre` |
| `lireDht11`, `releveAJoindre`, `releveParti` | `Dht11::lire`, `releveAJoindre`, `releveParti` |
| `httpTask`, `wifiTask`, `envoyerVersDjango` | `TacheReseau.cpp`, `FileEnvoi::deposer` |
| `RESEAUX_WIFI`, `apiKeyDevice`, `MOT_DE_PASSE_OTA` | `include/secrets.h` |

Supprimé parce que **jamais lu** : `usbPontActif`, les compteurs `nb_connexions` / `nb_deconnexions` / `t_debut`, les
constantes `SEUIL_ECRET_HAUT` / `SEUIL_ECRET_BAS` / `AMP_ECRET_BAS`, l'include `WiFiClientSecure.h`.

## 8. Limites connues

- La **tension du secteur n'est pas mesurée** : `Electrique::tensionSecteurV` l'estime entre 220 et 230 V. La puissance affichée
  en dépend.
- Sans Wi-Fi, le démarrage attend ~50 s que les réseaux soient essayés (deux tours) avant de mesurer le bruit de départ.
- La file d'envoi (20 mesures) perd la mesure la plus récente si elle est pleine, plutôt que de ralentir la mesure.
- Le tampon hors ligne est effacé à chaque redémarrage de la carte (`Tampon::purgerAuDemarrage`).
- Les modules `materiel/` et `reseau/` ne sont testés que sur la carte (essai de bout en bout) ; seul le domaine a des tests sur PC.
