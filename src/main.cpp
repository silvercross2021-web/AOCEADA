#include <Arduino.h>

/*
  ZMCT103C - Logger 2 capteurs : lampe (A0) + prise (A1)
  K derive depuis les parametres materiels, valable pour tout appareil.
  Pour ajouter un capteur : ajouter une ligne dans capteurs[].
*/

// ---- Parametres electriques (communs) ----------------------------------
const float V_REF     = 5.0f;     // Reference ADC Arduino (V)
const float R_BURDEN  = 100.0f;   // Resistance de charge sur le module (Ohm)
const float N_TURNS   = 1000.0f;  // Rapport transformation ZMCT103C (1000:1)
const float TENSION_V = 220.0f;   // Tension secteur (V)
const float K = (V_REF / 1024.0f) / R_BURDEN * N_TURNS;  // A/ADC

// ---- Parametres acquisition --------------------------------------------
const unsigned long FENETRE_MS  = 200UL;
const int           NB_FENETRES = 5;

// ---- Seuils ecretage ---------------------------------------------------
const int SEUIL_ECRET_HAUT = 505;
const int SEUIL_ECRET_BAS  = 5;
const int AMP_ECRET_BAS    = 40;

// ---- Structure etat par capteur ----------------------------------------
struct EtatCapteur {
  const char*   id;
  int           pin;
  int           seuil_off;
  int           seuil_on;
  const char*   label_on;
  const char*   label_off;
  bool          actif;
  unsigned long t_debut;
  unsigned int  nb_connexions;
  unsigned int  nb_deconnexions;
  float         somme_rms_on;
  unsigned long nb_rms_on;
};

// ---- Declaration des capteurs ------------------------------------------
// Pour ajouter un capteur : dupliquer une ligne, modifier id/pin/seuils/labels
EtatCapteur capteurs[] = {
  // id           pin  s_off  s_on  label_on           label_off          -- ne pas modifier la suite --
  {"Capteur_1",   A0,   25,   35,   "LAMPE ALLUMEE",   "LAMPE ETEINTE",   false, 0, 0, 0, 0.0f, 0UL},
  {"Capteur_2",   A1,   25,   35,   "PRISE BRANCHEE",  "PRISE LIBRE",     false, 0, 0, 0, 0.0f, 0UL},
};
const int NB_CAPTEURS = sizeof(capteurs) / sizeof(capteurs[0]);

// ========================================================================
struct Fenetre { float rms; float centre; int vMin; int vMax; };

Fenetre acquerir(int pin) {
  long          sumX  = 0L;
  unsigned long sumX2 = 0UL;
  int           nb = 0, vMin = 1023, vMax = 0;
  unsigned long t0 = millis();
  while (millis() - t0 < FENETRE_MS) {
    int v = analogRead(pin);
    sumX  += (long)v;
    sumX2 += (unsigned long)v * (unsigned long)v;
    if (v < vMin) vMin = v;
    if (v > vMax) vMax = v;
    nb++;
  }
  if (nb < 1) nb = 1;
  Fenetre f;
  f.vMin   = vMin;
  f.vMax   = vMax;
  f.centre = (float)sumX / (float)nb;
  float var = (float)sumX2 / (float)nb - f.centre * f.centre;
  f.rms    = (var > 0.0f) ? sqrtf(var) : 0.0f;
  return f;
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

static void printDuree(unsigned long ms) {
  Serial.print(ms / 1000UL); Serial.print('.');
  Serial.print((unsigned int)((ms % 1000UL) / 100UL)); Serial.print('s');
}

static void printMesure(const __FlashStringHelper* label,
                        float v, int dec,
                        const __FlashStringHelper* unite) {
  Serial.print(F("  ")); Serial.print(label);
  Serial.print('='); printFloat(v, dec); Serial.print(unite);
}

// ========================================================================
void traiterCapteur(EtatCapteur& c) {

  // Acquisition
  float somme_rms    = 0.0f;
  float somme_centre = 0.0f;
  int   abs_min = 1023, abs_max = 0;

  for (int i = 0; i < NB_FENETRES; i++) {
    Fenetre f = acquerir(c.pin);
    somme_rms    += f.rms;
    somme_centre += f.centre;
    if (f.vMin < abs_min) abs_min = f.vMin;
    if (f.vMax > abs_max) abs_max = f.vMax;
  }

  unsigned long maintenant = millis();
  float rms_moy    = somme_rms    / (float)NB_FENETRES;
  float centre_moy = somme_centre / (float)NB_FENETRES;
  int   amplitude  = abs_max - abs_min;
  float courant_A  = K * rms_moy;
  float puissance  = TENSION_V * courant_A;

  // Hysteresis
  bool etat_avant = c.actif;
  if (!c.actif && amplitude > c.seuil_on)  c.actif = true;
  if ( c.actif && amplitude < c.seuil_off) c.actif = false;

  if (c.actif) { c.somme_rms_on += rms_moy; c.nb_rms_on++; }

  // ---- Evenement ON ----
  if (c.actif && !etat_avant) {
    c.nb_connexions++;
    c.somme_rms_on = 0.0f;
    c.nb_rms_on    = 0;
    Serial.println(F("---"));
    printTemps(maintenant);
    Serial.print(F("  +++ ")); Serial.print(c.label_on);
    Serial.print(F("  #")); Serial.print(c.nb_connexions);
    Serial.print(F("  [")); Serial.print(c.id); Serial.println(F("]"));
    c.t_debut = maintenant;
  }

  // ---- Evenement OFF ----
  if (!c.actif && etat_avant) {
    c.nb_deconnexions++;
    float rms_on   = (c.nb_rms_on > 0) ? (c.somme_rms_on / (float)c.nb_rms_on) : 0.0f;
    float cour_moy = K * rms_on;
    float puis_moy = TENSION_V * cour_moy;

    printTemps(maintenant);
    Serial.print(F("  --- ")); Serial.print(c.label_off);
    Serial.print(F("  #")); Serial.print(c.nb_deconnexions);
    Serial.print(F("  [")); Serial.print(c.id);
    Serial.print(F("]  Duree=")); printDuree(maintenant - c.t_debut);
    Serial.println();
    Serial.print(F("    "));
    printMesure(F("Courant"),   cour_moy, 3, F("A"));
    printMesure(F("Tension"),   TENSION_V, 0, F("V"));
    printMesure(F("Puissance"), puis_moy,  1, F("W"));
    printMesure(F("K"),         K,         5, F(""));
    Serial.println();
    Serial.println(F("---"));

    c.t_debut      = maintenant;
    c.somme_rms_on = 0.0f;
    c.nb_rms_on    = 0;
  }

  // ---- Statut continu ----
  printTemps(maintenant);
  Serial.print(F("  [")); Serial.print(c.id); Serial.print(F("]"));
  Serial.print(F("  Centre=")); Serial.print((int)centre_moy);
  Serial.print(F("  Ampl="));   Serial.print(amplitude);

  if (c.actif) {
    Serial.print(F("  [ON ]"));
    printMesure(F("Courant"),   courant_A, 3, F("A"));
    printMesure(F("Tension"),   TENSION_V, 0, F("V"));
    printMesure(F("Puissance"), puissance, 1, F("W"));
  } else {
    Serial.print(F("  [OFF]"));
  }

  if (abs_max >= SEUIL_ECRET_HAUT) Serial.print(F("  !ECRET_HAUT -> baisser pot"));
  if (abs_min <= SEUIL_ECRET_BAS && amplitude > AMP_ECRET_BAS) Serial.print(F("  !ECRET_BAS"));

  Serial.println();
}

// ========================================================================
void setup() {
  Serial.begin(9600);
  Serial.println(F("=== ZMCT103C - LOGGER 2 CAPTEURS ==="));
  Serial.print(F("Capteurs   : "));
  for (int i = 0; i < NB_CAPTEURS; i++) {
    if (i > 0) Serial.print(F(" | "));
    Serial.print(capteurs[i].id);
    Serial.print(F(" -> A")); Serial.print(capteurs[i].pin - A0);
  }
  Serial.println();
  Serial.print(F("R_BURDEN   = ")); printFloat(R_BURDEN, 0); Serial.println(F(" Ohm"));
  Serial.print(F("N. tours   = ")); printFloat(N_TURNS,  0); Serial.println(F(":1"));
  Serial.print(F("Tension    = ")); printFloat(TENSION_V,0); Serial.println(F(" V"));
  Serial.print(F("K calcule  = ")); printFloat(K,        5); Serial.println(F(" A/ADC"));
  Serial.println(F("---"));
}

void loop() {
  for (int i = 0; i < NB_CAPTEURS; i++) {
    traiterCapteur(capteurs[i]);
  }
}
