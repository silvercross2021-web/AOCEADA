"""Outils « function calling » de l'assistant IA.

Chaque outil est une LECTURE bornée au client authentifié qui réutilise les
fonctions analytics déjà éprouvées ailleurs (mêmes chiffres que les pages
Dashboard/Historique/Prévisions — rien n'est recalculé différemment). Le LLM
choisit lui-même le ou les outils selon la question, au lieu de recevoir
d'office un paquet figé limité à « aujourd'hui / 7 jours » : n'importe quelle
période historique devient interrogeable, sans jamais inventer un chiffre.

Contrat d'un outil : fonction(client, arguments: dict) -> dict JSON-sérialisable.
En cas de paramètre invalide, l'outil renvoie {"erreur": "..."} (jamais une
exception) pour que le LLM puisse corriger ses paramètres et réessayer.

Seule exception à la lecture : preparer_coupure (13/10/2026). Il n'écrit RIEN non
plus : il prépare une demande de coupure que la personne doit valider d'un clic.
Un outil peut renvoyer « carte_page » : une carte pour la page seulement, retirée
avant que le résultat soit renvoyé au LLM (fournisseurs.flux_deepseek, live_agent).
"""
import logging
import re
import unicodedata
from datetime import datetime as _datetime, timedelta

from django.db.models import Avg, Max, Sum  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]

from .chatbot.baoule_demandes import nom_simple

logger = logging.getLogger(__name__)

# Bornes de sécurité : fenêtre d'analyse d'1 an max, détail par jour seulement
# sur les fenêtres courtes (au-delà, le détail exploserait le budget tokens).
MAX_JOURS_FENETRE = 366
MAX_JOURS_DETAIL = 31

JOURS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre")

# Périodes RELATIVES calculées ici, jamais par le LLM. Constaté en test réel (agent
# Live, 01/10/2026) : pour « la semaine dernière », le modèle choisissait tantôt la
# semaine calendaire (lun. 21 → dim. 27 sept. : 127,63 kWh), tantôt les 7 jours
# avant aujourd'hui (24 → 30 sept. : 112,48 kWh) — deux réponses différentes à la
# même question. Conventions (françaises, et celles de la page Historique) :
#   - une semaine va du LUNDI au DIMANCHE ;
#   - « les 7 / 30 derniers jours » = J-6 / J-29 → aujourd'hui inclus (comme les
#     boutons « 7 jours » / « 30 jours » de la page Historique) ;
#   - « ce week-end » : samedi-dimanche en cours le week-end, sinon le dernier passé.
PERIODES = {
    "aujourd_hui": "aujourd'hui",
    "hier": "hier",
    "avant_hier": "avant-hier",
    "cette_semaine": "cette semaine",
    "semaine_derniere": "la semaine dernière",
    "7_derniers_jours": "les 7 derniers jours",
    "ce_week_end": "ce week-end",
    "week_end_dernier": "le week-end dernier",
    "ce_mois": "ce mois-ci",
    "mois_dernier": "le mois dernier",
    "30_derniers_jours": "les 30 derniers jours",
}


def _mois_precedent(d, jour=None):
    """Même jour (ou `jour`) le mois d'avant, ramené au dernier jour du mois si besoin
    (31 mars -> 28/29 février)."""
    fin_mois_prec = d.replace(day=1) - timedelta(days=1)
    return fin_mois_prec.replace(day=min(jour or d.day, fin_mois_prec.day))


def resoudre_periode(code, today):
    """(premier jour, dernier jour, période précédente comparable) d'une période
    relative, en dates LOCALES incluses. La période précédente suit l'unité de la
    période : la semaine d'avant pour une semaine, le mois d'avant pour un mois, le
    week-end d'avant pour un week-end ; pour une fenêtre glissante, la même durée
    juste avant (même règle que la page Historique)."""
    lundi = today - timedelta(days=today.weekday())
    un_jour, une_semaine = timedelta(days=1), timedelta(days=7)
    if code in ("aujourd_hui", "hier", "avant_hier"):
        d = today - timedelta(days=("aujourd_hui", "hier", "avant_hier").index(code))
        return d, d, (d - un_jour, d - un_jour)
    if code == "cette_semaine":
        return lundi, today, (lundi - une_semaine, today - une_semaine)
    if code == "semaine_derniere":
        f, t = lundi - une_semaine, lundi - un_jour
        return f, t, (f - une_semaine, t - une_semaine)
    if code in ("ce_week_end", "week_end_dernier"):
        en_cours = today.weekday() >= 5                      # samedi ou dimanche
        if code == "ce_week_end" and en_cours:
            samedi = lundi + timedelta(days=5)
            return samedi, today, (samedi - une_semaine, today - une_semaine)
        # le dernier week-end TERMINÉ (en plein week-end, « le week-end dernier » est celui d'avant)
        f, t = lundi - timedelta(days=2), lundi - un_jour
        return f, t, (f - une_semaine, t - une_semaine)
    if code == "ce_mois":
        f = today.replace(day=1)
        return f, today, (_mois_precedent(f, 1), _mois_precedent(today))
    if code == "mois_dernier":
        t = today.replace(day=1) - un_jour
        f = t.replace(day=1)
        tp = f - un_jour
        return f, t, (tp.replace(day=1), tp)
    if code in ("7_derniers_jours", "30_derniers_jours"):
        n = 7 if code == "7_derniers_jours" else 30
        f = today - timedelta(days=n - 1)
        return f, today, (f - timedelta(days=n), f - un_jour)
    raise ValueError(f"Paramètre periode inconnu : {code!r}. Valeurs possibles : {', '.join(PERIODES)}.")


def _date_txt(d, annee=True, mois=True):
    jour = f"{d.day}{'er' if d.day == 1 else ''}"
    return " ".join([JOURS_FR[d.weekday()], jour] + ([MOIS_FR[d.month - 1]] if mois else [])
                    + ([str(d.year)] if annee else []))


def libelle_dates(f, t):
    """« le jeudi 1er octobre 2026 », « du lundi 21 au dimanche 27 septembre 2026 »,
    « du lundi 28 septembre au jeudi 1er octobre 2026 » : la période exacte, à citer
    telle quelle (l'assistant ne recalcule rien)."""
    if f == t:
        return f"le {_date_txt(f)}"
    meme_annee, meme_mois = f.year == t.year, (f.year, f.month) == (t.year, t.month)
    return f"du {_date_txt(f, annee=not meme_annee, mois=not meme_mois)} au {_date_txt(t)}"


def _fenetre(args, today):
    """Fenêtre demandée : `periode` (relative, calculée ici) OU date_debut/date_fin
    (dates précises). -> (f, t, période précédente ou None, code ou None)."""
    code = args.get('periode')
    if code:
        f, t, prec = resoudre_periode(str(code), today)
        return f, t, prec, str(code)
    if not args.get('date_debut') and not args.get('date_fin'):
        raise ValueError("Indique `periode` (ex. semaine_derniere, hier, ce_mois) pour une période "
                         "relative, ou date_debut et date_fin (AAAA-MM-JJ) pour des dates précises.")
    deb, fin = args.get('date_debut'), args.get('date_fin')
    f = _parse_date_locale(deb, 'date_debut') if deb else None
    t = _parse_date_locale(fin, 'date_fin') if fin else None
    return f or t, t or f, None, None                      # une seule date : ce jour-là


def _description_periode(code, f, t, today, demande_fin=None):
    """Bloc « periode » des résultats : ce qui a VRAIMENT été lu, en toutes lettres."""
    texte = libelle_dates(f, t)
    if code:
        texte = f"{PERIODES[code]}, {texte}"
    desc = {"code": code, "libelle": texte, "inclut_aujourd_hui": t == today}
    if t == today:
        desc["note"] = "La journée d'aujourd'hui est en cours : chiffres jusqu'à maintenant."
    if demande_fin and demande_fin > today:
        desc["note_dates"] = "La date de fin demandée était dans le futur : ramenée à aujourd'hui."
    return desc


def _parse_date_locale(valeur, nom_champ):
    try:
        return _datetime.strptime(str(valeur), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise ValueError(f"Paramètre {nom_champ} invalide : attendu AAAA-MM-JJ, reçu {valeur!r}.")


def _bornes_fenetre(f, t):
    """Bornes LOCALES inclusives (00:00:00 → 23:59:59) d'une fenêtre en jours
    calendaires, clampée à aujourd'hui et à MAX_JOURS_FENETRE — même convention
    que RepartitionCapteursView (bornes incluses, jamais de futur)."""
    if f > t:
        f, t = t, f
    today = timezone.localdate()
    if t > today:
        t = today
    if f > t:
        f = t
    if (t - f).days > MAX_JOURS_FENETRE:
        f = t - timedelta(days=MAX_JOURS_FENETRE)
    start = timezone.make_aware(_datetime.combine(f, _datetime.min.time()))
    end = timezone.make_aware(_datetime.combine(t, _datetime.max.time()))
    return start, end, f, t


def _bornes_jours(f, t):
    return (timezone.make_aware(_datetime.combine(f, _datetime.min.time())),
            timezone.make_aware(_datetime.combine(t, _datetime.max.time())))


# Période SANS AUCUNE MESURE (19/10/2026, vu en vrai) : « la semaine dernière » (du 5 au 11 octobre) n'avait aucune mesure,
# les mesures étaient du 12 et du 14 ; l'outil répondait seulement « 0 » et l'IA concluait « pas de consommation ». Il dit
# maintenant que RIEN n'a été mesuré (capteurs éteints ou hors ligne) et où se trouvent les mesures les plus proches.
SANS_MESURE = ("AUCUNE mesure n'a été reçue sur cette période (capteurs hors ligne ou pas encore installés) : ce n'est PAS "
               "une consommation nulle, ne dis jamais « vous n'avez rien consommé ». Dis-le en une phrase, cite la date de la "
               "dernière mesure, puis DONNE DIRECTEMENT les chiffres de la période la plus proche qui a des mesures (appelle "
               "l'outil avec cette période, par exemple cette_semaine ou 30_derniers_jours) en la nommant précisément.")


def _derniere_mesure(client):
    from apps.sensors.models import MesureEnergie
    d = MesureEnergie.objects.filter(capteur__client=client).aggregate(Max("timestamp"))["timestamp__max"]
    return timezone.localtime(d) if d else None


def _mesures_ailleurs(client, start, end):
    """Où sont les mesures du client quand la période [start, end] n'en a aucune."""
    from django.db.models.functions import TruncDate
    from apps.sensors.models import MesureEnergie
    tz = timezone.get_current_timezone()
    qs = MesureEnergie.objects.filter(capteur__client=client)
    jours = sorted({j for j in qs.filter(timestamp__lt=start).annotate(j=TruncDate("timestamp", tzinfo=tz))
                    .values_list("j", flat=True).distinct().order_by("-j")[:20]}, reverse=True)[:3]
    jours_apres = sorted({j for j in qs.filter(timestamp__gt=end).annotate(j=TruncDate("timestamp", tzinfo=tz))
                          .values_list("j", flat=True).distinct().order_by("j")[:20]})[:3]
    derniere = _derniere_mesure(client)
    return {
        "aucune_mesure_sur_la_periode": True,
        "derniere_mesure": derniere.isoformat(timespec="minutes") if derniere else None,
        "derniers_jours_mesures_avant": [_date_txt(j) for j in sorted(jours)],
        "premiers_jours_mesures_apres": [_date_txt(j) for j in jours_apres],
        "a_savoir": SANS_MESURE if derniere else "Ce compte n'a encore AUCUNE mesure : les capteurs n'ont jamais rien envoyé.",
    }


def _outil_conso_periode(client, args):
    """kWh réels sur une période quelconque + détail par jour + comparaison avec
    la période précédente comparable (None si aucune mesure avant — jamais de
    faux « -100 % », même règle que HistoriqueJournalierView)."""
    from apps.analytics.views import _aggregate_jours, _capteurs_du_client, _kwh_consommes
    from apps.analytics.tarifs_cie import prix_kwh_tout_compris
    from apps.sensors.models import MesureEnergie

    today = timezone.localdate()
    f0, t0, prec, code = _fenetre(args, today)
    start, end, f, t = _bornes_fenetre(f0, t0)
    nb_jours = (t - f).days + 1
    kwh = float(_kwh_consommes(client, start, end))
    prix = float(prix_kwh_tout_compris(client))
    res = {
        "periode": _description_periode(code, f, t, today, demande_fin=max(f0, t0)),
        "date_debut": f.isoformat(),
        "date_fin": t.isoformat(),
        "nb_jours": nb_jours,
        "kwh_total": round(kwh, 2),
        "cout_estime_fcfa": int(round(kwh * prix)),
        "note": "cout_estime_fcfa = kWh × prix marginal TTC (hors prime fixe) : une "
                "estimation, pas une facture CIE — pour le montant exact d'une période de "
                "facturation, utiliser historique_mensuel.",
    }
    if nb_jours <= MAX_JOURS_DETAIL:
        # même calcul que la page Historique (19/10/2026) : jours « mesure » / « eteint » (vrai 0), sans les jours
        # sans aucune trace (boîtier hors ligne), que l'assistant ne doit jamais présenter comme 0 kWh
        res["jours"], _manquants = _aggregate_jours(_capteurs_du_client(client), f, t)
    derniere = _derniere_mesure(client)
    res["derniere_mesure"] = derniere.isoformat(timespec="minutes") if derniere else None
    if not MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=start, timestamp__lte=end).exists():
        res.update(_mesures_ailleurs(client, start, end))

    # Période précédente : celle de la période relative (semaine d'avant, mois d'avant…),
    # sinon la même durée juste avant (dates précises, comme la page Historique).
    if prec:
        prev_debut, prev_fin = prec
    else:
        prev_fin = f - timedelta(days=1)
        prev_debut = prev_fin - timedelta(days=nb_jours - 1)
    p_start, p_end = _bornes_jours(prev_debut, prev_fin)
    # période calendaire EN COURS (aujourd'hui, cette semaine, ce mois, ce week-end) : la précédente
    # est comparée jusqu'à la MÊME heure (sinon une journée entamée face à une journée entière) ;
    # fenêtres glissantes et dates précises : jours entiers, comme la page Historique
    meme_heure = code in ("aujourd_hui", "cette_semaine", "ce_mois", "ce_week_end") and t == today
    if meme_heure:
        p_end = min(p_end, timezone.make_aware(_datetime.combine(prev_fin, timezone.localtime().time())))
    if MesureEnergie.objects.filter(capteur__client=client,
                                    timestamp__gte=p_start, timestamp__lte=p_end).exists():
        res["periode_precedente"] = {
            "libelle": libelle_dates(prev_debut, prev_fin) + (", jusqu'à la même heure" if meme_heure else ""),
            "date_debut": prev_debut.isoformat(),
            "date_fin": prev_fin.isoformat(),
            "kwh_total": round(float(_kwh_consommes(client, p_start, p_end)), 2),
        }
    else:
        res["periode_precedente"] = None
    return res


def _outil_repartition_appareils(client, args):
    """Part de chaque appareil (kWh, %, pic W) sur une période quelconque — même
    agrégation que RepartitionCapteursView, mais avec des dates libres. Liste vide
    honnête si rien n'a été mesuré sur la période."""
    from apps.sensors.models import MesureEnergie

    today = timezone.localdate()
    f0, t0, _, code = _fenetre(args, today)
    start, end, f, t = _bornes_fenetre(f0, t0)
    rows = (MesureEnergie.objects
            .filter(capteur__client=client, timestamp__gte=start, timestamp__lte=end)
            .values('capteur__nom')
            .annotate(kwh=Sum('energie'), peak=Max('puissance'))
            .order_by('-kwh'))
    appareils = [{"nom": r['capteur__nom'], "kwh": round(float(r['kwh'] or 0), 3),
                  "pic_w": round(float(r['peak'] or 0))} for r in rows]
    total = sum(a["kwh"] for a in appareils)
    for a in appareils:
        a["pct"] = round(a["kwh"] / total * 100) if total > 0 else 0
    res = {
        "periode": _description_periode(code, f, t, today, demande_fin=max(f0, t0)),
        "date_debut": f.isoformat(), "date_fin": t.isoformat(),
        "kwh_total": round(total, 2), "appareils": appareils,
    }
    if not appareils:
        res.update(_mesures_ailleurs(client, start, end))
    return res


def _outil_historique_mensuel(client, args):
    """kWh + montant FCFA réels des 6 derniers mois (moteur tarifaire CIE) —
    exactement les chiffres de la carte « Historique mensuel »."""
    from apps.analytics.views import historique_fcfa_mensuel
    return {
        "mois": historique_fcfa_mensuel(client),
        "note": "Une ligne par période de facturation : BIMESTRE pour un compteur postpayé "
                "(la facture CIE couvre deux mois), mois pour un prépayé (periode_type). total_fcfa "
                "est recalculé selon l'arrêté n° 1355 depuis la consommation réelle ; la période "
                "marquée en_cours=true est partielle (à ce jour).",
    }


def _outil_heures_de_pointe(client, args):
    """Profil horaire (0-23h locales) : puissance moyenne et kWh par heure sur les
    N derniers jours, avec les 3 heures les plus consommatrices."""
    from django.db.models.functions import ExtractHour
    from apps.sensors.models import MesureEnergie

    try:
        nb_jours = int(args.get('nb_jours') or 7)
    except (TypeError, ValueError):
        nb_jours = 7
    nb_jours = max(1, min(nb_jours, 30))
    since = timezone.now() - timedelta(days=nb_jours)
    tz = timezone.get_current_timezone()
    rows = (MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=since)
            .annotate(hr=ExtractHour('timestamp', tzinfo=tz))
            .values('hr')
            .annotate(avg_w=Avg('puissance'), kwh=Sum('energie'))
            .order_by('hr'))
    heures = [{"heure": r['hr'], "puissance_moyenne_w": round(float(r['avg_w'] or 0)),
               "kwh": round(float(r['kwh'] or 0), 3)}
              for r in rows if r['hr'] is not None]
    top = sorted(heures, key=lambda h: h['kwh'], reverse=True)[:3]
    depuis = timezone.localtime(since)
    res = {"nb_jours": nb_jours,
           "periode": {"libelle": f"les {nb_jours} derniers jours (depuis le {_date_txt(depuis)}, "
                                  f"{depuis:%H} h {depuis:%M})"},
           "heures": heures, "heures_de_pointe": top}
    if not heures:
        res.update(_mesures_ailleurs(client, since, timezone.now()))
    return res


def _outil_prevision_fin_mois(client, args):
    """Fourchette de facture de fin de période (fin du bimestre en postpayé, du mois en
    prépayé) — même moteur que la page Prévisions."""
    from apps.analytics.views import _prevision_fin_de_mois
    return _prevision_fin_de_mois(client)


def _outil_credit_et_recharges(client, args):
    """Crédit prépayé restant estimé + dernières recharges déclarées. Réponse
    honnête (pas de solde fabriqué) pour les compteurs postpayés."""
    from apps.alerts.utils import credit_prepaye_info
    from apps.analytics.views import _credit_payload
    from apps.analytics.models import RechargeCredit

    if getattr(client, 'typeCompteur', 'postpaye') != 'prepaye':
        return {"type_compteur": "postpaye",
                "note": "Compteur postpayé : pas de crédit prépayé, le client règle une facture tous les deux mois (bimestre)."}
    recharges = [{"montant_fcfa": float(r.montant_FCFA),
                  "date": timezone.localtime(r.dateRecharge).isoformat()}
                 for r in RechargeCredit.objects.filter(client=client)[:5]]
    return {
        "type_compteur": "prepaye",
        "credit": _credit_payload(credit_prepaye_info(client)),
        "dernieres_recharges": recharges,
    }


def _outil_alertes(client, args):
    """Alertes du client (type, sévérité, message, date, lue) + compte des non lues."""

    seulement_non_lues = bool(args.get('seulement_non_lues', False))
    try:
        limite = int(args.get('limite') or 10)
    except (TypeError, ValueError):
        limite = 10
    limite = max(1, min(limite, 20))
    from apps.alerts.utils import alertes_du_client
    qs = alertes_du_client(client).order_by('-createdAt')   # même règle que le tableau de bord et la cloche
    if seulement_non_lues:
        qs = qs.filter(lue=False)
    alertes = [{"type": a.get_type_display(), "severite": a.sévérité,
                "message": (a.message or '')[:200],
                "date": timezone.localtime(a.createdAt).isoformat(), "lue": a.lue}
               for a in qs[:limite]]
    return {
        "nb_non_lues": alertes_du_client(client).filter(lue=False).count(),
        "alertes": alertes,
    }


def _outil_interventions(client, args):
    """Les 5 dernières interventions techniques du client (type, statut, dates, résultat)."""
    from apps.sensors.models import Intervention

    out = []
    for it in Intervention.objects.filter(client=client).order_by('-dateIntervention')[:5]:
        out.append({
            "type": it.get_typeIntervention_display(),
            "statut": it.get_statut_display(),
            "description": (it.description or '')[:200],
            "date": timezone.localtime(it.dateIntervention).isoformat() if it.dateIntervention else None,
            "date_programmee": timezone.localtime(it.dateProgrammee).isoformat() if it.dateProgrammee else None,
            "resultat": (it.résultat or '')[:200] or None,
        })
    return {"interventions": out}


def _outil_etat_capteurs(client, args):
    """État instantané de chaque capteur : ON/OFF, seuil, fraîcheur de la dernière
    lecture (etat=OFF ≠ hors ligne — même distinction que le dashboard)."""
    from apps.sensors.models import Capteur

    now = timezone.now()
    capteurs = []
    for cap in Capteur.objects.filter(client=client):
        secondes = int((now - cap.derniereLecture).total_seconds()) if cap.derniereLecture else None
        capteurs.append({
            "nom": cap.nom,
            "actif": cap.actif,
            "etat": cap.etatCourant,  # ON = consomme, OFF = branché mais éteint
            "seuil_puissance_w": float(cap.valeurMax),
            "derniere_lecture": timezone.localtime(cap.derniereLecture).isoformat() if cap.derniereLecture else None,
            "secondes_depuis_derniere_lecture": secondes,
            # Relais du boîtier : True = courant coupé à distance, False = courant présent,
            # None = pas de relais connu (ne peut pas être coupé à distance)
            "coupe_a_distance": cap.coupureEffective,
            "ordre_en_attente": cap.coupureEffective is not None and cap.coupureDemandee != cap.coupureEffective,
        })
    return {
        "nb_capteurs": len(capteurs), "capteurs": capteurs,
        "note": "etat=OFF signifie éteint mais joignable ; « hors ligne » = derniere_lecture "
                "ancienne (plus de quelques minutes) ou absente. coupe_a_distance=true : courant coupé "
                "par le relais depuis AOCEDA ; ordre_en_attente : le boîtier ne l'a pas encore appliqué.",
    }


# ── Coupure à distance demandée à l'assistant (13/10/2026) ───────────────────
# L'assistant ne coupe RIEN lui-même : cet outil prépare seulement la demande
# (quel appareil, quelle action) et la renvoie en carte « Couper le courant de la
# prise ? [Oui] [Non] ». Seul le clic « Oui » de la personne, sur la page, envoie
# l'ordre, par la même demande que le bouton du tableau de bord. Même si l'IA
# comprend mal ou se trompe, elle ne peut donc rien couper sans ce clic.
DUREE_CONFIRMATION_S = 120   # au-delà, la carte ne peut plus être validée
_MOTS_VIDES = {"le", "la", "les", "l", "de", "du", "des", "d", "un", "une", "mon", "ma", "mes",
               "the", "my", "a", "an", "of", "courant", "power"}


# Mots courants qui désignent le même appareil (18/10/2026) : « éteins la lumière » doit trouver « Capteur 1 - Lampe »,
# quelle que soit la langue du mot recopié par le cerveau IA (« light », « socket »...)
_SYNONYMES = {"lumiere": "lampe", "lumieres": "lampe", "lampes": "lampe", "ampoule": "lampe", "eclairage": "lampe",
              "light": "lampe", "lights": "lampe", "lamp": "lampe", "bulb": "lampe",
              "prises": "prise", "socket": "prise", "plug": "prise", "outlet": "prise",
              "clim": "climatiseur", "climatisation": "climatiseur", "frigo": "refrigerateur", "fridge": "refrigerateur",
              "tele": "television", "tv": "television", "ventilo": "ventilateur", "fan": "ventilateur"}


def _mots(texte):
    """Mots d'un nom, sans accents ni majuscules ni ponctuation (« Capteur 2 - Prise » -> capteur, 2, prise),
    synonymes ramenés au même mot (« lumière » -> lampe)."""
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    return [_SYNONYMES.get(m, m) for m in re.findall(r"[a-z0-9]+", t)]


def _trouver_appareil(client, demande):
    """(capteur, None) pour l'appareil du client désigné par `demande` (son nom, ou des mots de son nom),
    sinon (None, résultat d'erreur avec la liste de ses appareils, pour que l'IA demande lequel)."""
    from apps.sensors.models import Capteur

    capteurs = list(Capteur.objects.filter(client=client))
    noms = [c.nom for c in capteurs]
    voulus = [m for m in _mots(demande) if m not in _MOTS_VIDES]
    if not voulus:
        return None, {"erreur": "Précise l'appareil (son nom).", "appareils": noms}
    exacts = [c for c in capteurs if [m for m in _mots(c.nom) if m not in _MOTS_VIDES] == voulus]
    if len(exacts) == 1:
        return exacts[0], None
    # Sinon : l'appareil dont le nom contient le plus de mots demandés, s'il est seul en tête
    scores = [(sum(m in _mots(c.nom) for m in voulus), c) for c in capteurs]
    meilleur = max((s for s, _ in scores), default=0)
    tete = [c for s, c in scores if s == meilleur]
    if meilleur == 0:
        return None, {"erreur": f"Aucun appareil ne correspond à « {demande} ».", "appareils": noms}
    if len(tete) > 1:
        return None, {"erreur": f"Plusieurs appareils correspondent à « {demande} » : demande lequel.",
                      "appareils": [c.nom for c in tete]}
    return tete[0], None


SANS_CARTE = ("AUCUNE carte Oui / Non n'est affichée : ne parle PAS de bouton Oui ni Non, et ne dis pas « J'ai bien "
              "compris : vous voulez que… ».")


def _outil_preparer_coupure(client, args):
    action = args.get("action")
    if action not in ("couper", "retablir"):
        raise ValueError("action doit valoir « couper » ou « retablir ».")
    capteur, erreur = _trouver_appareil(client, args.get("appareil"))
    if erreur:
        # vu le 18/10/2026 (vrai DeepSeek) : « Éteins » -> « … lequel, la lampe ou la prise ? Appuyez sur Oui… » : il
        # n'y a pourtant AUCUNE carte à l'écran
        return {**erreur, "a_savoir": SANS_CARTE + " Demande seulement lequel, en nommant ses appareils "
                                                   "simplement (« la lampe ou la prise ? »)."}
    if capteur.dispositif_id is None or capteur.coupureEffective is None:
        return {"erreur": f"« {capteur.nom} » n'a pas de relais connu : il ne peut pas être coupé ni rétabli "
                          "à distance. Il se commande avec son propre interrupteur.", "a_savoir": SANS_CARTE}
    coupe = action == "couper"
    if capteur.coupureDemandee == coupe:
        applique = capteur.coupureEffective == coupe
        etat = "coupé" if coupe else "alimenté (courant rétabli)"
        return {"deja": True, "appareil": capteur.nom, "nom": nom_simple(capteur.nom), "action": action,
                "applique": applique,
                "message": (f"« {capteur.nom} » est déjà {etat} : rien à faire." if applique else
                            f"C'est déjà demandé pour « {capteur.nom} » : le boîtier l'appliquera à son prochain contact."),
                "a_savoir": SANS_CARTE + " Dis-le simplement."}
    # « nom » : l'appareil dit simplement (« la lampe ») pour la phrase de la carte et la reformulation de l'IA
    demande = {"capteur_id": str(capteur.id), "appareil": capteur.nom, "nom": nom_simple(capteur.nom), "action": action,
               "expire": (timezone.now() + timedelta(seconds=DUREE_CONFIRMATION_S)).isoformat()}
    ordre = "j'éteigne" if coupe else "je rallume"
    return {
        "demande_confirmation": demande,
        "carte_page": {"type": "coupure", "titre": "Éteindre un appareil" if coupe else "Rallumer un appareil", **demande},
        "a_savoir": ("RIEN n'est encore fait. Une carte Oui / Non s'affiche à l'écran. Reformule d'abord ce que tu as "
                     f"compris (« J'ai bien compris : vous voulez que {ordre} {demande['nom']}. »), dans la langue "
                     "de ta réponse, puis demande d'appuyer sur Oui pour confirmer, ou sur Non pour annuler. "
                     "Ne dis JAMAIS que l'appareil est coupé ou rétabli : seul son clic le fait."),
    }


# ── Registre + spécification OpenAI-compatible ──────────────────────────────
# nom → (fonction, label FR affiché dans l'UI « Données consultées : … »)
OUTILS = {
    "conso_periode": (_outil_conso_periode, "consommation par période"),
    "repartition_appareils": (_outil_repartition_appareils, "répartition par appareil"),
    "historique_mensuel": (_outil_historique_mensuel, "historique mensuel"),
    "heures_de_pointe": (_outil_heures_de_pointe, "heures de pointe"),
    "prevision_fin_mois": (_outil_prevision_fin_mois, "prévision de fin de mois"),
    "credit_et_recharges": (_outil_credit_et_recharges, "crédit prépayé"),
    "alertes": (_outil_alertes, "alertes"),
    "interventions": (_outil_interventions, "interventions"),
    "etat_capteurs": (_outil_etat_capteurs, "état des capteurs"),
    "preparer_coupure": (_outil_preparer_coupure, "demande de coupure"),
}


def _spec(nom, description, proprietes=None, requis=None):
    return {
        "type": "function",
        "function": {
            "name": nom,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": proprietes or {},
                "required": requis or [],
            },
        },
    }


_PROP_PERIODE = {"type": "string", "enum": list(PERIODES),
                 "description": "Période RELATIVE, calculée par le serveur (ne calcule pas les dates "
                                "toi-même) : aujourd_hui, hier, avant_hier, cette_semaine (lundi -> "
                                "aujourd'hui ; aussi « depuis lundi », « du lundi passé jusqu'à ce "
                                "dimanche »), semaine_derniere (lundi -> dimanche précédents), "
                                "7_derniers_jours, ce_week_end, week_end_dernier, ce_mois, "
                                "mois_dernier, 30_derniers_jours."}
_PROP_DATE_DEBUT = {"type": "string",
                    "description": "Seulement pour des dates PRÉCISES (« du 3 au 10 mai », « en juin ») : "
                                   "premier jour, format AAAA-MM-JJ (inclus). Ignoré si periode est donné."}
_PROP_DATE_FIN = {"type": "string",
                  "description": "Seulement avec date_debut : dernier jour, format AAAA-MM-JJ (inclus ; "
                                 "ramené à aujourd'hui s'il est dans le futur)."}
_PROPS_FENETRE = {"periode": _PROP_PERIODE, "date_debut": _PROP_DATE_DEBUT, "date_fin": _PROP_DATE_FIN}

OUTILS_SPEC = [
    _spec("conso_periode",
          "Consommation électrique RÉELLE du client sur une période : kWh total, coût estimé, "
          "détail par jour (si ≤ 31 jours) et comparaison avec la période précédente comparable "
          "(semaine d'avant, mois d'avant…). Pour « hier », « la semaine dernière », « ce mois-ci », "
          "« ce week-end »… passe `periode` ; pour des dates précises (« du 3 au 10 mai »), "
          "date_debut et date_fin. Dans ta réponse, cite la période exacte : `periode.libelle`.",
          _PROPS_FENETRE),
    _spec("repartition_appareils",
          "Part de chaque appareil/capteur (kWh, %, pic de puissance) sur une période. À utiliser "
          "pour « quel appareil consomme le plus », « combien a consommé le climatiseur en juin », "
          "etc. Période relative : `periode` ; dates précises : date_debut et date_fin. Cite "
          "`periode.libelle` dans ta réponse.",
          _PROPS_FENETRE),
    _spec("historique_mensuel",
          "Historique des 6 dernières périodes de facturation : kWh et montant FCFA réels "
          "(part fixe / variable). Postpayé : une ligne par BIMESTRE (la facture CIE couvre "
          "deux mois) ; prépayé : une ligne par mois. Période en cours partielle. SEULE source "
          "valable pour « combien j'ai payé » ou comparer des factures."),
    _spec("heures_de_pointe",
          "Profil horaire de consommation (0-23 h) sur les N derniers jours : à quelle heure "
          "le client consomme le plus ou le moins.",
          {"nb_jours": {"type": "integer",
                        "description": "Fenêtre d'analyse en jours (1 à 30, défaut 7)."}}),
    _spec("prevision_fin_mois",
          "Prévision honnête du montant en FIN de période (fin du bimestre en postpayé, fin "
          "du mois en prépayé, voir periode.libelle) : fourchette basse/centrale/haute en FCFA, "
          "niveau de confiance, recharge conseillée si prépayé. SEULE source valable pour "
          "« combien vais-je payer »."),
    _spec("credit_et_recharges",
          "Crédit prépayé restant estimé, date et heure de fin prévues (fin_estimee, avec sa fourchette "
          "fin_tot / fin_tard ; l'heure seulement si heure_fiable), selon les habitudes du foyer et la "
          "température annoncée, et dernières recharges déclarées (compteurs prépayés uniquement)."),
    _spec("alertes",
          "Alertes du client (dépassement de seuil, consommation nocturne fantôme, crédit bas, tranche "
          "de la facture postpayée proche ou atteinte) : type, sévérité, message, date, lue/non lue.",
          {"seulement_non_lues": {"type": "boolean",
                                  "description": "true = seulement les alertes non lues (défaut false)."},
           "limite": {"type": "integer",
                      "description": "Nombre maximal d'alertes renvoyées (1 à 20, défaut 10)."}}),
    _spec("interventions",
          "Les 5 dernières interventions techniques du client (installation, calibration, "
          "panne, maintenance) : type, statut, dates, résultat."),
    _spec("etat_capteurs",
          "État actuel de chaque capteur/appareil suivi : allumé (ON) / éteint (OFF), seuil "
          "d'alerte, dernière lecture (permet de repérer un capteur hors ligne), courant coupé à "
          "distance ou non (coupe_a_distance)."),
    _spec("preparer_coupure",
          "Quand la personne demande de COUPER le courant d'un appareil, ou de le RÉTABLIR (« coupe la "
          "prise », « éteins la lampe », « remets le courant de la prise »). Ne coupe RIEN : affiche à "
          "l'écran une carte Oui / Non, et seul le clic de la personne sur « Oui » envoie l'ordre. Après "
          "l'appel, demande-lui d'appuyer sur Oui ou Non ; ne dis jamais que c'est fait. « Allumer » = "
          "rétablir le courant (un appareil éteint par son propre interrupteur ne s'allume pas à "
          "distance). Si l'appareil est ambigu, l'outil renvoie la liste : demande lequel.",
          {"appareil": {"type": "string",
                        "description": "Le nom de l'appareil tel que la personne le dit (« prise », « lampe »...)."},
           "action": {"type": "string", "enum": ["couper", "retablir"],
                      "description": "couper : couper le courant ; retablir : le remettre."}},
          ["appareil", "action"]),
]


def label_outil(nom):
    """Label FR d'un outil pour l'UI ; renvoie le nom brut si inconnu."""
    entree = OUTILS.get(nom)
    return entree[1] if entree else nom


def executer_outil(client, nom, arguments):
    """Exécute un outil pour CE client. Toujours un dict JSON-sérialisable :
    {"erreur": ...} si l'outil est inconnu, les paramètres invalides ou la
    lecture échoue — le LLM peut alors corriger et réessayer, jamais de 500."""
    entree = OUTILS.get(nom)
    if entree is None:
        return {"erreur": f"Outil inconnu : {nom}. Outils disponibles : {', '.join(sorted(OUTILS))}."}
    try:
        return entree[0](client, arguments if isinstance(arguments, dict) else {})
    except ValueError as e:
        return {"erreur": str(e)}
    except Exception:
        logger.exception("Échec de l'outil IA %s (client=%s)", nom, client.pk)
        return {"erreur": "Lecture des données impossible pour cet outil (erreur interne)."}
