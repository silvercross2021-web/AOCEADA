#include <Arduino.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <time.h>

/*
  ZMCT103C - LOGGER IoT POUR AOCEDA (ESP32 avec Wi-Fi)
*/

// ========================================================================
// ⚠️ CONFIGURATION WI-FI & SERVEUR (À REMPLIR PAR TOI) ⚠️
// ========================================================================
const char *ssid = "AXELTHONY 2.4G";
const char *password = "20062024";

// ⚠️ L'IP ci-dessous est celle du PC (serveur Django) sur le reseau Wi-Fi,
// attribuee par DHCP : elle CHANGE a chaque fois que le PC change de reseau (ou
// parfois au redemarrage du routeur/partage de connexion). Si l'ESP32 se
// connecte au Wi-Fi mais que tout finit en tampon ("[HTTP] Hors-ligne" /
// "[Tampon] Echec"), commence TOUJOURS par verifier cette IP : sur le PC,
// `ipconfig` -> adaptateur "Wi-Fi" -> "Adresse IPv4". Le message "[Serveur]
// INJOIGNABLE" au demarrage confirme ce cas.
const char *serverName = "http://192.168.1.7:8000/api/sensors/zmct/";
const char *apiKeyDevice = "c9f1d4e372a0b518642c3e8d1f059b27";

// ========================================================================
// Parametres electriques & Acquisition
// ========================================================================
const float V_REF = 3.3f;
const float R_BURDEN = 100.0f;
const float N_TURNS = 1000.0f;
const float K = (V_REF / 4096.0f) / R_BURDEN * N_TURNS;

const unsigned long FENETRE_MS =
    1000UL; // 1 seconde de filtrage complet pour stabiliser le bruit
const uint8_t CONFIRMATIONS = 2; // 2 * 1000ms = 2s de stabilité (anti-rebond)
const unsigned long INTERVALLE_ENVOI_HTTP_MS =
    1000; // Envoi régulier toutes les 1 seconde

const int SEUIL_ECRET_HAUT = 4000;
const int SEUIL_ECRET_BAS = 90;
const int AMP_ECRET_BAS = 240;

struct EtatCapteur {
  const char *id;
  uint8_t pin;
  float seuilOn;
  float seuilOff;
  const char *labelOn;
  const char *labelOff;
  float offset;
  bool actif;
  uint8_t cptConfirm;
  unsigned long t_debut;
  unsigned int nb_connexions;
  unsigned int nb_deconnexions;
  float somme_rms_on;
  unsigned long nb_rms_on;
  unsigned long last_send; // Temps du dernier envoi HTTP
  float bruit_variance;    // Bruit de fond calibré au démarrage
};

EtatCapteur capteurs[] = {
    // REALITE PHYSIQUE CONFIRMEE PAR LES LOGS :
    // Capteur_1 (GPIO 34) = AMPOULE : seuil ON=400 (bruit repos~100, signal
    // lampe~1150-1450)
    // Capteur_2 (GPIO 35) = PRISE   : seuil ON=70  (bruit repos~2, diaphonie
    // lampe=max 9,
    //                                                ventilateur~200-350, fer a
    //                                                repasser~5000+)
    {"Capteur_1", 34, 400.0f, 200.0f, "LAMPE ALLUMEE", "LAMPE ETEINTE", 2048.0f,
     false, 0, 0, 0, 0, 0.0f, 0UL, 0UL, 0.0f},
    {"Capteur_2", 35, 70.0f, 25.0f, "PRISE BRANCHEE", "PRISE LIBRE", 2048.0f,
     false, 0, 0, 0, 0, 0.0f, 0UL, 0UL, 0.0f},

};
const int NB_CAPTEURS = sizeof(capteurs) / sizeof(capteurs[0]);

struct Mesure {
  float var;
  float rms;
  int vMin;
  int vMax;
};

// ========================================================================
// File d'attente pour le réseau (Évite de bloquer les mesures !)
// ========================================================================
struct HttpData {
  char capteur[16];
  char etat[4];
  float courant;
  float puissance;
  unsigned long timestamp;
};

QueueHandle_t httpQueue;

// ========================================================================
// Tampon hors-ligne persistant (survit aux coupures WiFi/serveur ET aux
// redémarrages/coupures de courant, contrairement à une simple file en RAM) :
// un fichier LittleFS en JSON Lines (une mesure par ligne, ajoutée en fin de
// fichier), et un OFFSET d'octets déjà rejoués persisté en NVS (Preferences).
// Rejouer = relire depuis l'offset, jamais réécrire le fichier ligne par
// ligne (coûteux sur flash) ; une fois entièrement rejoué, le fichier est
// simplement supprimé et l'offset remis à zéro.
// ========================================================================
const char *BUFFER_PATH = "/buffer.jsonl";
const size_t MAX_BUFFER_BYTES = 300000; // ~300 Ko ≈ plusieurs heures de coupure
const int MAX_REJEU_PAR_TOUR = 20; // borne le temps passé à rejouer par cycle

Preferences prefs;
// Reflète en RAM l'existence du fichier tampon : évite d'appeler
// LittleFS.exists() à chaque cycle réseau (toutes les ~2 s) quand il n'y a rien
// à rejouer — l'appel VFS sous-jacent journalise une erreur bruyante à chaque
// essai sur un fichier absent (comportement connu du coeur Arduino
// ESP32/LittleFS), ce qui noierait le moniteur série en fonctionnement normal.
// Mis à jour UNIQUEMENT par bufferiser() (passe à true) et rejouerTampon()
// (repasse à false une fois le tampon vidé) — initialisé une seule fois au
// démarrage (voir setup()).
bool tamponEnAttente = false;

// ========================================================================
// Horodatage réel (NTP) : indispensable pour qu'une mesure mise en tampon
// garde SA vraie date d'acquisition quand elle est rejouée plus tard (voir
// timestamp_unix côté serveur, apps.sensors.views._horodatage_mesure) — sans
// ça, toute une coupure serait tassée sur quelques secondes au moment du
// rejeu au lieu d'être répartie sur sa vraie durée dans l'historique.
// Côte d'Ivoire = UTC+0, pas d'heure d'été : aucun décalage à appliquer.
// ========================================================================
const unsigned long TIMESTAMP_MIN_VALIDE =
    1700000000UL; // avant : pas encore synchronisé

void synchroniserHeure() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  Serial.print("Synchronisation NTP");
  unsigned long debut = millis();
  time_t maintenant = time(nullptr);
  while ((unsigned long)maintenant < TIMESTAMP_MIN_VALIDE &&
         millis() - debut < 10000) {
    delay(300);
    Serial.print(".");
    maintenant = time(nullptr);
  }
  if ((unsigned long)maintenant >= TIMESTAMP_MIN_VALIDE) {
    Serial.println(" OK");
  } else {
    Serial.println(" echec (les mesures tamponnees seront horodatees a la "
                   "reception serveur).");
  }
}

// 0 = pas d'heure fiable disponible -> le serveur utilisera l'heure de
// reception.
unsigned long heureActuelleUnix() {
  time_t t = time(nullptr);
  return ((unsigned long)t >= TIMESTAMP_MIN_VALIDE) ? (unsigned long)t : 0UL;
}

// Diagnostic de joignabilite du serveur : distingue clairement "IP serveur
// perimee" (erreur de connexion, code <= 0 : refuse/timeout) d'une simple
// absence de reseau, au lieu de laisser deviner via le flot generique de
// messages "hors-ligne" / "echec pendant le rejeu". Un GET sur l'URL d'envoi
// suffit : meme si Django repond 405 (methode non autorisee), une reponse HTTP
// prouve que l'IP/port sont corrects.
void verifierJoignabiliteServeur() {
  HTTPClient http;
  http.begin(serverName);
  http.setTimeout(3000);
  int code = http.GET();
  if (code > 0) {
    Serial.printf("[Serveur] Joignable a %s (code HTTP %d).\n", serverName,
                  code);
  } else {
    Serial.printf("[Serveur] INJOIGNABLE a %s (erreur %d : %s).\n"
                  "  -> L'IP du PC a probablement change (DHCP). Verifie avec "
                  "`ipconfig`\n"
                  "     (adaptateur Wi-Fi) et mets a jour 'serverName' en haut "
                  "de main.cpp.\n",
                  serverName, code, http.errorToString(code).c_str());
  }
  http.end();
}

// ========================================================================
// Reconnexion Wi-Fi NON BLOQUANTE : contrairement à l'ancienne version qui
// pouvait attendre indéfiniment au démarrage, chaque tentative est bornée
// dans le temps ; l'appareil démarre et continue de fonctionner (mesures
// mises en tampon) même si le réseau n'est pas encore disponible, et une
// reconnexion est retentée automatiquement en tâche de fond — plus besoin de
// débrancher/rebrancher manuellement après une coupure du partage de connexion.
// ========================================================================
unsigned long derniereTentativeWifi = 0;
const unsigned long INTERVALLE_RECONNEXION_MS = 15000;

bool assurerWifi() {
  if (WiFi.status() == WL_CONNECTED)
    return true;

  unsigned long maintenant = millis();
  if (maintenant - derniereTentativeWifi < INTERVALLE_RECONNEXION_MS)
    return false;
  derniereTentativeWifi = maintenant;

  Serial.println("[WiFi] Tentative de (re)connexion...");
  WiFi.disconnect();
  WiFi.begin(ssid, password);
  unsigned long debut = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - debut < 8000) {
    delay(300);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[WiFi] Connecte ! IP = ");
    Serial.println(WiFi.localIP());
    synchroniserHeure();
    verifierJoignabiliteServeur();
    return true;
  }
  Serial.println("[WiFi] Toujours indisponible, nouvel essai dans 15 s.");
  return false;
}

// ========================================================================
// Construction du JSON d'une mesure (partagée entre envoi direct et tampon).
// ========================================================================
String construireJsonMesure(const char *capteurId, const char *etat,
                            float courant, float puissance,
                            unsigned long horodatageUnix) {
  // Capteur_1 (GPIO 34) = AMPOULE physiquement -> index 2 dans Django ("Capteur
  // 2 - ampoule") Capteur_2 (GPIO 35) = PRISE physiquement   -> index 1 dans
  // Django ("Capteur 1 - prise")
  int idx = (strcmp(capteurId, "Capteur_1") == 0) ? 2 : 1;
  char buf[160];
  snprintf(buf, sizeof(buf),
           "{\"capteur_index\":%d,\"etat\":\"%s\",\"courant\":%.3f,"
           "\"puissance\":%.1f,\"timestamp_unix\":%lu}",
           idx, etat, courant, puissance, horodatageUnix);
  return String(buf);
}

bool envoyerJson(const String &json) {
  HTTPClient http;
  http.begin(serverName);
  http.addHeader("Content-Type", "application/json");
  char authHeader[100];
  snprintf(authHeader, sizeof(authHeader), "Device %s", apiKeyDevice);
  http.addHeader("Authorization", authHeader);
  http.setTimeout(3000);
  int code = http.POST(json);
  http.end();
  return code == 201;
}

// Ajoute une mesure au tampon persistant (échec d'envoi, WiFi ou serveur
// indisponible).
void bufferiser(const String &json) {
  size_t tailleActuelle = 0;
  if (tamponEnAttente) {
    File f = LittleFS.open(BUFFER_PATH, "r");
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
  File f = LittleFS.open(BUFFER_PATH, "a");
  if (!f) {
    Serial.println("[TAMPON] ERREUR : Impossible d'ouvrir le fichier tampon.");
    return;
  }
  f.println(json);
  f.close();
  tamponEnAttente = true;
  Serial.println("[TAMPON] SUCCES : Trame correctement empilee dans LittleFS.");
}

// Rejoue une partie du tampon (bornee à MAX_REJEU_PAR_TOUR mesures par appel,
// pour ne pas monopoliser la tâche réseau en cas de très longue coupure).
// Ne progresse (offset persisté) qu'après un envoi confirmé 201 — une coupure
// pendant le rejeu laisse le reste du tampon intact pour le prochain essai.
void rejouerTampon() {
  if (!tamponEnAttente)
    return;
  File f = LittleFS.open(BUFFER_PATH, "r");
  if (!f) {
    tamponEnAttente = false;
    return;
  }

  size_t taille = f.size();
  uint32_t offset = prefs.getUInt("offset", 0);
  if (offset >= taille) {
    f.close();
    LittleFS.remove(BUFFER_PATH);
    prefs.putUInt("offset", 0);
    tamponEnAttente = false;
    return;
  }

  f.seek(offset);
  int rejouees = 0;
  while (rejouees < MAX_REJEU_PAR_TOUR && f.available()) {
    String ligne = f.readStringUntil('\n');
    if (ligne.length() == 0)
      break;
    size_t octetsLigne =
        ligne.length() + 1; // + '\n' consomme par readStringUntil

    if (!envoyerJson(ligne)) {
      Serial.println("[TAMPON] INTERROMPU : Echec pendant le rejeu. La purge "
                     "reprendra plus tard.");
      break;
    }
    offset += octetsLigne;
    prefs.putUInt("offset", offset);
    rejouees++;
  }
  f.close();

  if (rejouees > 0) {
    Serial.printf("[TAMPON] PURGE PARTIELLE : %d mesure(s) rejouee(s) (offset "
                  "%lu / %lu octets).\n",
                  rejouees, (unsigned long)offset, (unsigned long)taille);
  }
  if (offset >= taille) {
    LittleFS.remove(BUFFER_PATH);
    prefs.putUInt("offset", 0);
    tamponEnAttente = false;
    Serial.println("[TAMPON] PURGE TERMINEE : Toutes les donnees ont ete "
                   "rejouees sans perte. Fichier efface.");
  }
}

// Tâche FreeRTOS d'arrière-plan pour le réseau : envoi direct si possible,
// sinon mise en tampon ; et rejeu du tampon dès que la connexion est là.
// Le timeout de xQueueReceive (au lieu de portMAX_DELAY) permet de vérifier
// le WiFi et de rejouer le tampon même quand aucune nouvelle mesure n'arrive.
void httpTask(void *pvParameters) {
  HttpData data;

  while (1) {
    bool recu =
        (xQueueReceive(httpQueue, &data, pdMS_TO_TICKS(2000)) == pdPASS);
    bool connecte = assurerWifi();

    if (connecte) {
      rejouerTampon();
    }

    if (recu) {
      String json = construireJsonMesure(data.capteur, data.etat, data.courant,
                                         data.puissance, data.timestamp);
      if (connecte && envoyerJson(json)) {
        Serial.printf("[HTTP] [%s] TRAME ENVOYEE AVEC SUCCES : %s\n",
                      data.capteur, json.c_str());
      } else {
        bufferiser(json);
        Serial.printf("[HTTP] [%s] ECHEC D'ENVOI (Hors-ligne), TRAME MISE EN "
                      "TAMPON : %s\n",
                      data.capteur, json.c_str());
      }
    }
  }
}

// Fonction utilitaire pour ajouter à la file d'envoi
void envoyerVersDjango(EtatCapteur &c, float courant, float puissance) {
  HttpData hd;
  // Utilisation de snprintf pour garantir la présence du '\0' final
  snprintf(hd.capteur, sizeof(hd.capteur), "%s", c.id);
  snprintf(hd.etat, sizeof(hd.etat), "%s", c.actif ? "ON" : "OFF");
  hd.courant = c.actif ? courant : 0.0f;
  hd.puissance = c.actif ? puissance : 0.0f;
  hd.timestamp = heureActuelleUnix();

  // Ajoute dans la file (sans bloquer si c'est plein)
  xQueueSend(httpQueue, &hd, 0);
}

// ========================================================================
Mesure acquerir(EtatCapteur &c) {
  analogRead(c.pin); // Lecture à vide pour commuter et stabiliser le MUX ADC
  unsigned long debut = millis();
  uint64_t sumX = 0;
  uint64_t sumX2 = 0;
  uint32_t n = 0;
  int vMin = 4095, vMax = 0;

  while (millis() - debut < FENETRE_MS) {
    int brut = analogRead(c.pin);
    sumX += (uint64_t)brut;
    sumX2 += (uint64_t)brut * (uint64_t)brut;
    if (brut < vMin)
      vMin = brut;
    if (brut > vMax)
      vMax = brut;
    n++;
  }

  Mesure m;
  m.vMin = vMin;
  m.vMax = vMax;

  if (n > 0) {
    double moy = (double)sumX / (double)n;
    double var = ((double)sumX2 / (double)n) - (moy * moy);
    m.var = (float)var;
    double var_nette = var - (double)c.bruit_variance;
    if (var_nette < 0.0)
      var_nette = 0.0;
    m.rms = (float)sqrt(var_nette);
    // Sauvegarde la variance brute pour le debug
    c.somme_rms_on = (float)var;
  } else {
    m.var = 0.0f;
    m.rms = 0.0f;
  }
  return m;
}

// ========================================================================
void traiterCapteur(EtatCapteur &c) {
  Mesure m = acquerir(c);
  float var = m.var;
  float rms = m.rms;
  float courant_A = K * rms;
  float puissance = 220.0f * courant_A;
  unsigned long maintenant = millis();
  bool etat_avant = c.actif;

  // Détection adaptative basée sur le Delta de variance
  if (!c.actif) {
    if (var >= (c.bruit_variance + c.seuilOn)) {
      c.cptConfirm++;
      if (c.cptConfirm >= CONFIRMATIONS) {
        c.actif = true;
        c.cptConfirm = 0;
      }
    } else {
      c.cptConfirm = 0;
      // Ligne de base adaptative : mise a jour UNIQUEMENT si le signal est dans
      // la zone de repos (en-dessous de seuilOff). Cela empeche un appareil de
      // faible puissance (ex: ventilateur ~30W) ou un demarrage progressif
      // d'etre absorbe dans le bruit de fond !
      if (var < (c.bruit_variance + c.seuilOff * 0.5f)) {
        c.bruit_variance = 0.98f * c.bruit_variance + 0.02f * var;
      }
    }
  } else {
    if (var < (c.bruit_variance + c.seuilOff)) {
      c.cptConfirm++;
      if (c.cptConfirm >= CONFIRMATIONS) {
        c.actif = false;
        c.cptConfirm = 0;
      }
    } else {
      c.cptConfirm = 0;
    }
  }

  if (c.actif) {
    c.somme_rms_on += rms;
    c.nb_rms_on++;
  }

  // ---- Evenement ON ----
  if (c.actif && !etat_avant) {
    c.nb_connexions++;
    c.somme_rms_on = 0.0f;
    c.nb_rms_on = 0;
    c.t_debut = maintenant;
    Serial.printf("[%s] ETAT : %s (RMS=%.1f)\n", c.id, c.labelOn, rms);

    // Envoi HTTP immédiat
    envoyerVersDjango(c, courant_A, puissance);
    c.last_send = maintenant;
  }

  // ---- Evenement OFF ----
  if (!c.actif && etat_avant) {
    c.nb_deconnexions++;
    c.t_debut = maintenant;
    c.somme_rms_on = 0.0f;
    c.nb_rms_on = 0;
    Serial.printf("[%s] ETAT : %s (RMS=%.1f)\n", c.id, c.labelOff, rms);

    // Envoi HTTP immédiat
    envoyerVersDjango(c, 0.0f, 0.0f);
    c.last_send = maintenant;
  }

  // ---- Envoi HTTP régulier (Toutes les X secondes) ----
  if (maintenant - c.last_send > INTERVALLE_ENVOI_HTTP_MS) {
    envoyerVersDjango(c, courant_A, puissance);
    c.last_send = maintenant;
    // Debug continu pour analyser le signal
    Serial.printf("[DEBUG-SIGNAL] %s | Brut Var: %.0f | Base Var: %.0f | RMS "
                  "Net: %.2f | Etat: %s\n",
                  c.id, c.somme_rms_on, c.bruit_variance, rms,
                  c.actif ? "ON" : "OFF");
  }
}

// ========================================================================
void setup() {
  Serial.begin(9600);

  // 1. Initialisation de la file pour le Wi-Fi (capacité de 20 requêtes)
  httpQueue = xQueueCreate(20, sizeof(HttpData));

  // 2. Tampon hors-ligne persistant (LittleFS + offset NVS)
  if (!LittleFS.begin(
          true)) { // true = formate automatiquement au tout premier boot
    Serial.println(
        "Erreur montage LittleFS : le tampon hors-ligne sera indisponible.");
  }
  prefs.begin("aoceda", false);
  // Nettoyage immédiat du tampon saturé pour repartir sur un direct 100% propre
  if (LittleFS.exists(BUFFER_PATH)) {
    LittleFS.remove(BUFFER_PATH);
    prefs.putUInt("offset", 0);
    Serial.println("[TAMPON] Ancien tampon sature efface avec succes !");
  }
  tamponEnAttente = false;

  // 3. Connexion Wi-Fi — BORNEE dans le temps (jamais de blocage indefini) :
  // si le reseau n'est pas encore la, l'appareil demarre quand meme et mesure
  // en mode hors-ligne ; assurerWifi() (appelee dans httpTask) reessaiera
  // automatiquement en arriere-plan, sans intervention manuelle.
  Serial.println("\n=== ZMCT103C - AOCEDA IOT (Wi-Fi) ===");
  Serial.print("Serveur configure : ");
  Serial.println(serverName);
  Serial.print("Connexion a ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(1000);

  // --- DIAGNOSTIC : liste des reseaux 2,4 GHz visibles par l'ESP32 ---
  // Si le reseau cible n'apparait pas ici, c'est qu'il emet en 5 GHz
  // (invisible pour l'ESP32) ou qu'il est hors de portee.
  Serial.println("\n[SCAN] Reseaux Wi-Fi 2,4 GHz visibles :");
  int nbReseaux = WiFi.scanNetworks();
  if (nbReseaux <= 0) {
    Serial.println("  (aucun reseau detecte)");
  } else {
    bool cibleVue = false;
    for (int i = 0; i < nbReseaux; i++) {
      Serial.printf("  %2d) \"%s\"  RSSI=%d dBm  canal=%d  %s\n", i + 1,
                    WiFi.SSID(i).c_str(), WiFi.RSSI(i), WiFi.channel(i),
                    (WiFi.encryptionType(i) == WIFI_AUTH_OPEN) ? "ouvert"
                                                               : "protege");
      if (WiFi.SSID(i) == String(ssid))
        cibleVue = true;
    }
    Serial.printf("[SCAN] Reseau cible \"%s\" %s dans le scan 2,4 GHz.\n", ssid,
                  cibleVue ? "TROUVE" : "ABSENT (=> probablement en 5 GHz)");
  }
  WiFi.scanDelete();

  bool connecte = false;
  for (int tentative = 0; tentative < 3 && !connecte; tentative++) {
    WiFi.begin(ssid, password);
    unsigned long debut = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - debut < 10000) {
      delay(400);
      Serial.print(".");
    }
    connecte = (WiFi.status() == WL_CONNECTED);
    if (!connecte)
      Serial.println("\nNouvel essai...");
  }

  if (connecte) {
    Serial.print("\nWiFi connecte ! Adresse IP de l'ESP32 : ");
    Serial.println(WiFi.localIP());
    synchroniserHeure();
    verifierJoignabiliteServeur();
  } else {
    Serial.println(
        "\nWiFi indisponible pour l'instant : demarrage en mode hors-ligne "
        "(mesures mises en tampon), reconnexion automatique en arriere-plan.");
  }

  // 4. Démarrage de la tâche HTTP en arrière-plan (sur le coeur 0, l'ADC reste
  // sur le coeur 1) Pile augmentee (8192, contre 4096 avant) :
  // String/HTTPClient/LittleFS ensemble consomment davantage que le simple
  // appel HTTP d'origine.
  xTaskCreatePinnedToCore(httpTask,    // Fonction de la tache
                          "HTTP Task", // Nom
                          8192,        // Taille de la pile
                          NULL,        // Parametres
                          1,           // Priorite
                          NULL,        // Handle
                          0            // Epingle sur le coeur 0
  );

  Serial.println("Stabilisation offset...");
  for (int i = 0; i < 5; i++) {
    for (int j = 0; j < NB_CAPTEURS; j++) {
      acquerir(capteurs[j]);
    }
  }

  Serial.println("Calibration du bruit de fond... (NE RIEN ALLUMER)");
  for (int j = 0; j < NB_CAPTEURS; j++) {
    capteurs[j].bruit_variance = 0.0f;
  }
  for (int i = 0; i < 8;
       i++) { // 8 cycles de 1s par capteur = 16s de calibration très précise
    for (int j = 0; j < NB_CAPTEURS; j++) {
      analogRead(capteurs[j].pin);
      unsigned long debut = millis();
      uint64_t sumX = 0;
      uint64_t sumX2 = 0;
      uint32_t n = 0;
      while (millis() - debut < FENETRE_MS) {
        int brut = analogRead(capteurs[j].pin);
        sumX += (uint64_t)brut;
        sumX2 += (uint64_t)brut * (uint64_t)brut;
        n++;
      }
      if (n > 0) {
        double moy = (double)sumX / (double)n;
        double var = ((double)sumX2 / (double)n) - (moy * moy);
        if (var > 0.0)
          capteurs[j].bruit_variance += (float)var;
      }
    }
  }
  for (int j = 0; j < NB_CAPTEURS; j++) {
    capteurs[j].bruit_variance /= 8.0f;
    // Plus de marge forcée à 1.10x, on utilise le seuil (delta) et l'adaptation
    // !
    Serial.printf(
        "[%s] Bruit calibre : variance = %.1f (RMS equivalent = %.1f)\n",
        capteurs[j].id, capteurs[j].bruit_variance,
        sqrtf(capteurs[j].bruit_variance));
  }

  Serial.println("Pret a mesurer !");
}

void loop() {
  for (int i = 0; i < NB_CAPTEURS; i++) {
    traiterCapteur(capteurs[i]);
    delay(10); // Laisse l'ADC liberer sa charge entre deux canaux
  }
}
