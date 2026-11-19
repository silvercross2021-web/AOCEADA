#pragma once
/*
  MODELE des secrets du firmware. Copier ce fichier en include/secrets.h (non versionné,
  ignoré par Git) puis y mettre les vraies valeurs. Ne jamais mettre de vrai mot de passe
  dans CE fichier : il est versionné.

  Sans include/secrets.h, le firmware compile quand même avec ces valeurs d'exemple : le
  Wi-Fi reste inactif (réseaux « A_REMPLIR » sautés) et les mesures partent par le câble
  USB vers le pont du PC (AOCEDA/outils/pont_usb_esp32.py).
*/

// Clé du boîtier, celle du compte du boîtier côté serveur (en-tête « Authorization:
// Device <clé> »). Le pont USB la lit aussi dans ce fichier.
#define AOCEDA_CLE_DISPOSITIF "remplacer-par-la-cle-du-boitier"

// Mot de passe des mises à jour du programme par Wi-Fi (voir src/reseau/Ota.cpp)
#define AOCEDA_MOT_DE_PASSE_OTA "remplacer-par-un-mot-de-passe-ota"

// Réseaux essayés dans l'ordre : { nom du Wi-Fi, mot de passe, adresse du serveur sur CE
// réseau }. L'ESP32 garde le PREMIER où il joint vraiment le serveur. Wi-Fi 2,4 GHz
// seulement (l'ESP32 ne voit pas le 5 GHz).
// L'adresse du PC est attribuée par DHCP : elle CHANGE quand le PC change de réseau (ou
// parfois au redémarrage de la box / du partage de connexion). Si l'ESP32 se connecte mais
// que tout finit en tampon (« [Serveur] INJOIGNABLE »), vérifier d'abord cette adresse :
// sur le PC, `ipconfig` -> adaptateur « Wi-Fi » -> « Adresse IPv4 ».
// Mot de passe pas encore saisi : écrire "A_REMPLIR" (le réseau est sauté).
#define AOCEDA_RESEAUX_WIFI                                                    \
  {"MonWifi", "A_REMPLIR", "http://192.168.1.10:8003/api/sensors/zmct/"},      \
  {"MonPartageDeConnexion", "A_REMPLIR", "http://172.20.10.2:8003/api/sensors/zmct/"},
