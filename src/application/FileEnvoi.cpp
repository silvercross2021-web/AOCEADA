#include "application/FileEnvoi.h"
#include "systeme/Horloge.h"
#include <Arduino.h>

namespace FileEnvoi {

namespace {
QueueHandle_t file;
volatile bool enCours = false;
} // namespace

void creer() { file = xQueueCreate(Reglages::TAILLE_FILE_ENVOI, sizeof(MesureAEnvoyer)); }

void deposer(const EtatCapteur &c, float courant, float puissance) {
  MesureAEnvoyer m;
  // snprintf garantit la présence du '\0' final
  snprintf(m.capteur, sizeof(m.capteur), "%s", c.id);
  snprintf(m.etat, sizeof(m.etat), "%s", c.actif ? "ON" : "OFF");
  m.courant = c.actif ? courant : 0.0f;
  m.puissance = c.actif ? puissance : 0.0f;
  m.timestamp = Horloge::heureUnix();
  xQueueSend(file, &m, 0); // sans bloquer si la file est pleine
}

bool recevoir(MesureAEnvoyer &mesure, unsigned long attenteMs) {
  return xQueueReceive(file, &mesure, pdMS_TO_TICKS(attenteMs)) == pdPASS;
}

int enAttente() { return (int)uxQueueMessagesWaiting(file); }

void definirEnvoiEnCours(bool valeur) { enCours = valeur; }

bool envoiEnCours() { return enCours; }

} // namespace FileEnvoi
