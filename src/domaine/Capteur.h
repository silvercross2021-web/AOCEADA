#pragma once
/*
  Types du domaine : ce qu'on sait d'un capteur de courant et d'une fenêtre de mesure.
  Aucune dépendance à Arduino ni au matériel.
*/
#include "config/Reglages.h"
#include <stdint.h>

// Moyenne glissante des NB_LISSAGE dernières valeurs
struct Lissage {
  float valeurs[Reglages::NB_LISSAGE];
  uint8_t idx;
  uint8_t nb;
};

// Résultat d'une fenêtre de mesure (1 s) d'un capteur
struct Mesure {
  float var;     // variance totale (ancienne méthode, gardée pour comparer)
  float p50;     // puissance à 50 Hz
  float pHarm;   // puissance à 150 + 250 Hz
  float secteur; // p50 + pHarm : courant de l'appareil + bruit résiduel
  int vMin;
  int vMax;
};

// État d'un capteur de courant (un appareil surveillé)
struct EtatCapteur {
  const char *id;
  uint8_t pin;
  float seuilOn;  // écart minimal au-dessus du bruit pour déclarer l'appareil allumé
  float seuilOff; // écart minimal pour rester allumé (< seuilOn : hystérésis)
  const char *labelOn;
  const char *labelOff;
  float offset; // point milieu de l'ADC, suivi à chaque fenêtre
  bool actif;
  uint8_t cptConfirm;
  unsigned long last_send; // instant (millis) du dernier envoi au serveur
  float seuilOnEff;        // seuils réellement appliqués à la dernière fenêtre
  float seuilOffEff;
  float bruit;     // bruit appris (médiane de « secteur » au repos)
  Lissage secteur; // dernières valeurs « secteur »
};

// Relevé d'air du DHT11, tel qu'il est joint à une trame
struct ReleveAir {
  float temperatureC;
  float humiditePct;
  unsigned long instantUnix; // heure réelle (UTC) du relevé
};
