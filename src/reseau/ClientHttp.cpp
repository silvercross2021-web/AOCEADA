#include "reseau/ClientHttp.h"
#include "config/Reglages.h"
#include "config/Identifiants.h"
#include "reseau/ReponseServeur.h"
#include "reseau/Reseau.h"
#include "systeme/VerrouRadio.h"
#include <HTTPClient.h>

namespace ClientHttp {

namespace {
int echecs = 0;
}

bool envoyer(const String &json) {
  HTTPClient http;
  http.begin(Reseau::serveur());
  http.addHeader("Content-Type", "application/json");
  char authHeader[100];
  snprintf(authHeader, sizeof(authHeader), "Device %s", AOCEDA_CLE_DISPOSITIF);
  http.addHeader("Authorization", authHeader);
  http.setTimeout(Reglages::TIMEOUT_HTTP_MS);
  // Jamais pendant une fenêtre de mesure : la radio brouille l'ADC (timeout 5 s pour éviter
  // tout blocage indéfini)
  bool verrou = VerrouRadio::prendre(5000);
  int code = http.POST(json);
  echecs = (code > 0) ? 0 : echecs + 1;
  // La réponse porte les ordres de coupure des relais
  String reponse = (code == 201) ? http.getString() : String();
  http.end();
  if (verrou)
    VerrouRadio::rendre();
  if (code == 201)
    ReponseServeur::recue(reponse);
  return code == 201;
}

int echecsSansReponse() { return echecs; }

void reinitialiserEchecs() { echecs = 0; }

} // namespace ClientHttp
