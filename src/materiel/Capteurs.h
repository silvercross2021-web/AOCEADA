#pragma once
/*
  Les capteurs de courant du boîtier et leur numérotation.
    Capteur_1 (GPIO 34, relais GPIO 26) = LAMPE  -> index 1 côté serveur (« coupe_1 »)
    Capteur_2 (GPIO 35, relais GPIO 27) = PRISE  -> index 2 côté serveur (« coupe_2 »)
  La prise accepte n'importe quel appareil (chargeur de téléphone : ~+50 à +2 000 selon sa
  charge ; lampe LED : ~+600 ; chargeur de PC : ~+10 000) : mêmes seuils.
  Cette correspondance directe aligne le matériel avec l'espace client AOCEDA.
*/
#include "domaine/Capteur.h"

namespace Capteurs {

constexpr int NB = Reglages::NB_CAPTEURS;

// Etat de chaque capteur, dans l'ordre des relais
extern EtatCapteur etat[NB];

// Numéro du capteur côté serveur (Capteur.indexDispositif) ; 1 si l'identifiant est inconnu
int indexServeur(const char *capteurId);

// Position du capteur dans etat[] (et donc de son relais), -1 si inconnu
int indexLocal(const char *capteurId);

} // namespace Capteurs
