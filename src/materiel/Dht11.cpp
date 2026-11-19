#include "materiel/Dht11.h"
#include "domaine/Trame.h"
#include "systeme/Horloge.h"
#include "systeme/Journal.h"
#include <Arduino.h>
#include <DHT.h>

using namespace Reglages;

namespace Dht11 {

namespace {
DHT dht(PIN_DHT, DHT11);

// Dernier relevé valide (NAN tant qu'aucun n'a réussi : jamais de valeur inventée)
portMUX_TYPE verrou = portMUX_INITIALIZER_UNLOCKED;
float derniereTemperatureC = NAN;
float derniereHumiditePct = NAN;
unsigned long dernierReleveUnix = 0; // son heure réelle (UTC) ; 0 = heure inconnue
uint32_t numeroReleve = 0;           // +1 à chaque relevé valide
uint32_t numeroParti = 0;            // dernier relevé parti

unsigned long dernierEssai = 0;
bool premierEssaiFait = false;
int echecsDeSuite = 0;
int etatLignePrecedent = -1; // -1 = inconnu, 0 = bas, 1 = haut, 2 = instable
} // namespace

void initialiser() {
  // La première lecture a lieu en fin de loop(), bien après le délai d'une seconde dont le
  // capteur a besoin après sa mise sous tension
  dht.begin();
  Serial.printf("[DHT11] Capteur sur GPIO %d (S), alimentation 3V3, une lecture "
                "toutes les %lu s\n",
                PIN_DHT, DHT_INTERVALLE_MS / 1000UL);
}

uint32_t releveAJoindre(ReleveAir &releve) {
  uint32_t numero = 0;
  portENTER_CRITICAL(&verrou);
  if (numeroReleve != numeroParti && dernierReleveUnix != 0 &&
      !isnan(derniereTemperatureC) && !isnan(derniereHumiditePct)) {
    releve.temperatureC = derniereTemperatureC;
    releve.humiditePct = derniereHumiditePct;
    releve.instantUnix = dernierReleveUnix;
    numero = numeroReleve;
  }
  portEXIT_CRITICAL(&verrou);
  return numero;
}

void releveParti(uint32_t numero) {
  portENTER_CRITICAL(&verrou);
  if (numero > numeroParti)
    numeroParti = numero;
  portEXIT_CRITICAL(&verrou);
}

void lire() {
  unsigned long maintenant = millis();
  // En panne, on réessaie toutes les 5 s (le DHT11 tolère 1 lecture/s) : le résultat
  // apparaît vite après un changement de câblage. Quand tout va bien, une lecture toutes
  // les 30 s.
  unsigned long intervalle =
      (echecsDeSuite > 0) ? DHT_INTERVALLE_PANNE_MS : DHT_INTERVALLE_MS;
  if (premierEssaiFait && maintenant - dernierEssai < intervalle)
    return;
  premierEssaiFait = true;
  dernierEssai = maintenant;

  float humidite = dht.readHumidity();
  float temperature = dht.readTemperature(); // en degrés Celsius
  bool lue = !isnan(humidite) && !isnan(temperature);
  bool plausible = lue && Trame::releveVraisemblable(temperature, humidite);
  if (lue && !plausible) {
    // Réponse reçue mais hors de la plage d'un logement : capteur en défaut, ignorée
    echecsDeSuite++;
    if (echecsDeSuite == 1 || echecsDeSuite % 5 == 0)
      Journal::ecrire("[DHT11] Valeur hors plage ignoree (%.0f C, %.0f %%) : "
                      "capteur en defaut ?\n",
                      temperature, humidite);
    return;
  }
  if (!lue) {
    echecsDeSuite++;
    // Etat du fil après l'échec, pour savoir D'OU vient le défaut (rappel interne actif) :
    //   toujours BAS -> la ligne est reliée à la masse (fil S sur GND, S/- inversés, capteur
    //                   en court-circuit)
    //   HAUT         -> le fil est libre mais rien ne répond (capteur absent, non alimenté,
    //                   + non branché)
    pinMode(PIN_DHT, INPUT_PULLUP);
    delay(2);
    int nbHaut = 0;
    for (int i = 0; i < 10; i++) {
      nbHaut += digitalRead(PIN_DHT);
      delay(1);
    }
    // 0 = bas, 1 = haut ; on ne parle que d'un état franc
    int etatLigne = (nbHaut == 0) ? 0 : (nbHaut == 10 ? 1 : 2);
    // Message au premier échec, quand l'état du fil CHANGE (on vient de toucher au
    // câblage), puis un sur cinq (pas de flot de messages)
    if (echecsDeSuite == 1 || etatLigne != etatLignePrecedent ||
        echecsDeSuite % 5 == 0) {
      const char *texteLigne =
          etatLigne == 0
              ? "ligne tenue a la masse (le fil S touche GND, ou capteur en "
                "court-circuit)"
          : etatLigne == 1
              ? "ligne haute mais aucune reponse (capteur non alimente ou "
                "absent)"
              : "ligne instable";
      Journal::ecrire("[DHT11] Lecture impossible (%d echec(s) de suite) : %s | "
                      "verifier S->GPIO %d, + ->3V3, - ->GND\n",
                      echecsDeSuite, texteLigne, PIN_DHT);
    }
    etatLignePrecedent = etatLigne;
    return;
  }
  // Heure réelle du relevé : sans elle, le relevé reste local (le serveur ne recevrait
  // qu'une heure approximative) et n'est pas envoyé.
  unsigned long quand = Horloge::heureUnix();
  portENTER_CRITICAL(&verrou);
  derniereTemperatureC = temperature;
  derniereHumiditePct = humidite;
  dernierReleveUnix = quand;
  numeroReleve++;
  portEXIT_CRITICAL(&verrou);
  echecsDeSuite = 0;
  etatLignePrecedent = -1;
  Journal::ecrire("[DHT11] Temperature %.0f C | Humidite %.0f %% (%s)\n",
                  temperature, humidite,
                  quand != 0 ? "sera envoye au serveur avec la prochaine mesure"
                             : "heure inconnue : non envoye");
}

} // namespace Dht11
