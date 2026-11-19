#pragma once
/*
  Relais : coupure du courant à distance (bouton « Couper » du site AOCEDA).
  Un module relais 5 V « S + - » par appareil, dans l'ordre des capteurs :
    Capteur_1 (lampe, GPIO 34) -> S du relais 1 sur GPIO 26
    Capteur_2 (prise, GPIO 35) -> S du relais 2 sur GPIO 27
  Le + des relais va sur VIN (5 V), jamais sur 3V3 : en 3,3 V la lumière du module
  s'allume mais le relais ne bascule pas, et deux relais ne tiennent pas (13/10/2026).
  Contacts sur COM + NO (« ouvert par défaut ») : relais au repos = appareil coupé. Hors
  ordre « couper », le relais est donc activé en permanence, et l'appareil suit son
  interrupteur normal. ESP32 éteint = lampe et prise coupées : c'est le câblage qui le
  veut, aucun programme n'y peut rien (en COM + NC, ce serait l'inverse).
  L'ordre en vigueur de chaque appareil (true = courant coupé) est gardé en mémoire NVS :
  au retour du courant, l'ESP32 le réapplique dès le démarrage, sans le serveur.
*/
#include <Arduino.h>

namespace Relais {

// Lit les derniers ordres (NVS), prépare les broches. Tant que le bruit de fond n'est pas
// mesuré (retenus()), tous les contacts restent ouverts.
void initialiser();

// Pose le niveau de la broche selon l'ordre en vigueur et la retenue de démarrage
void appliquer(int i);

// Ordre en vigueur : true = courant coupé
bool estCoupe(int i);

// Au démarrage, le bruit de fond des capteurs se mesure appareils COUPES : sinon le courant
// d'un appareil déjà allumé est appris comme du bruit et l'appareil n'est plus jamais vu
// allumé. Tant que retenus() est vrai, les ordres reçus sont gardés et appliqués ensuite.
bool retenus();

// Fin de la mesure du bruit : chaque appareil retrouve son ordre
void liberer();

// Un ordre a changé depuis le dernier passage ? Lit ET efface le drapeau : la boucle de
// mesure le journalise (seule à pouvoir utiliser la radio pour le journal UDP).
bool ordreAJournaliser(int i);

// Réponse du serveur à une mesure : {"created":1,"coupe_1":false,"coupe_2":true}. Absents
// (ancien serveur) : rien ne change. Appelée par les tâches réseau.
void appliquerReponseServeur(const String &reponse);

} // namespace Relais
