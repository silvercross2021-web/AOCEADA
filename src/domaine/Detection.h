#pragma once
/*
  Détection allumé / éteint d'un appareil à partir des fenêtres de mesure : lissage,
  bruit appris, seuils, machine d'états avec anti-rebond. Logique pure (testable sur PC).
*/
#include "domaine/Capteur.h"

namespace Detection {

// Ajoute une valeur et rend la moyenne des NB_LISSAGE dernières
float lisser(Lissage &l, float valeur);

// Borne le bruit entre BRUIT_MIN et BRUIT_MAX (un bruit nul rendrait le moindre
// parasite « allumé », un bruit trop haut masquerait un appareil déjà branché)
void borneBruit(EtatCapteur &c);

// Seuils réellement appliqués, multiples du bruit appris
void calculerSeuils(EtatCapteur &c);

// Bruit de départ : médiane de NB_FENETRES_BRUIT_DEPART fenêtres (le tableau est trié)
float bruitDeDepart(float *valeurs);

// Une fenêtre de plus : met à jour c.actif, c.cptConfirm et le bruit suivi.
//   secteurBrut  : valeur « secteur » de la fenêtre ; secteurLisse : sa moyenne glissante
//   coupeParRelais : le relais est ouvert, l'appareil ne peut consommer aucun courant
void evaluer(EtatCapteur &c, float secteurBrut, float secteurLisse,
             bool coupeParRelais);

} // namespace Detection
