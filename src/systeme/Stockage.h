#pragma once
/*
  Mémoire persistante de la carte :
   - LittleFS : fichiers (tampon hors ligne des mesures) ;
   - NVS (Preferences, espace « aoceda ») : petits réglages (ordre de coupure de chaque
     relais, position de lecture du tampon).
*/
#include <Preferences.h>

namespace Stockage {

// Monte LittleFS (formate au tout premier démarrage) puis ouvre les Preferences
void demarrer();

Preferences &prefs();

} // namespace Stockage
