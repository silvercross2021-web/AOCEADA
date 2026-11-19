#pragma once
/*
  Canal de secours USB : quand le Wi-Fi ou le serveur ne répond pas, la mesure part par le
  câble USB (port série) vers le pont du PC (AOCEDA/outils/pont_usb_esp32.py), qui la transmet
  à Django et renvoie, dans un accusé de réception, la MÊME réponse que le serveur donnerait en
  Wi-Fi : les ordres de coupure des relais passent donc aussi par l'USB.
    ESP32 -> PC : @USB {json de la mesure}
    PC -> ESP32 : @HEURE <heure UNIX du PC>            (ignorée si la carte a déjà une heure)
                  @ACK {"created":1,"coupe_1":false,"coupe_2":false}
  Sans accusé dans USB_ATTENTE_ACK_MS (pont absent ou serveur arrêté), la mesure est traitée
  comme un échec d'envoi (tampon habituel) et l'USB n'est retenté qu'une fois toutes les
  USB_PAUSE_SANS_PONT_MS : aucun ralentissement si le pont n'est pas lancé. Jamais utilisé
  quand l'envoi Wi-Fi a réussi : pas de doublon.
  L'heure du PC sert quand il n'y a pas de Wi-Fi, donc pas de NTP : sans elle, le relevé de
  température ne pourrait pas être daté et ne partirait jamais.
*/
#include <Arduino.h>

namespace CanalUsb {

// true = le pont a acquitté la mesure
bool envoyer(const String &json);

} // namespace CanalUsb
