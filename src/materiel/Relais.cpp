#include "materiel/Relais.h"
#include "domaine/Trame.h"
#include "materiel/Capteurs.h"
#include "systeme/Journal.h"
#include "systeme/Stockage.h"

using namespace Reglages;

namespace Relais {

namespace {
static_assert(sizeof(PINS_RELAIS) / sizeof(PINS_RELAIS[0]) == Capteurs::NB,
              "un relais par capteur");

volatile bool coupe[Capteurs::NB] = {false, false};
volatile bool aJournaliser[Capteurs::NB] = {false, false};
volatile bool retenue = true;

void cleNvs(int i, char *cle, size_t taille) {
  snprintf(cle, taille, "coupe%d", i);
}
} // namespace

void appliquer(int i) {
  // Appareil alimenté <=> le courant doit passer vers la charge.
  // En COM + NO : l'appareil est alimenté lorsque le relais est activé (contact fermé).
  // En COM + NC : l'appareil est alimenté lorsque le relais est au repos (contact fermé).
  bool alimente = !retenue && !coupe[i];
  bool activerRelais = CONTACT_NO[i] ? alimente : !alimente;
  uint8_t niveau = (activerRelais == RELAIS_ACTIF_NIVEAU_HAUT[i]) ? HIGH : LOW;
  digitalWrite(PINS_RELAIS[i], niveau);
}

void initialiser() {
  // Dernier ordre enregistré, lu avant même le Wi-Fi, sans attendre le serveur. Il n'est
  // appliqué qu'après la mesure du bruit de fond (fin du démarrage, ~30 s) : jusque-là les
  // appareils restent coupés. Le niveau est écrit avant de passer la broche en sortie (pas
  // d'à-coup).
  for (int i = 0; i < Capteurs::NB; i++) {
    char cle[8];
    cleNvs(i, cle, sizeof(cle));
    coupe[i] = Stockage::prefs().getBool(cle, false);
    appliquer(i);
    pinMode(PINS_RELAIS[i], OUTPUT);
    Serial.printf(
        "[RELAIS] %s (GPIO %d) : ordre enregistre = %s ; coupe le temps de "
        "mesurer le bruit de fond\n",
        Capteurs::etat[i].id, PINS_RELAIS[i],
        coupe[i] ? "COUPE" : "courant present");
  }
}

bool estCoupe(int i) { return coupe[i]; }

bool retenus() { return retenue; }

void liberer() {
  retenue = false;
  for (int i = 0; i < Capteurs::NB; i++) {
    appliquer(i);
    Journal::ecrire("[RELAIS] %s : %s\n", Capteurs::etat[i].id,
                    coupe[i] ? "reste COUPE (ordre enregistre)"
                             : "courant RETABLI");
  }
}

bool ordreAJournaliser(int i) {
  if (!aJournaliser[i])
    return false;
  aJournaliser[i] = false;
  return true;
}

void appliquerReponseServeur(const String &reponse) {
  for (int i = 0; i < Capteurs::NB; i++) {
    bool ordre;
    if (!Trame::lireOrdreCoupure(reponse.c_str(),
                                 Capteurs::indexServeur(Capteurs::etat[i].id),
                                 ordre))
      continue;
    if (ordre != coupe[i]) {
      coupe[i] = ordre;
      appliquer(i);
      char cle[8];
      cleNvs(i, cle, sizeof(cle));
      Stockage::prefs().putBool(cle, ordre);
      aJournaliser[i] = true;
    }
  }
}

} // namespace Relais
