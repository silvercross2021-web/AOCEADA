"""Température du jour, ville par ville, pour la prévision (19/10/2026).

Quand il fait plus chaud, un logement consomme plus (climatiseur, ventilateur, réfrigérateur). La température vient
d'Open-Meteo (gratuit, sans clé) : UNE requête donne les 92 derniers jours (pour apprendre l'effet de la chaleur) et les
16 jours à venir (pour prévoir). Les valeurs sont gardées en base (MeteoJour), relues au plus toutes les 6 heures par
ville, en arrière-plan : la page n'attend jamais Internet, et une panne du service ne casse rien (la prévision se fait alors sans la
température, et le dit).
"""
import logging
import threading
import time
from datetime import date

import requests
from django.conf import settings
from django.utils import timezone

from apps.accounts.villes import VILLE_PAR_DEFAUT, VILLES

from .models import MeteoJour

logger = logging.getLogger(__name__)

URL = "https://api.open-meteo.com/v1/forecast"
JOURS_PASSES = 92
JOURS_FUTURS = 16
RAFRAICHIR_S = 6 * 3600
DELAI_S = 6
_derniere = {}                       # ville -> heure du dernier essai (réussi ou non), dans ce processus
_en_cours = set()                    # villes en cours de relecture (arrière-plan)
_verrou = threading.Lock()


def ville_du_client(client):
    v = getattr(client, "ville", None)
    return v if v in VILLES else VILLE_PAR_DEFAUT


def _telecharger(ville):
    """[(« AAAA-MM-JJ », moyenne °C, maximum °C)] chez Open-Meteo. Lève une exception si le service ne répond pas."""
    lat, lon = VILLES[ville]
    r = requests.get(URL, timeout=DELAI_S, params={
        "latitude": lat, "longitude": lon, "daily": "temperature_2m_mean,temperature_2m_max",
        "past_days": JOURS_PASSES, "forecast_days": JOURS_FUTURS, "timezone": "Africa/Abidjan"})
    r.raise_for_status()
    d = r.json()["daily"]
    return list(zip(d["time"], d["temperature_2m_mean"], d["temperature_2m_max"]))


def rafraichir(ville, forcer=False):
    """Relit les températures de la ville si la dernière lecture date de plus de 6 h. True si la base a été mise à jour."""
    if not getattr(settings, "METEO_EN_LIGNE", True):
        return False
    with _verrou:
        if not forcer and time.time() - _derniere.get(ville, 0.0) < RAFRAICHIR_S:
            return False
        _derniere[ville] = time.time()
    try:
        lignes = _telecharger(ville)
    except Exception as e:                    # service en panne ou pas d'Internet : on garde ce qu'on a
        logger.warning("Météo indisponible pour %s : %s", ville, e)
        return False
    aujourd_hui = timezone.localdate()
    jours = [MeteoJour(ville=ville, date=date.fromisoformat(jour), t_moy=round(float(t_moy), 1),
                       t_max=round(float(t_max), 1) if t_max is not None else None,
                       prevue=date.fromisoformat(jour) > aujourd_hui)
             for jour, t_moy, t_max in lignes if t_moy is not None]
    # une seule écriture groupée (le boîtier écrit toutes les 2 s : pas d'une centaine d'écritures à la suite)
    MeteoJour.objects.bulk_create(jours, update_conflicts=True, unique_fields=["ville", "date"],
                                  update_fields=["t_moy", "t_max", "prevue", "maj"])
    return True


def rafraichir_en_fond(ville):
    """Relecture en arrière-plan si besoin : la page n'attend JAMAIS Internet (audit du 19/10/2026 : la 1re prévision
    du jour attendait Open-Meteo jusqu'à 6 s). Elle utilise ce qui est déjà en base ; la suivante aura la mise à jour."""
    if not getattr(settings, "METEO_EN_LIGNE", True):
        return
    with _verrou:
        if time.time() - _derniere.get(ville, 0.0) < RAFRAICHIR_S or ville in _en_cours:
            return
        _en_cours.add(ville)

    def travail():
        try:
            rafraichir(ville)
        finally:
            from django.db import connection
            connection.close()
            with _verrou:
                _en_cours.discard(ville)
    threading.Thread(target=travail, daemon=True, name=f"meteo-{ville}").start()


def temperatures(ville, debut, fin):
    """{date: température moyenne (°C)} de debut à fin incluses, d'après la base (relue en arrière-plan si besoin)."""
    ville = ville if ville in VILLES else VILLE_PAR_DEFAUT
    rafraichir_en_fond(ville)
    return {m.date: float(m.t_moy) for m in MeteoJour.objects.filter(ville=ville, date__gte=debut, date__lte=fin)}
