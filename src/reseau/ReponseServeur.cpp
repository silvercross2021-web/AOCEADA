#include "reseau/ReponseServeur.h"

namespace ReponseServeur {

namespace {
Ecouteur ecouteurCourant = nullptr;
}

void definirEcouteur(Ecouteur ecouteur) { ecouteurCourant = ecouteur; }

void recue(const String &reponse) {
  if (ecouteurCourant)
    ecouteurCourant(reponse);
}

} // namespace ReponseServeur
