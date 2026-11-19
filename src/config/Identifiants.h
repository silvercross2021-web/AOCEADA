#pragma once
/*
  Point d'entrée UNIQUE des identifiants (Wi-Fi, clé du boîtier, mot de passe OTA).
  Les vraies valeurs sont dans include/secrets.h, non versionné. S'il manque (copie neuve du
  dépôt), le modèle secrets.example.h prend le relais : le programme compile, le Wi-Fi reste
  inactif et les mesures partent par le câble USB.
*/
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#warning "include/secrets.h absent : valeurs d'exemple utilisees (Wi-Fi inactif, USB seulement). Copier include/secrets.example.h en include/secrets.h."
#endif
