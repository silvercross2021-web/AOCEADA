#include "reseau/Ota.h"
#include "config/Identifiants.h"
#include "reseau/Reseau.h"
#include "systeme/Journal.h"
#include <ArduinoOTA.h>
#include <WiFi.h>

namespace Ota {

namespace {
bool pret = false;

void demarrer() {
  if (pret || !Reseau::connecte())
    return;
  ArduinoOTA.setHostname("aoceda-esp32");
  ArduinoOTA.setPassword(AOCEDA_MOT_DE_PASSE_OTA);
  ArduinoOTA.onStart(
      []() { Serial.println("[OTA] Mise a jour du programme..."); });
  ArduinoOTA.onError(
      [](ota_error_t e) { Serial.printf("[OTA] Echec (%u)\n", e); });
  ArduinoOTA.begin();
  pret = true;
  Journal::ecrire("[OTA] Mise a jour par Wi-Fi possible a l'adresse %s\n",
                  WiFi.localIP().toString().c_str());
}
} // namespace

void suivre() {
  demarrer();
  ArduinoOTA.handle();
}

} // namespace Ota
