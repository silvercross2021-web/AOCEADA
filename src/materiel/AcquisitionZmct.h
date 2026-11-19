#pragma once
/*
  Acquisition du courant par les capteurs ZMCT103C : une fenêtre de mesure d'une seconde
  sur l'ADC, analysée aux fréquences du secteur (50 Hz et harmoniques 150 / 250 Hz).
*/
#include "domaine/Capteur.h"

namespace AcquisitionZmct {

// Prépare les tables cos / sin de la transformée de Fourier
void initialiser();

// Mesure une fenêtre sur le capteur c et met à jour son point milieu (c.offset).
// Prend le verrou radio pendant toute la fenêtre (un envoi en cours se termine d'abord).
Mesure fenetre(EtatCapteur &c);

} // namespace AcquisitionZmct
