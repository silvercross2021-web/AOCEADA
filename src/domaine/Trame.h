#pragma once
/*
  Contrat avec le serveur : la trame JSON d'une mesure (POST /api/sensors/zmct/) et la
  lecture des ordres de coupure dans sa réponse. Logique pure (testable sur PC).
*/
#include "domaine/Capteur.h"
#include <stddef.h>

namespace Trame {

// Écrit la trame dans buf (terminée par '\0') et rend sa longueur.
//   indexServeur   : numéro du capteur côté serveur (1 = lampe, 2 = prise)
//   relaisCoupe    : état réel du relais au moment de l'envoi
//   horodatageUnix : 0 = heure inconnue (le serveur utilise l'heure de réception)
//   releve         : relevé du DHT11 à joindre, ou nullptr
//   releveInclus   : mis à true si le relevé a bien été écrit dans la trame
size_t construireMesure(char *buf, size_t taille, int indexServeur,
                        const char *etat, float courant, float puissance,
                        unsigned long horodatageUnix, bool relaisCoupe,
                        const ReleveAir *releve, bool *releveInclus);

// Cherche « "coupe_N": true|false » dans la réponse du serveur. Rend false si l'ordre est
// absent (ancien serveur : rien ne change).
bool lireOrdreCoupure(const char *reponse, int indexServeur, bool &ordre);

// Un relevé DHT11 est-il plausible pour un logement ? (écarte « 0 C, 0 % »)
bool releveVraisemblable(float temperatureC, float humiditePct);

} // namespace Trame
