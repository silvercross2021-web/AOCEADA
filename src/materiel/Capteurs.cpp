#include "materiel/Capteurs.h"
#include <string.h>

using namespace Reglages;

namespace Capteurs {

EtatCapteur etat[NB] = {
    // id, broche, seuilOn, seuilOff, libellé allumé, libellé éteint, milieu ADC,
    // actif, confirmations, dernier envoi, seuils effectifs (calculés), bruit de départ
    {"Capteur_1", PIN_CAPTEUR_1, SEUIL_ON_DEFAUT, SEUIL_OFF_DEFAUT,
     "LAMPE ALLUMEE", "LAMPE ETEINTE", 2048.0f, false, 0, 0UL, 0.0f, 0.0f,
     BRUIT_MIN},
    {"Capteur_2", PIN_CAPTEUR_2, SEUIL_ON_DEFAUT, SEUIL_OFF_DEFAUT,
     "PRISE BRANCHEE", "PRISE LIBRE", 2048.0f, false, 0, 0UL, 0.0f, 0.0f,
     BRUIT_MIN},
};

int indexServeur(const char *capteurId) {
  if (strcmp(capteurId, "Capteur_1") == 0)
    return 1;
  if (strcmp(capteurId, "Capteur_2") == 0)
    return 2;
  return 1;
}

int indexLocal(const char *capteurId) {
  for (int i = 0; i < NB; i++)
    if (strcmp(etat[i].id, capteurId) == 0)
      return i;
  return -1;
}

} // namespace Capteurs
