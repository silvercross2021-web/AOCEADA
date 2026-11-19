"""Température et humidité de l'air envoyées par le boîtier (capteur DHT11) : validation et enregistrement (18/11/2026).

Le firmware joint, UNE fois par relevé (toutes les 30 s), trois champs à une trame de mesure :
  temperature_c, humidite_pct, releve_unix (l'instant du relevé, epoch UTC).
Rien n'est jamais inventé : un champ absent ou aberrant ne donne AUCUNE ligne (ou une ligne sans humidité), jamais une
valeur par défaut. Une valeur aberrante n'est pas un motif de refuser toute la trame : les mesures de courant, qui
passent par la même requête, doivent arriver quoi qu'il arrive.
"""
import logging
import math
from decimal import Decimal

from .models import ReleveAmbiant

logger = logging.getLogger(__name__)

# Bornes de plausibilité de l'air d'un logement. Le DHT11 mesure de 0 à 50 °C (± 2 °C) et de 20 à 90 % (± 5 %) :
# au-delà de ces marges, c'est un capteur en défaut, pas de la météo. Le défaut typique est le couple « 0 °C, 0 % »
# (réponse vide mais de somme de contrôle valide) : aucun logement n'est à moins de 5 °C, et la précision du DHT11
# s'effondre près de 0 °C. On écarte donc ces valeurs plutôt que de les enregistrer comme une nuit glaciale.
TEMPERATURE_MIN_C = 5.0
TEMPERATURE_MAX_C = 60.0
HUMIDITE_MIN_PCT = 1.0
HUMIDITE_MAX_PCT = 100.0


def _nombre_plausible(valeur, minimum, maximum):
    """La valeur arrondie au dixième, ou None si elle est absente, non numérique ou hors des bornes."""
    if valeur is None or isinstance(valeur, bool):
        return None
    try:
        v = float(valeur)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v < minimum or v > maximum:
        return None
    return round(v, 1)


def releve_valide(temperature_c, humidite_pct):
    """(température, humidité) arrondies au dixième, ou None si la température est inutilisable. Une humidité
    aberrante est ignorée (None) sans écarter la température : ce sont deux mesures du même capteur, mais la
    température seule suffit à la prévision."""
    t = _nombre_plausible(temperature_c, TEMPERATURE_MIN_C, TEMPERATURE_MAX_C)
    if t is None:
        return None
    return t, _nombre_plausible(humidite_pct, HUMIDITE_MIN_PCT, HUMIDITE_MAX_PCT)


def noter_releves(dispositif, releves):
    """Enregistre les relevés d'un boîtier : [(instant, température, humidité)]. Renvoie le nombre de lignes
    réellement créées. Les relevés aberrants sont écartés ; un relevé déjà connu (même boîtier, même instant) est
    ignoré sans erreur (accusé perdu, tampon rejoué)."""
    a_creer, vus = [], set()
    for instant, temperature, humidite in releves:
        valide = releve_valide(temperature, humidite)
        if valide is None:
            if temperature is not None:
                logger.info("Relevé ambiant écarté (hors bornes) pour %s : %r °C, %r %%", dispositif.pk,
                            temperature, humidite)
            continue
        if instant in vus:
            continue
        vus.add(instant)
        t, h = valide
        a_creer.append(ReleveAmbiant(dispositif=dispositif, instant=instant, temperature_c=Decimal(str(t)),
                                     humidite_pct=Decimal(str(h)) if h is not None else None))
    if not a_creer:
        return 0
    avant = ReleveAmbiant.objects.filter(dispositif=dispositif, instant__in=[r.instant for r in a_creer]).count()
    ReleveAmbiant.objects.bulk_create(a_creer, ignore_conflicts=True)
    return len(a_creer) - avant
