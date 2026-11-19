/*
  AOCEDA - micrologiciel de l'ESP32 : mesure du courant de deux appareils (ZMCT103C), coupure
  à distance par relais, température ambiante (DHT11), envoi au serveur Django par Wi-Fi ou,
  à défaut, par le câble USB.

  Ce fichier ne contient que le point d'entrée. Le code est découpé en couches, chacune ne
  dépendant que de celles du dessous :
    config/       réglages (broches, seuils, rythmes) et accès aux secrets (include/secrets.h)
    domaine/      logique pure, sans matériel : détection allumé/éteint, grandeurs
                  électriques, trame JSON du serveur
    systeme/      services de la carte : journal, heure, mémoire, verrou de la radio
    materiel/     capteurs ZMCT103C, relais, DHT11
    reseau/       Wi-Fi, envoi HTTP, canal USB, tampon hors ligne, mise à jour OTA
    application/  démarrage, boucle de mesure, tâches réseau (assemble le tout)
  Plan complet et règles : docs/firmware/architecture-firmware.md
*/
#include "application/BoucleMesure.h"
#include "application/Demarrage.h"
#include <Arduino.h>

void setup() { Demarrage::executer(); }

void loop() { BoucleMesure::tour(); }
