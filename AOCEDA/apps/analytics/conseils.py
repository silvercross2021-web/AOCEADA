"""Conseils du tableau de bord (19/10/2026) : calculés sur les VRAIES mesures du client, jamais écrits en dur.

Chaque règle regarde une donnée réelle (mesures des 14 derniers jours, crédit, tranche, météo annoncée) et renvoie un
conseil avec ses chiffres, ou rien. Les conseils sont classés par priorité ; les conseils généraux (liste fixe, marqués
« general ») ne servent qu'en dernier recours, quand aucune règle ne s'applique. Une donnée absente ne produit jamais
un chiffre inventé : la règle se tait.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncHour
from django.utils import timezone

from apps.sensors.models import Capteur, MesureEnergie

from .tarifs_cie import PUISSANCE_KW

FENETRE_J = 7
NUIT = set(range(22, 24)) | set(range(0, 6))          # 22 h → 6 h
PART_NUIT_MIN = 0.25                                  # au moins 25 % de la consommation de nuit
KWH_MIN = 2.0                                         # en dessous, trop peu de mesure pour conseiller (une part de 61 % sur 1,6 kWh = du bruit)
KWH_MIN_AVANT = 1.0                                   # semaine de référence de la comparaison
HAUSSE_MIN = 0.20
ALLUME_LONGTEMPS_H = 8
CHALEUR_C = 33.0
MOTS_CLIM = ("climatis", "clim", "split")

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


def _conseil(kind, priorite, titre, texte, lien="/historique/", **chiffres):
    return {"kind": kind, "priorite": priorite, "mesure": True, "titre": titre, "texte": texte, "lien": lien,
            "chiffres": chiffres}


def _donnees(client, maintenant):
    """kWh par (capteur, heure locale) sur 14 jours, pic de puissance par capteur sur 7 jours."""
    debut = maintenant - timedelta(days=2 * FENETRE_J)
    lignes = (MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=debut)
              .annotate(h=TruncHour('timestamp'))
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


def _pics(client, maintenant):
    from django.db.models import Max
    rows = (MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=maintenant - timedelta(days=FENETRE_J))
            .values('capteur__nom').annotate(p=Max('puissance')))
    return {r['capteur__nom']: float(r['p'] or 0) for r in rows}


def regles(client, maintenant=None):
    """Tous les conseils applicables, sans tri."""
    maintenant = maintenant or timezone.now()
    out = []
    recents, avant, nuit = _donnees(client, maintenant)
    total = sum(v['kwh'] for v in recents.values())
    total_avant = sum(avant.values())
    pics = _pics(client, maintenant)
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

    # 2. Prépayé : crédit bientôt épuisé
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
                "Pensez à acheter de l'énergie avant la coupure, puis mettez à jour votre crédit.", lien="/previsions/",
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
    for c in Capteur.objects.filter(client=client, actif=True, etatCourant='ON'):
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

    # 8. Un appareil pèse l'essentiel de la consommation
    if total >= KWH_MIN and len(recents) >= 2:
        nom, v = max(recents.items(), key=lambda x: x[1]['kwh'])
        part = round(v['kwh'] / total * 100)
        if part >= 50:
            out.append(_conseil(
                "dominant", 40, f"« {nom} » représente {part} % de votre consommation",
                f"{_f(v['kwh'])} kWh sur {_f(total)} kWh ces 7 derniers jours. Agir sur cet appareil donne le plus "
                "d'économies : vérifiez ses réglages et ses heures d'usage.", nom=nom, part=part, kwh=round(v['kwh'], 1)))
    return out


def conseils_du_client(client, maintenant=None, n=2):
    """Les n meilleurs conseils (priorité décroissante). Complétés, si besoin, par des conseils généraux du jour (liste
    fixe), clairement marqués `mesure: False`. `vide` : aucune mesure du tout, la page le dit honnêtement."""
    maintenant = maintenant or timezone.now()
    liste = sorted(regles(client, maintenant), key=lambda c: -c['priorite'])[:n]
    # Complète avec des conseils généraux DISTINCTS (liste fixe, tournant avec le jour de l'année)
    i = timezone.localtime(maintenant).timetuple().tm_yday
    while len(liste) < n:
        titre, texte = CONSEILS_GENERAUX[i % len(CONSEILS_GENERAUX)]
        i += 1
        liste.append({"kind": "general", "priorite": 0, "mesure": False, "titre": titre, "texte": texte,
                      "lien": "/ia/", "chiffres": {}})
    a_des_mesures = MesureEnergie.objects.filter(
        capteur__client=client, timestamp__gte=maintenant - timedelta(days=2 * FENETRE_J)).exists()
    return {"conseils": liste, "mesures_recentes": a_des_mesures}
