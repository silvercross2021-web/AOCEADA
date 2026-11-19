#pragma once
/*
  Démarrage de la carte, dans l'ordre :
   1. services de base (série, verrou radio, file d'envoi, mémoire) ;
   2. relais (dernier ordre enregistré, appareils coupés le temps de mesurer le bruit) et DHT11 ;
   3. Wi-Fi, BORNE dans le temps : si le réseau n'est pas là, la carte démarre quand même et
      mesure hors ligne ; la reconnexion se fait en arrière-plan ;
   4. tâches réseau ;
   5. bruit de fond de chaque capteur (relais ouverts), puis les appareils retrouvent leur ordre.
*/

namespace Demarrage {

void executer();

} // namespace Demarrage
