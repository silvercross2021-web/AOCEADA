#include "application/Demarrage.h"
#include "application/FileEnvoi.h"
#include "application/TacheReseau.h"
#include "config/Reglages.h"
#include "domaine/Detection.h"
#include "materiel/AcquisitionZmct.h"
#include "materiel/Capteurs.h"
#include "materiel/Dht11.h"
#include "materiel/Relais.h"
#include "reseau/ReponseServeur.h"
#include "reseau/Reseau.h"
#include "reseau/Tampon.h"
#include "systeme/Horloge.h"
#include "systeme/Journal.h"
#include "systeme/Stockage.h"
#include "systeme/VerrouRadio.h"
#include <Arduino.h>

using namespace Reglages;

namespace Demarrage {

namespace {

void demarrerServices() {
  Serial.begin(115200);
  AcquisitionZmct::initialiser();
  VerrouRadio::creer();
  Reseau::initialiser(); // serveur et journal UDP du 1er réseau, en attendant la connexion
  FileEnvoi::creer();
  // Les ordres de coupure reçus du serveur (Wi-Fi ou USB) vont aux relais
  ReponseServeur::definirEcouteur(Relais::appliquerReponseServeur);
  Stockage::demarrer();
}

void demarrerMateriel() {
  Relais::initialiser();
  Dht11::initialiser();
  // Purge automatique au démarrage pour éliminer tout ancien tampon saturé qui bloquerait
  // l'envoi des nouvelles mesures en direct.
  Tampon::purgerAuDemarrage();
}

void connecterReseau() {
  Serial.println("\n=== ZMCT103C - AOCEDA IOT (Wi-Fi) ===");
  Reseau::afficherConfiguration();
  Reseau::demarrerRadio();
  Reseau::diagnostiquer();

  // Chaque réseau dans l'ordre, deux tours au plus (une box peut mettre du temps)
  bool connecte = false;
  for (int tour = 0; tour < 2 && !connecte; tour++)
    connecte = Reseau::connecter(10000);

  if (connecte) {
    Horloge::synchroniser();
  } else {
    Serial.println(
        "\nWiFi indisponible pour l'instant : demarrage en mode hors-ligne "
        "(mesures mises en tampon), reconnexion automatique en arriere-plan.");
  }
}

// Bruit de départ : médiane de 8 fenêtres par capteur, appareils coupés par les relais
// (Relais::retenus) : ce qui est mesuré n'est que du bruit, propre à chaque capteur. Le suivi
// continu corrige ensuite les écarts (changement d'alimentation, Wi-Fi...).
void mesurerBruitDeDepart() {
  Serial.println("Stabilisation offset...");
  for (int i = 0; i < 5; i++)
    for (int j = 0; j < Capteurs::NB; j++)
      AcquisitionZmct::fenetre(Capteurs::etat[j]);

  float valeurs[Capteurs::NB][NB_FENETRES_BRUIT_DEPART];
  for (int i = 0; i < NB_FENETRES_BRUIT_DEPART; i++)
    for (int j = 0; j < Capteurs::NB; j++)
      valeurs[j][i] = AcquisitionZmct::fenetre(Capteurs::etat[j]).secteur;
  for (int j = 0; j < Capteurs::NB; j++) {
    Capteurs::etat[j].bruit = Detection::bruitDeDepart(valeurs[j]);
    Detection::borneBruit(Capteurs::etat[j]);
  }
  for (int j = 0; j < Capteurs::NB; j++) {
    EtatCapteur &c = Capteurs::etat[j];
    Detection::calculerSeuils(c);
    Journal::ecrire(
        "[%s] Bruit de depart : %.0f -> seuils ON / OFF = %.0f / %.0f\n", c.id,
        c.bruit, c.seuilOnEff, c.seuilOffEff);
  }
  // Bruit mesuré : chaque appareil retrouve son ordre (y compris un ordre reçu du serveur
  // pendant la mesure)
  Relais::liberer();
  Journal::ecrire("Pret a mesurer !\n");
}

} // namespace

void executer() {
  demarrerServices();
  demarrerMateriel();
  connecterReseau();
  TacheReseau::demarrer();
  Serial.println("Canal de secours USB actif : si le Wi-Fi ou le serveur ne "
                 "repond pas, les mesures partent par ce cable vers le pont du "
                 "PC (AOCEDA/outils/pont_usb_esp32.py).");
  mesurerBruitDeDepart();
}

} // namespace Demarrage
