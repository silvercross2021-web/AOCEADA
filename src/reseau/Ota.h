#pragma once
/*
  Mise à jour du programme par Wi-Fi, sans câble. Depuis le PC, avec un Python autorisé par le
  pare-feu :
    python espota.py -i <IP de l'ESP32> -a <mot de passe OTA> -f firmware.bin
  (espota.py : dossier tools du paquet framework-arduinoespressif32 de PlatformIO ; le mot de
  passe est AOCEDA_MOT_DE_PASSE_OTA, dans include/secrets.h).
*/

namespace Ota {

// À appeler à chaque tour de boucle : démarre le service dès que le Wi-Fi est là, puis
// traite les demandes de mise à jour
void suivre();

} // namespace Ota
