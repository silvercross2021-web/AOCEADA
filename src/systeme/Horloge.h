#pragma once
/*
  Heure réelle (UTC ; Côte d'Ivoire = UTC+0, pas d'heure d'été : aucun décalage).
  Indispensable pour qu'une mesure mise en tampon garde SA vraie date d'acquisition quand
  elle est rejouée plus tard (timestamp_unix côté serveur), et pour dater le relevé DHT11.
  Sources : NTP (Wi-Fi) ou, sans Wi-Fi, l'heure du PC envoyée par le pont USB.
*/

namespace Horloge {

// Avant cette valeur, l'heure n'est pas fiable (l'horloge de l'ESP32 démarre en 1970)
constexpr unsigned long TIMESTAMP_MIN_VALIDE = 1700000000UL;

// Synchronisation NTP (attend 10 s au plus)
void synchroniser();

// Heure UNIX actuelle, 0 si inconnue (le serveur utilisera alors l'heure de réception)
unsigned long heureUnix();

// Règle l'horloge SEULEMENT si elle n'a pas d'heure. true si elle vient d'être réglée.
bool reglerSiInconnue(unsigned long heureUnix);

} // namespace Horloge
