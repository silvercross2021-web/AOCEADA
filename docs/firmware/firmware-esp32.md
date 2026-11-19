# Le firmware ESP32 actuel (`src/`)

Description du programme **tel qu'il est**. Depuis le 19/11/2026 il n'est plus dans un seul fichier : le code est découpé en
couches (`config`, `domaine`, `systeme`, `materiel`, `reseau`, `application`), voir
[architecture-firmware.md](architecture-firmware.md), qui dit aussi où est passé chaque morceau de l'ancien `main.cpp`. Le document
[detection-onoff-zmct103c.md](detection-onoff-zmct103c.md) raconte la méthode d'origine (RMS sur Arduino Uno) : la
détection a changé depuis (voir §3). Pour tester de bout en bout : [guide-test-bout-en-bout.md](guide-test-bout-en-bout.md).

## 1. Matériel et brochage

| Élément | Broche | Rôle |
|---|---|---|
| `Capteur_1` : ZMCT103C sur une **ampoule** | GPIO 34 (ADC) | courant de la lampe |
| `Capteur_2` : ZMCT103C sur une **prise** | GPIO 35 (ADC) | courant d'un appareil branché (chargeur, lampe LED…) |
| Relais 1 (module « S + - », 5 V) | GPIO 26 | coupe le courant de la lampe |
| Relais 2 | GPIO 27 | coupe le courant de la prise |
| Capteur **DHT11** (température et humidité de l'air, module à 3 broches) | GPIO 4 (D4) | air du logement, voir §4 bis |

- DHT11 : la borne de signal est marquée **S** ou **OUT** selon le module (l'ordre des trois bornes varie : lire les inscriptions du
  module, pas leur position). Branchement : **S/OUT → GPIO 4**, **+ → 3V3** (jamais VIN : le signal serait à 5 V), **− → GND**. Le module
  porte déjà sa résistance de rappel : aucune résistance à ajouter. Posé à l'écart des relais (leur chaleur fausse la lecture) et, si un
  climatiseur existe, dans une pièce qu'il ne refroidit pas directement.
- Le « + » des relais va sur **VIN (5 V)**, jamais sur 3V3 (en 3,3 V le voyant s'allume mais le relais ne bascule pas).
- Contacts sur **COM + NO** : relais au repos = appareil **coupé**. Hors ordre « couper », le relais est donc actionné en
  permanence. ESP32 éteint = lampe et prise coupées (c'est le câblage qui le veut). Les constantes `RELAIS_ACTIF_NIVEAU_HAUT` et
  `CONTACT_NO` (`src/config/Reglages.h`) décrivent ce montage.
- Burden 100 Ω, 1 000 spires, référence ADC 3,3 V sur 12 bits : `K = (3,3 / 4096) / 100 × 1000`. Courant = `K × RMS` ;
  puissance affichée = 220 V × courant.
- `platformio.ini` : carte `esp32dev`, framework Arduino, moniteur série à **115 200 bauds**, `upload_port = COM4` (à adapter).

## 2. Configuration à faire avant de flasher (`include/secrets.h`)

Les secrets ne sont plus dans le code. Copier `include/secrets.example.h` en `include/secrets.h` (ignoré par Git) et le remplir :

```cpp
#define AOCEDA_CLE_DISPOSITIF "..."          // clé du Dispositif créé côté Django
#define AOCEDA_MOT_DE_PASSE_OTA "..."        // mot de passe des mises à jour par Wi-Fi
#define AOCEDA_RESEAUX_WIFI \
  {"nom du réseau 2,4 GHz", "mot de passe", "http://<IP du PC sur ce réseau>:8003/api/sensors/zmct/"}, \
  /* autant de lignes que de réseaux ; mot de passe "A_REMPLIR" = réseau sauté */
```

Les réglages qui ne sont pas des secrets (broches, seuils, délais) sont dans `src/config/Reglages.h`.

- **Plusieurs réseaux.** L'ESP32 les essaie dans l'ordre et garde le **premier où le serveur répond vraiment** (un `GET` sur
  l'adresse). Chaque réseau a **sa propre adresse de serveur** : l'IP du PC change d'un réseau à l'autre (DHCP). Si aucun serveur
  ne répond, il reste sur le premier réseau joint et met les mesures en tampon.
- Wi-Fi **2,4 GHz seulement**. Au démarrage, l'ESP32 liste les réseaux visibles (`[SCAN]`) et dit si le sien est absent.
- `include/secrets.h` n'est **jamais commité** (`.gitignore`) : seul le modèle `secrets.example.h` l'est. Sans ce fichier, le
  firmware compile avec les valeurs d'exemple : Wi-Fi inactif, mesures par le câble USB.
- `AOCEDA_CLE_DISPOSITIF` est envoyée dans l'en-tête `Authorization: Device <clé>` ; elle doit correspondre à un `Dispositif` en base
  (les commandes de démonstration `seed_demo` et `creer_client_anzouango` en créent un).

## 3. Détection allumé / éteint (méthode actuelle)

La radio Wi-Fi brouille l'ADC : la variance totale au repos monte de ~350 (Wi-Fi coupé) à ~2 000-5 000 (Wi-Fi + envois). Les
anciens seuils sur la variance donnaient de faux « allumé » (essais du 12/10/2026). La méthode actuelle :

1. **Mesure par fréquences du secteur** : fenêtre de 1 s (50 périodes à 50 Hz). Une DFT calée sur l'horodatage réel de chaque
   échantillon mesure la puissance à **50 Hz** et aux harmoniques **150 + 250 Hz** (par sous-fenêtres de 200 ms, car la fréquence
   du réseau dérive de 49,8 à 50,2 Hz). Le courant d'un appareil est à 50 Hz et ses harmoniques impaires ; le brouillage Wi-Fi non.
   Les harmoniques comptent : une lampe LED ou un chargeur consomment surtout en harmoniques.
2. **Bruit appris** : chaque capteur suit la **médiane** de son bruit au repos (pas multiplicatif de 5 %) ; le bruit dépend de
   l'alimentation (~15-25 sur le port USB d'un PC, ~130-190 sur un powerbank). Au démarrage, il est mesuré **appareils coupés**
   (`Relais::retenus()`), pour ne pas apprendre le courant d'un appareil déjà allumé comme du bruit.
3. **Seuils relatifs** : allumé si la moyenne des 3 dernières fenêtres ≥ `max(2,5 × bruit, bruit + 15)` ; éteint si une fenêtre
   (brute ou lissée) < `max(1,6 × bruit, bruit + 7,5)`. **Confirmation** : 2 fenêtres d'affilée avant tout changement d'état
   (anti-rebond). L'allumage utilise la moyenne (un parasite isolé ne fait jamais « allumé »), l'extinction réagit en ~5 s.
4. **Relais ouvert** : l'appareil ne peut rien consommer ; l'état est forcé à « éteint » et le bruit n'est pas appris sur ce signal.

## 4. Envoi au serveur

- **Format** (`POST /api/sensors/zmct/`, contrat figé) : `{"capteur_index":2,"etat":"ON","courant":0.523,"puissance":115.1,"timestamp_unix":...,"coupe":false}`.
  `coupe` = état réel du relais au moment de l'envoi (le serveur ne s'en sert que pour une mesure récente, pas pour une mesure rejouée).
- **Air ambiant (DHT11)** : voir §4 bis. Les trois champs `temperature_c`, `humidite_pct`, `releve_unix` s'ajoutent à la trame, une seule
  fois par relevé : `{"capteur_index":2,...,"coupe":false,"temperature_c":30.0,"humidite_pct":72.0,"releve_unix":1794995206}`.
- ⚠️ **Numéros inversés (historique, à ne jamais changer)** : côté serveur, `Capteur_1` (GPIO 34, **lampe**) est le capteur **2**, et `Capteur_2`
  (GPIO 35, **prise**) est le capteur **1** (`indexServeur()`). Donc dans la réponse du serveur, `coupe_2` pilote le relais de la **lampe** (GPIO 26)
  et `coupe_1` celui de la **prise** (GPIO 27). Les changer enverrait les mesures et les ordres de coupure vers l'autre appareil.
- Envoi **à chaque changement d'état** et **toutes les secondes** sinon. La mesure et la radio ne se chevauchent jamais
  (`VerrouRadio`) : les envois se font entre deux fenêtres de mesure, dans une tâche réseau séparée alimentée par une file.
- **Heure réelle (NTP)** : sert à garder la vraie date d'une mesure rejouée plus tard (Côte d'Ivoire = UTC+0). Sans Wi-Fi, donc sans NTP, la carte reçoit l'heure du PC par le pont USB (ligne `@HEURE <unix>` envoyée juste avant chaque accusé `@ACK`) ; elle ne la prend que si elle n'a pas déjà d'heure, ce qui permet au relevé DHT11 de partir par le câble.
- **Tampon hors ligne** : si le Wi-Fi ou le serveur est indisponible, les mesures vont dans `/buffer.jsonl` (LittleFS, 300 Ko max,
  une mesure par ligne) ; l'offset déjà rejoué est gardé en NVS ; rejouées par lots de 20 dès que le serveur répond, puis le fichier est supprimé.
  ⚠️ **Au démarrage de la carte, un tampon existant est effacé** (`setup()` : « Ancien tampon sature efface ») : une mesure encore en attente
  lors d'un redémarrage ou d'une coupure de courant est donc perdue (malgré le commentaire du code qui parle de survie aux redémarrages).
- **Reconnexion non bloquante** : nouvel essai toutes les 15 s ; après 15 envois d'affilée sans aucune réponse HTTP (`ECHECS_AVANT_AUTRE_RESEAU`), l'ESP32 se déconnecte pour
  réessayer tous les réseaux (utile quand le PC change de réseau).

## 4 bis. Température et humidité (DHT11)

**Pourquoi** : quand il fait chaud, un logement consomme plus (climatiseur, ventilateur, réfrigérateur). La prévision des factures et de la
fin du crédit s'en sert (`AOCEDA/apps/analytics/temperature_locale.py`, `prevision_ia.py`).

**Côté boîtier** (`Dht11::lire`, fin de la boucle de mesure) :
- un relevé toutes les **30 s** (toutes les 5 s tant que le capteur ne répond pas, pour voir vite l'effet d'un changement de câblage) ;
- un relevé n'est **valide** que dans la plage d'un logement : 5 à 50 °C et 5 à 99 % (un DHT11 en défaut répond souvent « 0 °C, 0 % » avec
  une somme de contrôle valide : ce n'est pas une nuit glaciale, il est écarté) ;
- il est **joint une seule fois** à une trame de mesure (`Dht11::releveAJoindre` / `releveParti`, sous verrou : la boucle de mesure et la tâche réseau
  y touchent), avec l'**heure réelle du relevé** (NTP). Sans heure réelle, il n'est pas envoyé. Il n'est marqué « parti » que si sa trame l'est
  (envoyée, acquittée par l'USB ou mise en tampon) ; une trame « éteint » perdue n'emporte donc pas de relevé ;
- **jamais de valeur inventée** : capteur muet = aucun champ dans la trame.

**Diagnostic** : quand le capteur ne répond pas, la ligne `[DHT11] Lecture impossible` dit d'où vient le défaut, d'après l'état du fil
(rappel interne actif) :
- « **ligne tenue à la masse** » : le fil de signal touche une borne GND, S et − sont inversés, ou le capteur est en court-circuit ;
- « **ligne haute mais aucune réponse** » : le fil est libre ; capteur non alimenté ou absent, **− (GND) mal enfoncé**, ou capteur mort.
Le message est répété quand l'état du fil change (on vient de toucher au câblage), sinon un sur cinq.

**Côté serveur** (modèle `ReleveAmbiant`, `apps/sensors/ambiance.py`) : les relevés sont validés (mêmes bornes), datés à l'instant du relevé,
et jamais comptés deux fois (unique par boîtier et instant : accusé perdu, tampon rejoué). Une valeur aberrante ne fait jamais perdre les mesures
de courant de la même requête. La prévision n'utilise le capteur qu'**après calibration** sur la météo de la ville (7 journées complètes
communes), pour ne jamais mélanger deux échelles de température : voir l'en-tête de `temperature_locale.py`.

## 5. Coupure à distance

La réponse du serveur à chaque envoi porte les ordres : `{"created":1,"coupe_1":false,"coupe_2":true}` (numéros côté serveur : voir l'inversion
plus haut, §4). `true` = relais ouvert, courant coupé (côté serveur : `Capteur.coupureDemandee`, voir `apps/sensors/views.py`). L'ordre est **gardé en NVS** : au retour du
courant, l'ESP32 le réapplique tout de suite, sans attendre le serveur. L'envoi d'un « éteint » est immédiat après une coupure.
Ancien serveur sans ces clés : rien ne change.

## 6. Journal, mises à jour et diagnostic

- **Journal** : câble USB, et copie **UDP** vers le PC du serveur sur le port **5005** (`JOURNAL_WIFI`), pour suivre une carte
  alimentée par un simple chargeur. Les lignes `[DEBUG-SIGNAL]` donnent secteur, lissé, bruit, P50, harmoniques, seuils, courant, état.
- **OTA** : mise à jour par Wi-Fi sans câble, nom d'hôte `aoceda-esp32` :
  `python espota.py -i <IP de l'ESP32> -a <MOT_DE_PASSE_OTA> -f firmware.bin` (`espota.py` est dans le paquet
  `framework-arduinoespressif32` de PlatformIO).

## 7. Ce que le firmware ne fait pas

Il ne calcule aucune facture (tout est côté serveur, voir [tarification](../architecture/tarification-cie.md)), n'a pas de
protocole sécurisé au-delà de la clé de dispositif, et n'a pas de test automatisé (`test/` ne contient que le README PlatformIO).
