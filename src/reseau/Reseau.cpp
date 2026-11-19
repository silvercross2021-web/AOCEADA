#include "reseau/Reseau.h"
#include "config/Reglages.h"
#include "config/Identifiants.h"
#include "systeme/Journal.h"
#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>

namespace Reseau {

namespace {

struct ReseauWifi {
  const char *ssid;
  const char *motDePasse;
  const char *serveur;
};

// Mot de passe pas encore saisi : le réseau est sauté
const char *const A_REMPLIR = "A_REMPLIR";

const ReseauWifi RESEAUX[] = {AOCEDA_RESEAUX_WIFI};
const int NB_RESEAUX = sizeof(RESEAUX) / sizeof(RESEAUX[0]);

int actif = 0; // réseau en cours (ou dernier essayé)
const char *serveurActif = RESEAUX[0].serveur;
unsigned long derniereTentative = 0;

void choisir(int i) {
  actif = i;
  serveurActif = RESEAUX[i].serveur;
  Journal::definirDestinataire(serveurActif);
}

// Diagnostic de joignabilité du serveur : distingue clairement « IP du serveur périmée »
// (erreur de connexion, code <= 0 : refusé / timeout) d'une simple absence de réseau. Un
// GET sur l'URL d'envoi suffit : même si Django répond 405 (méthode non autorisée), une
// réponse HTTP prouve que l'IP et le port sont corrects.
bool serveurJoignable() {
  HTTPClient http;
  http.begin(serveurActif);
  http.setTimeout(Reglages::TIMEOUT_HTTP_MS);
  int code = http.GET();
  if (code > 0) {
    Serial.printf("[Serveur] Joignable a %s (code HTTP %d).\n", serveurActif,
                  code);
  } else {
    Serial.printf("[Serveur] INJOIGNABLE a %s (erreur %d : %s).\n"
                  "  -> Serveur pas lance, PC sur un autre reseau, ou IP du PC "
                  "changee (DHCP) : verifie avec `ipconfig`\n"
                  "     (adaptateur Wi-Fi) et mets a jour AOCEDA_RESEAUX_WIFI "
                  "dans include/secrets.h.\n",
                  serveurActif, code, http.errorToString(code).c_str());
  }
  http.end();
  return code > 0;
}

bool joindre(int i, unsigned long attenteMs) {
  const ReseauWifi &r = RESEAUX[i];
  Serial.printf("[WiFi] Essai de \"%s\"...\n", r.ssid);
  WiFi.disconnect();
  WiFi.begin(r.ssid, r.motDePasse);
  unsigned long debut = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - debut < attenteMs)
    delay(300);
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("[WiFi] \"%s\" : pas de connexion (absent, hors de portee ou "
                  "mauvais mot de passe).\n",
                  r.ssid);
    return false;
  }
  choisir(i);
  Serial.printf("[WiFi] Connecte a \"%s\" ! IP de l'ESP32 = %s\n", r.ssid,
                WiFi.localIP().toString().c_str());
  return true;
}

} // namespace

void initialiser() { choisir(0); }

void demarrerRadio() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(1000);
}

void afficherConfiguration() {
  for (int i = 0; i < NB_RESEAUX; i++)
    Serial.printf("Reseau %d : \"%s\" -> serveur %s\n", i + 1, RESEAUX[i].ssid,
                  RESEAUX[i].serveur);
}

void diagnostiquer() {
  Serial.println("\n[SCAN] Reseaux Wi-Fi 2,4 GHz visibles :");
  int nbReseaux = WiFi.scanNetworks();
  if (nbReseaux <= 0) {
    Serial.println("  (aucun reseau detecte)");
  } else {
    for (int i = 0; i < nbReseaux; i++) {
      Serial.printf("  %2d) \"%s\"  RSSI=%d dBm  canal=%d  %s\n", i + 1,
                    WiFi.SSID(i).c_str(), WiFi.RSSI(i), WiFi.channel(i),
                    (WiFi.encryptionType(i) == WIFI_AUTH_OPEN) ? "ouvert"
                                                               : "protege");
    }
    for (int r = 0; r < NB_RESEAUX; r++) {
      bool vu = false;
      for (int i = 0; i < nbReseaux && !vu; i++)
        vu = WiFi.SSID(i) == String(RESEAUX[r].ssid);
      Serial.printf("[SCAN] Reseau \"%s\" %s dans le scan 2,4 GHz.\n",
                    RESEAUX[r].ssid,
                    vu ? "TROUVE"
                       : "ABSENT (=> eteint, hors de portee ou en 5 GHz)");
    }
  }
  WiFi.scanDelete();
}

bool connecte() { return WiFi.status() == WL_CONNECTED; }

const char *serveur() { return serveurActif; }

const char *ssidActif() { return RESEAUX[actif].ssid; }

bool connecter(unsigned long attenteMs) {
  int premierJoint = -1;
  for (int i = 0; i < NB_RESEAUX; i++) {
    if (strcmp(RESEAUX[i].motDePasse, A_REMPLIR) == 0) {
      Serial.printf("[WiFi] \"%s\" saute : mot de passe a remplir dans "
                    "include/secrets.h.\n",
                    RESEAUX[i].ssid);
      continue;
    }
    if (!joindre(i, attenteMs))
      continue;
    if (serveurJoignable())
      return true;
    if (premierJoint < 0)
      premierJoint = i;
  }
  if (premierJoint < 0)
    return false;
  if (actif != premierJoint || WiFi.status() != WL_CONNECTED)
    joindre(premierJoint, attenteMs);
  Serial.println(
      "[WiFi] Serveur joignable sur aucun reseau : mesures en tampon.");
  return WiFi.status() == WL_CONNECTED;
}

bool reconnecterSiBesoin() {
  if (WiFi.status() == WL_CONNECTED)
    return false;

  unsigned long maintenant = millis();
  if (maintenant - derniereTentative < Reglages::INTERVALLE_RECONNEXION_MS)
    return false;
  derniereTentative = maintenant;

  Serial.println("[WiFi] Tentative de (re)connexion...");
  if (connecter(8000))
    return true;
  Serial.println("[WiFi] Toujours indisponible, nouvel essai dans 15 s.");
  return false;
}

void forcerReconnexion() {
  WiFi.disconnect();
  derniereTentative = 0; // reconnexion tout de suite
}

} // namespace Reseau
