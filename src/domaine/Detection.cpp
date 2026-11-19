#include "domaine/Detection.h"
#include <algorithm>
#include <math.h>

using namespace Reglages;

/*
  Pourquoi un bruit APPRIS (mesures du 12/10/2026) : le bruit dépend de l'alimentation de la
  carte. Valeur « secteur » au repos : ~15-25 sur le port USB du PC, ~130-190 sur un
  powerbank (lampe : ~600 / ~550-1 030 ; chargeur de téléphone : ~70 / ~900). Un seuil fixe
  ne convient donc à aucune alimentation : chaque capteur apprend son bruit (médiane suivie
  au repos) et ses seuils en sont des multiples :
    allumé si moyenne des NB_LISSAGE dernières fenêtres >= max(FACTEUR_ON x bruit,
    bruit + seuilOn) ; éteint si < max(FACTEUR_OFF x bruit, bruit + seuilOff).
  Chaque capteur a SON bruit. Depuis les relais, le bruit de départ se mesure appareils
  COUPES (voir Relais::retenir) : ce qui est mesuré n'est que du bruit.
*/

namespace Detection {

float lisser(Lissage &l, float valeur) {
  l.valeurs[l.idx] = valeur;
  l.idx = (l.idx + 1) % NB_LISSAGE;
  if (l.nb < NB_LISSAGE)
    l.nb++;
  float somme = 0.0f;
  for (int i = 0; i < l.nb; i++)
    somme += l.valeurs[i];
  return somme / l.nb;
}

void borneBruit(EtatCapteur &c) {
  c.bruit = fminf(BRUIT_MAX, fmaxf(BRUIT_MIN, c.bruit));
}

void calculerSeuils(EtatCapteur &c) {
  c.seuilOnEff = fmaxf(FACTEUR_ON * c.bruit, c.bruit + c.seuilOn);
  c.seuilOffEff = fmaxf(FACTEUR_OFF * c.bruit, c.bruit + c.seuilOff);
}

float bruitDeDepart(float *valeurs) {
  std::sort(valeurs, valeurs + NB_FENETRES_BRUIT_DEPART);
  return 0.5f * (valeurs[3] + valeurs[4]);
}

void evaluer(EtatCapteur &c, float secteurBrut, float secteurLisse,
             bool coupeParRelais) {
  // Relais ouvert : l'appareil ne peut consommer AUCUN courant (le capteur est sur le même
  // fil). Ce qui est mesuré n'est alors que du bruit : éteint d'office, et pas
  // d'apprentissage du bruit sur ce signal (13/10/2026 : capteur 2 mal branché, 200 à 400
  // mesures relais ouvert, il restait « allumé »).
  if (coupeParRelais) {
    c.actif = false;
    c.cptConfirm = 0;
  } else if (!c.actif) {
    if (secteurLisse >= c.seuilOnEff) {
      c.cptConfirm++;
      if (c.cptConfirm >= CONFIRMATIONS) {
        c.actif = true;
        c.cptConfirm = 0;
      }
    } else {
      c.cptConfirm = 0;
      // Suivi de la médiane du bruit, par pas multiplicatifs : seulement capteur éteint et
      // fenêtre sous le seuil d'allumage, jamais sur un appareil détecté.
      if (secteurBrut < c.seuilOnEff) {
        c.bruit *= (secteurBrut > c.bruit) ? (1.0f + PAS_SUIVI_BRUIT)
                                           : (1.0f - PAS_SUIVI_BRUIT);
        borneBruit(c);
      }
    }
  } else {
    // Le retour à « éteint » ne dépend que du signal secteur comparé au bruit appris,
    // jamais d'une référence figée : un appareil coupé y retombe toujours. La fenêtre brute
    // compte aussi (14/10/2026) : attendre que la moyenne des 3 dernières fenêtres tombe
    // ajoutait ~5 s ; deux fenêtres d'affilée sous le seuil suffisent (~5 s). L'allumage
    // reste sur la moyenne : un pic de parasite isolé ne fait jamais « allumé ».
    if (fminf(secteurLisse, secteurBrut) < c.seuilOffEff) {
      c.cptConfirm++;
      if (c.cptConfirm >= CONFIRMATIONS) {
        c.actif = false;
        c.cptConfirm = 0;
      }
    } else {
      c.cptConfirm = 0;
    }
  }
}

} // namespace Detection
