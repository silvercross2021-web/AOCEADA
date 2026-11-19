#pragma once
/*
  Envoi d'une mesure au serveur par Wi-Fi : POST JSON sur Reseau::serveur(), en-tête
  « Authorization: Device <clé du boîtier> ». La réponse (201) porte les ordres de coupure
  des relais : elle est transmise à ReponseServeur.
*/
#include <Arduino.h>

namespace ClientHttp {

// true = le serveur a répondu 201 (mesure acceptée). Jamais pendant une fenêtre de mesure :
// prend le verrou radio (attente 5 s au plus, pour ne jamais bloquer indéfiniment).
bool envoyer(const String &json);

// Envois d'affilée sans AUCUNE réponse HTTP (serveur muet, PC sur un autre réseau...)
int echecsSansReponse();
void reinitialiserEchecs();

} // namespace ClientHttp
