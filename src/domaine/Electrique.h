#pragma once
/*
  Grandeurs électriques déduites de la mesure. Logique pure (testable sur PC).
  ATTENTION : la tension du secteur n'est PAS mesurée (pas de capteur de tension) : c'est
  une ESTIMATION comprise entre 220 V et 230 V (valeurs relevées au multimètre : ~224 V).
*/

namespace Electrique {

// Tension secteur estimée à l'instant tSecondes : onde lente (période ~30 s) + petite
// variation aléatoire fournie par l'appelant (microVariationV, de -0,6 à +0,6 V)
float tensionSecteurV(float tSecondes, float microVariationV);

// Courant (A) : racine de la puissance « secteur » nette du bruit appris, fois K
float courantA(float secteur, float bruit);

// Puissance apparente (W) = tension estimée x courant
float puissanceW(float tensionV, float courantA);

} // namespace Electrique
