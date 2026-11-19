#pragma once
/*
  Connexion Wi-Fi à plusieurs réseaux. Les réseaux (nom, mot de passe, adresse du serveur sur
  CE réseau) sont dans include/secrets.h et essayés dans l'ordre : l'ESP32 garde le PREMIER
  où il joint vraiment le serveur (un GET y répond). Si le serveur ne répond sur aucun, il
  reste sur le premier réseau joint : les mesures partent en tampon, rejouées plus tard.
  Aucune tentative ne bloque indéfiniment : l'appareil démarre et mesure même sans réseau, et
  la reconnexion est retentée en tâche de fond.
*/

namespace Reseau {

// Choisit le réseau n°0 (serveur et journal UDP) en attendant la connexion
void initialiser();

// Mode station, déconnecté (début du démarrage)
void demarrerRadio();

// Affiche la liste des réseaux configurés
void afficherConfiguration();

// Liste les réseaux 2,4 GHz visibles. Si un réseau configuré n'apparaît pas, c'est qu'il
// émet en 5 GHz (invisible pour l'ESP32), qu'il est éteint ou hors de portée.
void diagnostiquer();

bool connecte();

// Adresse du serveur sur le réseau en cours ("http://IP:port/api/sensors/zmct/")
const char *serveur();

// Nom du réseau en cours
const char *ssidActif();

// Essaie les réseaux dans l'ordre, chacun pendant attenteMs au plus. true si connecté.
bool connecter(unsigned long attenteMs);

// Reconnexion de fond, au plus une tentative toutes les 15 s. true seulement quand une
// connexion vient d'être établie (le moment de resynchroniser l'heure).
bool reconnecterSiBesoin();

// Se déconnecte et autorise une nouvelle tentative tout de suite (serveur muet : on
// réessaie tous les réseaux)
void forcerReconnexion();

} // namespace Reseau
