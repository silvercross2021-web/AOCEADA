"""Température de l'air CHEZ le client : le capteur DHT11 du boîtier, ramené à l'échelle de la météo de la ville (18/11/2026).

Pourquoi : quand il fait chaud, un logement consomme plus (climatiseur, ventilateur, réfrigérateur). La prévision
(prevision_ia) apprend l'effet de la chaleur sur les jours passés puis prévoit les jours à venir. Jusqu'ici, la
température venait seulement de la météo de la ville (Open-Meteo). Le DHT11 mesure l'air réel du logement.

Le piège à éviter : Open-Meteo est la seule source pour les jours À VENIR (le capteur ne mesure que le présent). Si l'on
apprenait l'effet de la chaleur avec le capteur, puis qu'on prévoyait avec la météo de la ville, on mélangerait deux
échelles : un capteur posé dans un boîtier, près des relais, lit souvent 1 à 3 °C de plus que l'air extérieur. Chaque degré
d'écart serait pris pour de la chaleur et fausserait la prévision. La règle suivie ici :

  1. Une journée « mesurée » = au moins 20 heures différentes sur 24 avec relevés (la moyenne de 24 heures est la
     définition de la température du jour d'Open-Meteo). Une journée trouée n'est pas utilisée : jamais de moyenne
     tirée de quelques heures chaudes seulement.
  2. Tant qu'il y a moins de 7 journées mesurées ET connues d'Open-Meteo, le capteur sert à CALIBRER seulement : la
     prévision garde la météo de la ville telle quelle (aucun mélange). C'est dit à l'écran.
  3. Ensuite, l'écart habituel entre le capteur et la ville est sa MÉDIANE sur les 45 derniers jours communs (robuste
     à une journée étrange). Les jours mesurés prennent la valeur du capteur ; tous les autres (jours sans relevé,
     aujourd'hui, jours à venir) prennent la météo de la ville CORRIGÉE de cet écart. Tout est donc sur la même
     échelle : celle de l'air du logement.
  4. Un écart supérieur à 12 °C n'est pas de la météo : capteur posé au soleil ou près d'une source de chaleur, ou en
     défaut. On revient alors à la météo de la ville, et on le dit.

Limite à connaître : le DHT11 est précis à ± 2 °C et à 1 °C près. Une moyenne de plusieurs milliers de relevés gomme
l'arrondi, pas un biais constant : c'est l'écart (point 3) qui le corrige. Et si le capteur est dans une pièce
rafraîchie par un climatiseur, sa température baisse justement quand l'appareil tourne : il vaut mieux le poser dans une
pièce que le climatiseur ne refroidit pas directement.
"""
import statistics
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.core.cache import cache
from django.db.models import Avg, Count
from django.db.models.functions import TruncHour
from django.utils import timezone

from apps.sensors.models import ReleveAmbiant

from . import meteo

HEURES_MIN_JOUR = 20            # heures distinctes (sur 24) avec relevés pour qu'une journée compte (≈ 83 %)
RELEVES_MIN_HEURE = 5           # relevés dans une heure pour qu'elle compte (2 min 30 : pas un relevé isolé)
JOURS_CALIBRATION_MIN = 7       # journées communes capteur / ville avant de se servir du capteur
FENETRE_DECALAGE_J = 45         # l'écart capteur - ville est la médiane des 45 derniers jours communs
DECALAGE_MAX_C = 12.0           # au-delà, ce n'est pas de la météo : capteur en défaut ou posé près d'une source de chaleur
AGE_MAX_RELEVE_S = 15 * 60      # un relevé plus vieux n'est plus « la température de maintenant »


def moyennes_journalieres(client, debut, fin):
    """{date: température moyenne de la journée (°C)} d'après les relevés du DHT11, pour les seules journées couvertes
    sur au moins HEURES_MIN_JOUR heures. Moyenne des moyennes horaires : une heure compte autant qu'une autre, même si
    le boîtier a envoyé plus de relevés pendant l'une d'elles."""
    tz = timezone.get_current_timezone()
    debut_dt = timezone.make_aware(datetime.combine(debut, time.min), tz)
    fin_dt = timezone.make_aware(datetime.combine(fin + timedelta(days=1), time.min), tz)
    par_heure = (ReleveAmbiant.objects.filter(dispositif__client=client, instant__gte=debut_dt, instant__lt=fin_dt)
                 .annotate(h=TruncHour("instant", tzinfo=tz)).values("h")
                 .annotate(t=Avg("temperature_c"), n=Count("id")))
    jours = defaultdict(list)
    for r in par_heure:
        if r["n"] >= RELEVES_MIN_HEURE and r["t"] is not None:
            jours[timezone.localtime(r["h"], tz).date()].append(float(r["t"]))
    return {d: sum(v) / len(v) for d, v in jours.items() if len(v) >= HEURES_MIN_JOUR}


def temperatures(client, debut, fin, maintenant=None):
    """({date: température (°C)}, info) de debut à fin incluses, sur UNE seule échelle (voir l'en-tête du module).

    info : source « capteur » (calibré, la prévision s'en sert) ou « ville » (météo d'Open-Meteo telle quelle) ;
    jours_mesures (journées couvertes par le DHT11), jours_communs (celles que la ville connaît aussi),
    jours_pour_calibrer (seuil), decalage_c (capteur - ville, si calibré), raison (pourquoi « ville » alors qu'un
    capteur existe : « calibration » ou « ecart_anormal »)."""
    maintenant = timezone.localtime(maintenant) if maintenant else timezone.localtime()
    ville = meteo.ville_du_client(client)
    de_la_ville = meteo.temperatures(ville, debut, fin)
    info = {"source": "ville", "calibre": False, "decalage_c": None, "jours_mesures": 0, "jours_communs": 0,
            "jours_pour_calibrer": JOURS_CALIBRATION_MIN, "raison": None}

    hier = maintenant.date() - timedelta(days=1)     # une journée en cours n'est pas finie : sa moyenne serait fausse
    mesures = moyennes_journalieres(client, debut, min(fin, hier)) if debut <= min(fin, hier) else {}
    info["jours_mesures"] = len(mesures)
    if not mesures:
        return de_la_ville, info                     # pas de DHT11, ou aucune journée complète : la ville, sans bruit

    communs = sorted(d for d in mesures if d in de_la_ville)[-FENETRE_DECALAGE_J:]
    info["jours_communs"] = len(communs)
    if len(communs) < JOURS_CALIBRATION_MIN:
        info["raison"] = "calibration"
        return de_la_ville, info

    decalage = statistics.median(mesures[d] - de_la_ville[d] for d in communs)
    if abs(decalage) > DECALAGE_MAX_C:
        info["raison"] = "ecart_anormal"
        info["decalage_c"] = round(decalage, 1)
        return de_la_ville, info

    sur_l_echelle_du_logement = {d: t + decalage for d, t in de_la_ville.items()}
    sur_l_echelle_du_logement.update({d: t for d, t in mesures.items() if debut <= d <= fin})
    info.update(source="capteur", calibre=True, decalage_c=round(decalage, 1))
    return sur_l_echelle_du_logement, info


ETAT_CACHE_S = 300              # l'avancement de la calibration ne bouge que d'un jour à l'autre : relu toutes les 5 min


def etat(client, maintenant=None):
    """Ce que le tableau de bord montre du capteur de température, INDÉPENDAMMENT de la prévision (qui n'affiche rien
    tant qu'elle n'a pas appris 3 journées) :
      capteur     : ce boîtier a-t-il déjà envoyé au moins un relevé ? (sinon le tableau de bord n'affiche rien)
      ambiance    : l'air de maintenant (relevé de moins de 15 min) ou None (capteur muet, boîtier hors ligne)
      calibration : source, jours_mesures, jours_communs, jours_pour_calibrer, decalage_c, raison (voir temperatures())
    Le calcul de la calibration lit des semaines de relevés : gardé 5 minutes, alors que l'air de maintenant est relu à
    chaque appel (une seule ligne)."""
    ambiance = releve_actuel(client, maintenant)
    if not ReleveAmbiant.objects.filter(dispositif__client=client).exists():
        return {"capteur": False, "ambiance": None, "calibration": None}
    cle = f"temperature_locale:etat:{client.pk}"
    calibration = cache.get(cle)
    if calibration is None:
        m = timezone.localtime(maintenant) if maintenant else timezone.localtime()
        _, calibration = temperatures(client, m.date() - timedelta(days=FENETRE_DECALAGE_J), m.date() + timedelta(days=1), m)
        cache.set(cle, calibration, ETAT_CACHE_S)
    return {"capteur": True, "ambiance": ambiance, "calibration": calibration}


def releve_actuel(client, maintenant=None):
    """Le dernier relevé du DHT11 s'il date de moins de 15 minutes : {temperature_c, humidite_pct, il_y_a_s}, sinon None
    (boîtier sans capteur, capteur muet, boîtier hors ligne : jamais une valeur périmée présentée comme actuelle)."""
    instant_actuel = maintenant or timezone.now()
    r = ReleveAmbiant.objects.filter(dispositif__client=client).order_by("-instant").first()
    if r is None:
        return None
    age = (instant_actuel - r.instant).total_seconds()
    if age > AGE_MAX_RELEVE_S or age < -300:
        return None
    return {"temperature_c": float(r.temperature_c),
            "humidite_pct": float(r.humidite_pct) if r.humidite_pct is not None else None,
            "il_y_a_s": max(0, int(age))}
