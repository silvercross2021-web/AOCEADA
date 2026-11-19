#include "application/TacheReseau.h"
#include "application/FileEnvoi.h"
#include "config/Reglages.h"
#include "domaine/Trame.h"
#include "materiel/Capteurs.h"
#include "materiel/Dht11.h"
#include "materiel/Relais.h"
#include "reseau/CanalUsb.h"
#include "reseau/ClientHttp.h"
#include "reseau/Reseau.h"
#include "reseau/Tampon.h"
#include "systeme/Horloge.h"
#include <Arduino.h>

using namespace Reglages;

namespace TacheReseau {

namespace {

// Trame JSON d'une mesure, avec le relevé du DHT11 s'il n'est pas encore parti. Son numéro
// est rendu dans releveJoint (0 = aucun) : l'appelant le marque « parti » seulement une fois
// la trame envoyée, acquittée ou mise en tampon.
// « coupe » : état réel du relais au moment de l'envoi. Le serveur ne s'en sert que pour une
// mesure récente (pas pour une mesure rejouée depuis le tampon).
String construireTrame(const MesureAEnvoyer &d, uint32_t &releveJoint) {
  int local = Capteurs::indexLocal(d.capteur);
  bool relaisCoupe = (local >= 0) && Relais::estCoupe(local);
  ReleveAir releve;
  releveJoint = Dht11::releveAJoindre(releve);
  char buf[300];
  bool inclus = false;
  Trame::construireMesure(buf, sizeof(buf), Capteurs::indexServeur(d.capteur),
                          d.etat, d.courant, d.puissance, d.timestamp,
                          relaisCoupe, releveJoint ? &releve : nullptr,
                          &inclus);
  if (!inclus)
    releveJoint = 0;
  return String(buf);
}

// Envoie une mesure : Wi-Fi, sinon USB, sinon tampon. true si elle est « partie » (envoyée,
// acquittée par le pont ou mise en tampon).
bool acheminer(const MesureAEnvoyer &data, const String &json, bool connecte) {
  if (connecte && ClientHttp::envoyer(json)) {
    Serial.printf("[HTTP] [%s] TRAME ENVOYEE AVEC SUCCES : %s\n", data.capteur,
                  json.c_str());
    return true;
  }
  if (CanalUsb::envoyer(json)) {
    // Wi-Fi ou serveur indisponible : la mesure est passée par le câble USB et le pont du PC
    // l'a transmise à Django (accusé reçu)
    Serial.printf("[USB] [%s] TRAME ENVOYEE PAR USB (acquittee par le pont "
                  "du PC)\n",
                  data.capteur);
    return true;
  }
  // Ne met en tampon que les mesures ON horodatées pour ne jamais saturer LittleFS avec des
  // trames OFF (0 W) ou timestamp_unix=0.
  if (strcmp(data.etat, "ON") == 0 && data.puissance > 0.0f &&
      data.timestamp >= Horloge::TIMESTAMP_MIN_VALIDE) {
    Tampon::ajouter(json);
    Serial.printf("[HTTP] [%s] ECHEC D'ENVOI (Hors-ligne), TRAME MISE EN "
                  "TAMPON : %s\n",
                  data.capteur, json.c_str());
    return true; // le relevé voyage avec la trame tamponnée
  }
  Serial.printf("[HTTP] [%s] ECHEC D'ENVOI (trame %s non tamponnee)\n",
                data.capteur, data.etat);
  return false;
}

void tacheEnvoi(void *) {
  MesureAEnvoyer data;

  while (1) {
    bool recu = FileEnvoi::recevoir(data, 2000);
    if (recu)
      FileEnvoi::definirEnvoiEnCours(true);

    // Connecté mais le serveur ne répond plus (PC passé sur l'autre réseau, serveur
    // arrêté...) : on se déconnecte pour que la tâche Wi-Fi réessaie tous les réseaux
    if (Reseau::connecte() &&
        ClientHttp::echecsSansReponse() >= ECHECS_AVANT_AUTRE_RESEAU) {
      Serial.printf(
          "[WiFi] %d envois sans reponse du serveur sur \"%s\" : essai des "
          "autres reseaux.\n",
          ClientHttp::echecsSansReponse(), Reseau::ssidActif());
      ClientHttp::reinitialiserEchecs();
      Reseau::forcerReconnexion();
    }
    // La reconnexion elle-même est faite par tacheWifi : une tentative bloque jusqu'à ~8 s
    // par réseau, ce qui affamerait l'envoi (HTTP, tampon, USB).
    bool connecte = Reseau::connecte();

    if (recu) {
      uint32_t releveJoint = 0;
      String json = construireTrame(data, releveJoint);
      bool partie = acheminer(data, json, connecte);
      // Le relevé n'est marqué « parti » que si sa trame l'est : sinon il sera joint à la
      // prochaine trame (une trame OFF perdue n'emporte pas de relevé)
      if (partie && releveJoint != 0)
        Dht11::releveParti(releveJoint);
      FileEnvoi::definirEnvoiEnCours(false);
    }

    if (connecte && Tampon::enAttente() && FileEnvoi::enAttente() == 0) {
      FileEnvoi::definirEnvoiEnCours(true);
      Tampon::rejouer();
      FileEnvoi::definirEnvoiEnCours(false);
    }
    vTaskDelay(pdMS_TO_TICKS(10)); // laisse la tâche IDLE de FreeRTOS respirer
  }
}

void tacheWifi(void *) {
  while (1) {
    if (Reseau::reconnecterSiBesoin())
      Horloge::synchroniser();
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

} // namespace

void demarrer() {
  // Pile augmentée (8192, contre 4096 avant) : String / HTTPClient / LittleFS ensemble
  // consomment davantage que le simple appel HTTP d'origine.
  xTaskCreatePinnedToCore(tacheEnvoi, "HTTP Task", PILE_TACHE_RESEAU, NULL, 1,
                          NULL, 0);
  xTaskCreatePinnedToCore(tacheWifi, "WiFi Task", PILE_TACHE_RESEAU, NULL, 1,
                          NULL, 0);
}

} // namespace TacheReseau
