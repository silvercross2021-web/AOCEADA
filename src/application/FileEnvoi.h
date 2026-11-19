#pragma once
/*
  File d'attente entre la boucle de mesure (producteur) et la tâche réseau (consommateur) :
  évite de bloquer les mesures pendant un envoi. Une mesure est déposée SANS attendre : si la
  file est pleine (20 mesures), elle est perdue plutôt que de ralentir la mesure.
*/
#include "domaine/Capteur.h"

struct MesureAEnvoyer {
  char capteur[16];
  char etat[4]; // "ON" / "OFF"
  float courant;
  float puissance;
  unsigned long timestamp; // heure UNIX, 0 si inconnue
};

namespace FileEnvoi {

void creer();

// Dépose l'état courant du capteur (courant et puissance à 0 s'il est éteint)
void deposer(const EtatCapteur &c, float courant, float puissance);

// Attend une mesure au plus attenteMs
bool recevoir(MesureAEnvoyer &mesure, unsigned long attenteMs);

// Nombre de mesures en attente d'envoi
int enAttente();

// Drapeau « un envoi est en cours » : la boucle de mesure laisse la radio à la tâche réseau
void definirEnvoiEnCours(bool enCours);
bool envoiEnCours();

} // namespace FileEnvoi
