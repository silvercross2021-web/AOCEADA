"""Conseils du tableau de bord et de l'historique : calculés sur les VRAIES mesures et habitudes du client.

Chaque règle regarde des données réelles (mesures récentes, habitudes par appareil sur 30 jours, crédit, tranche,
météo annoncée) et renvoie un conseil chiffré et actionnable, ou rien. Les règles d'urgence (pic au-dessus de
l'abonnement, crédit bas, tranche, appareil allumé longtemps, hausse, nuit élevée) passent en premier, suivies des
analyses d'habitudes par appareil (plages horaires habituelles, répartition entre appareils, pics récurrents, rythme
semaine/week-end, durée quotidienne d'usage). Les conseils généraux (liste fixe, marqués « general ») ne servent qu'en
dernier recours, quand aucune mesure exploitable n'existe. Une donnée absente ne produit jamais un chiffre inventé.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Max, Sum
from django.db.models.functions import TruncHour
from django.utils import timezone

from apps.sensors.models import Capteur, MesureEnergie

from .tarifs_cie import PUISSANCE_KW

FENETRE_J = 7
FENETRE_HABITUDES_J = 30
NUIT = set(range(22, 24)) | set(range(0, 6))          # 22 h → 6 h
PART_NUIT_MIN = 0.25                                  # au moins 25 % de la consommation de nuit
KWH_MIN = 2.0                                         # seuil des règles hebdomadaires (hausse, nuit, dominant)
KWH_MIN_AVANT = 1.0                                   # semaine de référence de la comparaison
HAUSSE_MIN = 0.20
ALLUME_LONGTEMPS_H = 8
CHALEUR_C = 33.0
MOTS_CLIM = ("climatis", "clim", "split")

CRENEAUX = (
    ("matin", tuple(range(6, 12)), "le matin"),
    ("apres_midi", tuple(range(12, 18)), "l'après-midi"),
    ("soiree", tuple(range(18, 22)), "en soirée"),
    ("nuit", (22, 23, 0, 1, 2, 3, 4, 5), "la nuit"),
)
JOURS_SEMAINE_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

CATEGORIES_APPAREILS = (
    ("clim", ("climatis", "clim", "split")),
    ("frigo", ("réfrigér", "refriger", "frigo", "congél", "congel")),
    ("eclairage", ("ampoule", "lampe", "éclair", "eclair", "led", "lumière", "lumiere", "lustre", "néon", "neon")),
    ("prise", ("prise", "multiprise", "chargeur", "bureau", "ordinateur", "pc")),
    ("tv", ("télé", "tele", "tv", "décodeur", "decodeur", "box", "console")),
    ("chauffe_eau", ("chauffe", "ballon", "bouilloire", "cumulus")),
    ("ventilateur", ("ventil", "brasseur")),
    ("cuisson", ("four", "micro", "cuisine", "plaque", "cuisini", "fer", "repass")),
)

CONSEILS_GENERAUX = [
    ("Éteignez les appareils en veille", "Les veilles s'additionnent : une multiprise à interrupteur les coupe toutes d'un geste."),
    ("Climatiseur réglé vers 26 °C", "Chaque degré plus froid fait travailler davantage le climatiseur. Fermez portes et fenêtres quand il tourne."),
    ("Préférez le ventilateur", "Un ventilateur consomme bien moins qu'un climatiseur : gardez la climatisation pour les heures les plus chaudes."),
    ("Aérez l'arrière du réfrigérateur", "Laissez un espace derrière lui, loin du soleil et de la cuisinière, et dégivrez-le : il consommera moins."),
    ("Passez aux ampoules LED", "Pour la même lumière, une ampoule LED consomme bien moins qu'une ampoule classique et dure plus longtemps."),
    ("Débranchez les chargeurs", "Un chargeur resté branché continue de consommer, même sans téléphone au bout."),
    ("Repassez en une seule fois", "Le fer consomme surtout pour chauffer : regroupez le linge pour ne le faire chauffer qu'une fois."),
    ("Chauffez juste l'eau qu'il faut", "Bouilloire ou chauffe-eau : ne faites chauffer que la quantité d'eau dont vous avez besoin."),
]


def _f(x, dec=1):
    """Nombre à la française : 1 234,5."""
    s = f"{float(x):,.{dec}f}".replace(",", " ").replace(".", ",")
    return s.replace(",0", "") if dec and s.endswith(",0") else s


def _energie(kwh):
    """Affiche en Wh sous 1 kWh (évite « 0 kWh » pour une ampoule ou une prise), sinon en kWh."""
    val = float(kwh or 0)
    if val < 1.0:
        wh = round(val * 1000)
        return f"{_f(wh, 0)} Wh" if wh >= 1 else "moins d'1 Wh"
    return f"{_f(val, 1)} kWh"


def _categorie_appareil(nom):
    n = (nom or "").lower()
    for cat, mots in CATEGORIES_APPAREILS:
        if any(m in n for m in mots):
            return cat
    return "autre"


def _action_appareil(categorie, contexte):
    """Conseil concret adapté au type réel de l'appareil et à l'habitude constatée."""
    regles_actions = {
        ("eclairage", "jour"): "Profitez au maximum de la lumière naturelle et éteignez-la dès que la pièce est assez éclairée ou vide.",
        ("eclairage", "nuit"): "Vérifiez qu'elle ne reste pas allumée pendant votre sommeil ; vous pouvez la couper à distance depuis le tableau de bord.",
        ("eclairage", "soiree"): "Pensez à l'éteindre en quittant la pièce et privilégiez une ampoule LED basse consommation.",
        ("eclairage", "duree"): "Éteignez-la systématiquement dans les pièces inoccupées : sur la durée, ces heures pèsent sur votre facture.",
        ("eclairage", "pic"): "Vérifiez qu'aucun appareil énergivore n'est branché sur ce circuit d'éclairage et privilégiez des ampoules LED.",
        ("eclairage", "repartition"): "Éteignez-la dès que vous quittez la pièce et remplacez les ampoules classiques par des LED.",
        ("prise", "pic"): "Évitez de brancher plusieurs appareils puissants en même temps sur cette prise pour protéger votre disjoncteur.",
        ("prise", "nuit"): "Débranchez les chargeurs ou coupez cette prise le soir (ou à distance) pour supprimer les veilles nocturnes.",
        ("prise", "jour"): "Débranchez les appareils dès la fin d'utilisation ou coupez la prise à distance pour éviter toute veille inutile.",
        ("prise", "soiree"): "Coupez la prise ou utilisez une multiprise à interrupteur dès que vos appareils n'ont plus besoin de charger.",
        ("prise", "duree"): "Coupez cette prise dès la fin de charge ou d'usage afin d'éliminer les consommations fantômes.",
        ("prise", "repartition"): "Identifiez l'appareil le plus gourmand branché sur cette prise et coupez-la hors utilisation.",
        ("clim", "nuit"): "Réglez-le vers 26 °C et programmez son arrêt avant le réveil pour économiser sans perdre en confort.",
        ("clim", "jour"): "Gardez portes et fenêtres fermées, réglez-le vers 26 °C et nettoyez ses filtres régulièrement.",
        ("clim", "soiree"): "Réglez-le vers 26 °C, fermez bien la pièce et coupez-le dès que la fraîcheur suffit.",
        ("clim", "duree"): "Alternez avec un ventilateur aux heures moins chaudes et coupez-le dans les pièces vides.",
        ("clim", "pic"): "Évitez de lancer le climatiseur en même temps que d'autres gros appareils (fer, chauffe-eau, four).",
        ("clim", "repartition"): "Régler le thermostat à 26 °C et fermer portes et fenêtres offre les économies les plus rapides.",
        ("frigo", "pic"): "Vérifiez que l'arrière est bien ventilé et que le compresseur ne force pas à cause de joints usés.",
        ("frigo", "duree"): "Laissez un espace ventilé derrière l'appareil, vérifiez les joints de porte et dégivrez-le régulièrement.",
        ("frigo", "repartition"): "Éloignez-le de la chaleur, évitez d'y placer des plats chauds et dégivrez-le régulièrement.",
        ("tv", "nuit"): "Éteignez complètement le téléviseur et le décodeur avant de dormir pour éviter des heures de veille.",
        ("tv", "duree"): "Coupez complètement l'écran et sa box après usage plutôt que de les laisser en veille.",
        ("tv", "repartition"): "Éteignez complètement le poste et le décodeur (ou via une multiprise) dès que vous ne regardez plus.",
        ("chauffe_eau", "pic"): "Évitez de le faire chauffer en même temps que le climatiseur ou le fer pour éviter une disjonction.",
        ("chauffe_eau", "duree"): "Allumez-le uniquement 30 à 60 min avant usage au lieu de maintenir l'eau chaude en continu.",
        ("chauffe_eau", "repartition"): "Ne chauffez que la quantité ou la durée nécessaire, puis coupez-le dès que l'eau est prête.",
        ("ventilateur", "nuit"): "Programmez son arrêt ou réduisez sa vitesse une fois la nuit plus fraîche.",
        ("ventilateur", "duree"): "Éteignez-le en sortant de la pièce : un ventilateur rafraîchit les personnes, pas une pièce vide.",
        ("ventilateur", "repartition"): "Coupez-le systématiquement quand personne n'est dans la pièce.",
        ("cuisson", "pic"): "Évitez d'utiliser cet appareil en même temps que d'autres gros équipements pour limiter les pics.",
        ("cuisson", "repartition"): "Regroupez vos sessions (cuisson ou repassage) pour éviter les montées en température répétées.",
    }
    if (categorie, contexte) in regles_actions:
        return regles_actions[(categorie, contexte)]
    if (categorie, "repartition") in regles_actions:
        return regles_actions[(categorie, "repartition")]
    defauts = {
        "nuit": "Vérifiez si cet appareil doit vraiment tourner la nuit ; l'éteindre ou le couper à distance réduira votre facture.",
        "pic": "Évitez de le faire fonctionner en même temps que d'autres gros appareils pour préserver votre installation.",
        "duree": "Réduire un peu sa durée de fonctionnement quotidien aura un effet direct sur votre facture.",
        "weekend": "Surveillez les appareils restés allumés plus longtemps le week-end et coupez ceux qui ne servent pas.",
        "semaine": "Éteignez cet appareil dès la fin de vos activités en semaine pour garder une consommation maîtrisée.",
    }
    return defauts.get(
        contexte,
        "Ajustez ses horaires d'usage et éteignez-le dès qu'il n'est plus nécessaire pour garantir une bonne consommation.",
    )


def _creneau_de(heure):
    for code, heures, _ in CRENEAUX:
        if heure in heures:
            return code
    return "jour"


def _formater_heure(h):
    return "minuit" if h == 0 else f"{h} h"


def _plage_pic(par_heure, heures_autorisees=None):
    """Trouve le créneau continu de 1 à 3 h le plus chargé. Renvoie (format_court, phrase_fr)."""
    if not par_heure:
        return ("", "")
    heures = list(heures_autorisees) if heures_autorisees else list(range(24))
    actives = [h for h in heures if par_heure.get(h, 0.0) > 0]
    if not actives:
        return ("", "")
    # Meilleure fenêtre de 2 heures consécutives dans la liste des heures du créneau
    meilleure_somme = -1.0
    meilleur_i = 0
    for i, h in enumerate(heures):
        s = par_heure.get(h, 0.0)
        if i + 1 < len(heures):
            s += par_heure.get(heures[i + 1], 0.0)
        if s > meilleure_somme:
            meilleure_somme = s
            meilleur_i = i
    h0 = heures[meilleur_i]
    v0 = par_heure.get(h0, 0.0)
    h1 = heures[meilleur_i + 1] if meilleur_i + 1 < len(heures) else None
    v1 = par_heure.get(h1, 0.0) if h1 is not None else 0.0
    pic_local = max(v0, v1)
    if v0 == 0 and h1 is not None:
        h0, v0 = h1, v1
        meilleur_i += 1
        h1 = heures[meilleur_i + 1] if meilleur_i + 1 < len(heures) else None
        v1 = par_heure.get(h1, 0.0) if h1 is not None else 0.0
    if h1 is not None and v1 >= pic_local * 0.20:
        h2 = heures[meilleur_i + 2] if meilleur_i + 2 < len(heures) else None
        v2 = par_heure.get(h2, 0.0) if h2 is not None else 0.0
        if h2 is not None and v2 >= pic_local * 0.25:
            fin = (h2 + 1) % 24
        else:
            fin = (h1 + 1) % 24
        return (f"{h0} h–{_formater_heure(fin)}", f"entre {h0} h et {_formater_heure(fin)}")
    return (f"vers {h0} h", f"vers {h0} h")


def _conseil(kind, priorite, titre, texte, lien="/historique/", habitude=False, **chiffres):
    return {
        "kind": kind,
        "priorite": priorite,
        "mesure": True,
        "habitude": bool(habitude),
        "titre": titre,
        "texte": texte,
        "lien": lien,
        "chiffres": chiffres,
    }


def _donnees(client, maintenant, sensor_id=None):
    """kWh par (capteur, heure locale) sur 14 jours."""
    debut = maintenant - timedelta(days=2 * FENETRE_J)
    qs = MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=debut)
    if sensor_id:
        qs = qs.filter(capteur_id=sensor_id)
    lignes = (qs.annotate(h=TruncHour('timestamp'))
              .values('capteur__nom', 'h').annotate(e=Sum('energie')))
    recents, avant = defaultdict(lambda: defaultdict(float)), defaultdict(float)
    limite = maintenant - timedelta(days=FENETRE_J)
    nuit = defaultdict(float)
    for r in lignes:
        e = float(r['e'] or 0)
        if r['h'] >= limite:
            recents[r['capteur__nom']]['kwh'] += e
            if timezone.localtime(r['h']).hour in NUIT:
                nuit[r['capteur__nom']] += e
        else:
            avant[r['capteur__nom']] += e
    return recents, avant, nuit


def _pics(client, maintenant, sensor_id=None):
    qs = MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=maintenant - timedelta(days=FENETRE_J))
    if sensor_id:
        qs = qs.filter(capteur_id=sensor_id)
    rows = qs.values('capteur__nom').annotate(p=Max('puissance'))
    return {r['capteur__nom']: float(r['p'] or 0) for r in rows}


def _habitudes_appareils(client, maintenant, sensor_id=None):
    """Analyse agrégée des habitudes par appareil sur les 30 derniers jours (ou les 30 derniers jours enregistrés)."""
    base_qs = MesureEnergie.objects.filter(capteur__client=client)
    if sensor_id:
        base_qs = base_qs.filter(capteur_id=sensor_id)

    debut = maintenant - timedelta(days=FENETRE_HABITUDES_J)
    fenetre_recente = True

    def _agg(qs):
        return list(
            qs.annotate(h=TruncHour('timestamp'))
              .values('capteur_id', 'capteur__nom', 'h')
              .annotate(
                  kwh=Sum('energie'),
                  p_moy=Avg('puissance'),
                  p_max=Max('puissance'),
                  n=Count('id'),
              )
        )

    lignes = _agg(base_qs.filter(timestamp__gte=debut, timestamp__lte=maintenant))
    if not lignes:
        derniere = base_qs.aggregate(m=Max('timestamp'))['m']
        if derniere is None:
            return None
        fenetre_recente = False
        debut_hist = derniere - timedelta(days=FENETRE_HABITUDES_J)
        lignes = _agg(base_qs.filter(timestamp__gte=debut_hist, timestamp__lte=derniere))
        if not lignes:
            return None

    par_cap = {}
    for r in lignes:
        cid = r['capteur_id']
        nom = r['capteur__nom']
        kwh = float(r['kwh'] or 0)
        p_moy = float(r['p_moy'] or 0)
        p_max = float(r['p_max'] or 0)
        n = int(r['n'] or 0)
        if kwh <= 0 and p_max <= 0:
            continue
        dt_loc = timezone.localtime(r['h'])
        jour = dt_loc.date()
        heure = dt_loc.hour
        creneau = _creneau_de(heure)

        app = par_cap.get(cid)
        if app is None:
            app = {
                "id": str(cid),
                "nom": nom,
                "categorie": _categorie_appareil(nom),
                "kwh": 0.0,
                "n": 0,
                "p_somme": 0.0,
                "p_max": 0.0,
                "heures_actives": 0,
                "jours_actifs": set(),
                "par_heure": defaultdict(float),
                "par_creneau": defaultdict(float),
                "par_jour": defaultdict(float),
            }
            par_cap[cid] = app

        app["kwh"] += kwh
        app["n"] += n
        app["p_somme"] += p_moy * n
        if p_max > app["p_max"]:
            app["p_max"] = p_max
        app["heures_actives"] += 1
        app["jours_actifs"].add(jour)
        app["par_heure"][heure] += kwh if kwh > 0 else (p_moy / 1000.0)
        app["par_creneau"][creneau] += kwh if kwh > 0 else (p_moy / 1000.0)
        app["par_jour"][jour] += kwh

    appareils = []
    for app in par_cap.values():
        nb_j = len(app["jours_actifs"])
        app["p_moy"] = (app["p_somme"] / app["n"]) if app["n"] > 0 else 0.0
        app["heures_par_jour"] = (app["heures_actives"] / nb_j) if nb_j > 0 else 0.0
        appareils.append(app)

    appareils.sort(key=lambda a: (-a["kwh"], -a["p_max"]))
    total_kwh = sum(a["kwh"] for a in appareils)
    if not appareils:
        return None
    return {
        "appareils": appareils,
        "total_kwh": total_kwh,
        "fenetre_recente": fenetre_recente,
    }


def _a_des_habitudes(app):
    """Au moins 2 créneaux horaires distincts ou 2 jours distincts : une mesure isolée n'est pas une habitude."""
    return app["heures_actives"] >= 2 or len(app["jours_actifs"]) >= 2


def _regles_habitudes(client, maintenant, cap_w, existants, sensor_id=None):
    """Conseils personnalisés issus des habitudes réelles d'utilisation de chaque appareil."""
    data = _habitudes_appareils(client, maintenant, sensor_id=sensor_id)
    if not data:
        return []
    appareils = data["appareils"]
    total_kwh = data["total_kwh"]
    portee = "ces 30 derniers jours" if data["fenetre_recente"] else "sur vos dernières mesures enregistrées"
    out = []

    eligibles = [a for a in appareils if _a_des_habitudes(a)]
    if not eligibles:
        return []

    # H1. Pics de puissance inhabituels ou récurrents par appareil (si la règle critique 7 j ne l'a pas déjà signalé)
    for rang, app in enumerate(eligibles):
        nom, cat = app["nom"], app["categorie"]
        if ("pic", nom) in existants:
            continue
        if app["p_max"] >= 500 and (app["p_max"] > cap_w or (app["p_moy"] > 0 and app["p_max"] >= 2.5 * app["p_moy"])):
            if app["p_max"] > cap_w:
                out.append(_conseil(
                    "habitude_pic_appareil", 52 - min(rang, 2),
                    f"Pics jusqu'à {_f(app['p_max'], 0)} W sur « {nom} »",
                    f"En moyenne à {_f(app['p_moy'], 0)} W, « {nom} » est monté à {_f(app['p_max'], 0)} W {portee} "
                    f"(limite abonnement : {_f(cap_w, 0)} W). {_action_appareil(cat, 'pic')}",
                    lien="/historique/", habitude=True,
                    nom=nom, pic_w=round(app["p_max"]), moy_w=round(app["p_moy"]), capacite_w=cap_w))
            else:
                out.append(_conseil(
                    "habitude_pic_appareil", 44 - min(rang, 2),
                    f"Forts pics de puissance sur « {nom} » ({_f(app['p_max'], 0)} W)",
                    f"Habituellement autour de {_f(app['p_moy'], 0)} W, « {nom} » atteint jusqu'à "
                    f"{_f(app['p_max'], 0)} W {portee}. {_action_appareil(cat, 'pic')}",
                    lien="/historique/", habitude=True,
                    nom=nom, pic_w=round(app["p_max"]), moy_w=round(app["p_moy"])))

    # H2. Créneau horaire habituel de chaque appareil (matin, après-midi, soirée, nuit)
    for rang, app in enumerate(eligibles):
        nom, cat = app["nom"], app["categorie"]
        somme_c = sum(app["par_creneau"].values())
        if somme_c <= 0:
            continue
        meilleur = max(CRENEAUX, key=lambda item: app["par_creneau"].get(item[0], 0.0))
        code_c, heures_c, lib_c = meilleur
        part_c = app["par_creneau"].get(code_c, 0.0) / somme_c
        if part_c < 0.40:
            continue
        if code_c == "nuit" and ("nuit", nom) in existants:
            continue
        plage_court, plage_phrase = _plage_pic(app["par_heure"], heures_c)
        titres = {
            "nuit": f"« {nom} » surtout actif la nuit ({plage_court})",
            "soiree": f"« {nom} » très utilisé en soirée ({plage_court})",
            "apres_midi": f"« {nom} » surtout utilisé l'après-midi ({plage_court})",
            "matin": f"« {nom} » surtout utilisé le matin ({plage_court})",
        }
        ctx = "nuit" if code_c == "nuit" else ("soiree" if code_c == "soiree" else "jour")
        part_pct = round(part_c * 100)
        prio = 50 if rang == 0 else (47 if rang == 1 else 45)
        detail_portee = "" if data["fenetre_recente"] else f", {portee}"
        out.append(_conseil(
            "habitude_horaire", prio,
            titres[code_c],
            f"{part_pct} % de l'usage de « {nom} » ({_energie(app['kwh'])}, ~{_f(app['p_moy'], 0)} W en marche) "
            f"a lieu {lib_c}, surtout {plage_phrase}{detail_portee}. {_action_appareil(cat, ctx)}",
            lien="/historique/", habitude=True,
            nom=nom, creneau=code_c, part=part_pct, plage=plage_court,
            moy_w=round(app["p_moy"]), kwh=round(app["kwh"], 3)))

    # H3. Répartition entre vos appareils enregistrés (hors filtre mono-capteur)
    if sensor_id is None and len(appareils) >= 2 and total_kwh > 0:
        top, second = appareils[0], appareils[1]
        if ("dominant", top["nom"]) not in existants:
            part = round(top["kwh"] / total_kwh * 100)
            part2 = round(second["kwh"] / total_kwh * 100)
            if part >= 45:
                out.append(_conseil(
                    "habitude_repartition", 48,
                    f"« {top['nom']} » concentre {part} % de vos usages",
                    f"« {top['nom']} » représente {_energie(top['kwh'])} contre {_energie(second['kwh'])} pour "
                    f"« {second['nom']} » {portee} (~{_f(top['p_moy'], 0)} W en marche). "
                    f"{_action_appareil(top['categorie'], 'repartition')}",
                    lien="/historique/", habitude=True,
                    nom=top["nom"], part=part, kwh=round(top["kwh"], 3), total_kwh=round(total_kwh, 3)))
            else:
                out.append(_conseil(
                    "habitude_repartition", 46,
                    f"Usages partagés entre « {top['nom']} » et « {second['nom']} »",
                    f"« {top['nom']} » ({part} %, {_energie(top['kwh'])}) et « {second['nom']} » ({part2} %, "
                    f"{_energie(second['kwh'])}) portent l'essentiel de vos usages {portee}. "
                    f"{_action_appareil(top['categorie'], 'repartition')}",
                    lien="/historique/", habitude=True,
                    nom=top["nom"], part=part, kwh=round(top["kwh"], 3), total_kwh=round(total_kwh, 3)))

    # H4. Rythme semaine / week-end ou jour de la semaine le plus chargé par appareil
    for rang, app in enumerate(eligibles[:3]):
        nom, cat = app["nom"], app["categorie"]
        if len(app["jours_actifs"]) < 4:
            continue
        sem = [e for j, e in app["par_jour"].items() if j.weekday() < 5]
        we = [e for j, e in app["par_jour"].items() if j.weekday() >= 5]
        if sem and we:
            moy_sem = sum(sem) / len(sem)
            moy_we = sum(we) / len(we)
            if moy_sem > 0 and moy_we >= moy_sem * 1.25:
                pct = round((moy_we / moy_sem - 1) * 100)
                out.append(_conseil(
                    "habitude_jours", 43 - min(rang, 2),
                    f"« {nom} » consomme {pct} % de plus le week-end",
                    f"En moyenne {_energie(moy_we)}/jour le week-end contre {_energie(moy_sem)}/jour en semaine "
                    f"{portee}. {_action_appareil(cat, 'weekend')}",
                    lien="/historique/", habitude=True,
                    nom=nom, pct=pct, mode="weekend"))
                continue
            if moy_we > 0 and moy_sem >= moy_we * 1.25:
                pct = round((moy_sem / moy_we - 1) * 100)
                out.append(_conseil(
                    "habitude_jours", 43 - min(rang, 2),
                    f"« {nom} » surtout sollicité en semaine (+{pct} %)",
                    f"En moyenne {_energie(moy_sem)}/jour du lundi au vendredi contre {_energie(moy_we)}/jour le "
                    f"week-end {portee}. {_action_appareil(cat, 'semaine')}",
                    lien="/historique/", habitude=True,
                    nom=nom, pct=pct, mode="semaine"))
                continue
        par_dow = defaultdict(list)
        for j, e in app["par_jour"].items():
            par_dow[j.weekday()].append(e)
        if len(par_dow) >= 4:
            moy_dow = {d: sum(vs) / len(vs) for d, vs in par_dow.items()}
            d_max, val_max = max(moy_dow.items(), key=lambda x: x[1])
            autres = [v for d, v in moy_dow.items() if d != d_max]
            moy_autres = sum(autres) / len(autres) if autres else 0.0
            if moy_autres > 0 and val_max >= moy_autres * 1.40:
                jour_fr = JOURS_SEMAINE_FR[d_max]
                out.append(_conseil(
                    "habitude_jours", 42 - min(rang, 2),
                    f"Le {jour_fr} est le jour le plus chargé sur « {nom} »",
                    f"« {nom} » consomme en moyenne {_energie(val_max)} le {jour_fr} contre {_energie(moy_autres)} "
                    f"les autres jours {portee}. {_action_appareil(cat, 'semaine')}",
                    lien="/historique/", habitude=True,
                    nom=nom, jour=jour_fr))

    # H5. Durée quotidienne habituelle d'utilisation par appareil
    for rang, app in enumerate(eligibles[:3]):
        nom, cat = app["nom"], app["categorie"]
        if len(app["jours_actifs"]) >= 2 and app["heures_par_jour"] >= 3.0:
            h_moy = round(app["heures_par_jour"])
            if h_moy >= 22:
                titre = f"« {nom} » fonctionne presque en continu"
                texte = (
                    f"« {nom} » consomme près de {h_moy} h/jour (~{_f(app['p_moy'], 0)} W en marche, soit "
                    f"{_energie(app['kwh'])} {portee}). {_action_appareil(cat, 'duree')}"
                )
            else:
                titre = f"« {nom} » actif ~{h_moy} h par jour d'usage"
                texte = (
                    f"Les jours où vous l'allumez, « {nom} » consomme environ {h_moy} h (~{_f(app['p_moy'], 0)} W en "
                    f"marche, soit {_energie(app['kwh'])} {portee}). {_action_appareil(cat, 'duree')}"
                )
            out.append(_conseil(
                "habitude_duree", 41 - min(rang, 2), titre, texte,
                lien="/historique/", habitude=True,
                nom=nom, heures_jour=h_moy, moy_w=round(app["p_moy"])))

    # H6. Synthèse personnalisée de secours pour chaque appareil mesuré avec habitudes
    for rang, app in enumerate(eligibles[:4]):
        nom, cat = app["nom"], app["categorie"]
        _, plage_phrase = _plage_pic(app["par_heure"])
        moment = f" surtout {plage_phrase}" if plage_phrase else ""
        out.append(_conseil(
            "habitude_appareil", 35 - min(rang, 3),
            f"Maîtriser la consommation de « {nom} »",
            f"Vous utilisez « {nom} »{moment} (~{_f(app['p_moy'], 0)} W en marche, {_energie(app['kwh'])} {portee}). "
            f"{_action_appareil(cat, 'repartition')}",
            lien="/historique/", habitude=True,
            nom=nom, moy_w=round(app["p_moy"]), kwh=round(app["kwh"], 3)))

    return out


def regles(client, maintenant=None, sensor_id=None):
    """Tous les conseils applicables (urgences mesurées + habitudes par appareil), sans tri."""
    maintenant = maintenant or timezone.now()
    out = []
    recents, avant, nuit = _donnees(client, maintenant, sensor_id=sensor_id)
    total = sum(v['kwh'] for v in recents.values())
    total_avant = sum(avant.values())
    pics = _pics(client, maintenant, sensor_id=sensor_id)
    amperage = int(getattr(client, 'amperage', 10) or 10)
    cap_w = int(float(PUISSANCE_KW.get(amperage, Decimal('2.2'))) * 1000)

    # 1. Pic de puissance au-dessus de la capacité de l'abonnement : risque de disjonction
    if pics:
        nom, pic = max(pics.items(), key=lambda x: x[1])
        if pic > cap_w:
            out.append(_conseil(
                "pic", 100, f"Pic de {_f(pic, 0)} W sur « {nom} »",
                f"Votre abonnement de {amperage} A supporte environ {_f(cap_w, 0)} W. Évitez d'allumer cet appareil "
                "en même temps que d'autres gros consommateurs, sinon le disjoncteur risque de sauter.",
                nom=nom, pic_w=round(pic), capacite_w=cap_w))

    # 2. Prépayé : crédit bientôt épuisé (conseil global du foyer)
    if sensor_id is None:
        try:
            from apps.alerts.utils import credit_prepaye_info
            credit = credit_prepaye_info(client)
        except Exception:
            credit = None
        if credit and credit.get('fin_estimee') is not None:
            j = (credit['fin_estimee'] - timezone.localtime()).total_seconds() / 86400
            if j <= 5:
                quand = "aujourd'hui" if j < 1 else f"dans environ {int(round(j))} jours"
                out.append(_conseil(
                    "credit", 95, "Votre crédit va bientôt se terminer",
                    f"Au rythme de votre foyer, il sera épuisé {quand} (reste {_f(credit['restant_fcfa'], 0)} FCFA). "
                    "Pensez à acheter de l'énergie avant la coupure, puis mettez à jour votre crédit.",
                    lien="/previsions/",
                    restant_fcfa=round(float(credit['restant_fcfa'])), jours=round(j, 1)))

        # 3. Postpayé : la tranche suivante approche
        try:
            from apps.alerts.utils import etat_tranche
            t = etat_tranche(client)
        except Exception:
            t = None
        if t and t['seuil'] > 0:
            kwh, seuil = float(t['kwh']), float(t['seuil'])
            if kwh >= seuil * 0.8 or (t['jours_avant_seuil'] is not None and t['jours_avant_seuil'] <= 10):
                reste = max(0.0, seuil - kwh)
                texte = (f"Vous avez consommé {_f(kwh)} kWh sur les {_f(seuil, 0)} kWh de la tranche 1 de ce bimestre"
                         + (f", soit {_f(reste)} kWh de marge." if reste else ", la tranche 2 est atteinte."))
                if t['type_tarif'] == 'social' and reste:
                    texte += " Au tarif social, la tranche 2 coûte environ deux fois plus cher par kWh."
                out.append(_conseil("tranche", 90, "La tranche suivante approche", texte, lien="/previsions/",
                                    kwh=round(kwh, 1), seuil=round(seuil), reste_kwh=round(reste, 1)))

    # 4. Appareil allumé depuis longtemps (boîtier qui répond)
    cap_on_qs = Capteur.objects.filter(client=client, actif=True, etatCourant='ON')
    if sensor_id:
        cap_on_qs = cap_on_qs.filter(pk=sensor_id)
    for c in cap_on_qs:
        if (c.etatDepuis and c.derniereLecture
                and (maintenant - c.derniereLecture).total_seconds() <= 60
                and maintenant - c.etatDepuis >= timedelta(hours=ALLUME_LONGTEMPS_H)):
            h = int((maintenant - c.etatDepuis).total_seconds() // 3600)
            out.append(_conseil(
                "allume", 80, f"« {c.nom} » tourne depuis {h} h",
                "Cet appareil est allumé sans interruption. S'il n'a pas besoin de fonctionner en continu, "
                "éteignez-le pour réduire votre facture.", lien="/dashboard/", nom=c.nom, heures=h))
            break

    # 5. Hausse par rapport à la semaine d'avant
    if total >= KWH_MIN and total_avant >= KWH_MIN_AVANT and total > total_avant * (1 + HAUSSE_MIN):
        pct = round((total / total_avant - 1) * 100)
        plus = max(recents.items(), key=lambda x: x[1]['kwh'] - avant.get(x[0], 0.0))
        out.append(_conseil(
            "hausse", 70, f"Consommation en hausse de {pct} % cette semaine",
            f"{_f(total)} kWh sur les 7 derniers jours contre {_f(total_avant)} kWh la semaine d'avant. "
            f"C'est « {plus[0]} » qui a le plus augmenté.", pct=pct, kwh=round(total, 1),
            kwh_avant=round(total_avant, 1), nom=plus[0]))

    # 6. Consommation de nuit élevée
    total_nuit = sum(nuit.values())
    if total >= KWH_MIN and total_nuit / total >= PART_NUIT_MIN:
        nom = max(nuit.items(), key=lambda x: x[1])[0]
        part = round(total_nuit / total * 100)
        out.append(_conseil(
            "nuit", 60, f"{part} % de votre consommation a lieu la nuit",
            f"Entre 22 h et 6 h, vous avez consommé {_f(total_nuit)} kWh sur les 7 derniers jours, surtout avec "
            f"« {nom} ». Vérifiez ce qui reste allumé quand vous dormez.", part=part, kwh=round(total_nuit, 1), nom=nom))

    # 7. Forte chaleur annoncée et climatiseur
    try:
        from .meteo import ville_du_client
        from .models import MeteoJour
        ville = ville_du_client(client)
        demain = timezone.localdate() + timedelta(days=1)
        m = MeteoJour.objects.filter(ville=ville, date__in=[timezone.localdate(), demain]).order_by('-t_max').first()
        chaud = float(m.t_max) if m and m.t_max is not None else None
    except Exception:
        chaud = None
    clims = [n for n in recents if any(mot in n.lower() for mot in MOTS_CLIM)]
    if chaud is not None and chaud >= CHALEUR_C and clims:
        out.append(_conseil(
            "chaleur", 55, f"{_f(chaud, 0)} °C annoncés",
            f"Il fera chaud : « {clims[0]} » va beaucoup tourner. Réglez-le vers 26 °C, fermez portes et fenêtres, "
            "et gardez-le éteint dans les pièces vides.", lien="/previsions/", t_max=round(chaud), nom=clims[0]))

    # 8. Un appareil pèse l'essentiel de la consommation (7 derniers jours, ≥ 2 kWh)
    if sensor_id is None and total >= KWH_MIN and len(recents) >= 2:
        nom, v = max(recents.items(), key=lambda x: x[1]['kwh'])
        part = round(v['kwh'] / total * 100)
        if part >= 50:
            out.append(_conseil(
                "dominant", 40, f"« {nom} » représente {part} % de votre consommation",
                f"{_f(v['kwh'])} kWh sur {_f(total)} kWh ces 7 derniers jours. Agir sur cet appareil donne le plus "
                "d'économies : vérifiez ses réglages et ses heures d'usage.", nom=nom, part=part, kwh=round(v['kwh'], 1)))

    # 9. Analyse des habitudes réelles par appareil
    existants = {(c["kind"], c["chiffres"].get("nom")) for c in out}
    out.extend(_regles_habitudes(client, maintenant, cap_w, existants, sensor_id=sensor_id))
    return out


def _selectionner_conseils(candidats, n, sensor_id=None):
    """Sélectionne les n meilleurs conseils en diversifiant les appareils et les angles d'analyse."""
    tries = sorted(candidats, key=lambda c: -c['priorite'])
    choisis = []
    noms_vus = set()
    kinds_vus = set()
    utilises = set()

    def _ajouter(idx, c):
        choisis.append(c)
        utilises.add(idx)
        nom = c.get("chiffres", {}).get("nom")
        if nom:
            noms_vus.add(nom)
        kinds_vus.add(c["kind"])

    # Passe 1 : urgences (≥ 80) d'abord, puis diversification par appareil ET par type de conseil
    for idx, c in enumerate(tries):
        if len(choisis) >= n:
            break
        if c["priorite"] >= 80:
            _ajouter(idx, c)
            continue
        nom = c.get("chiffres", {}).get("nom")
        meme_appareil = (sensor_id is None) and bool(nom) and (nom in noms_vus)
        if not meme_appareil and c["kind"] not in kinds_vus:
            _ajouter(idx, c)

    # Passe 2 : un autre appareil même si le type de conseil est déjà vu (ex. 2e appareil sur ses horaires)
    if len(choisis) < n and sensor_id is None:
        for idx, c in enumerate(tries):
            if len(choisis) >= n:
                break
            if idx in utilises:
                continue
            nom = c.get("chiffres", {}).get("nom")
            if nom and nom not in noms_vus:
                _ajouter(idx, c)

    # Passe 3 : autre angle d'analyse (même appareil possible)
    if len(choisis) < n:
        for idx, c in enumerate(tries):
            if len(choisis) >= n:
                break
            if idx in utilises:
                continue
            if c["kind"] not in kinds_vus:
                _ajouter(idx, c)

    # Passe 4 : compléter avec les conseils mesurés/habitudes restants
    if len(choisis) < n:
        for idx, c in enumerate(tries):
            if len(choisis) >= n:
                break
            if idx not in utilises:
                _ajouter(idx, c)

    return choisis


def conseils_du_client(client, maintenant=None, n=2, sensor_id=None):
    """Les n meilleurs conseils (priorité décroissante, diversifiés par appareil). Complétés, seulement si aucune
    habitude/mesure ne suffit, par des conseils généraux du jour clairement marqués `mesure: False`."""
    maintenant = maintenant or timezone.now()
    liste = _selectionner_conseils(regles(client, maintenant, sensor_id=sensor_id), n, sensor_id=sensor_id)
    # Complète avec des conseils généraux DISTINCTS (liste fixe, tournant avec le jour de l'année)
    i = timezone.localtime(maintenant).timetuple().tm_yday
    while len(liste) < n:
        titre, texte = CONSEILS_GENERAUX[i % len(CONSEILS_GENERAUX)]
        i += 1
        liste.append({
            "kind": "general", "priorite": 0, "mesure": False, "habitude": False,
            "titre": titre, "texte": texte, "lien": "/ia/", "chiffres": {},
        })
    qs_rec = MesureEnergie.objects.filter(
        capteur__client=client, timestamp__gte=maintenant - timedelta(days=2 * FENETRE_J))
    if sensor_id:
        qs_rec = qs_rec.filter(capteur_id=sensor_id)
    a_des_mesures = qs_rec.exists()
    return {"conseils": liste, "mesures_recentes": a_des_mesures}
