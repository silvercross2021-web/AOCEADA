#pragma once
/*
  Boucle de mesure (coeur 1) : pour chaque capteur, une fenêtre de mesure, la détection
  allumé / éteint, l'envoi de l'état au serveur ; puis la lecture du DHT11.
*/

namespace BoucleMesure {

// Un tour complet de tous les capteurs (appelé par loop())
void tour();

} // namespace BoucleMesure
