#include <Arduino.h>

// ========================================================================
// TEST ISOLE DES RELAIS ESP32 (SANS LE CODE DE PRODUCTION)
// ========================================================================
// GPIO 26 : Relais 1 (Lampe) / GPIO 27 : Relais 2 (Prise)
//
// Chaque relais est teste SEPAREMENT pour savoir quel module commande quoi :
//   1. tout coupe 5 s
//   2. relais 1 seul actif 8 s (la lampe doit s'allumer si elle est sur le relais 1)
//   3. tout coupe 5 s
//   4. relais 2 seul actif 8 s (la prise doit etre alimentee si elle est sur le relais 2)
//
// Pour un module « actif a l'etat bas » : ACTIF = LOW.
// Si le clac se produit pendant les phases « coupe » au lieu des phases
// « actif », mettre ACTIF_A_L_ETAT_BAS a false.
// ========================================================================

const uint8_t PIN_RELAIS_1 = 26; // Lampe
const uint8_t PIN_RELAIS_2 = 27; // Prise

const bool ACTIF_A_L_ETAT_BAS = false;
const uint8_t NIVEAU_ACTIF = ACTIF_A_L_ETAT_BAS ? LOW : HIGH;
const uint8_t NIVEAU_REPOS = ACTIF_A_L_ETAT_BAS ? HIGH : LOW;

void phase(const char *titre, bool r1, bool r2, int secondes) {
  digitalWrite(PIN_RELAIS_1, r1 ? NIVEAU_ACTIF : NIVEAU_REPOS);
  digitalWrite(PIN_RELAIS_2, r2 ? NIVEAU_ACTIF : NIVEAU_REPOS);
  Serial.printf("\n>>> %s\n    Relais 1 (GPIO 26) = %s | Relais 2 (GPIO 27) = %s\n",
                titre, r1 ? "ACTIF" : "repos", r2 ? "ACTIF" : "repos");
  for (int s = secondes; s > 0; s--) {
    Serial.printf("    reste %d s\n", s);
    delay(1000);
  }
}

void setup() {
  Serial.begin(115200);
  // Niveau ecrit avant la sortie : pas d'a-coup au demarrage
  digitalWrite(PIN_RELAIS_1, NIVEAU_REPOS);
  digitalWrite(PIN_RELAIS_2, NIVEAU_REPOS);
  pinMode(PIN_RELAIS_1, OUTPUT);
  pinMode(PIN_RELAIS_2, OUTPUT);
  delay(1000);
  Serial.println("\n=== BANC D'ESSAI RELAIS (un relais a la fois) ===");
}

void loop() {
  phase("TOUT AU REPOS", false, false, 5);
  phase("RELAIS 1 SEUL ACTIF (lampe ?)", true, false, 8);
  phase("TOUT AU REPOS", false, false, 5);
  phase("RELAIS 2 SEUL ACTIF (prise ?)", false, true, 8);
}
