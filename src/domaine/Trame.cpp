#include "domaine/Trame.h"
#include "config/Reglages.h"
#include <stdio.h>
#include <string.h>

namespace Trame {

size_t construireMesure(char *buf, size_t taille, int indexServeur,
                        const char *etat, float courant, float puissance,
                        unsigned long horodatageUnix, bool relaisCoupe,
                        const ReleveAir *releve, bool *releveInclus) {
  if (releveInclus)
    *releveInclus = false;
  if (taille == 0)
    return 0;
  buf[0] = '\0';
  int n = snprintf(buf, taille,
                   "{\"capteur_index\":%d,\"etat\":\"%s\",\"courant\":%.3f,"
                   "\"puissance\":%.1f,\"timestamp_unix\":%lu,\"coupe\":%s",
                   indexServeur, etat, courant, puissance, horodatageUnix,
                   relaisCoupe ? "true" : "false");
  buf[taille - 1] = '\0'; // certaines bibliothèques C ne terminent pas une sortie tronquée
  if (releve && n > 0 && n < (int)taille) {
    n += snprintf(buf + n, taille - n,
                  ",\"temperature_c\":%.1f,\"humidite_pct\":%.1f,"
                  "\"releve_unix\":%lu",
                  releve->temperatureC, releve->humiditePct,
                  releve->instantUnix);
    buf[taille - 1] = '\0';
    if (releveInclus)
      *releveInclus = true;
  }
  if (n > 0 && n < (int)taille - 1) {
    buf[n] = '}';
    buf[n + 1] = '\0';
  }
  return strlen(buf);
}

bool lireOrdreCoupure(const char *reponse, int indexServeur, bool &ordre) {
  char cle[16];
  snprintf(cle, sizeof(cle), "\"coupe_%d\"", indexServeur);
  const char *p = strstr(reponse, cle);
  if (!p)
    return false;
  p = strchr(p, ':');
  if (!p)
    return false;
  p++;
  while (*p == ' ')
    p++;
  if (strncmp(p, "true", 4) == 0)
    ordre = true;
  else if (strncmp(p, "false", 5) == 0)
    ordre = false;
  else
    return false;
  return true;
}

bool releveVraisemblable(float temperatureC, float humiditePct) {
  return temperatureC >= Reglages::DHT_T_MIN &&
         temperatureC <= Reglages::DHT_T_MAX &&
         humiditePct >= Reglages::DHT_H_MIN &&
         humiditePct <= Reglages::DHT_H_MAX;
}

} // namespace Trame
