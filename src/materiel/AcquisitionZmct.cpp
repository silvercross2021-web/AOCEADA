#include "materiel/AcquisitionZmct.h"
#include "systeme/VerrouRadio.h"
#include <Arduino.h>

using namespace Reglages;

/*
  Détection par les fréquences du secteur (test guidé sur la carte, 12/10/2026).
  La radio Wi-Fi de l'ESP32 brouille l'ADC. Variance totale au repos, tout éteint :
    Wi-Fi coupé 348 / 744 (stable) ; Wi-Fi connecté 1967 / 3102 ; Wi-Fi + envois HTTP
    3860 / 5464, avec des pointes à 6553 (Capteur_1 / Capteur_2).
  Les anciens seuils (variance > bruit + 400 / + 70) avaient été réglés sans Wi-Fi : le bruit
  seul les dépassait (faux « allumé ») et le retour « éteint » était impossible. Le courant
  d'un appareil est à 50 Hz (+ harmoniques impaires), le brouillage Wi-Fi non : on ne mesure
  plus que ces fréquences (DFT calée sur l'horodatage réel de chaque échantillon). La
  détection porte sur 50 + 150 + 250 Hz, pas sur le 50 Hz seul : une lampe LED ou un chargeur
  consomment surtout en harmoniques (lampe : 50 Hz 140-485, harmoniques 295-470 ; chargeur
  de PC : 1 619-5 920 et 4 468-9 168). Mesures sur la carte avec Wi-Fi + envois : repos 7-77,
  lampe 451-934, chargeur de PC 6 087-15 088.
  Unité des seuils : « puissance » = carré du RMS de la composante, en points ADC^2 (même
  échelle que l'ancienne variance).
  Harmoniques 150 / 250 Hz mesurées par sous-fenêtres de 10 périodes : la fréquence du
  réseau dérive (49,8-50,2 Hz), et sur 1 s entière une harmonique décalée de 1 Hz
  s'annulerait.
*/

namespace AcquisitionZmct {

namespace {
float tableCos[TAILLE_TABLE], tableSin[TAILLE_TABLE];
}

void initialiser() {
  for (int i = 0; i < TAILLE_TABLE; i++) {
    tableCos[i] = cosf(2.0f * PI * i / TAILLE_TABLE);
    tableSin[i] = -sinf(2.0f * PI * i / TAILLE_TABLE);
  }
}

// Une fenêtre de mesure : variance totale (comparaison), puissance à 50 Hz et à
// 150 + 250 Hz (courant de l'appareil).
// Pour une composante A.cos(wt + phi), I = moyenne(x.cos), Q = moyenne(x.sin) donnent A^2/4,
// d'où puissance = 2(I^2 + Q^2) = A^2/2 = RMS^2. Les échantillons sont recentrés sur le point
// milieu de la fenêtre précédente ; le petit écart restant est retranché à la fin (termes en d).
Mesure fenetre(EtatCapteur &c) {
  analogRead(c.pin); // Lecture à vide pour commuter et stabiliser le MUX ADC
  const float off = c.offset;
  uint64_t sumX = 0;
  uint64_t sumX2 = 0;
  uint32_t n = 0;
  int vMin = 4095, vMax = 0;
  float c1 = 0, s1 = 0, sc1 = 0,
        ss1 = 0; // 50 Hz, cohérent sur toute la fenêtre

  // Harmoniques : une DFT par sous-fenêtre, puissances moyennées
  float cr[NB_RAIES_SOUS] = {0}, sr[NB_RAIES_SOUS] = {0};
  float scr[NB_RAIES_SOUS] = {0}, ssr[NB_RAIES_SOUS] = {0};
  float sxSous = 0, pHarmSomme = 0;
  uint32_t nSous = 0, sousCourante = 0, nbSous = 0;
  auto fermerSousFenetre = [&]() {
    if (nSous == 0)
      return;
    float d = sxSous / nSous;
    for (int r = 0; r < NB_RAIES_SOUS; r++) {
      float I = (cr[r] - d * scr[r]) / nSous, Q = (sr[r] - d * ssr[r]) / nSous;
      pHarmSomme += 2.0f * (I * I + Q * Q);
      cr[r] = sr[r] = scr[r] = ssr[r] = 0;
    }
    nbSous++;
    sxSous = 0;
    nSous = 0;
  };

  // Radio réservée à la mesure pendant toute la fenêtre (un envoi en cours se termine
  // d'abord). Si le réseau la garde trop longtemps, on mesure quand même.
  bool verrou = VerrouRadio::prendre(ATTENTE_RADIO_MAX_MS);
  const uint32_t debut = micros();
  const uint32_t duree = FENETRE_MS * 1000UL;
  for (;;) {
    uint32_t t = micros() - debut;
    if (t >= duree)
      break;
    int brut = analogRead(c.pin);
    if (t / SOUS_FENETRE_US != sousCourante) {
      fermerSousFenetre();
      sousCourante = t / SOUS_FENETRE_US;
    }
    float xc = (float)brut - off;
    int i1 = (t % PERIODE_SECTEUR_US) / PAS_TABLE_US;
    c1 += xc * tableCos[i1];
    s1 += xc * tableSin[i1];
    sc1 += tableCos[i1];
    ss1 += tableSin[i1];
    // raie à 25 x M Hz : phase = t x M / 2 rapportée à la période du 50 Hz
    for (int r = 0; r < NB_RAIES_SOUS; r++) {
      int i = (((t * MULT_25HZ[r]) >> 1) % PERIODE_SECTEUR_US) / PAS_TABLE_US;
      cr[r] += xc * tableCos[i];
      sr[r] += xc * tableSin[i];
      scr[r] += tableCos[i];
      ssr[r] += tableSin[i];
    }
    sxSous += xc;
    nSous++;
    sumX += (uint64_t)brut;
    sumX2 += (uint64_t)brut * (uint64_t)brut;
    if (brut < vMin)
      vMin = brut;
    if (brut > vMax)
      vMax = brut;
    n++;
  }
  if (verrou)
    VerrouRadio::rendre();
  fermerSousFenetre();

  Mesure m = {0.0f, 0.0f, 0.0f, 0.0f, vMin, vMax};
  if (n == 0)
    return m;
  double moy = (double)sumX / (double)n;
  m.var = (float)(((double)sumX2 / (double)n) - (moy * moy));
  float d = (float)(moy - off);
  float I1 = (c1 - d * sc1) / n, Q1 = (s1 - d * ss1) / n;
  m.p50 = 2.0f * (I1 * I1 + Q1 * Q1);
  m.pHarm = nbSous ? pHarmSomme / nbSous : 0.0f;
  m.secteur = m.p50 + m.pHarm;
  c.offset = (float)moy;
  return m;
}

} // namespace AcquisitionZmct
