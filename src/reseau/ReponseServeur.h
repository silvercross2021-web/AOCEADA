#pragma once
/*
  Réponse du serveur à une mesure, quel que soit le chemin (Wi-Fi ou câble USB). Elle porte
  les ordres de coupure des relais. La couche réseau ne connaît pas les relais : l'application
  branche ici celui qui s'en occupe (voir application/Demarrage.cpp).
*/
#include <Arduino.h>

namespace ReponseServeur {

using Ecouteur = void (*)(const String &reponse);

void definirEcouteur(Ecouteur ecouteur);

// Appelée par ClientHttp et CanalUsb quand une mesure est acquittée
void recue(const String &reponse);

} // namespace ReponseServeur
