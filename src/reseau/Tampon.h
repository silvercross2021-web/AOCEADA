#pragma once
/*
  Tampon hors ligne persistant : il survit aux coupures Wi-Fi / serveur ET aux redémarrages,
  contrairement à une simple file en RAM. Un fichier LittleFS en JSON Lines (une mesure par
  ligne, ajoutée en fin de fichier) et un OFFSET d'octets déjà rejoués gardé en NVS. Rejouer =
  relire depuis l'offset, jamais réécrire le fichier ligne par ligne (coûteux sur flash) ;
  une fois entièrement rejoué, le fichier est supprimé et l'offset remis à zéro.
  Seules les mesures « allumé » horodatées sont tamponnées (voir application/TacheReseau.cpp) :
  les trames « éteint » ne saturent jamais la mémoire.
*/
#include <Arduino.h>

namespace Tampon {

// Efface un ancien tampon au démarrage (un tampon saturé bloquerait les envois en direct)
void purgerAuDemarrage();

// Y a-t-il des mesures à rejouer ?
bool enAttente();

// Ajoute une mesure en fin de fichier (refusée si le tampon est plein)
void ajouter(const String &json);

// Rejoue une partie du tampon (au plus MAX_REJEU_PAR_TOUR mesures par appel, pour ne pas
// monopoliser la tâche réseau après une très longue coupure). La position n'avance qu'après
// un envoi confirmé : une coupure pendant le rejeu laisse le reste intact.
void rejouer();

} // namespace Tampon
