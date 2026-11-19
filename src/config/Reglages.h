#pragma once
/*
  Réglages du firmware : broches, constantes électriques, rythmes, tailles.
  Rien de secret ici (Wi-Fi, clé du boîtier : include/secrets.h). Aucune dépendance à
  Arduino : le domaine (src/domaine) lit aussi ce fichier.
  Les seuils et facteurs de détection ont été MESURES sur la carte (voir
  docs/firmware/detection-onoff-zmct103c.md) : ne pas les « arrondir ».
*/
#include <stddef.h>
#include <stdint.h>

namespace Reglages {

// ============================== Matériel ==============================
constexpr int NB_CAPTEURS = 2;
constexpr uint8_t PIN_CAPTEUR_1 = 34; // lampe  (ZMCT103C, entrée ADC seule)
constexpr uint8_t PIN_CAPTEUR_2 = 35; // prise  (ZMCT103C, entrée ADC seule)
// Un module relais 5 V « S + - » par appareil, dans l'ordre des capteurs.
constexpr uint8_t PINS_RELAIS[NB_CAPTEURS] = {26, 27};
// Polarité de pilotage : true = le relais s'enclenche au niveau HAUT (module à
// transistor direct), false = au niveau BAS (modules à optocoupleur, les plus courants).
constexpr bool RELAIS_ACTIF_NIVEAU_HAUT[NB_CAPTEURS] = {true, true};
// Contacts câblés sur COM + NO (« ouvert par défaut ») : true. En COM + NC : false.
constexpr bool CONTACT_NO[NB_CAPTEURS] = {true, true};
// DHT11 : S -> GPIO 4, + -> 3V3 (jamais VIN : signal à 5 V), - -> GND
constexpr uint8_t PIN_DHT = 4;

// ============================== Électrique ============================
constexpr float V_REF = 3.3f;
constexpr float R_BURDEN = 100.0f;
constexpr float N_TURNS = 1000.0f;
constexpr float K = (V_REF / 4096.0f) / R_BURDEN * N_TURNS; // A par unité RMS « ADC »

// Tension secteur ESTIMEE (pas de capteur de tension) : 220 V à 230 V, centrée autour
// des ~224,5 V mesurés au multimètre.
constexpr float TENSION_MIN_V = 220.0f;
constexpr float TENSION_MAX_V = 230.0f;
constexpr float TENSION_NOMINALE_V = 224.5f;

// ============================== Mesure ================================
constexpr unsigned long FENETRE_MS = 1000UL; // 1 s = 50 périodes du secteur par fenêtre
constexpr uint8_t CONFIRMATIONS = 2;         // fenêtres d'affilée avant un changement d'état
constexpr unsigned long INTERVALLE_ENVOI_MS = 1000; // envoi régulier toutes les secondes

// Détection par les fréquences du secteur (50 Hz + harmoniques 150 / 250 Hz). Voir
// src/materiel/AcquisitionZmct.cpp pour la méthode et les mesures.
constexpr uint32_t PERIODE_SECTEUR_US = 20000UL; // 50 Hz
constexpr uint32_t PAS_TABLE_US = 100UL;         // table cos/sin : 200 points par période
constexpr int TAILLE_TABLE = PERIODE_SECTEUR_US / PAS_TABLE_US;
constexpr uint32_t SOUS_FENETRE_US = 200000UL;   // harmoniques : sous-fenêtres de 10 périodes
constexpr int NB_RAIES_SOUS = 2;
constexpr uint32_t MULT_25HZ[NB_RAIES_SOUS] = {6, 10}; // 150 Hz et 250 Hz

// Bruit appris par chaque capteur et seuils qui en découlent (voir domaine/Detection.cpp)
constexpr int NB_LISSAGE = 3;
constexpr float FACTEUR_ON = 2.5f;
constexpr float FACTEUR_OFF = 1.6f;
constexpr float PAS_SUIVI_BRUIT = 0.05f; // suivi de la médiane : pas multiplicatif de 5 %
constexpr float BRUIT_MIN = 5.0f;
constexpr float BRUIT_MAX = 50.0f; // empêche d'apprendre un appareil actif comme bruit
constexpr float SEUIL_ON_DEFAUT = 15.0f;  // écart minimal au-dessus du bruit pour « allumé »
constexpr float SEUIL_OFF_DEFAUT = 7.5f;  // écart pour rester allumé (< ON : hystérésis)
constexpr int NB_FENETRES_BRUIT_DEPART = 8;

// ============================== Radio et tâches =======================
// Mesure et radio ne se chevauchent jamais : les envois Wi-Fi (HTTP, journal) se font
// entre deux fenêtres de mesure, jamais pendant (voir systeme/VerrouRadio).
constexpr unsigned long PAUSE_RADIO_MS = 30;          // laisse la tâche réseau prendre la radio
constexpr unsigned long ATTENTE_RADIO_MAX_MS = 4000;  // au-delà, on mesure quand même
constexpr unsigned long PAUSE_RADIO_MAX_MS = 1500;    // limite du vidage de la file entre 2 fenêtres
constexpr int TAILLE_FILE_ENVOI = 20;
constexpr uint32_t PILE_TACHE_RESEAU = 8192;

// ============================== Réseau ================================
constexpr bool JOURNAL_WIFI = true;  // copie des messages vers le PC du serveur, en UDP
constexpr uint16_t PORT_JOURNAL = 5005;
constexpr unsigned long INTERVALLE_RECONNEXION_MS = 15000;
constexpr int ECHECS_AVANT_AUTRE_RESEAU = 15;
constexpr unsigned long TIMEOUT_HTTP_MS = 3000;

// ============================== Tampon hors ligne =====================
constexpr size_t MAX_BUFFER_BYTES = 300000; // ~300 Ko = plusieurs heures de coupure
constexpr int MAX_REJEU_PAR_TOUR = 3;       // borne le temps passé à rejouer par cycle

// ============================== Canal USB =============================
constexpr unsigned long USB_ATTENTE_ACK_MS = 1500;
constexpr unsigned long USB_PAUSE_SANS_PONT_MS = 10000;

// ============================== DHT11 =================================
constexpr unsigned long DHT_INTERVALLE_MS = 30000;   // une lecture toutes les 30 s
constexpr unsigned long DHT_INTERVALLE_PANNE_MS = 5000; // en panne : le DHT11 tolère 1 lecture/s
// Plage plausible d'un logement. Un DHT11 en défaut répond souvent « 0 C, 0 % » avec une
// somme de contrôle valide : ce n'est pas une nuit glaciale, on l'écarte (le serveur
// applique les mêmes bornes, AOCEDA/apps/sensors/ambiance.py).
constexpr float DHT_T_MIN = 5.0f, DHT_T_MAX = 50.0f;
constexpr float DHT_H_MIN = 5.0f, DHT_H_MAX = 99.0f;

} // namespace Reglages
