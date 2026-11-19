#include "reseau/CanalUsb.h"
#include "config/Reglages.h"
#include "reseau/ReponseServeur.h"
#include "systeme/Horloge.h"

using namespace Reglages;

namespace CanalUsb {

namespace {
unsigned long prochainEssai = 0; // pas d'essai USB avant cet instant (millis)
}

bool envoyer(const String &json) {
  if ((long)(millis() - prochainEssai) < 0)
    return false; // pont absent au dernier essai : on attend la prochaine fenêtre

  while (Serial.available()) // jette ce qui traîne (jamais lu ailleurs)
    Serial.read();

  // Une seule écriture : la ligne ne peut pas être coupée par un message de la boucle de
  // mesure (l'autre coeur écrit aussi sur ce port)
  char ligne[320]; // trame (~110 octets, ~175 avec un relevé DHT11) + "@USB "
  int n = snprintf(ligne, sizeof(ligne), "@USB %s\n", json.c_str());
  if (n <= 0 || n >= (int)sizeof(ligne))
    return false;
  Serial.write((const uint8_t *)ligne, (size_t)n);

  char rx[200];
  size_t k = 0;
  unsigned long debut = millis();
  while (millis() - debut < USB_ATTENTE_ACK_MS) {
    while (Serial.available()) {
      int c = Serial.read();
      if (c == '\n') {
        rx[k] = '\0';
        k = 0;
        if (strncmp(rx, "@HEURE ", 7) == 0) {
          // Heure du PC (UTC), envoyée par le pont juste avant l'accusé. Prise seulement si
          // la carte n'a pas d'heure (pas de Wi-Fi donc pas de NTP).
          Horloge::reglerSiInconnue(strtoul(rx + 7, nullptr, 10));
        } else if (strncmp(rx, "@ACK", 4) == 0) {
          ReponseServeur::recue(String(rx + 4)); // mêmes ordres de coupure qu'en Wi-Fi
          prochainEssai = 0;
          return true;
        }
      } else if (c != '\r' && k < sizeof(rx) - 1) {
        rx[k++] = (char)c;
      }
    }
    vTaskDelay(pdMS_TO_TICKS(5));
  }
  prochainEssai = millis() + USB_PAUSE_SANS_PONT_MS;
  return false;
}

} // namespace CanalUsb
