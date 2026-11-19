#include "systeme/Horloge.h"
#include <Arduino.h>
#include <sys/time.h>
#include <time.h>

namespace Horloge {

void synchroniser() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  Serial.print("Synchronisation NTP");
  unsigned long debut = millis();
  time_t maintenant = time(nullptr);
  while ((unsigned long)maintenant < TIMESTAMP_MIN_VALIDE &&
         millis() - debut < 10000) {
    delay(300);
    Serial.print(".");
    maintenant = time(nullptr);
  }
  if ((unsigned long)maintenant >= TIMESTAMP_MIN_VALIDE) {
    Serial.println(" OK");
  } else {
    Serial.println(" echec (les mesures tamponnees seront horodatees a la "
                   "reception serveur).");
  }
}

unsigned long heureUnix() {
  time_t t = time(nullptr);
  return ((unsigned long)t >= TIMESTAMP_MIN_VALIDE) ? (unsigned long)t : 0UL;
}

bool reglerSiInconnue(unsigned long heure) {
  if (heure < TIMESTAMP_MIN_VALIDE || heureUnix() != 0)
    return false;
  struct timeval tv = {(time_t)heure, 0};
  settimeofday(&tv, nullptr);
  return true;
}

} // namespace Horloge
