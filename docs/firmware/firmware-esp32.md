# Le firmware ESP32 actuel (`src/main.cpp`)

Description du programme **tel qu'il est** (relu dans `src/main.cpp`, 1 082 lignes, le 2026-10-19). Le document
[detection-onoff-zmct103c.md](detection-onoff-zmct103c.md) raconte la méthode d'origine (RMS sur Arduino Uno) : la
détection a changé depuis (voir §3). Pour tester de bout en bout : [guide-test-bout-en-bout.md](guide-test-bout-en-bout.md).

## 1. Matériel et brochage

| Élément | Broche | Rôle |
|---|---|---|
| `Capteur_1` : ZMCT103C sur une **ampoule** | GPIO 34 (ADC) | courant de la lampe |
| `Capteur_2` : ZMCT103C sur une **prise** | GPIO 35 (ADC) | courant d'un appareil branché (chargeur, lampe LED…) |
| Relais 1 (module « S + - », 5 V) | GPIO 26 | coupe le courant de la lampe |
| Relais 2 | GPIO 27 | coupe le courant de la prise |

- Le « + » des relais va sur **VIN (5 V)**, jamais sur 3V3 (en 3,3 V le voyant s'allume mais le relais ne bascule pas).
- Contacts sur **COM + NO** : relais au repos = appareil **coupé**. Hors ordre « couper », le relais est donc actionné en
  permanence. ESP32 éteint = lampe et prise coupées (c'est le câblage qui le veut). Les constantes `RELAIS_ACTIF_NIVEAU_HAUT` et
  `CONTACT_NO` décrivent ce montage.
- Burden 100 Ω, 1 000 spires, référence ADC 3,3 V sur 12 bits : `K = (3,3 / 4096) / 100 × 1000`. Courant = `K × RMS` ;
  puissance affichée = 220 V × courant.
- `platformio.ini` : carte `esp32dev`, framework Arduino, moniteur série à **9 600 bauds**, `upload_port = COM4` (à adapter).

## 2. Configuration à faire avant de flasher (haut de `main.cpp`)

```cpp
const ReseauWifi RESEAUX_WIFI[] = {
    {"nom du réseau 2,4 GHz", "mot de passe", "http://<IP du PC sur ce réseau>:8003/api/sensors/zmct/"},
    // autant de lignes que de réseaux ; mot de passe "A_REMPLIR" = réseau sauté
};
const char *apiKeyDevice = "...";        // clé du Dispositif créé côté Django
const char *MOT_DE_PASSE_OTA = "...";    // mot de passe des mises à jour par Wi-Fi
```

- **Plusieurs réseaux.** L'ESP32 les essaie dans l'ordre et garde le **premier où le serveur répond vraiment** (un `GET` sur
  l'adresse). Chaque réseau a **sa propre adresse de serveur** : l'IP du PC change d'un réseau à l'autre (DHCP). Si aucun serveur
  ne répond, il reste sur le premier réseau joint et met les mesures en tampon.
- Wi-Fi **2,4 GHz seulement**. Au démarrage, l'ESP32 liste les réseaux visibles (`[SCAN]`) et dit si le sien est absent.
- **Ne jamais commiter de vrais mots de passe Wi-Fi** dans ce fichier (le dépôt contient `A_REMPLIR`). Les mots de passe locaux
  de la machine restent non commités.
- `apiKeyDevice` est envoyée dans l'en-tête `Authorization: Device <clé>` ; elle doit correspondre à un `Dispositif` en base
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
   (`relaisRetenus`), pour ne pas apprendre le courant d'un appareil déjà allumé comme du bruit.
3. **Seuils relatifs** : allumé si la moyenne des 3 dernières fenêtres ≥ `max(2,5 × bruit, bruit + 15)` ; éteint si une fenêtre
   (brute ou lissée) < `max(1,6 × bruit, bruit + 7,5)`. **Confirmation** : 2 fenêtres d'affilée avant tout changement d'état
   (anti-rebond). L'allumage utilise la moyenne (un parasite isolé ne fait jamais « allumé »), l'extinction réagit en ~5 s.
4. **Relais ouvert** : l'appareil ne peut rien consommer ; l'état est forcé à « éteint » et le bruit n'est pas appris sur ce signal.

## 4. Envoi au serveur

- **Format** (`POST /api/sensors/zmct/`, contrat figé) : `{"capteur_index":2,"etat":"ON","courant":0.523,"puissance":115.1,"timestamp_unix":...,"coupe":false}`.
  `coupe` = état réel du relais au moment de l'envoi (le serveur ne s'en sert que pour une mesure récente, pas pour une mesure rejouée).
- ⚠️ **Numéros inversés (historique, à ne jamais changer)** : côté serveur, `Capteur_1` (GPIO 34, **lampe**) est le capteur **2**, et `Capteur_2`
  (GPIO 35, **prise**) est le capteur **1** (`indexServeur()`). Donc dans la réponse du serveur, `coupe_2` pilote le relais de la **lampe** (GPIO 26)
  et `coupe_1` celui de la **prise** (GPIO 27). Les changer enverrait les mesures et les ordres de coupure vers l'autre appareil.
- Envoi **à chaque changement d'état** et **toutes les secondes** sinon. La mesure et la radio ne se chevauchent jamais
  (`verrouRadio`) : les envois se font entre deux fenêtres de mesure, dans une tâche réseau séparée alimentée par une file.
- **Heure réelle (NTP)** : sert à garder la vraie date d'une mesure rejouée plus tard (Côte d'Ivoire = UTC+0).
- **Tampon hors ligne** : si le Wi-Fi ou le serveur est indisponible, les mesures vont dans `/buffer.jsonl` (LittleFS, 300 Ko max,
  une mesure par ligne) ; l'offset déjà rejoué est gardé en NVS ; rejouées par lots de 20 dès que le serveur répond, puis le fichier est supprimé.
  ⚠️ **Au démarrage de la carte, un tampon existant est effacé** (`setup()` : « Ancien tampon sature efface ») : une mesure encore en attente
  lors d'un redémarrage ou d'une coupure de courant est donc perdue (malgré le commentaire du code qui parle de survie aux redémarrages).
- **Reconnexion non bloquante** : nouvel essai toutes les 15 s ; après 15 envois d'affilée sans aucune réponse HTTP (`ECHECS_AVANT_AUTRE_RESEAU`), l'ESP32 se déconnecte pour
  réessayer tous les réseaux (utile quand le PC change de réseau).

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
