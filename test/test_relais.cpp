#include <Arduino.h>
#include <math.h>

// ============================================================
// BANC D'ESSAI ISOLÉ : RELAIS + ZMCT103C + TENSION SECTEUR (220-230 V)
// (N'affecte pas src/main.cpp — compilé uniquement via env:test_relais)
// ============================================================

// 1. CONFIGURATION DES BROCHES
// Relais
const uint8_t PIN_RELAIS_1 = 26; // Lampe
const uint8_t PIN_RELAIS_2 = 27; // Prise

// Capteurs de courant ZMCT103C
const uint8_t PIN_CAPTEUR_1 = 34; // Lampe
const uint8_t PIN_CAPTEUR_2 = 35; // Prise

// 2. CONFIGURATION DES RELAIS
// false : relais actif HIGH (validé sur le matériel)
// true  : relais actif LOW
const bool ACTIF_A_L_ETAT_BAS = false;
const uint8_t NIVEAU_ACTIF = ACTIF_A_L_ETAT_BAS ? LOW : HIGH;
const uint8_t NIVEAU_REPOS = ACTIF_A_L_ETAT_BAS ? HIGH : LOW;

// 3. CONFIGURATION DES CAPTEURS DE COURANT (ZMCT103C)
const float ADC_MAX = 4095.0f;
const float TENSION_ADC = 3.3f;

// Durée de mesure : 200 ms (10 périodes à 50 Hz)
const unsigned long DUREE_MESURE_US = 200000;
const unsigned int DELAI_ECHANTILLON_US = 250;
const unsigned long INTERVALLE_AFFICHAGE = 1000;

// Seuil de suppression du bruit (en Volts RMS côté ADC)
const float SEUIL_BRUIT_V = 0.015f;

// Coefficients de calibration alignés sur src/main.cpp (A par V RMS capteur)
float CALIBRATION_LAMPE_A_PAR_V = 6.10f;
float CALIBRATION_PRISE_A_PAR_V = 5.65f;

// 4. CONFIGURATION DE LA TENSION SECTEUR ESTIMÉE (REMPLACEMENT ZMPT101B)
// Tension mesurée au multimètre au laboratoire : ~224 V
// Plage autorisée : [220.0 V .. 230.0 V]
const float TENSION_MIN_V = 220.0f;
const float TENSION_MAX_V = 230.0f;
const float TENSION_NOMINALE_V = 224.5f; // Centrée près des 224 V mesurés
float tensionSecteurActuelle = TENSION_NOMINALE_V;

// Simule une fluctuation lente et réaliste du secteur entre 220 V et 230 V
float obtenirTensionSecteur() {
  // Onde lente (période ~30 s) + légère variation aléatoire (+/- 0.6 V)
  float t = millis() / 1000.0f;
  float ondeLente = 3.2f * sinf(2.0f * PI * t / 30.0f) +
                    1.1f * cosf(2.0f * PI * t / 11.0f);
  float microVariation = ((float)random(-60, 61)) / 100.0f; // -0.60 à +0.60 V

  float u = TENSION_NOMINALE_V + ondeLente + microVariation;
  if (u < TENSION_MIN_V)
    u = TENSION_MIN_V;
  if (u > TENSION_MAX_V)
    u = TENSION_MAX_V;

  tensionSecteurActuelle = u;
  return u;
}

// 5. VARIABLES DE GESTION DES RELAIS
bool relaisActifs = false;
unsigned long debutPhase = 0;
unsigned long derniereMesure = 0;

const unsigned long TEMPS_REPOS = 5000; // 5 s éteint
const unsigned long TEMPS_ACTIF = 8000; // 8 s allumé

// 6. COMMANDE DES RELAIS
void commanderRelais(bool lampe, bool prise) {
  digitalWrite(PIN_RELAIS_1, lampe ? NIVEAU_ACTIF : NIVEAU_REPOS);
  digitalWrite(PIN_RELAIS_2, prise ? NIVEAU_ACTIF : NIVEAU_REPOS);

  Serial.println("\n================================");
  Serial.println("       ETAT DES RELAIS");
  Serial.println("================================");
  Serial.printf("Lampe (GPIO 26) : %s\n", lampe ? "ON" : "OFF");
  Serial.printf("Prise (GPIO 27) : %s\n", prise ? "ON" : "OFF");
  Serial.println("================================");
}

// 7. MESURE DU COURANT RMS (ZMCT103C)
float mesurerCourant(uint8_t pin, float &tensionRMS, float calibration) {
  double somme = 0.0;
  double sommeCarres = 0.0;
  unsigned long debut = micros();
  unsigned long nombreEchantillons = 0;

  while ((unsigned long)(micros() - debut) < DUREE_MESURE_US) {
    int valeur = analogRead(pin);
    somme += valeur;
    sommeCarres += (double)valeur * valeur;
    nombreEchantillons++;
    delayMicroseconds(DELAI_ECHANTILLON_US);
  }

  if (nombreEchantillons == 0) {
    tensionRMS = 0.0f;
    return 0.0f;
  }

  double moyenne = somme / nombreEchantillons;
  double variance = (sommeCarres / nombreEchantillons) - (moyenne * moyenne);
  if (variance < 0.0) {
    variance = 0.0;
  }

  float rmsADC = sqrt(variance);
  tensionRMS = rmsADC * (TENSION_ADC / ADC_MAX);

  if (tensionRMS < SEUIL_BRUIT_V) {
    tensionRMS = 0.0f;
  }

  return tensionRMS * calibration;
}

// 8. AFFICHAGE DES MESURES (TENSION, COURANT, PUISSANCE)
void afficherMesures() {
  float tensionCapteurLampe = 0.0f;
  float tensionCapteurPrise = 0.0f;

  // Tension secteur (varie entre 220.0 V et 230.0 V autour de ~224.5 V)
  float tensionReseauV = obtenirTensionSecteur();

  // Mesure du courant sur les deux voies ZMCT103C
  float courantLampe = mesurerCourant(PIN_CAPTEUR_1, tensionCapteurLampe,
                                      CALIBRATION_LAMPE_A_PAR_V);
  float courantPrise = mesurerCourant(PIN_CAPTEUR_2, tensionCapteurPrise,
                                      CALIBRATION_PRISE_A_PAR_V);

  // Si les relais sont coupés, le courant et la puissance sont forcés à 0
  if (!relaisActifs) {
    courantLampe = 0.0f;
    courantPrise = 0.0f;
  }

  float puissanceLampeW = tensionReseauV * courantLampe;
  float puissancePriseW = tensionReseauV * courantPrise;

  Serial.println("\n========================================");
  Serial.println("          MESURES ELECTRIQUES");
  Serial.println("========================================");
  Serial.printf("Tension secteur (estimee 220-230V) : %.1f V\n", tensionReseauV);
  Serial.printf("Relais                             : %s\n",
                relaisActifs ? "ACTIFS (ON)" : "COUPES (OFF)");

  Serial.println("\n[ LAMPE - ZMCT103C 1 (GPIO 34) ]");
  Serial.printf("  Tension capteur RMS : %.4f V\n", tensionCapteurLampe);
  Serial.printf("  Tension secteur U   : %.1f V\n", tensionReseauV);
  Serial.printf("  Courant I           : %.3f A\n", courantLampe);
  Serial.printf("  Puissance P (U x I) : %.2f W\n", puissanceLampeW);

  Serial.println("\n[ PRISE - ZMCT103C 2 (GPIO 35) ]");
  Serial.printf("  Tension capteur RMS : %.4f V\n", tensionCapteurPrise);
  Serial.printf("  Tension secteur U   : %.1f V\n", tensionReseauV);
  Serial.printf("  Courant I           : %.3f A\n", courantPrise);
  Serial.printf("  Puissance P (U x I) : %.2f W\n", puissancePriseW);
  Serial.println("========================================");
}

// 9. GESTION AUTOMATIQUE DES PHASES
void gererPhases() {
  unsigned long maintenant = millis();
  unsigned long dureeActuelle = relaisActifs ? TEMPS_ACTIF : TEMPS_REPOS;

  if (maintenant - debutPhase >= dureeActuelle) {
    relaisActifs = !relaisActifs;
    debutPhase = maintenant;

    if (relaisActifs) {
      Serial.println("\n>>> ACTIVATION DES DEUX RELAIS (8 s)");
      commanderRelais(true, true);
    } else {
      Serial.println("\n>>> DESACTIVATION DES DEUX RELAIS (5 s)");
      commanderRelais(false, false);
    }
  }
}

// 10. INITIALISATION
void setup() {
  Serial.begin(115200);

  // Initialisation sécurisée des relais
  digitalWrite(PIN_RELAIS_1, NIVEAU_REPOS);
  digitalWrite(PIN_RELAIS_2, NIVEAU_REPOS);
  pinMode(PIN_RELAIS_1, OUTPUT);
  pinMode(PIN_RELAIS_2, OUTPUT);

  // Initialisation des capteurs ZMCT103C
  pinMode(PIN_CAPTEUR_1, INPUT);
  pinMode(PIN_CAPTEUR_2, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_CAPTEUR_1, ADC_11db);
  analogSetPinAttenuation(PIN_CAPTEUR_2, ADC_11db);

  // Graine pour les micro-variations de tension
  randomSeed(analogRead(PIN_CAPTEUR_1) ^ micros());

  delay(1000);

  Serial.println("\n========================================");
  Serial.println("  BANC ISOLE : ZMCT103C + TENSION 220-230V");
  Serial.println("========================================");
  Serial.println("ZMCT103C 1 : GPIO 34 - LAMPE");
  Serial.println("ZMCT103C 2 : GPIO 35 - PRISE");
  Serial.println("RELAIS 1   : GPIO 26 - LAMPE");
  Serial.println("RELAIS 2   : GPIO 27 - PRISE");
  Serial.println("TENSION U  : 220.0 V a 230.0 V (centree ~224.5 V)");

  commanderRelais(false, false);
  relaisActifs = false;
  debutPhase = millis();
  derniereMesure = millis();
}

// 11. BOUCLE PRINCIPALE
void loop() {
  gererPhases();

  if (millis() - derniereMesure >= INTERVALLE_AFFICHAGE) {
    derniereMesure = millis();
    afficherMesures();
  }

  delay(1);
}
