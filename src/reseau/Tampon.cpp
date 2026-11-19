#include "reseau/Tampon.h"
#include "config/Reglages.h"
#include "reseau/ClientHttp.h"
#include "systeme/Stockage.h"
#include <LittleFS.h>

using namespace Reglages;

namespace Tampon {

namespace {
const char *const CHEMIN = "/buffer.jsonl";
bool contientDesMesures = false;
} // namespace

void purgerAuDemarrage() {
  if (LittleFS.exists(CHEMIN)) {
    LittleFS.remove(CHEMIN);
    Stockage::prefs().putUInt("offset", 0);
    Serial.println("[TAMPON] Ancien tampon sature efface avec succes !");
  }
  contientDesMesures = false;
}

bool enAttente() { return contientDesMesures; }

void ajouter(const String &json) {
  size_t tailleActuelle = 0;
  if (contientDesMesures) {
    File f = LittleFS.open(CHEMIN, "r");
    if (f) {
      tailleActuelle = f.size();
      f.close();
    }
  }
  if (tailleActuelle >= MAX_BUFFER_BYTES) {
    Serial.println("[TAMPON] ERREUR : Espace plein (MAX_BUFFER_BYTES atteint). "
                   "La mesure est ignoree.");
    return;
  }
  File f = LittleFS.open(CHEMIN, "a");
  if (!f) {
    Serial.println("[TAMPON] ERREUR : Impossible d'ouvrir le fichier tampon.");
    return;
  }
  f.println(json);
  f.close();
  contientDesMesures = true;
  Serial.println("[TAMPON] SUCCES : Trame correctement empilee dans LittleFS.");
}

void rejouer() {
  if (!contientDesMesures)
    return;
  File f = LittleFS.open(CHEMIN, "r");
  if (!f) {
    contientDesMesures = false;
    return;
  }

  Preferences &prefs = Stockage::prefs();
  size_t taille = f.size();
  uint32_t offset = prefs.getUInt("offset", 0);
  if (offset >= taille) {
    f.close();
    LittleFS.remove(CHEMIN);
    prefs.putUInt("offset", 0);
    contientDesMesures = false;
    return;
  }

  f.seek(offset);
  int rejouees = 0;
  while (rejouees < MAX_REJEU_PAR_TOUR && f.available()) {
    String ligne = f.readStringUntil('\n');
    size_t octetsLigne =
        ligne.length() + 1; // + '\n' consommé par readStringUntil
    ligne.trim();
    if (ligne.length() == 0) {
      offset += octetsLigne;
      continue;
    }

    if (!ClientHttp::envoyer(ligne)) {
      Serial.println("[TAMPON] INTERROMPU : Echec pendant le rejeu. La purge "
                     "reprendra plus tard.");
      break;
    }
    offset += octetsLigne;
    rejouees++;
  }
  f.close();

  if (rejouees > 0) {
    prefs.putUInt("offset", offset);
    Serial.printf("[TAMPON] PURGE PARTIELLE : %d mesure(s) rejouee(s) (offset "
                  "%lu / %lu octets).\n",
                  rejouees, (unsigned long)offset, (unsigned long)taille);
  }
  if (offset >= taille) {
    LittleFS.remove(CHEMIN);
    prefs.putUInt("offset", 0);
    contientDesMesures = false;
    Serial.println("[TAMPON] PURGE TERMINEE : Toutes les donnees ont ete "
                   "rejouees sans perte. Fichier efface.");
  }
}

} // namespace Tampon
