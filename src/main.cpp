#include <Arduino.h>

/*
  ZMCT103C - Logger 2 capteurs : lampe (A0) + prise (A1)

  Methode : RMS + suivi d'offset continu + hysteresis + confirmation.
  Ref: methode_detection_onoff_zmct103c.md

  Regles absolues (ne pas modifier) :
  - Jamais de detection de pic (max/min) pour decider ON/OFF.
  - L'offset continu est suivi en permanence avec un filtre lent.
  - L'etat ne change qu'apres CONFIRMATIONS mesures consecutives d'accord.
*/

// ---- Parametres electriques -----------------------------------------------
const float V_REF     = 5.0f;
const float R_BURDEN  = 100.0f;
const float N_TURNS   = 1000.0f;
const float TENSION_V = 220.0f;
const float K = (V_REF / 1024.0f) / R_BURDEN * N_TURNS;  // A par unite ADC

// ---- Acquisition ----------------------------------------------------------
const unsigned long FENETRE_MS  = 100UL;  // 100 ms = 5 cycles a 50 Hz
const uint8_t       CONFIRMATIONS = 3;    // mesures consecutives avant tout changement d'etat

// Seuils ON/OFF : voir capteurs[] ci-dessous (colonne sOn / sOff).
// Calibres sur mesures reelles (methode_detection_onoff_zmct103c.md §5) :
//   Lampe (A0) : eteint ~4.5 (max 5.47)  |  allume ~5.8 (min 5.28)
//   Prise (A1) : eteint ~3.4 (max 4.0)   |  allume ~6.5 (min 6.2)

// ---- Seuils ecretage (controle qualite signal, pas utilises pour ON/OFF) --
const int SEUIL_ECRET_HAUT = 990;
const int SEUIL_ECRET_BAS  = 5;
const int AMP_ECRET_BAS    = 40;

// ---- Structure etat par capteur -------------------------------------------
struct EtatCapteur {
  const char*   id;
  uint8_t       pin;
  float         seuilOn;       // RMS ADC minimum pour passer ON
  float         seuilOff;      // RMS ADC maximum pour repasser OFF (< seuilOn)
  const char*   labelOn;
  const char*   labelOff;
  float         offset;        // DC continu suivi en permanence (anti-derive)
  bool          actif;
  uint8_t       cptConfirm;   // compteur de confirmation avant changement d'etat
  unsigned long t_debut;
  unsigned int  nb_connexions;
  unsigned int  nb_deconnexions;
  float         somme_rms_on;
  unsigned long nb_rms_on;
};

EtatCapteur capteurs[] = {
  //  id           pin   sOn    sOff   labelOn            labelOff          offset   actif  cpt  t  nc  nd  srms   nrms
  {"Capteur_1",   A0,   5.6f,  5.0f,  "LAMPE ALLUMEE",   "LAMPE ETEINTE",  512.0f,  false, 0,   0, 0,  0,  0.0f,  0UL},
  {"Capteur_2",   A1,   5.5f,  4.5f,  "PRISE BRANCHEE",  "PRISE LIBRE",    512.0f,  false, 0,   0, 0,  0,  0.0f,  0UL},
};
const int NB_CAPTEURS = sizeof(capteurs) / sizeof(capteurs[0]);

// ---- Resultat d'une fenetre d'acquisition ---------------------------------
struct Mesure { float rms; int vMin; int vMax; };

// ========================================================================
// Acquiert 100 ms de signal sur la broche du capteur.
// Met a jour c.offset (suivi lent du DC, anti-derive).
// Retourne la RMS de la composante alternative (unites ADC brutes).
Mesure acquerir(EtatCapteur& c) {
  unsigned long debut = millis();
  unsigned long n = 0;
  float sommeCarres = 0.0f;
  int vMin = 1023, vMax = 0;

  while (millis() - debut < FENETRE_MS) {
    int brut = analogRead(c.pin);
    // Filtre passe-bas tres lent : suit la derive du DC (offset) sans suivre le 50 Hz
    c.offset += ((float)brut - c.offset) / 1024.0f;
    float ac = (float)brut - c.offset;  // composante alternative seule
    sommeCarres += ac * ac;
    if (brut < vMin) vMin = brut;
    if (brut > vMax) vMax = brut;
    n++;
  }

  Mesure m;
  m.rms  = (n > 0) ? sqrtf(sommeCarres / (float)n) : 0.0f;
  m.vMin = vMin;
  m.vMax = vMax;
  return m;
}

// ========================================================================
static void printFloat(float v, int dec) {
  char buf[12]; dtostrf(v, 1, dec, buf); Serial.print(buf);
}

static void printTemps(unsigned long ms) {
  unsigned long s = ms / 1000UL;
  unsigned int  d = (unsigned int)((ms % 1000UL) / 100UL);
  Serial.print(F("t="));
  if (s <    10) Serial.print(' ');
  if (s <   100) Serial.print(' ');
  if (s <  1000) Serial.print(' ');
  if (s < 10000) Serial.print(' ');
  Serial.print(s); Serial.print('.'); Serial.print(d); Serial.print('s');
}

// ========================================================================
void traiterCapteur(EtatCapteur& c) {

  Mesure m     = acquerir(c);
  float rms    = m.rms;
  float courant_A = K * rms;
  float puissance = TENSION_V * courant_A;
  unsigned long maintenant = millis();
  bool etat_avant = c.actif;

  // ---- Hysteresis + confirmation (RMS uniquement, jamais amplitude crete) ----
  if (!c.actif) {
    // En attente d'allumage : on compte les mesures au-dessus de seuilOn
    if (rms >= c.seuilOn) {
      c.cptConfirm++;
      if (c.cptConfirm >= CONFIRMATIONS) { c.actif = true; c.cptConfirm = 0; }
    } else {
      c.cptConfirm = 0;  // mesure contradictoire : on repart a zero
    }
  } else {
    // Allume : on compte les mesures en-dessous de seuilOff
    if (rms < c.seuilOff) {
      c.cptConfirm++;
      if (c.cptConfirm >= CONFIRMATIONS) { c.actif = false; c.cptConfirm = 0; }
    } else {
      c.cptConfirm = 0;
    }
  }

  if (c.actif) { c.somme_rms_on += rms; c.nb_rms_on++; }

  // ---- Evenement ON ----
  if (c.actif && !etat_avant) {
    c.nb_connexions++;
    c.somme_rms_on = 0.0f;
    c.nb_rms_on    = 0;
    Serial.println(F("---"));
    printTemps(maintenant);
    Serial.print(F("  +++ ")); Serial.print(c.labelOn);
    Serial.print(F("  #")); Serial.print(c.nb_connexions);
    Serial.print(F("  [")); Serial.print(c.id); Serial.println(F("]"));
    c.t_debut = maintenant;
  }

  // ---- Evenement OFF ----
  if (!c.actif && etat_avant) {
    c.nb_deconnexions++;
    float rms_moy_on = (c.nb_rms_on > 0) ? (c.somme_rms_on / (float)c.nb_rms_on) : 0.0f;
    float cour_moy   = K * rms_moy_on;
    float puis_moy   = TENSION_V * cour_moy;
    unsigned long duree = maintenant - c.t_debut;

    printTemps(maintenant);
    Serial.print(F("  --- ")); Serial.print(c.labelOff);
    Serial.print(F("  #")); Serial.print(c.nb_deconnexions);
    Serial.print(F("  [")); Serial.print(c.id);
    Serial.print(F("]  Duree="));
    Serial.print(duree / 1000UL); Serial.print('.');
    Serial.print((unsigned int)((duree % 1000UL) / 100UL)); Serial.print('s');
    Serial.println();
    Serial.print(F("    "));
    Serial.print(F("Courant=")); printFloat(cour_moy, 3); Serial.print(F("A"));
    Serial.print(F("  Tension=")); Serial.print((int)TENSION_V); Serial.print(F("V"));
    Serial.print(F("  Puissance=")); printFloat(puis_moy, 1); Serial.println(F("W"));
    Serial.println(F("---"));

    c.t_debut      = maintenant;
    c.somme_rms_on = 0.0f;
    c.nb_rms_on    = 0;
  }

  // ---- Statut continu (format compatible serial_bridge.py) ----
  printTemps(maintenant);
  Serial.print(F("  [")); Serial.print(c.id); Serial.print(F("]"));
  Serial.print(F("  Centre=")); Serial.print((int)c.offset);
  Serial.print(F("  Ampl="));   Serial.print((int)rms);  // RMS ADC (pas crete-a-crete)

  if (c.actif) {
    Serial.print(F("  [ON ]"));
    Serial.print(F("  Courant=")); printFloat(courant_A, 3); Serial.print(F("A"));
    Serial.print(F("  Tension=")); Serial.print((int)TENSION_V); Serial.print(F("V"));
    Serial.print(F("  Puissance=")); printFloat(puissance, 1); Serial.print(F("W"));
  } else {
    Serial.print(F("  [OFF]"));
  }

  if (m.vMax >= SEUIL_ECRET_HAUT) Serial.print(F("  !ECRET_HAUT -> baisser pot"));
  if (m.vMin <= SEUIL_ECRET_BAS && (m.vMax - m.vMin) > AMP_ECRET_BAS) Serial.print(F("  !ECRET_BAS"));

  Serial.println();
}

// ========================================================================
void setup() {
  Serial.begin(9600);
  Serial.println(F("=== ZMCT103C - LOGGER 2 CAPTEURS ==="));
  Serial.print(F("K calcule  = ")); printFloat(K, 5); Serial.println(F(" A/ADC"));
  Serial.println(F("Seuils (RMS ADC) :"));
  for (int i = 0; i < NB_CAPTEURS; i++) {
    Serial.print(F("  ")); Serial.print(capteurs[i].id);
    Serial.print(F(" ON>="));  printFloat(capteurs[i].seuilOn,  2);
    Serial.print(F("  OFF<")); printFloat(capteurs[i].seuilOff, 2);
    Serial.println();
  }

  // Laisser l'offset converger vers la vraie valeur DC avant de surveiller
  Serial.println(F("Stabilisation offset (8 x 100ms)..."));
  for (int i = 0; i < 8; i++) {
    for (int j = 0; j < NB_CAPTEURS; j++) {
      acquerir(capteurs[j]);  // met a jour capteurs[j].offset
    }
  }
  Serial.println(F("---"));
}

void loop() {
  for (int i = 0; i < NB_CAPTEURS; i++) {
    traiterCapteur(capteurs[i]);
  }
}
