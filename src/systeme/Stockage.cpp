#include "systeme/Stockage.h"
#include <Arduino.h>
#include <LittleFS.h>

namespace Stockage {

namespace {
Preferences preferences;
}

void demarrer() {
  if (!LittleFS.begin(
          true)) { // true = formate automatiquement au tout premier boot
    Serial.println(
        "Erreur montage LittleFS : le tampon hors-ligne sera indisponible.");
  }
  preferences.begin("aoceda", false);
}

Preferences &prefs() { return preferences; }

} // namespace Stockage
