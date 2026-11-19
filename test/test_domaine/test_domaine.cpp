/*
  Tests du DOMAINE du firmware (détection, grandeurs électriques, trame JSON) : de la logique
  pure, sans ESP32. Ils tournent sur le PC :
      pio test -e native
  (PlatformIO installe tout seul le compilateur sous Windows.) Les valeurs attendues sont celles
  du comportement mesuré sur la carte : ne pas les « arranger » pour faire passer un test.
*/
#include "domaine/Capteur.h"
#include "domaine/Detection.h"
#include "domaine/Electrique.h"
#include "domaine/Trame.h"
#include <string.h>
#include <unity.h>

using namespace Reglages;

void setUp() {}
void tearDown() {}

// Un capteur « éteint » au bruit donné, seuils calculés
static EtatCapteur capteurAuRepos(float bruit) {
  EtatCapteur c = {};
  c.id = "Capteur_1";
  c.seuilOn = SEUIL_ON_DEFAUT;
  c.seuilOff = SEUIL_OFF_DEFAUT;
  c.offset = 2048.0f;
  c.bruit = bruit;
  Detection::calculerSeuils(c);
  return c;
}

// ------------------------------------------------------------------ Detection
void test_seuils_sont_des_multiples_du_bruit() {
  EtatCapteur c = capteurAuRepos(10.0f);
  // allumé : max(2,5 x 10 ; 10 + 15) = 25 ; éteint : max(1,6 x 10 ; 10 + 7,5) = 17,5
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 25.0f, c.seuilOnEff);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 17.5f, c.seuilOffEff);
  EtatCapteur fort = capteurAuRepos(40.0f); // bruit élevé : le facteur domine
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 100.0f, fort.seuilOnEff);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 64.0f, fort.seuilOffEff);
}

void test_allumage_demande_deux_fenetres_d_affilee() {
  EtatCapteur c = capteurAuRepos(10.0f);
  Detection::evaluer(c, 100.0f, 100.0f, false);
  TEST_ASSERT_FALSE(c.actif); // anti-rebond : une seule fenêtre ne suffit pas
  TEST_ASSERT_EQUAL_UINT8(1, c.cptConfirm);
  Detection::evaluer(c, 100.0f, 100.0f, false);
  TEST_ASSERT_TRUE(c.actif);
  TEST_ASSERT_EQUAL_UINT8(0, c.cptConfirm);
}

void test_un_pic_isole_ne_fait_pas_allumer() {
  EtatCapteur c = capteurAuRepos(10.0f);
  Detection::evaluer(c, 100.0f, 100.0f, false); // pic
  Detection::evaluer(c, 8.0f, 8.0f, false);     // retour au calme
  TEST_ASSERT_FALSE(c.actif);
  TEST_ASSERT_EQUAL_UINT8(0, c.cptConfirm); // le compteur repart de zéro
}

void test_extinction_par_hysteresis() {
  EtatCapteur c = capteurAuRepos(10.0f);
  c.actif = true;
  // Entre le seuil d'extinction (17,5) et celui d'allumage (25) : reste allumé
  Detection::evaluer(c, 20.0f, 20.0f, false);
  Detection::evaluer(c, 20.0f, 20.0f, false);
  TEST_ASSERT_TRUE(c.actif);
  // Sous le seuil d'extinction, deux fenêtres d'affilée : éteint
  Detection::evaluer(c, 5.0f, 5.0f, false);
  TEST_ASSERT_TRUE(c.actif);
  Detection::evaluer(c, 5.0f, 5.0f, false);
  TEST_ASSERT_FALSE(c.actif);
}

void test_extinction_suit_la_fenetre_brute_pas_seulement_la_moyenne() {
  EtatCapteur c = capteurAuRepos(10.0f);
  c.actif = true;
  // Moyenne encore haute, fenêtre brute basse : le retour à « éteint » compte (14/10/2026)
  Detection::evaluer(c, 5.0f, 300.0f, false);
  Detection::evaluer(c, 5.0f, 300.0f, false);
  TEST_ASSERT_FALSE(c.actif);
}

void test_relais_ouvert_force_eteint_sans_apprentissage() {
  EtatCapteur c = capteurAuRepos(10.0f);
  c.actif = true;
  c.cptConfirm = 1;
  Detection::evaluer(c, 400.0f, 400.0f, true); // du bruit sur un fil coupé
  TEST_ASSERT_FALSE(c.actif);
  TEST_ASSERT_EQUAL_UINT8(0, c.cptConfirm);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 10.0f, c.bruit); // le bruit n'a pas bougé
}

void test_bruit_suivi_par_pas_de_5_pour_cent() {
  EtatCapteur c = capteurAuRepos(10.0f);
  Detection::evaluer(c, 12.0f, 12.0f, false); // au-dessus du bruit, sous le seuil
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 10.5f, c.bruit);
  Detection::evaluer(c, 8.0f, 8.0f, false); // sous le bruit
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 9.975f, c.bruit);
}

void test_bruit_borne_entre_min_et_max() {
  EtatCapteur haut = capteurAuRepos(49.9f);
  haut.seuilOnEff = 1000.0f; // pour que la fenêtre reste « sous le seuil »
  Detection::evaluer(haut, 60.0f, 60.0f, false);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, BRUIT_MAX, haut.bruit);

  EtatCapteur bas = capteurAuRepos(5.1f);
  Detection::evaluer(bas, 0.0f, 0.0f, false);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, BRUIT_MIN, bas.bruit);
}

void test_un_appareil_detecte_n_est_jamais_appris_comme_bruit() {
  EtatCapteur c = capteurAuRepos(10.0f);
  c.actif = true;
  Detection::evaluer(c, 500.0f, 500.0f, false);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 10.0f, c.bruit);
}

void test_bruit_de_depart_est_la_mediane() {
  float v[NB_FENETRES_BRUIT_DEPART] = {8, 1, 7, 2, 6, 3, 5, 4};
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 4.5f, Detection::bruitDeDepart(v));
}

void test_lissage_moyenne_glissante() {
  Lissage l = {};
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 3.0f, Detection::lisser(l, 3.0f));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 4.0f, Detection::lisser(l, 5.0f));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 5.0f, Detection::lisser(l, 7.0f));
  // 4e valeur : la plus ancienne (3) sort -> moyenne de 5, 7, 9
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 7.0f, Detection::lisser(l, 9.0f));
}

// ------------------------------------------------------------------ Electrique
void test_tension_reste_entre_220_et_230_volts() {
  for (int t = 0; t < 600; t++) {
    for (int a = -60; a <= 60; a += 30) {
      float u = Electrique::tensionSecteurV((float)t, a / 100.0f);
      TEST_ASSERT_TRUE(u >= TENSION_MIN_V);
      TEST_ASSERT_TRUE(u <= TENSION_MAX_V);
    }
  }
}

void test_courant_nul_sous_le_bruit() {
  TEST_ASSERT_EQUAL_FLOAT(0.0f, Electrique::courantA(8.0f, 10.0f));
}

void test_courant_est_k_fois_la_racine_de_la_puissance_nette() {
  // puissance nette 100 -> RMS 10 -> courant K x 10
  TEST_ASSERT_FLOAT_WITHIN(0.0001f, K * 10.0f, Electrique::courantA(110.0f, 10.0f));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 224.5f * 0.5f, Electrique::puissanceW(224.5f, 0.5f));
}

// ------------------------------------------------------------------ Trame
void test_trame_sans_releve() {
  char buf[300];
  bool inclus = true;
  Trame::construireMesure(buf, sizeof(buf), 1, "ON", 0.123f, 27.6f, 1731999999UL,
                          false, nullptr, &inclus);
  TEST_ASSERT_FALSE(inclus);
  TEST_ASSERT_EQUAL_STRING("{\"capteur_index\":1,\"etat\":\"ON\",\"courant\":0.123,"
                           "\"puissance\":27.6,\"timestamp_unix\":1731999999,"
                           "\"coupe\":false}",
                           buf);
}

void test_trame_avec_releve_du_dht11() {
  char buf[300];
  bool inclus = false;
  ReleveAir r = {23.0f, 87.0f, 1731999990UL};
  Trame::construireMesure(buf, sizeof(buf), 2, "OFF", 0.0f, 0.0f, 1731999999UL,
                          true, &r, &inclus);
  TEST_ASSERT_TRUE(inclus);
  TEST_ASSERT_EQUAL_STRING("{\"capteur_index\":2,\"etat\":\"OFF\",\"courant\":0.000,"
                           "\"puissance\":0.0,\"timestamp_unix\":1731999999,"
                           "\"coupe\":true,\"temperature_c\":23.0,"
                           "\"humidite_pct\":87.0,\"releve_unix\":1731999990}",
                           buf);
}

void test_trame_trop_petite_ne_deborde_pas() {
  char buf[40];
  ReleveAir r = {23.0f, 87.0f, 1731999990UL};
  bool inclus = true;
  size_t n = Trame::construireMesure(buf, sizeof(buf), 1, "ON", 1.0f, 1.0f, 1UL,
                                     false, &r, &inclus);
  TEST_ASSERT_FALSE(inclus);
  TEST_ASSERT_TRUE(n < sizeof(buf));
  TEST_ASSERT_EQUAL_UINT(n, strlen(buf));
}

void test_ordres_de_coupure_du_serveur() {
  const char *rep = "{\"created\":1,\"coupe_1\":false,\"coupe_2\": true}";
  bool ordre = false;
  TEST_ASSERT_TRUE(Trame::lireOrdreCoupure(rep, 1, ordre));
  TEST_ASSERT_FALSE(ordre);
  TEST_ASSERT_TRUE(Trame::lireOrdreCoupure(rep, 2, ordre));
  TEST_ASSERT_TRUE(ordre);
}

void test_ordre_absent_ou_illisible_ne_change_rien() {
  bool ordre = true;
  TEST_ASSERT_FALSE(Trame::lireOrdreCoupure("{\"created\":1}", 1, ordre)); // ancien serveur
  TEST_ASSERT_TRUE(ordre);
  TEST_ASSERT_FALSE(Trame::lireOrdreCoupure("{\"coupe_1\":null}", 1, ordre));
  TEST_ASSERT_FALSE(Trame::lireOrdreCoupure("{\"coupe_1\"", 1, ordre));
  TEST_ASSERT_TRUE(ordre);
}

void test_releve_vraisemblable() {
  TEST_ASSERT_TRUE(Trame::releveVraisemblable(23.0f, 87.0f));
  TEST_ASSERT_FALSE(Trame::releveVraisemblable(0.0f, 0.0f)); // DHT11 en défaut
  TEST_ASSERT_FALSE(Trame::releveVraisemblable(60.0f, 50.0f));
  TEST_ASSERT_FALSE(Trame::releveVraisemblable(25.0f, 100.0f));
  TEST_ASSERT_TRUE(Trame::releveVraisemblable(DHT_T_MIN, DHT_H_MIN));
  TEST_ASSERT_TRUE(Trame::releveVraisemblable(DHT_T_MAX, DHT_H_MAX));
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_seuils_sont_des_multiples_du_bruit);
  RUN_TEST(test_allumage_demande_deux_fenetres_d_affilee);
  RUN_TEST(test_un_pic_isole_ne_fait_pas_allumer);
  RUN_TEST(test_extinction_par_hysteresis);
  RUN_TEST(test_extinction_suit_la_fenetre_brute_pas_seulement_la_moyenne);
  RUN_TEST(test_relais_ouvert_force_eteint_sans_apprentissage);
  RUN_TEST(test_bruit_suivi_par_pas_de_5_pour_cent);
  RUN_TEST(test_bruit_borne_entre_min_et_max);
  RUN_TEST(test_un_appareil_detecte_n_est_jamais_appris_comme_bruit);
  RUN_TEST(test_bruit_de_depart_est_la_mediane);
  RUN_TEST(test_lissage_moyenne_glissante);
  RUN_TEST(test_tension_reste_entre_220_et_230_volts);
  RUN_TEST(test_courant_nul_sous_le_bruit);
  RUN_TEST(test_courant_est_k_fois_la_racine_de_la_puissance_nette);
  RUN_TEST(test_trame_sans_releve);
  RUN_TEST(test_trame_avec_releve_du_dht11);
  RUN_TEST(test_trame_trop_petite_ne_deborde_pas);
  RUN_TEST(test_ordres_de_coupure_du_serveur);
  RUN_TEST(test_ordre_absent_ou_illisible_ne_change_rien);
  RUN_TEST(test_releve_vraisemblable);
  return UNITY_END();
}
