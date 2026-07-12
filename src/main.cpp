#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>

/*
  ZMCT103C - LOGGER IoT POUR AOCEDA (ESP32 avec Wi-Fi)
*/

// ========================================================================
// ⚠️ CONFIGURATION WI-FI & SERVEUR (À REMPLIR PAR TOI) ⚠️
// ========================================================================
const char* ssid       = "xx";
const char* password   = "1234567890";

// L'adresse IP de l'ordinateur trouvée sur le réseau "xx" est 10.11.255.194
const char* serverName = "http://10.11.255.194:8003/api/sensors/zmct/"; 
const char* apiKeyDevice = "c9f1d4e372a0b518642c3e8d1f059b27";


// ========================================================================
// Parametres electriques & Acquisition
// ========================================================================
const float V_REF     = 3.3f;
const float R_BURDEN  = 100.0f;
const float N_TURNS   = 1000.0f;
const float K = (V_REF / 4096.0f) / R_BURDEN * N_TURNS;

const unsigned long FENETRE_MS  = 100UL;
const uint8_t       CONFIRMATIONS = 3;
const unsigned long INTERVALLE_ENVOI_HTTP_MS = 2000; // Envoi régulier toutes les 2 secondes

const int SEUIL_ECRET_HAUT = 4000;
const int SEUIL_ECRET_BAS  = 90;
const int AMP_ECRET_BAS    = 240;

struct EtatCapteur {
  const char*   id;
  uint8_t       pin;
  float         seuilOn;
  float         seuilOff;
  const char*   labelOn;
  const char*   labelOff;
  float         offset;
  bool          actif;
  uint8_t       cptConfirm;
  unsigned long t_debut;
  unsigned int  nb_connexions;
  unsigned int  nb_deconnexions;
  float         somme_rms_on;
  unsigned long nb_rms_on;
  unsigned long last_send; // Temps du dernier envoi HTTP
};

EtatCapteur capteurs[] = {
  {"Capteur_1",   34,   34.0f, 30.0f, "LAMPE ALLUMEE",   "LAMPE ETEINTE",  2048.0f, false, 0,   0, 0,  0,  0.0f,  0UL, 0UL},
  {"Capteur_2",   35,   33.0f, 27.0f, "PRISE BRANCHEE",  "PRISE LIBRE",    2048.0f, false, 0,   0, 0,  0,  0.0f,  0UL, 0UL},
};
const int NB_CAPTEURS = sizeof(capteurs) / sizeof(capteurs[0]);

struct Mesure { float rms; int vMin; int vMax; };

// ========================================================================
// File d'attente pour le réseau (Évite de bloquer les mesures !)
// ========================================================================
struct HttpData {
    char capteur[16];
    char etat[4];
    float courant;
    float puissance;
};

QueueHandle_t httpQueue;

// Tâche FreeRTOS d'arrière-plan pour envoyer les requêtes HTTP
void httpTask(void *pvParameters) {
    HttpData data;
    HTTPClient http;
    
    while(1) {
        // Attend qu'il y ait des données dans la file
        if (xQueueReceive(httpQueue, &data, portMAX_DELAY) == pdPASS) {
            if (WiFi.status() == WL_CONNECTED) {
                http.begin(serverName);
                http.addHeader("Content-Type", "application/json");
                
                char authHeader[100];
                snprintf(authHeader, sizeof(authHeader), "Device %s", apiKeyDevice);
                http.addHeader("Authorization", authHeader);
                
                http.setTimeout(2000); // Timeout court pour ne pas s'enliser

                // Création du JSON
                int c_idx = (strcmp(data.capteur, "Capteur_1") == 0) ? 1 : 2;
                char json[128];
                snprintf(json, sizeof(json), "{\"capteur_index\":%d,\"etat\":\"%s\",\"courant\":%.3f,\"puissance\":%.1f}", 
                         c_idx, data.etat, data.courant, data.puissance);
                
                int httpResponseCode = http.POST(json);
                if (httpResponseCode > 0) {
                    Serial.printf("[HTTP] Envoi OK (%d) : %s\n", httpResponseCode, json);
                } else {
                    Serial.printf("[HTTP] Erreur : %s\n", http.errorToString(httpResponseCode).c_str());
                }
                http.end();
            }
        }
    }
}

// Fonction utilitaire pour ajouter à la file d'envoi
void envoyerVersDjango(EtatCapteur& c, float courant, float puissance) {
    HttpData hd;
    // Utilisation de snprintf pour garantir la présence du '\0' final
    snprintf(hd.capteur, sizeof(hd.capteur), "%s", c.id);
    snprintf(hd.etat, sizeof(hd.etat), "%s", c.actif ? "ON" : "OFF");
    hd.courant = c.actif ? courant : 0.0f;
    hd.puissance = c.actif ? puissance : 0.0f;
    
    // Ajoute dans la file (sans bloquer si c'est plein)
    xQueueSend(httpQueue, &hd, 0);
}

// ========================================================================
Mesure acquerir(EtatCapteur& c) {
  unsigned long debut = millis();
  unsigned long n = 0;
  float sommeCarres = 0.0f;
  int vMin = 4095, vMax = 0;

  while (millis() - debut < FENETRE_MS) {
    int brut = analogRead(c.pin);
    c.offset += ((float)brut - c.offset) / 1024.0f;
    float ac = (float)brut - c.offset;
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
void traiterCapteur(EtatCapteur& c) {
  Mesure m     = acquerir(c);
  float rms    = m.rms;
  float courant_A = K * rms;
  float puissance = 220.0f * courant_A;
  unsigned long maintenant = millis();
  bool etat_avant = c.actif;

  if (!c.actif) {
    if (rms >= c.seuilOn) {
      c.cptConfirm++;
      if (c.cptConfirm >= CONFIRMATIONS) { c.actif = true; c.cptConfirm = 0; }
    } else {
      c.cptConfirm = 0;
    }
  } else {
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
    c.t_debut = maintenant;
    Serial.printf("+++ %s ALLUME\n", c.id);
    
    // Envoi HTTP immédiat
    envoyerVersDjango(c, courant_A, puissance);
    c.last_send = maintenant;
  }

  // ---- Evenement OFF ----
  if (!c.actif && etat_avant) {
    c.nb_deconnexions++;
    c.t_debut = maintenant;
    c.somme_rms_on = 0.0f;
    c.nb_rms_on    = 0;
    Serial.printf("--- %s ETEINT\n", c.id);
    
    // Envoi HTTP immédiat
    envoyerVersDjango(c, 0.0f, 0.0f);
    c.last_send = maintenant;
  }

  // ---- Envoi HTTP régulier (Toutes les X secondes) ----
  if (maintenant - c.last_send > INTERVALLE_ENVOI_HTTP_MS) {
      envoyerVersDjango(c, courant_A, puissance);
      c.last_send = maintenant;
  }
}

// ========================================================================
void setup() {
  Serial.begin(9600);
  
  // 1. Initialisation de la file pour le Wi-Fi (capacité de 20 requêtes)
  httpQueue = xQueueCreate(20, sizeof(HttpData));

  // 2. Connexion Wi-Fi
  Serial.println("\n=== ZMCT103C - AOCEDA IOT (Wi-Fi) ===");
  Serial.print("Connexion a ");
  Serial.println(ssid);
  
  // Force le mode Station et reinitialise la puce Wi-Fi pour eviter les bugs
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(1000);
  
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connecte !");
  Serial.print("Adresse IP de l'ESP32 : ");
  Serial.println(WiFi.localIP());

  // 3. Démarrage de la tâche HTTP en arrière-plan (sur le coeur 0, l'ADC reste sur le coeur 1)
  xTaskCreatePinnedToCore(
      httpTask,      // Fonction de la tache
      "HTTP Task",   // Nom
      4096,          // Taille de la pile
      NULL,          // Parametres
      1,             // Priorite
      NULL,          // Handle
      0              // Epingle sur le coeur 0
  );

  Serial.println("Stabilisation offset...");
  for (int i = 0; i < 8; i++) {
    for (int j = 0; j < NB_CAPTEURS; j++) {
      acquerir(capteurs[j]);
    }
  }
  Serial.println("Pret a mesurer !");
}

void loop() {
  for (int i = 0; i < NB_CAPTEURS; i++) {
    traiterCapteur(capteurs[i]);
  }
}
