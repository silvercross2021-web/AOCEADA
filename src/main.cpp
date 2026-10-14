#include <Arduino.h>
#include <ArduinoOTA.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WiFiUdp.h>
#include <algorithm>
#include <stdarg.h>
#include <time.h>

/*
  ZMCT103C - LOGGER IoT POUR AOCEDA (ESP32 avec Wi-Fi)
*/

// ========================================================================
// ⚠️ CONFIGURATION WI-FI & SERVEUR (À REMPLIR PAR TOI) ⚠️
// ========================================================================
// Reseaux essayes dans l'ordre : l'ESP32 garde le PREMIER ou il joint vraiment le
// serveur (un GET y repond). Chaque reseau a SON adresse de serveur : celle du PC
// sur CE reseau (le PC n'a pas la meme adresse d'un reseau a l'autre). Wi-Fi
// 2,4 GHz seulement : l'ESP32 ne voit pas le 5 GHz.
// ⚠️ L'adresse du PC est attribuee par DHCP : elle CHANGE quand le PC change de
// reseau (ou parfois au redemarrage de la box / du partage de connexion). Si
// l'ESP32 se connecte mais que tout finit en tampon ("[Serveur] INJOIGNABLE"),
// verifier d'abord cette adresse : sur le PC, `ipconfig` -> adaptateur "Wi-Fi" ->
// "Adresse IPv4".
// Ne jamais commiter ce fichier avec de vrais mots de passe Wi-Fi.
struct ReseauWifi {
  const char *ssid;
  const char *motDePasse;
  const char *serveur;
};
const char *A_REMPLIR = "A_REMPLIR"; // mot de passe pas encore saisi : reseau saute
const ReseauWifi RESEAUX_WIFI[] = {
    {"xx", A_REMPLIR, "http://10.152.51.194:8003/api/sensors/zmct/"},
    {"EYDENMO-2.4G", A_REMPLIR, "http://192.168.1.3:8003/api/sensors/zmct/"},
};
const int NB_RESEAUX = sizeof(RESEAUX_WIFI) / sizeof(RESEAUX_WIFI[0]);
int reseauActif = 0;                              // reseau en cours (ou dernier essaye)
const char *serverName = RESEAUX_WIFI[0].serveur; // serveur du reseau en cours
const char *apiKeyDevice = "c9f1d4e372a0b518642c3e8d1f059b27";
// Mot de passe des mises a jour du programme par Wi-Fi (voir demarrerOta)
const char *MOT_DE_PASSE_OTA = "aoceda-ota";

// ========================================================================
// Parametres electriques & Acquisition
// ========================================================================
const float V_REF = 3.3f;
const float R_BURDEN = 100.0f;
const float N_TURNS = 1000.0f;
const float K = (V_REF / 4096.0f) / R_BURDEN * N_TURNS;

const unsigned long FENETRE_MS =
    1000UL; // 1 s = 50 periodes du secteur par fenetre de mesure
const uint8_t CONFIRMATIONS = 2; // 2 fenetres d'affilee avant tout changement d'etat (anti-rebond)
const unsigned long INTERVALLE_ENVOI_HTTP_MS =
    1000; // Envoi régulier toutes les 1 seconde

const int SEUIL_ECRET_HAUT = 4000;
const int SEUIL_ECRET_BAS = 90;
const int AMP_ECRET_BAS = 240;

// ========================================================================
// Detection par les frequences du secteur (test guide sur la carte, 12/10/2026)
// ========================================================================
// La radio Wi-Fi de l'ESP32 brouille l'ADC. Variance totale au repos, tout eteint :
//   Wi-Fi coupe 348 / 744 (stable) ; Wi-Fi connecte 1967 / 3102 ; Wi-Fi + envois
//   HTTP 3860 / 5464, avec des pointes a 6553 (Capteur_1 / Capteur_2).
// Les anciens seuils (variance > bruit + 400 / + 70) avaient ete regles sans Wi-Fi :
// le bruit seul les depassait (faux « allume ») et le retour « eteint » etait
// impossible. Le courant d'un appareil est a 50 Hz (+ harmoniques impaires), le
// brouillage Wi-Fi non : on ne mesure plus que ces frequences (DFT calee sur
// l'horodatage reel de chaque echantillon).
// La detection porte sur 50 + 150 + 250 Hz, pas sur le 50 Hz seul : une lampe LED
// ou un chargeur consomment surtout en harmoniques (lampe : 50 Hz 140-485, harmoniques
// 295-470 ; chargeur de PC : 1 619-5 920 et 4 468-9 168). Mesures sur la carte avec
// Wi-Fi + envois : repos 7-77, lampe 451-934, chargeur de PC 6 087-15 088.
// Unite des seuils : « puissance » = carre du RMS de la composante, en points ADC^2
// (meme echelle que l'ancienne variance).
const uint32_t PERIODE_SECTEUR_US = 20000UL; // 50 Hz
const uint32_t PAS_TABLE_US = 100UL;         // table cos/sin : 200 points par periode
const int TAILLE_TABLE = PERIODE_SECTEUR_US / PAS_TABLE_US;
// Harmoniques 150 / 250 Hz mesurees par sous-fenetres de 10 periodes : la frequence
// du reseau derive (49,8-50,2 Hz), et sur 1 s entiere une harmonique decalee de
// 1 Hz s'annulerait.
const uint32_t SOUS_FENETRE_US = 200000UL;
// Harmoniques mesurees par sous-fenetre, en multiples de 25 Hz : 150 et 250 Hz.
const int NB_RAIES_SOUS = 2;
const uint32_t MULT_25HZ[NB_RAIES_SOUS] = {6, 10};

// Bruit : il depend de l'alimentation de la carte. Mesures du 12/10/2026, valeur
// « secteur » au repos : ~15-25 sur le port USB du PC, ~130-190 sur un powerbank
// (lampe : ~600 / ~550-1 030 ; chargeur de telephone : ~70 / ~900). Un seuil fixe ne
// convient donc a aucune alimentation : chaque capteur apprend son bruit (mediane
// suivie au repos) et ses seuils en sont des multiples :
//   allume si moyenne des NB_LISSAGE dernieres fenetres >= max(FACTEUR_ON x bruit,
//   bruit + seuilOn) ; eteint si < max(FACTEUR_OFF x bruit, bruit + seuilOff).
// Chaque capteur a SON bruit. Jusqu'au 13/10/2026, le bruit de l'un etait borne a 2 x
// celui de l'autre (meme alimentation), pour ne pas prendre pour du bruit un appareil
// deja allume au demarrage. Depuis les relais, le bruit de depart se mesure appareils
// COUPES (relaisRetenus) : cette borne ne sert plus, et elle faussait tout quand un
// capteur est plus bruite que l'autre (13/10/2026 : capteur 2 a ~270, capteur 1 a ~2 ;
// borne a 5, le seuil du capteur 2 tombait a 20 et ses parasites le montraient
// allume en permanence).
const int NB_LISSAGE = 3;
const float FACTEUR_ON = 2.5f;
const float FACTEUR_OFF = 1.6f;
const float PAS_SUIVI_BRUIT = 0.05f; // suivi de la mediane : pas multiplicatif de 5 %
const float BRUIT_MIN = 5.0f;

// Mesure et radio ne se chevauchent jamais : les envois Wi-Fi (HTTP, journal) se
// font entre deux fenetres de mesure, jamais pendant (voir verrouRadio).
SemaphoreHandle_t verrouRadio = NULL;
const unsigned long PAUSE_RADIO_MS = 30; // laisse la tache reseau prendre la radio
const unsigned long ATTENTE_RADIO_MAX_MS = 4000; // au-dela, on mesure quand meme
// Entre deux fenetres, la tache reseau vide TOUTE sa file (dans cette limite). Avec
// un seul envoi par pause pour une trame produite par fenetre, un retard accumule
// (serveur redemarre...) ne se resorbait jamais : 17 s entre la decision de l'ESP32
// et le tableau de bord (constate le 12/10/2026).
const unsigned long PAUSE_RADIO_MAX_MS = 1500;

// Copie des messages de controle vers le PC du serveur (UDP), en plus du cable USB :
// permet de suivre la carte alimentee par un simple chargeur. Sur le PC :
// ecouter le port PORT_JOURNAL en UDP.
const bool JOURNAL_WIFI = true;
const uint16_t PORT_JOURNAL = 5005;
WiFiUDP udpJournal;
IPAddress ipJournal; // adresse du serveur, lue dans serverName

float tableCos[TAILLE_TABLE], tableSin[TAILLE_TABLE];

// Moyenne glissante des NB_LISSAGE dernieres valeurs
struct Lissage {
  float valeurs[NB_LISSAGE];
  uint8_t idx;
  uint8_t nb;
};

float ajouterLissage(Lissage &l, float valeur) {
  l.valeurs[l.idx] = valeur;
  l.idx = (l.idx + 1) % NB_LISSAGE;
  if (l.nb < NB_LISSAGE)
    l.nb++;
  float somme = 0.0f;
  for (int i = 0; i < l.nb; i++)
    somme += l.valeurs[i];
  return somme / l.nb;
}

struct EtatCapteur {
  const char *id;
  uint8_t pin;
  float seuilOn;  // ecart minimal au-dessus du bruit pour declarer l'appareil allume
  float seuilOff; // ecart minimal pour rester allume (< seuilOn : hysteresis)
  const char *labelOn;
  const char *labelOff;
  float offset; // point milieu de l'ADC, suivi a chaque fenetre
  bool actif;
  uint8_t cptConfirm;
  unsigned long t_debut;
  unsigned int nb_connexions;
  unsigned int nb_deconnexions;
  unsigned long last_send; // Temps du dernier envoi HTTP
  float seuilOnEff; // seuils reellement appliques a la derniere fenetre
  float seuilOffEff;
  float bruit;       // bruit appris (mediane de « secteur » au repos)
  Lissage secteur;   // dernieres valeurs « secteur »
};

EtatCapteur capteurs[] = {
    // REALITE PHYSIQUE CONFIRMEE PAR LES LOGS :
    // Capteur_1 (GPIO 34) = AMPOULE ; Capteur_2 (GPIO 35) = PRISE, ou peut se
    // brancher n'importe quel appareil (chargeur de telephone : ~+50 a +2 000 selon
    // sa charge ; lampe LED : ~+600 ; chargeur de PC : ~+10 000) : memes seuils.
    {"Capteur_1", 34, 15.0f, 7.5f, "LAMPE ALLUMEE", "LAMPE ETEINTE", 2048.0f,
     false, 0, 0, 0, 0, 0UL, 0.0f, 0.0f, BRUIT_MIN},
    {"Capteur_2", 35, 15.0f, 7.5f, "PRISE BRANCHEE", "PRISE LIBRE", 2048.0f,
     false, 0, 0, 0, 0, 0UL, 0.0f, 0.0f, BRUIT_MIN},

};
const int NB_CAPTEURS = sizeof(capteurs) / sizeof(capteurs[0]);

// ========================================================================
// Relais : coupure du courant a distance (bouton « Couper » du site AOCEDA)
// ========================================================================
// Un module relais 5 V « S + - » par appareil, dans l'ordre de capteurs[] :
//   Capteur_1 (lampe, GPIO 34) -> S du relais 1 sur GPIO 26
//   Capteur_2 (prise, GPIO 35) -> S du relais 2 sur GPIO 27
// Le + des relais va sur VIN (5 V), jamais sur 3V3 : en 3,3 V la lumiere du module
// s'allume mais le relais ne bascule pas, et deux relais ne tiennent pas (13/10/2026).
// Contacts sur COM + NO (« ouvert par defaut ») : relais au repos = appareil coupe.
// Hors ordre « couper », le relais est donc active en permanence, et l'appareil suit
// son interrupteur normal. ESP32 eteint = lampe et prise coupees : c'est le cablage
// qui le veut, aucun programme n'y peut rien (en COM + NC, ce serait l'inverse).
const uint8_t PINS_RELAIS[] = {26, 27};
static_assert(sizeof(PINS_RELAIS) / sizeof(PINS_RELAIS[0]) == NB_CAPTEURS,
              "un relais par capteur");
const bool RELAIS_ACTIF_NIVEAU_HAUT = true; // module « S + - » a transistor
const bool CONTACT_NO = true;               // false : contacts COM + NC
// Ordre en vigueur pour chaque appareil (true = courant coupe), garde en memoire NVS :
// au retour du courant, l'ESP32 le reapplique des le demarrage, sans le serveur.
volatile bool coupe[NB_CAPTEURS] = {false, false};
// Ordre change par la tache reseau, a journaliser par la boucle de mesure (seule a
// pouvoir utiliser la radio pour le journal UDP, hors fenetre de mesure)
volatile bool relaisAJournaliser[NB_CAPTEURS] = {false, false};
// Au demarrage, le bruit de fond des capteurs se mesure appareils COUPES : sinon le
// courant d'un appareil deja allume est appris comme du bruit et l'appareil n'est
// plus jamais vu allume (13/10/2026 : lampe vue a 760, bruit appris 758, seuil
// d'allumage 1 800). Tant que relaisRetenus est vrai, tous les contacts restent
// ouverts ; les ordres recus pendant ce temps sont gardes et appliques ensuite.
volatile bool relaisRetenus = true;

void appliquerRelais(int i) {
  // Courant present <=> contact ferme. En COM + NO, ferme quand le relais est active.
  bool alimente = !relaisRetenus && !coupe[i];
  bool activer = CONTACT_NO ? alimente : !alimente;
  digitalWrite(PINS_RELAIS[i], (activer == RELAIS_ACTIF_NIVEAU_HAUT) ? HIGH : LOW);
}

void cleNvsRelais(int i, char *cle, size_t taille) { snprintf(cle, taille, "coupe%d", i); }

struct Mesure {
  float var;          // variance totale (ancienne methode, gardee pour comparer)
  float p50;          // puissance a 50 Hz
  float pHarm;        // puissance a 150 + 250 Hz
  float secteur;      // p50 + pHarm : courant de l'appareil + bruit residuel
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
bool verifierJoignabiliteServeur() {
  HTTPClient http;
  http.begin(serverName);
  http.setTimeout(3000);
  int code = http.GET();
  if (code > 0) {
    Serial.printf("[Serveur] Joignable a %s (code HTTP %d).\n", serverName,
                  code);
  } else {
    Serial.printf("[Serveur] INJOIGNABLE a %s (erreur %d : %s).\n"
                  "  -> Serveur pas lance, PC sur un autre reseau, ou IP du PC "
                  "changee (DHCP) : verifie avec `ipconfig`\n"
                  "     (adaptateur Wi-Fi) et mets a jour RESEAUX_WIFI en haut "
                  "de main.cpp.\n",
                  serverName, code, http.errorToString(code).c_str());
  }
  http.end();
  return code > 0;
}

// Adresse du PC pour le journal UDP : l'hote du serveur en cours ("http://IP:port/...")
void majIpJournal() {
  String url = serverName;
  int debutHote = url.indexOf("//") + 2;
  int finHote = url.indexOf(':', debutHote);
  if (!ipJournal.fromString(url.substring(debutHote, finHote)))
    ipJournal = IPAddress(0, 0, 0, 0); // nom de domaine : pas de journal Wi-Fi
}

void choisirReseau(int i) {
  reseauActif = i;
  serverName = RESEAUX_WIFI[i].serveur;
  majIpJournal();
}

bool joindreReseau(int i, unsigned long attenteMs) {
  const ReseauWifi &r = RESEAUX_WIFI[i];
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
  choisirReseau(i);
  Serial.printf("[WiFi] Connecte a \"%s\" ! IP de l'ESP32 = %s\n", r.ssid,
                WiFi.localIP().toString().c_str());
  return true;
}

// Essaie les reseaux dans l'ordre et garde le premier ou le serveur repond. Si le
// serveur ne repond sur aucun, reste sur le premier reseau joint : les mesures
// partent en tampon et seront rejouees. true si connecte a un reseau.
bool connecterReseaux(unsigned long attenteMs) {
  int premierJoint = -1;
  for (int i = 0; i < NB_RESEAUX; i++) {
    if (strcmp(RESEAUX_WIFI[i].motDePasse, A_REMPLIR) == 0) {
      Serial.printf("[WiFi] \"%s\" saute : mot de passe a remplir dans main.cpp.\n",
                    RESEAUX_WIFI[i].ssid);
      continue;
    }
    if (!joindreReseau(i, attenteMs))
      continue;
    if (verifierJoignabiliteServeur())
      return true;
    if (premierJoint < 0)
      premierJoint = i;
  }
  if (premierJoint < 0)
    return false;
  if (reseauActif != premierJoint || WiFi.status() != WL_CONNECTED)
    joindreReseau(premierJoint, attenteMs);
  Serial.println("[WiFi] Serveur joignable sur aucun reseau : mesures en tampon.");
  return WiFi.status() == WL_CONNECTED;
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
  if (connecterReseaux(8000)) {
    synchroniserHeure();
    return true;
  }
  Serial.println("[WiFi] Toujours indisponible, nouvel essai dans 15 s.");
  return false;
}

// Connecte au Wi-Fi mais le serveur ne repond plus (PC passe sur l'autre reseau,
// serveur arrete...) : apres ECHECS_AVANT_AUTRE_RESEAU envois sans aucune reponse
// HTTP, on se deconnecte pour que assurerWifi() reessaie tous les reseaux.
const int ECHECS_AVANT_AUTRE_RESEAU = 15;
int echecsSansReponse = 0;

// ========================================================================
// Construction du JSON d'une mesure (partagée entre envoi direct et tampon).
// ========================================================================
// Numero du capteur sur le boitier, cote serveur (Capteur.indexDispositif, fixe) :
// Capteur_1 (GPIO 34) = LAMPE physiquement -> 2, nomme « Capteur 1 - Lampe » sur le site
// Capteur_2 (GPIO 35) = PRISE physiquement -> 1, nomme « Capteur 2 - Prise » sur le site
// Ces numeros internes sont inverses par rapport aux noms (historique) : ils ne se
// voient nulle part et ne doivent pas etre changes, sinon les mesures et les ordres
// de coupure partiraient vers l'autre appareil.
int indexServeur(const char *capteurId) {
  return (strcmp(capteurId, "Capteur_1") == 0) ? 2 : 1;
}

// Position du capteur dans capteurs[] (et donc de son relais), -1 si inconnu
int indexLocal(const char *capteurId) {
  for (int i = 0; i < NB_CAPTEURS; i++)
    if (strcmp(capteurs[i].id, capteurId) == 0)
      return i;
  return -1;
}

// « coupe » : etat reel du relais au moment de l'envoi. Le serveur ne s'en sert que
// pour une mesure recente (pas pour une mesure rejouee depuis le tampon).
String construireJsonMesure(const char *capteurId, const char *etat,
                            float courant, float puissance,
                            unsigned long horodatageUnix) {
  int idx = indexServeur(capteurId);
  int local = indexLocal(capteurId);
  bool relaisCoupe = (local >= 0) && coupe[local];
  char buf[200];
  snprintf(buf, sizeof(buf),
           "{\"capteur_index\":%d,\"etat\":\"%s\",\"courant\":%.3f,"
           "\"puissance\":%.1f,\"timestamp_unix\":%lu,\"coupe\":%s}",
           idx, etat, courant, puissance, horodatageUnix,
           relaisCoupe ? "true" : "false");
  return String(buf);
}

// Ordres de coupure dans la reponse du serveur : {"created":1,"coupe_1":false,
// "coupe_2":true}. Absents (ancien serveur) : rien ne change. Appelee par la tache
// reseau ; le changement est journalise ensuite par la boucle de mesure.
void lireOrdresRelais(const String &reponse) {
  for (int i = 0; i < NB_CAPTEURS; i++) {
    char cle[16];
    snprintf(cle, sizeof(cle), "\"coupe_%d\"", indexServeur(capteurs[i].id));
    int p = reponse.indexOf(cle);
    if (p < 0)
      continue;
    p = reponse.indexOf(':', p);
    if (p < 0)
      continue;
    p++;
    while (p < (int)reponse.length() && reponse[p] == ' ')
      p++;
    bool ordre;
    if (reponse.startsWith("true", p))
      ordre = true;
    else if (reponse.startsWith("false", p))
      ordre = false;
    else
      continue;
    if (ordre != coupe[i]) {
      coupe[i] = ordre;
      appliquerRelais(i);
      char cleNvs[8];
      cleNvsRelais(i, cleNvs, sizeof(cleNvs));
      prefs.putBool(cleNvs, ordre);
      relaisAJournaliser[i] = true;
    }
  }
}

// Message de controle : cable USB, et copie UDP vers le PC du serveur. Appelee
// uniquement depuis la boucle de mesure, hors fenetre de mesure.
void journal(const char *format, ...) {
  char buf[256];
  va_list args;
  va_start(args, format);
  vsnprintf(buf, sizeof(buf), format, args);
  va_end(args);
  Serial.print(buf);
  if (JOURNAL_WIFI && ipJournal != IPAddress(0, 0, 0, 0) &&
      WiFi.status() == WL_CONNECTED) {
    udpJournal.beginPacket(ipJournal, PORT_JOURNAL);
    udpJournal.write((const uint8_t *)buf, strlen(buf));
    udpJournal.endPacket();
  }
}

bool envoyerJson(const String &json) {
  HTTPClient http;
  http.begin(serverName);
  http.addHeader("Content-Type", "application/json");
  char authHeader[100];
  snprintf(authHeader, sizeof(authHeader), "Device %s", apiKeyDevice);
  http.addHeader("Authorization", authHeader);
  http.setTimeout(3000);
  // Jamais pendant une fenetre de mesure : la radio brouille l'ADC
  bool verrou = verrouRadio && xSemaphoreTake(verrouRadio, portMAX_DELAY) == pdTRUE;
  int code = http.POST(json);
  echecsSansReponse = (code > 0) ? 0 : echecsSansReponse + 1;
  // La reponse porte les ordres de coupure des relais
  String reponse = (code == 201) ? http.getString() : String();
  http.end();
  if (verrou)
    xSemaphoreGive(verrouRadio);
  if (code == 201)
    lireOrdresRelais(reponse);
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
    if (WiFi.status() == WL_CONNECTED && echecsSansReponse >= ECHECS_AVANT_AUTRE_RESEAU) {
      Serial.printf("[WiFi] %d envois sans reponse du serveur sur \"%s\" : essai des "
                    "autres reseaux.\n",
                    echecsSansReponse, RESEAUX_WIFI[reseauActif].ssid);
      echecsSansReponse = 0;
      WiFi.disconnect();
      derniereTentativeWifi = 0; // reconnexion tout de suite
    }
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
void initialiserTables() {
  for (int i = 0; i < TAILLE_TABLE; i++) {
    tableCos[i] = cosf(2.0f * PI * i / TAILLE_TABLE);
    tableSin[i] = -sinf(2.0f * PI * i / TAILLE_TABLE);
  }
}

// Une fenetre de mesure : variance totale (comparaison), puissance a 50 Hz et a
// 150 + 250 Hz (courant de l'appareil).
// Pour une composante A.cos(wt + phi),
// I = moyenne(x.cos), Q = moyenne(x.sin) donnent A^2/4, d'ou puissance = 2(I^2 + Q^2)
// = A^2/2 = RMS^2. Les echantillons sont recentres sur le point milieu de la fenetre
// precedente ; le petit ecart restant est retranche a la fin (termes en d).
Mesure acquerir(EtatCapteur &c) {
  analogRead(c.pin); // Lecture à vide pour commuter et stabiliser le MUX ADC
  const float off = c.offset;
  uint64_t sumX = 0;
  uint64_t sumX2 = 0;
  uint32_t n = 0;
  int vMin = 4095, vMax = 0;
  float c1 = 0, s1 = 0, sc1 = 0, ss1 = 0; // 50 Hz, coherent sur toute la fenetre

  // Harmoniques : une DFT par sous-fenetre, puissances moyennees
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

  // Radio reservee a la mesure pendant toute la fenetre (un envoi en cours se
  // termine d'abord). Si le reseau la garde trop longtemps, on mesure quand meme.
  bool verrou = verrouRadio && xSemaphoreTake(verrouRadio, pdMS_TO_TICKS(ATTENTE_RADIO_MAX_MS)) == pdTRUE;
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
    // raie a 25 x M Hz : phase = t x M / 2 rapportee a la periode du 50 Hz
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
    xSemaphoreGive(verrouRadio);
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

// Bruit de chaque capteur, jamais sous BRUIT_MIN (un bruit nul rendrait le moindre
// parasite « allume »). Plus de borne entre capteurs : voir le bloc des seuils.
void plancherBruit(EtatCapteur &c) { c.bruit = fmaxf(BRUIT_MIN, c.bruit); }

void calculerSeuils(EtatCapteur &c) {
  c.seuilOnEff = fmaxf(FACTEUR_ON * c.bruit, c.bruit + c.seuilOn);
  c.seuilOffEff = fmaxf(FACTEUR_OFF * c.bruit, c.bruit + c.seuilOff);
}

// ========================================================================
void traiterCapteur(EtatCapteur &c) {
  Mesure m = acquerir(c);
  float lisse = ajouterLissage(c.secteur, m.secteur);
  calculerSeuils(c);
  // Courant : frequences du secteur, moins le bruit appris
  float pNette = m.secteur - c.bruit;
  if (pNette < 0.0f)
    pNette = 0.0f;
  float rms = sqrtf(pNette);
  float courant_A = K * rms;
  float puissance = 220.0f * courant_A;
  unsigned long maintenant = millis();
  bool etat_avant = c.actif;
  // Relais ouvert : l'appareil ne peut consommer AUCUN courant (le capteur est sur le
  // meme fil). Ce qui est mesure n'est alors que du bruit : eteint d'office, et pas
  // d'apprentissage du bruit sur ce signal (13/10/2026 : capteur 2 mal branche, 200 a
  // 400 mesures relais ouvert, il restait « allume »).
  int local = indexLocal(c.id);
  bool coupeParRelais = local >= 0 && coupe[local] && !relaisRetenus;

  if (coupeParRelais) {
    c.actif = false;
    c.cptConfirm = 0;
  } else if (!c.actif) {
    if (lisse >= c.seuilOnEff) {
      c.cptConfirm++;
      if (c.cptConfirm >= CONFIRMATIONS) {
        c.actif = true;
        c.cptConfirm = 0;
      }
    } else {
      c.cptConfirm = 0;
      // Suivi de la mediane du bruit, par pas multiplicatifs : seulement capteur
      // eteint et fenetre sous le seuil d'allumage, jamais sur un appareil detecte.
      if (m.secteur < c.seuilOnEff) {
        c.bruit *= (m.secteur > c.bruit) ? (1.0f + PAS_SUIVI_BRUIT)
                                         : (1.0f - PAS_SUIVI_BRUIT);
        plancherBruit(c);
      }
    }
  } else {
    // Le retour a « eteint » ne depend que du signal secteur compare au bruit
    // appris, jamais d'une reference figee : un appareil coupe y retombe toujours.
    // La fenetre brute compte aussi (14/10/2026) : attendre que la moyenne des 3
    // dernieres fenetres tombe ajoutait ~5 s, l'extinction prenait 9 a 10 s ; deux
    // fenetres d'affilee sous le seuil suffisent (~5 s). L'allumage reste sur la
    // moyenne : un pic de parasite isole ne fait jamais « allume ».
    if (fminf(lisse, m.secteur) < c.seuilOffEff) {
      c.cptConfirm++;
      if (c.cptConfirm >= CONFIRMATIONS) {
        c.actif = false;
        c.cptConfirm = 0;
      }
    } else {
      c.cptConfirm = 0;
    }
  }

  // ---- Evenement ON ----
  if (c.actif && !etat_avant) {
    c.nb_connexions++;
    c.t_debut = maintenant;
    journal("[%s] ETAT : %s (secteur lisse=%.0f, bruit=%.0f)\n", c.id, c.labelOn,
            lisse, c.bruit);

    // Envoi HTTP immédiat
    envoyerVersDjango(c, courant_A, puissance);
    c.last_send = maintenant;
  }

  // ---- Evenement OFF ----
  if (!c.actif && etat_avant) {
    c.nb_deconnexions++;
    c.t_debut = maintenant;
    journal("[%s] ETAT : %s (secteur lisse=%.0f, bruit=%.0f)\n", c.id, c.labelOff,
            lisse, c.bruit);

    // Envoi HTTP immédiat
    envoyerVersDjango(c, 0.0f, 0.0f);
    c.last_send = maintenant;
  }

  // ---- Envoi HTTP régulier (Toutes les X secondes) ----
  if (maintenant - c.last_send > INTERVALLE_ENVOI_HTTP_MS) {
    envoyerVersDjango(c, courant_A, puissance);
    c.last_send = maintenant;
    // Debug continu pour analyser le signal
    journal("[DEBUG-SIGNAL] %s | Secteur: %.0f | Lisse: %.0f | Bruit: %.0f | "
            "P50: %.0f | Harm: %.0f | Var totale: %.0f | Milieu: %.0f | Seuils: "
            "%.0f/%.0f | I: %.3f A | Etat: %s%s\n",
            c.id, m.secteur, lisse, c.bruit, m.p50, m.pHarm, m.var, c.offset,
            c.seuilOnEff, c.seuilOffEff, courant_A, c.actif ? "ON" : "OFF",
            coupeParRelais ? " (relais ouvert)" : "");
  }
}

// Ordres de coupure appliques par la tache reseau depuis le dernier passage :
// journalises ici (radio libre, hors fenetre de mesure). Une coupure rend l'appareil
// « eteint » tout de suite, envoye au serveur sans attendre la prochaine fenetre de
// ce capteur (jusqu'a ~2,4 s gagnees a l'ecran).
void suivreOrdresRelais() {
  for (int i = 0; i < NB_CAPTEURS; i++) {
    if (!relaisAJournaliser[i])
      continue;
    relaisAJournaliser[i] = false;
    journal("[RELAIS] %s : %s\n", capteurs[i].id,
            coupe[i] ? "COUPE a distance" : "courant RETABLI");
    EtatCapteur &c = capteurs[i];
    if (coupe[i] && c.actif && !relaisRetenus) {
      c.actif = false;
      c.cptConfirm = 0;
      c.nb_deconnexions++;
      c.t_debut = millis();
      journal("[%s] ETAT : %s (relais coupe)\n", c.id, c.labelOff);
      envoyerVersDjango(c, 0.0f, 0.0f);
      c.last_send = millis();
    }
  }
}

// ========================================================================
// Mise a jour du programme par Wi-Fi, sans cable. Depuis le PC, avec un Python
// autorise par le pare-feu :
//   python espota.py -i <IP de l'ESP32> -a <MOT_DE_PASSE_OTA> -f firmware.bin
// (espota.py : dossier tools du paquet framework-arduinoespressif32 de PlatformIO)
// ========================================================================
bool otaPret = false;

void demarrerOta() {
  if (otaPret || WiFi.status() != WL_CONNECTED)
    return;
  ArduinoOTA.setHostname("aoceda-esp32");
  ArduinoOTA.setPassword(MOT_DE_PASSE_OTA);
  ArduinoOTA.onStart([]() { Serial.println("[OTA] Mise a jour du programme..."); });
  ArduinoOTA.onError([](ota_error_t e) { Serial.printf("[OTA] Echec (%u)\n", e); });
  ArduinoOTA.begin();
  otaPret = true;
  journal("[OTA] Mise a jour par Wi-Fi possible a l'adresse %s\n",
          WiFi.localIP().toString().c_str());
}

// ========================================================================
void setup() {
  Serial.begin(9600);
  initialiserTables();
  verrouRadio = xSemaphoreCreateMutex();
  choisirReseau(0); // serveur et journal UDP du 1er reseau, en attendant la connexion

  // 1. Initialisation de la file pour le Wi-Fi (capacité de 20 requêtes)
  httpQueue = xQueueCreate(20, sizeof(HttpData));

  // 2. Tampon hors-ligne persistant (LittleFS + offset NVS)
  if (!LittleFS.begin(
          true)) { // true = formate automatiquement au tout premier boot
    Serial.println(
        "Erreur montage LittleFS : le tampon hors-ligne sera indisponible.");
  }
  prefs.begin("aoceda", false);

  // Relais : dernier ordre enregistre, lu avant meme le Wi-Fi, sans attendre le
  // serveur. Il n'est applique qu'apres la mesure du bruit de fond (fin de setup,
  // ~30 s) : jusque-la les appareils restent coupes (voir relaisRetenus).
  // Le niveau est ecrit avant de passer la broche en sortie (pas d'a-coup).
  for (int i = 0; i < NB_CAPTEURS; i++) {
    char cleNvs[8];
    cleNvsRelais(i, cleNvs, sizeof(cleNvs));
    coupe[i] = prefs.getBool(cleNvs, false);
    appliquerRelais(i);
    pinMode(PINS_RELAIS[i], OUTPUT);
    Serial.printf("[RELAIS] %s (GPIO %d) : ordre enregistre = %s ; coupe le temps de "
                  "mesurer le bruit de fond\n",
                  capteurs[i].id, PINS_RELAIS[i], coupe[i] ? "COUPE" : "courant present");
  }
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
  for (int i = 0; i < NB_RESEAUX; i++)
    Serial.printf("Reseau %d : \"%s\" -> serveur %s\n", i + 1, RESEAUX_WIFI[i].ssid,
                  RESEAUX_WIFI[i].serveur);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(1000);

  // --- DIAGNOSTIC : liste des reseaux 2,4 GHz visibles par l'ESP32 ---
  // Si un reseau configure n'apparait pas ici, c'est qu'il emet en 5 GHz
  // (invisible pour l'ESP32) ou qu'il est hors de portee.
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
        vu = WiFi.SSID(i) == String(RESEAUX_WIFI[r].ssid);
      Serial.printf("[SCAN] Reseau \"%s\" %s dans le scan 2,4 GHz.\n", RESEAUX_WIFI[r].ssid,
                    vu ? "TROUVE" : "ABSENT (=> eteint, hors de portee ou en 5 GHz)");
    }
  }
  WiFi.scanDelete();

  // Chaque reseau dans l'ordre, deux tours au plus (une box peut mettre du temps)
  bool connecte = false;
  for (int tour = 0; tour < 2 && !connecte; tour++)
    connecte = connecterReseaux(10000);

  if (connecte) {
    synchroniserHeure();
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

  // Bruit de depart : mediane de 8 fenetres par capteur, appareils coupes par les
  // relais (relaisRetenus) : ce qui est mesure n'est que du bruit, propre a chaque
  // capteur. Le suivi continu corrige ensuite les ecarts (changement
  // d'alimentation, Wi-Fi...).
  float valeurs[NB_CAPTEURS][8];
  for (int i = 0; i < 8; i++)
    for (int j = 0; j < NB_CAPTEURS; j++)
      valeurs[j][i] = acquerir(capteurs[j]).secteur;
  for (int j = 0; j < NB_CAPTEURS; j++) {
    std::sort(valeurs[j], valeurs[j] + 8);
    capteurs[j].bruit = 0.5f * (valeurs[j][3] + valeurs[j][4]);
    plancherBruit(capteurs[j]);
  }
  for (int j = 0; j < NB_CAPTEURS; j++) {
    calculerSeuils(capteurs[j]);
    journal("[%s] Bruit de depart : %.0f -> seuils ON / OFF = %.0f / %.0f\n",
            capteurs[j].id, capteurs[j].bruit, capteurs[j].seuilOnEff,
            capteurs[j].seuilOffEff);
  }
  // Bruit mesure : chaque appareil retrouve son ordre (y compris un ordre recu du
  // serveur pendant la mesure)
  relaisRetenus = false;
  for (int i = 0; i < NB_CAPTEURS; i++) {
    appliquerRelais(i);
    journal("[RELAIS] %s : %s\n", capteurs[i].id,
            coupe[i] ? "reste COUPE (ordre enregistre)" : "courant RETABLI");
  }
  journal("Pret a mesurer !\n");
}

void loop() {
  demarrerOta();
  ArduinoOTA.handle();
  for (int i = 0; i < NB_CAPTEURS; i++) {
    traiterCapteur(capteurs[i]);
    // Laisse l'ADC liberer sa charge entre deux canaux, et la tache reseau vider sa
    // file pendant que l'ADC ne mesure pas (voir PAUSE_RADIO_MAX_MS)
    unsigned long debutPause = millis();
    do {
      delay(PAUSE_RADIO_MS);
    } while (uxQueueMessagesWaiting(httpQueue) > 0 &&
             millis() - debutPause < PAUSE_RADIO_MAX_MS);
    suivreOrdresRelais(); // apres chaque capteur : une coupure se voit tout de suite
  }
}
