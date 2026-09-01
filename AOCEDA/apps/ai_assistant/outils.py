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
"""
import logging
from datetime import datetime as _datetime, timedelta

from django.db.models import Avg, Max, Sum  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]

logger = logging.getLogger(__name__)

# Bornes de sécurité : fenêtre d'analyse d'1 an max, détail par jour seulement
# sur les fenêtres courtes (au-delà, le détail exploserait le budget tokens).
MAX_JOURS_FENETRE = 366
MAX_JOURS_DETAIL = 31


def _parse_date_locale(valeur, nom_champ):
    try:
        return _datetime.strptime(str(valeur), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise ValueError(f"Paramètre {nom_champ} invalide : attendu AAAA-MM-JJ, reçu {valeur!r}.")


def _bornes_fenetre(date_debut, date_fin):
    """Bornes LOCALES inclusives (00:00:00 → 23:59:59) d'une fenêtre en jours
    calendaires, clampée à aujourd'hui et à MAX_JOURS_FENETRE — même convention
    que RepartitionCapteursView (bornes incluses, jamais de futur)."""
    f = _parse_date_locale(date_debut, 'date_debut')
    t = _parse_date_locale(date_fin, 'date_fin')
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


def _outil_conso_periode(client, args):
    """kWh réels sur une période quelconque + détail par jour + comparaison avec
    la période précédente de même durée (None si aucune mesure avant — jamais de
    faux « -100 % », même règle que HistoriqueJournalierView)."""
    from apps.analytics.views import _aggregate_jours, _kwh_consommes
    from apps.analytics.tarifs_cie import prix_kwh_tout_compris
    from apps.sensors.models import MesureEnergie

    start, end, f, t = _bornes_fenetre(args.get('date_debut'), args.get('date_fin'))
    nb_jours = (t - f).days + 1
    kwh = float(_kwh_consommes(client, start, end))
    prix = float(prix_kwh_tout_compris(client))
    res = {
        "date_debut": f.isoformat(),
        "date_fin": t.isoformat(),
        "nb_jours": nb_jours,
        "kwh_total": round(kwh, 2),
        "cout_estime_fcfa": int(round(kwh * prix)),
        "note": "cout_estime_fcfa = kWh × prix marginal TTC (hors prime fixe mensuelle) : "
                "une estimation, pas une facture CIE — pour un montant mensuel exact, "
                "utiliser historique_mensuel.",
    }
    if nb_jours <= MAX_JOURS_DETAIL:
        qs = MesureEnergie.objects.filter(
            capteur__client=client, timestamp__gte=start, timestamp__lte=end)
        res["jours"] = _aggregate_jours(qs, timezone.get_current_timezone())

    prev_fin = f - timedelta(days=1)
    prev_debut = prev_fin - timedelta(days=nb_jours - 1)
    p_start = timezone.make_aware(_datetime.combine(prev_debut, _datetime.min.time()))
    p_end = timezone.make_aware(_datetime.combine(prev_fin, _datetime.max.time()))
    if MesureEnergie.objects.filter(capteur__client=client,
                                    timestamp__gte=p_start, timestamp__lte=p_end).exists():
        res["periode_precedente"] = {
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

    start, end, f, t = _bornes_fenetre(args.get('date_debut'), args.get('date_fin'))
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
    return {
        "date_debut": f.isoformat(), "date_fin": t.isoformat(),
        "kwh_total": round(total, 2), "appareils": appareils,
    }


def _outil_historique_mensuel(client, args):
    """kWh + montant FCFA réels des 6 derniers mois (moteur tarifaire CIE) —
    exactement les chiffres de la carte « Historique mensuel »."""
    from apps.analytics.views import historique_fcfa_mensuel
    return {
        "mois": historique_fcfa_mensuel(client),
        "note": "total_fcfa recalculé par le moteur tarifaire CIE depuis la consommation "
                "réelle ; le mois marqué en_cours=true est partiel (à ce jour).",
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
    return {"nb_jours": nb_jours, "heures": heures, "heures_de_pointe": top}


def _outil_prevision_fin_mois(client, args):
    """Fourchette de facture de fin de mois — même moteur que la page Prévisions."""
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
                "note": "Compteur postpayé : pas de crédit prépayé, le client règle une facture mensuelle."}
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
    from apps.alerts.models import Alerte

    seulement_non_lues = bool(args.get('seulement_non_lues', False))
    try:
        limite = int(args.get('limite') or 10)
    except (TypeError, ValueError):
        limite = 10
    limite = max(1, min(limite, 20))
    qs = Alerte.objects.filter(client=client)
    if seulement_non_lues:
        qs = qs.filter(lue=False)
    alertes = [{"type": a.get_type_display(), "severite": a.sévérité,
                "message": (a.message or '')[:200],
                "date": timezone.localtime(a.createdAt).isoformat(), "lue": a.lue}
               for a in qs[:limite]]
    return {
        "nb_non_lues": Alerte.objects.filter(client=client, lue=False).count(),
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
        })
    return {
        "nb_capteurs": len(capteurs), "capteurs": capteurs,
        "note": "etat=OFF signifie éteint mais joignable ; « hors ligne » = derniere_lecture "
                "ancienne (plus de quelques minutes) ou absente.",
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


_PROP_DATE_DEBUT = {"type": "string",
                    "description": "Premier jour de la période, format AAAA-MM-JJ (inclus)."}
_PROP_DATE_FIN = {"type": "string",
                  "description": "Dernier jour de la période, format AAAA-MM-JJ (inclus ; clampé à aujourd'hui)."}

OUTILS_SPEC = [
    _spec("conso_periode",
          "Consommation électrique RÉELLE du client sur une période quelconque : kWh total, "
          "coût estimé, détail par jour (si ≤ 31 jours) et comparaison avec la période "
          "précédente de même durée. À utiliser pour « hier », « la semaine dernière », "
          "« du 3 au 10 mai », « ce week-end », et toute comparaison de périodes.",
          {"date_debut": _PROP_DATE_DEBUT, "date_fin": _PROP_DATE_FIN},
          ["date_debut", "date_fin"]),
    _spec("repartition_appareils",
          "Part de chaque appareil/capteur (kWh, %, pic de puissance) sur une période "
          "quelconque. À utiliser pour « quel appareil consomme le plus », « combien a "
          "consommé le climatiseur en juin », etc.",
          {"date_debut": _PROP_DATE_DEBUT, "date_fin": _PROP_DATE_FIN},
          ["date_debut", "date_fin"]),
    _spec("historique_mensuel",
          "Historique des 6 derniers mois : kWh et montant FCFA réels par mois (part fixe / "
          "variable), mois en cours partiel. SEULE source valable pour « combien j'ai payé "
          "en mai » ou comparer des factures mensuelles."),
    _spec("heures_de_pointe",
          "Profil horaire de consommation (0-23 h) sur les N derniers jours : à quelle heure "
          "le client consomme le plus ou le moins.",
          {"nb_jours": {"type": "integer",
                        "description": "Fenêtre d'analyse en jours (1 à 30, défaut 7)."}}),
    _spec("prevision_fin_mois",
          "Prévision honnête de la facture de FIN de mois : fourchette basse/centrale/haute "
          "en FCFA, niveau de confiance, recharge conseillée si prépayé. SEULE source valable "
          "pour « combien vais-je payer ce mois-ci »."),
    _spec("credit_et_recharges",
          "Crédit prépayé restant estimé, jours d'autonomie au rythme actuel et dernières "
          "recharges déclarées (compteurs prépayés uniquement)."),
    _spec("alertes",
          "Alertes du client (dépassement de seuil, consommation nocturne fantôme, crédit "
          "bas) : type, sévérité, message, date, lue/non lue.",
          {"seulement_non_lues": {"type": "boolean",
                                  "description": "true = seulement les alertes non lues (défaut false)."},
           "limite": {"type": "integer",
                      "description": "Nombre maximal d'alertes renvoyées (1 à 20, défaut 10)."}}),
    _spec("interventions",
          "Les 5 dernières interventions techniques du client (installation, calibration, "
          "panne, maintenance) : type, statut, dates, résultat."),
    _spec("etat_capteurs",
          "État actuel de chaque capteur/appareil suivi : allumé (ON) / éteint (OFF), seuil "
          "d'alerte, dernière lecture (permet de repérer un capteur hors ligne)."),
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
