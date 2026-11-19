#pragma once
/*
  Journal : message de contrôle sur le câble USB, avec une copie UDP vers le PC du serveur
  (permet de suivre la carte alimentée par un simple chargeur ; sur le PC, écouter le port
  Reglages::PORT_JOURNAL en UDP).
  À n'appeler que depuis la boucle de mesure, hors fenêtre de mesure (la radio brouille
  l'ADC). Les tâches réseau écrivent directement sur Serial.
*/

namespace Journal {

// Adresse du PC du journal : l'hôte de l'URL du serveur (« http://IP:port/... »). Un nom
// de domaine donne pas de copie Wi-Fi.
void definirDestinataire(const char *urlServeur);

void ecrire(const char *format, ...) __attribute__((format(printf, 1, 2)));

} // namespace Journal
