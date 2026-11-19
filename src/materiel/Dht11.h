#pragma once
/*
  Température et humidité ambiantes : module DHT11 à 3 broches (S + -).
  Pourquoi : quand il fait chaud, les appareils consomment davantage. Le relevé est envoyé au
  serveur avec les mesures de courant (une fois par relevé) ; la prévision
  (AOCEDA/apps/analytics/temperature_locale.py) s'en sert après calibration sur la météo de
  la ville. Branchement (la borne de signal est marquée S ou OUT selon le module) :
    S/OUT -> GPIO 4 (D4)    + -> 3V3 (jamais VIN : le signal serait à 5 V)    - -> GND
  GPIO 4 : libre (34/35 = capteurs de courant, 26/27 = relais), bidirectionnel (le DHT11
  parle sur un seul fil), sans rôle au démarrage. Le module porte déjà sa résistance de
  rappel : aucune résistance à ajouter.
  La lecture dure ~25 ms (interruptions coupées ~4 ms) : elle est faite en FIN de boucle,
  jamais pendant une fenêtre de mesure du courant. DHT11 : 0 à 50 C (+/- 2 C), 20 à 80 %
  d'humidité (+/- 5 %), une lecture par seconde au plus.

  Le relevé est joint à UNE trame de mesure puis marqué « parti ». Deux tâches y touchent
  (boucle de mesure et tâche réseau) : copie et marquage se font sous verrou, pour ne jamais
  envoyer la température d'un relevé avec l'humidité ou l'heure d'un autre.
  Jamais de valeur inventée : tant qu'aucun relevé VALIDE n'est arrivé, ou si l'heure réelle
  est inconnue, rien n'est joint ; un relevé n'est jamais renvoyé après être parti (le
  serveur ignore de toute façon un relevé connu : même boîtier, même instant).
*/
#include "domaine/Capteur.h"
#include <stdint.h>

namespace Dht11 {

void initialiser();

// À appeler à chaque tour de boucle : ne lit que toutes les 30 s (5 s en cas de panne)
void lire();

// Copie cohérente du relevé s'il n'est pas encore parti. Rend son numéro, 0 si rien à joindre.
uint32_t releveAJoindre(ReleveAir &releve);

// Marque le relevé comme parti (envoyé, acquitté par l'USB ou mis en tampon)
void releveParti(uint32_t numero);

} // namespace Dht11
