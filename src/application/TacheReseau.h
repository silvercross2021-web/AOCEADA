#pragma once
/*
  Tâches réseau, sur le coeur 0 (l'ADC reste sur le coeur 1) :
   - tâche d'envoi : prend les mesures dans la file et les envoie par Wi-Fi ; sinon par le
     câble USB (pont du PC) ; sinon les met en tampon ; rejoue le tampon dès que possible ;
   - tâche Wi-Fi : reconnexion en arrière-plan, séparée de l'envoi (une tentative attend
     jusqu'à 8 s par réseau : dans la tâche d'envoi, elle bloquerait aussi le canal USB).
*/

namespace TacheReseau {

void demarrer();

} // namespace TacheReseau
