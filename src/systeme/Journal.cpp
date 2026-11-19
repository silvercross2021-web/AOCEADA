#include "systeme/Journal.h"
#include "config/Reglages.h"
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <stdarg.h>

namespace Journal {

namespace {
WiFiUDP udp;
IPAddress destinataire; // 0.0.0.0 = pas de copie Wi-Fi
} // namespace

void definirDestinataire(const char *urlServeur) {
  String url = urlServeur;
  int debutHote = url.indexOf("//") + 2;
  int finHote = url.indexOf(':', debutHote);
  if (!destinataire.fromString(url.substring(debutHote, finHote)))
    destinataire = IPAddress(0, 0, 0, 0); // nom de domaine : pas de journal Wi-Fi
}

void ecrire(const char *format, ...) {
  char buf[256];
  va_list args;
  va_start(args, format);
  vsnprintf(buf, sizeof(buf), format, args);
  va_end(args);
  Serial.print(buf);
  if (Reglages::JOURNAL_WIFI && destinataire != IPAddress(0, 0, 0, 0) &&
      WiFi.status() == WL_CONNECTED &&
      WiFi.localIP() != IPAddress(0, 0, 0, 0)) {
    udp.beginPacket(destinataire, Reglages::PORT_JOURNAL);
    udp.write((const uint8_t *)buf, strlen(buf));
    udp.endPacket();
  }
}

} // namespace Journal
