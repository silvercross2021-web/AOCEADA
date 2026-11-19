#pragma once
/*
  Verrou « radio » : la radio Wi-Fi de l'ESP32 brouille l'ADC. La mesure (une fenêtre d'une
  seconde) prend ce verrou ; les envois réseau le prennent aussi : mesure et radio ne se
  chevauchent donc jamais.
*/

namespace VerrouRadio {

void creer(); // au démarrage, avant toute mesure

// Prend le verrou (attente bornée). false = pas obtenu : l'appelant continue quand même
// (mieux vaut une mesure un peu brouillée qu'un blocage), et ne doit PAS rendre.
bool prendre(unsigned long attenteMs);

void rendre();

} // namespace VerrouRadio
