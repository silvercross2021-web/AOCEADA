#include "application/BoucleMesure.h"
#include "application/FileEnvoi.h"
#include "config/Reglages.h"
#include "domaine/Detection.h"
#include "domaine/Electrique.h"
#include "materiel/AcquisitionZmct.h"
#include "materiel/Capteurs.h"
#include "materiel/Dht11.h"
#include "materiel/Relais.h"
#include "reseau/Ota.h"
#include "systeme/Journal.h"
#include <Arduino.h>

using namespace Reglages;

namespace BoucleMesure {

namespace {

void traiterCapteur(EtatCapteur &c) {
  Mesure m = AcquisitionZmct::fenetre(c);
  float lisse = Detection::lisser(c.secteur, m.secteur);
  Detection::calculerSeuils(c);
  // Courant : fréquences du secteur, moins le bruit appris
  float tension_V = Electrique::tensionSecteurV(
      millis() / 1000.0f, ((float)random(-60, 61)) / 100.0f);
  float courant_A = Electrique::courantA(m.secteur, c.bruit);
  float puissance = Electrique::puissanceW(tension_V, courant_A);
  unsigned long maintenant = millis();
  bool etat_avant = c.actif;
  int local = Capteurs::indexLocal(c.id);
  bool coupeParRelais =
      local >= 0 && Relais::estCoupe(local) && !Relais::retenus();

  Detection::evaluer(c, m.secteur, lisse, coupeParRelais);

  // ---- Evenement ON ----
  if (c.actif && !etat_avant) {
    Journal::ecrire("[%s] ETAT : %s (secteur lisse=%.0f, bruit=%.0f)\n", c.id,
                    c.labelOn, lisse, c.bruit);
    FileEnvoi::deposer(c, courant_A, puissance); // envoi immédiat
    c.last_send = maintenant;
  }

  // ---- Evenement OFF ----
  if (!c.actif && etat_avant) {
    Journal::ecrire("[%s] ETAT : %s (secteur lisse=%.0f, bruit=%.0f)\n", c.id,
                    c.labelOff, lisse, c.bruit);
    FileEnvoi::deposer(c, 0.0f, 0.0f); // envoi immédiat
    c.last_send = maintenant;
  }

  // ---- Envoi régulier (toutes les INTERVALLE_ENVOI_MS) ----
  if (maintenant - c.last_send > INTERVALLE_ENVOI_MS) {
    FileEnvoi::deposer(c, courant_A, puissance);
    c.last_send = maintenant;
    // Debug continu pour analyser le signal
    Journal::ecrire(
        "[DEBUG-SIGNAL] %s | Secteur: %.0f | Lisse: %.0f | Bruit: %.0f | "
        "P50: %.0f | Harm: %.0f | Var totale: %.0f | Milieu: %.0f | Seuils: "
        "%.0f/%.0f | U: %.1f V | I: %.3f A | P: %.1f W | Etat: %s%s\n",
        c.id, m.secteur, lisse, c.bruit, m.p50, m.pHarm, m.var, c.offset,
        c.seuilOnEff, c.seuilOffEff, tension_V, courant_A,
        c.actif ? puissance : 0.0f, c.actif ? "ON" : "OFF",
        coupeParRelais ? " (relais ouvert)" : "");
  }
}

// Ordres de coupure appliqués par la tâche réseau depuis le dernier passage : journalisés ici
// (radio libre, hors fenêtre de mesure). Une coupure rend l'appareil « éteint » tout de suite,
// envoyé au serveur sans attendre la prochaine fenêtre de ce capteur (jusqu'à ~2,4 s gagnées à
// l'écran).
void suivreOrdresRelais() {
  for (int i = 0; i < Capteurs::NB; i++) {
    if (!Relais::ordreAJournaliser(i))
      continue;
    Journal::ecrire("[RELAIS] %s : %s\n", Capteurs::etat[i].id,
                    Relais::estCoupe(i) ? "COUPE a distance"
                                        : "courant RETABLI");
    EtatCapteur &c = Capteurs::etat[i];
    if (Relais::estCoupe(i) && c.actif && !Relais::retenus()) {
      c.actif = false;
      c.cptConfirm = 0;
      Journal::ecrire("[%s] ETAT : %s (relais coupe)\n", c.id, c.labelOff);
      FileEnvoi::deposer(c, 0.0f, 0.0f);
      c.last_send = millis();
    }
  }
}

} // namespace

void tour() {
  Ota::suivre();
  for (int i = 0; i < Capteurs::NB; i++) {
    traiterCapteur(Capteurs::etat[i]);
    // Laisse l'ADC libérer sa charge entre deux canaux, et la tâche réseau vider sa file
    // pendant que l'ADC ne mesure pas (voir PAUSE_RADIO_MAX_MS). Entre deux fenêtres, la
    // tâche réseau vide TOUTE sa file (dans cette limite) : avec un seul envoi par pause, un
    // retard accumulé (serveur redémarré...) ne se résorbait jamais (17 s entre la décision
    // de l'ESP32 et le tableau de bord, constaté le 12/10/2026).
    unsigned long debutPause = millis();
    do {
      delay(PAUSE_RADIO_MS);
    } while ((FileEnvoi::enAttente() > 0 || FileEnvoi::envoiEnCours()) &&
             millis() - debutPause < PAUSE_RADIO_MAX_MS);
    suivreOrdresRelais(); // après chaque capteur : une coupure se voit tout de suite
  }
  Dht11::lire(); // température ambiante (toutes les 30 s), hors fenêtre de mesure
}

} // namespace BoucleMesure
