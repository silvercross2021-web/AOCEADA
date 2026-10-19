import calendar
import math
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from django.db.models import Sum, Avg, Count, Min, Max, Q  # pyrefly: ignore [untyped-import]
from django.db.models.functions import TruncDate  # pyrefly: ignore [untyped-import]
from datetime import timedelta, datetime as _datetime, time as _time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .models import Prevision, RechargeCredit
from .serializers import PrevisionSerializer, RechargeCreditSerializer
from .tarifs_cie import (calculer_facture_pour_client, prix_kwh_tout_compris, PUISSANCE_KW, descriptif_tarif,
                         periode_contenant, periode_precedente, libelle_periode, est_prepaye)
from apps.sensors.models import Capteur, MesureEnergie

MOIS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
           "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def _fcfa_affiche(detail):
    """Total ENTIER affiché = somme des lignes arrondies (HALF_UP, comme JS Math.round).
    Garantit deux invariants : (1) somme des lignes affichées == Total ; (2) KPI (backend)
    == Total de la carte (front). On arrondit chaque composante puis on somme (jamais
    round de la somme exacte, qui pouvait diverger d'1 FCFA sur les valeurs en ,50)."""
    q = lambda v: Decimal(str(v)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    total = (q(detail['tranche1_fcfa']) + q(detail['tranche2_fcfa'])
             + q(detail['prime_fixe_fcfa']) + q(detail['taxes_fcfa']))
    return int(total)


def _credit_payload(info):
    """Rend le crédit prépayé compatible JSON (floats), ou None si postpayé."""
    if not info:
        return None
    return {
        "recharge_fcfa": float(info["recharge_fcfa"]),
        "consomme_fcfa": float(info["consomme_fcfa"]),
        "restant_fcfa": float(info["restant_fcfa"]),
        # None : aucun jour complet mesuré, pas de rythme fiable (jamais de chiffre inventé)
        "cout_jour_fcfa": float(info["cout_jour_fcfa"]) if info["cout_jour_fcfa"] is not None else None,
        "jours_restants": info["jours_restants"],
        # 19/10/2026 (note technique 4.2) : date de fin prévue (habitudes + température), avec sa fourchette ;
        # l'heure n'a de sens que si le profil horaire du foyer est connu (heure_fiable)
        "restant_kwh": info.get("restant_kwh"),
        "fin_estimee": _iso(info.get("fin_estimee")),
        "fin_tot": _iso(info.get("fin_tot")),
        "fin_tard": _iso(info.get("fin_tard")),
        "heure_fiable": bool(info.get("heure_fiable")),
        "source": info.get("source", "recharges"),
        "releve": ({"kwh": info["releve"]["kwh"], "le": _iso(info["releve"]["le"])} if info.get("releve") else None),
    }


def _iso(dt):
    return timezone.localtime(dt).isoformat(timespec="minutes") if dt is not None else None


def _kwh_consommes(client, depuis, jusqua):
    """Énergie consommée (kWh) sur la période.

    1) Source fiable : somme du champ `energie` (kWh) des mesures.
    2) Repli si `energie` absent : estimation par la puissance moyenne mesurée
       multipliée par la DURÉE RÉELLE couverte (tmax − tmin), sans supposer une
       fréquence d'échantillonnage fixe, bien plus robuste qu'un /60000.
    """
    agg = MesureEnergie.objects.filter(
        capteur__client=client, timestamp__gte=depuis, timestamp__lte=jusqua
    ).aggregate(e=Sum('energie'), pm=Avg('puissance'), n=Count('id'),
                tmin=Min('timestamp'), tmax=Max('timestamp'))

    total_energie = agg['e'] or Decimal('0')
    if total_energie > 0:
        return Decimal(total_energie)

    n = agg['n'] or 0
    if n == 0:
        return Decimal('0')
    avg_w = Decimal(str(agg['pm'] or 0))
    if n >= 2 and agg['tmin'] and agg['tmax']:
        span_h = Decimal(str((agg['tmax'] - agg['tmin']).total_seconds() / 3600.0))
        if span_h > 0:
            return avg_w / Decimal('1000') * span_h
    # Mesure unique : durée non fiable → estimation horaire prudente (1 h)
    return avg_w / Decimal('1000')


def _debut_jour(d):
    """Minuit LOCAL du jour `d` (date) : borne aware pour filtrer les mesures."""
    return timezone.make_aware(_datetime.combine(d, _time.min), timezone.get_current_timezone())


def periode_courante(client, now=None):
    """Période de facturation en cours : bimestre (postpayé) ou mois (prépayé).

    Renvoie un dict : debut/fin (dates incluses), type, libelle, jours, jours_ecoules,
    cle « AAAA-MM » (mois du début, sert de clé aux snapshots Prevision)."""
    now = now or timezone.localtime()
    debut, fin = periode_contenant(client, now.date())
    return {
        "debut": debut, "fin": fin,
        "type": "mois" if est_prepaye(client) else "bimestre",
        "libelle": libelle_periode(debut, fin),
        "jours": (fin - debut).days + 1,
        "jours_ecoules": (now.date() - debut).days + 1,
        "cle": debut.strftime("%Y-%m"),
    }


def facture_mois_a_ce_jour(client):
    """Facture RÉELLE de la période en cours, à ce jour : coût officiel des kWh
    RÉELLEMENT consommés depuis le début du bimestre (postpayé, arrêté n° 1355 :
    tranches, prime fixe, taxes) ou du mois (prépayé : prix unique par kWh).

    AUCUNE projection du futur : le montant ne monte que quand le client consomme,
    reste figé s'il n'allume rien, et devient sa facture réelle en fin de période.
    Le nom est historique (le postpayé était calculé par mois avant le 14/10/2026) ;
    les clés « mois » / « jours_du_mois » désignent désormais la période."""
    now = timezone.localtime()
    per = periode_courante(client, now)
    consommes = _kwh_consommes(client, _debut_jour(per["debut"]), now)
    detail = calculer_facture_pour_client(consommes, client)
    return {
        "annee_mois": per["cle"],
        "mois_libelle": per["libelle"],
        "jours_du_mois": per["jours"],
        "jours_ecoules": per["jours_ecoules"],
        "periode": per,
        "kwh_consommes": consommes.quantize(Decimal('0.01')),
        # Valeur EXACTE (non arrondie), la prévision doit tarifer sur le MÊME kWh que
        # le détail (cost_to_date), sinon convergence à ±1 F le dernier jour.
        "kwh_consommes_exact": consommes,
        "detail": detail,
    }


def _mesure_depuis(client, debut_periode):
    """Date (AAAA-MM-JJ) de la première mesure du client si elle tombe APRÈS le début de la période, sinon None :
    avant cette date AOCEDA n'a rien mesuré, le montant à ce jour ne peut pas la couvrir."""
    premiere = MesureEnergie.objects.filter(capteur__client=client).aggregate(m=Min('timestamp'))['m']
    if premiere is None:
        return None
    jour = timezone.localtime(premiere).date()
    return jour.isoformat() if jour > debut_periode else None


def _periode_json(per):
    return {"type": per["type"], "libelle": per["libelle"],
            "debut": per["debut"].isoformat(), "fin": per["fin"].isoformat(),
            "jours": per["jours"], "jours_ecoules": per["jours_ecoules"]}


def cout_entre(client, debut, fin):
    """Coût (FCFA, Decimal) de ce qui a été consommé entre deux instants aware.

    Prépayé : linéaire. Postpayé : par bimestre, coût CUMULÉ à `fin` moins coût cumulé
    à `debut` ; la part fixe (prime, redevances fixes) revient au morceau qui contient
    le DÉBUT du bimestre. La somme des morceaux d'un bimestre = sa facture exacte."""
    if fin <= debut:
        return Decimal('0')
    if est_prepaye(client):
        kwh = _kwh_consommes(client, debut, fin)
        return calculer_facture_pour_client(kwh, client)['total_fcfa'] if kwh > 0 else Decimal('0')
    total = Decimal('0')
    curseur = debut
    while curseur < fin:
        p_debut, p_fin = periode_contenant(client, timezone.localtime(curseur).date())
        t0 = _debut_jour(p_debut)
        t1 = min(_debut_jour(p_fin + timedelta(days=1)), fin)
        haut = calculer_facture_pour_client(_kwh_consommes(client, t0, t1), client)['total_fcfa']
        if curseur <= t0:
            bas = Decimal('0')
        else:
            bas = calculer_facture_pour_client(_kwh_consommes(client, t0, curseur), client)['total_fcfa']
        total += haut - bas
        curseur = t1
    return total


class PrevisionListView(generics.ListAPIView):
    serializer_class = PrevisionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'client'):
            return Prevision.objects.filter(client=user.client)
        return Prevision.objects.none()

    def list(self, request, *args, **kwargs):
        """Les périodes passées enregistrées + la période EN COURS calculée à l'instant, SANS rien écrire.
        Avant le 19/10/2026, ce GET (appelé toutes les 10 s par le tableau de bord) écrivait en base à chaque fois :
        avec le boîtier qui envoie toutes les 2 s, « database is locked » et des erreurs 500 sur la page."""
        user = request.user
        if not hasattr(user, 'client'):
            return Response([])
        client = user.client
        courant = snapshot_periode(client)
        passes = [self.get_serializer(p).data for p in
                  Prevision.objects.filter(client=client).exclude(annee_mois=courant["annee_mois"])]
        return Response(sorted([courant] + passes, key=lambda x: x.get("annee_mois") or "", reverse=True))


def snapshot_periode(client):
    """La période en cours, au format d'une Prevision (sans l'enregistrer)."""
    fac = facture_mois_a_ce_jour(client)
    ecart = ecart_a_date(client, fac)
    return {"id": None, "moisConcerné": fac["mois_libelle"], "annee_mois": fac["annee_mois"],
            "consomméeEstimée_kWh": str(round(fac["kwh_consommes"], 2)),
            "montantEstimé_FCFA": str(_fcfa_affiche(fac["detail"])),
            "écartSurMoisPrécédent": (f"{ecart['pct']:.2f}" if ecart["pct"] is not None else None),
            "ecart": ecart}


def enregistrer_prevision(client):
    """Garde l'instantané de la période en cours (tâche planifiée, jamais dans un GET) : les périodes passées gardent
    ainsi leur montant final."""
    from django.db import transaction
    snap = snapshot_periode(client)
    with transaction.atomic():
        qs = Prevision.objects.select_for_update().filter(client=client, annee_mois=snap["annee_mois"])
        ids = list(qs.values_list('id', flat=True))
        if len(ids) > 1:
            Prevision.objects.filter(id__in=ids[1:]).delete()
        Prevision.objects.update_or_create(client=client, annee_mois=snap["annee_mois"], defaults={
            'moisConcerné': snap["moisConcerné"],
            'consomméeEstimée_kWh': Decimal(snap["consomméeEstimée_kWh"]),
            'montantEstimé_FCFA': Decimal(snap["montantEstimé_FCFA"]),
            'écartSurMoisPrécédent': Decimal(snap["écartSurMoisPrécédent"] or "0")})


MOIS_COURTS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")


def _jour_court(d):
    return f"{'1er' if d.day == 1 else d.day} {MOIS_COURTS[d.month - 1]}"


def ecart_a_date(client, fac=None):
    """Écart de la facture à ce jour avec la MÊME durée de la période précédente (« à date ») : le 19 du bimestre est
    comparé aux 19 premiers jours du bimestre d'avant, pas à un bimestre entier (avant le 19/10/2026 : « ↓ 80 % »
    affiché chaque début de période). None quand la comparaison n'a pas de sens (période d'avant presque sans
    mesure, écart démesuré)."""
    fac = fac or facture_mois_a_ce_jour(client)
    now = timezone.localtime()
    debut = _debut_jour(fac["periode"]["debut"])
    p_debut, _ = periode_precedente(client, fac["periode"]["debut"])
    t0 = _debut_jour(p_debut)
    t1 = t0 + (now - debut)
    res = {"pct": None, "precedent_fcfa": None, "libelle": f"du {_jour_court(p_debut)} au {_jour_court(t1.date())}"}
    if not MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=t0, timestamp__lt=t1).exists():
        return res
    kwh_avant = _kwh_consommes(client, t0, t1)
    if kwh_avant < Decimal('0.1'):
        return res
    prec = _fcfa_affiche(calculer_facture_pour_client(kwh_avant, client))
    cur = _fcfa_affiche(fac["detail"])
    res["precedent_fcfa"] = prec
    if prec > 0:
        pct = (cur - prec) / prec * 100
        if abs(pct) <= 300:
            res["pct"] = round(float(pct), 1)
    return res


EN_LIGNE_S = 60


def etat_contact(client, now=None):
    """Dernier contact réel avec le boîtier (dernière trame reçue, allumé ou éteint, ou dernière mesure) et s'il est
    en ligne (contact de moins d'une minute). Le tableau de bord ne dit plus « données en direct » ni « 0 W » pour un
    boîtier muet depuis des jours (19/10/2026)."""
    now = now or timezone.now()
    lecture = Capteur.objects.filter(client=client).aggregate(m=Max('derniereLecture'))['m']
    mesure = MesureEnergie.objects.filter(capteur__client=client).aggregate(m=Max('timestamp'))['m']
    dernier = max([d for d in (lecture, mesure) if d is not None], default=None)
    return {"dernier_contact": dernier, "en_ligne": bool(dernier and (now - dernier).total_seconds() <= EN_LIGNE_S)}


class FactureDetailView(APIView):
    """Décomposition officielle CIE de la facture du mois en cours
    (grille EXPLICATION_TARIFAIRE.md : tranches, prime fixe, taxes, TVA incluse)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à la facture."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client
        from apps.alerts.utils import credit_prepaye_info
        # Compte sans capteur : état VIDE honnête, cohérent avec AnalyticsSummaryView —
        # surtout PAS le plancher « abonnement fixe » présenté comme une facture réelle.
        # Sans champ tranche1, le front (loadFacture) garde state.facture nul et la carte
        # retombe sur le 0 du résumé → aucune contradiction KPI (#kpi-bill) / carte.
        if not Capteur.objects.filter(client=client).exists():
            return Response({
                "mode": "vide",
                "type_compteur": getattr(client, 'typeCompteur', 'postpaye'),
                "credit_prepaye": _credit_payload(credit_prepaye_info(client)),
                "periode": _periode_json(periode_courante(client)),
            })
        fac = facture_mois_a_ce_jour(client)
        contact = etat_contact(client)
        d = fac["detail"]
        # Regroupement LISIBLE pour le client, en 2 seaux qui somment EXACTEMENT au KPI :
        #  • abonnement fixe = prime fixe + taxe fixe (dû chaque mois, quoi qu'on consomme)
        #  • consommation    = le reste (tranches + taxes par kWh) = total - abonnement
        # « consommation » dérivé par soustraction → garantit seau1 + seau2 == total affiché.
        def _r1(x):
            return int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        total_affiche = _fcfa_affiche(d)
        abonnement_fixe = _r1(d["prime_fixe_fcfa"]) + _r1(d["taxe_fixe_fcfa"])
        consommation_fcfa = total_affiche - abonnement_fixe
        return Response({
            "credit_prepaye": _credit_payload(credit_prepaye_info(client)),
            "mois": fac["mois_libelle"],
            "annee_mois": fac["annee_mois"],
            "periode": _periode_json(fac["periode"]),
            "regime": d["regime"],
            "jours_du_mois": fac["jours_du_mois"],
            "jours_ecoules": fac["jours_ecoules"],
            "kwh_consommes": float(fac["kwh_consommes"]),
            # kwh_projetes conservé pour compat front, mais = consommé réel (plus de projection)
            "kwh_projetes": float(fac["kwh_consommes"]),
            "type_tarif": d["type_tarif"],
            "amperage": d["amperage"],
            "type_compteur": getattr(client, 'typeCompteur', 'postpaye'),
            "seuil_t1_kwh": float(d["seuil_t1_kwh"]) if d["seuil_t1_kwh"] is not None else None,
            "tranche1": {"kwh": float(d["tranche1_kwh"]), "prix": float(d["tranche1_prix"]), "fcfa": float(d["tranche1_fcfa"])},
            "tranche2": {"kwh": float(d["tranche2_kwh"]), "prix": float(d["tranche2_prix"]), "fcfa": float(d["tranche2_fcfa"])},
            "prime_fixe_fcfa": float(d["prime_fixe_fcfa"]),
            "taxes_fcfa": float(d["taxes_fcfa"]),
            "taxes_variable_fcfa": float(d["taxes_variable_fcfa"]),
            "taxe_fixe_fcfa": float(d["taxe_fixe_fcfa"]),
            "taxes_par_kwh": float(d["taxes_par_kwh"]),
            "total_fcfa": float(d["total_fcfa"]),
            # Total ENTIER canonique (somme des lignes arrondies) = KPI du dashboard
            "total_fcfa_arrondi": total_affiche,
            # Vue SIMPLE en 2 parts (abonnement + consommation == total_fcfa_arrondi)
            "abonnement_fixe_fcfa": abonnement_fixe,
            "consommation_fcfa": consommation_fcfa,
            "prix_moyen_kwh": float(d["prix_moyen_kwh"]),
            "prix_kwh_tout_compris": float(prix_kwh_tout_compris(client)),
            "tva_incluse": True,
            # 19/10/2026 : écart avec la même durée de la période d'avant, et dernier contact réel du boîtier (la
            # carte ne dit plus « À jour » ni « consommation 0 F » quand rien n'est mesuré depuis des jours)
            "ecart": ecart_a_date(client, fac),
            "en_ligne": contact["en_ligne"],
            "dernier_contact": _iso(contact["dernier_contact"]),
            # 20/10/2026 : ce que le montant couvre RÉELLEMENT (appareils suivis, depuis quand), la fin de la période et
            # le tarif tout compris
            "mesure_depuis": _mesure_depuis(client, fac["periode"]["debut"]),
            "capteurs_suivis": Capteur.objects.filter(client=client, actif=True).count(),
            "fin_periode": fac["periode"]["fin"].isoformat(),
            "jours_restants_periode": max(0, (fac["periode"]["fin"] - timezone.localdate()).days),
            "aucune_mesure": float(fac["kwh_consommes"]) <= 0,
            "tarif": descriptif_tarif(client),
        })


class ReleveCompteurView(APIView):
    """Recalage du crédit prépayé (19/10/2026, note technique 4.2) : la personne lit les kWh restants sur l'écran de
    son compteur CIE ; le crédit estimé repart de cette lecture. {"kwh": 37.5} enregistre la lecture (maintenant) ;
    {"annuler": true} revient au calcul depuis le total des recharges."""
    permission_classes = [permissions.IsAuthenticated]
    KWH_MAX = Decimal("100000")

    def post(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent relever leur compteur."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client
        if getattr(client, 'typeCompteur', 'postpaye') != 'prepaye':
            return Response({"detail": "Le relevé du crédit ne concerne que les compteurs prépayés."},
                            status=status.HTTP_400_BAD_REQUEST)
        if request.data.get('annuler') in (True, 'true', '1', 1):
            client.creditReleve_kWh, client.creditReleveLe = None, None
            detail = "Relevé annulé : le crédit est de nouveau calculé depuis vos recharges."
        else:
            try:
                kwh = Decimal(str(request.data.get('kwh')).replace(',', '.').replace(' ', ''))
            except (TypeError, ValueError, InvalidOperation):
                return Response({"detail": "Saisissez les kWh affichés par votre compteur (ex. 37,5)."},
                                status=status.HTTP_400_BAD_REQUEST)
            if not kwh.is_finite() or not (Decimal('0') <= kwh <= self.KWH_MAX):
                return Response({"detail": "Valeur impossible pour un compteur."}, status=status.HTTP_400_BAD_REQUEST)
            client.creditReleve_kWh, client.creditReleveLe = kwh.quantize(Decimal('0.01')), timezone.now()
            detail = f"Relevé enregistré : {str(kwh).replace('.', ',')} kWh. Le crédit estimé repart de cette lecture."
        client.save(update_fields=['creditReleve_kWh', 'creditReleveLe'])
        from apps.alerts.utils import check_credit_prepaye
        check_credit_prepaye(client)
        from apps.accounts.audit import log_action
        log_action(user, 'RELEVE_COMPTEUR', detail, cible_id=client.id)
        from apps.alerts.utils import credit_prepaye_info
        return Response({"detail": detail, "credit_prepaye": _credit_payload(credit_prepaye_info(client))})


class AnalyticsSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à l'analyse."}, status=status.HTTP_403_FORBIDDEN)
            
        client = user.client
        now = timezone.now()
        from apps.alerts.utils import alertes_du_client, credit_prepaye_info
        alertes_actives = alertes_du_client(client).filter(lue=False).count()

        # Compte sans aucun capteur : on renvoie un état VIDE honnête (zéros),
        # jamais de fausses valeurs présentées comme réelles.
        if not Capteur.objects.filter(client=client).exists():
            credit = credit_prepaye_info(client)
            return Response({
                "puissance_instantanee": None,
                "consommation_jour_kwh": None,
                "facture_estimee_fcfa": 0,
                "alertes_actives": alertes_actives,
                "en_ligne": False, "dernier_contact": None,
                "type_compteur": getattr(client, 'typeCompteur', 'postpaye'),
                "credit_prepaye": _credit_payload(credit),
                "last_update": now.isoformat(),
                "mode": "vide",
            })

        # 1. Instantaneous power (sum of last measurement of active sensors)
        # Seulement les appareils ALLUMÉS (état persisté par l'ingestion) : sans ce
        # filtre, la dernière mesure d'un appareil qu'on vient d'éteindre restait comptée
        # jusqu'à 60 s (« ça continue de compter » après extinction, 12/10/2026).
        contact = etat_contact(client, now)
        active_sensors = Capteur.objects.filter(client=client, actif=True, etatCourant='ON')
        instantaneous_w = Decimal('0')
        # Fenêtre de fraîcheur : une mesure de plus de 60 s n'est PLUS « instantanée »
        # (un capteur muet depuis des heures ne doit pas gonfler la puissance affichée).
        # Aligne puissance_instantanee sur ce que le flux SSE agrège côté client.
        frais = now - timedelta(seconds=60)
        for sensor in active_sensors:
            last_m = MesureEnergie.objects.filter(
                capteur=sensor, timestamp__gte=frais
            ).order_by('-timestamp').first()
            if last_m:
                instantaneous_w += last_m.puissance

        # 2. Daily consumption in kWh (somme du champ energie, repli puissance/min)
        debut_jour = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        today_kwh = _kwh_consommes(client, debut_jour, now)

        # 3. Facture RÉELLE du mois à ce jour (coût CIE des kWh réellement consommés). Plus aucune écriture ici
        # (instantané de la période : tâche planifiée ; alerte « Crédit bas » : à la réception des mesures, à la
        # recharge et toutes les 5 minutes) : ce GET appelé toutes les 10 s provoquait « database is locked ».
        fac = facture_mois_a_ce_jour(client)
        montant_estime = _fcfa_affiche(fac["detail"])  # entier = somme des lignes (== carte)
        credit = credit_prepaye_info(client)

        # Boîtier muet : la puissance et la consommation d'aujourd'hui sont INCONNUES, pas nulles
        dernier = contact["dernier_contact"]
        mesure_aujourdhui = bool(dernier and timezone.localtime(dernier) >= debut_jour)
        return Response({
            # HALF_UP comme JS Math.round (l'ancien int() tronquait → 1 W/1 F d'écart)
            "puissance_instantanee": (int(instantaneous_w.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                                      if contact["en_ligne"] else None),
            "consommation_jour_kwh": round(float(today_kwh), 2) if mesure_aujourdhui else None,
            "facture_estimee_fcfa": montant_estime,  # déjà entier (somme des lignes, == carte)
            "alertes_actives": alertes_actives,
            "en_ligne": contact["en_ligne"],
            "dernier_contact": _iso(dernier),
            "type_compteur": getattr(client, 'typeCompteur', 'postpaye'),
            "credit_prepaye": _credit_payload(credit),
            "last_update": now.isoformat(),
            "mode": "production"
        })


def _parse_hist_window(qp, today):
    """(start_date, end_date) en dates LOCALES pour la page Historique, ou (None, err_response).

    Fenêtre ancrée sur des jours CALENDAIRES (le dernier = aujourd'hui pour les périodes) :
    corrige le 1er seau tronqué de l'ancien `now - Ndays` (instant en milieu de journée)."""
    date_from = qp.get('date_from')
    date_to = qp.get('date_to')

    def _pd(v):
        try:
            return _datetime.strptime(v, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    if date_from or date_to:
        a, b = _pd(date_from), _pd(date_to)
        if (date_from and a is None) or (date_to and b is None):
            return None, Response({"detail": "Format de date invalide (attendu AAAA-MM-JJ)."},
                                  status=status.HTTP_400_BAD_REQUEST)
        if a and b and a > b:
            return None, Response({"detail": "La date de début doit être antérieure ou égale à la date de fin."},
                                  status=status.HTTP_400_BAD_REQUEST)
        end_date = b or today
        start_date = a or (end_date - timedelta(days=6))
        if (end_date - start_date).days + 1 > JOURS_MAX_HIST:
            return None, Response({"detail": f"Plage limitée à {JOURS_MAX_HIST} jours."},
                                  status=status.HTTP_400_BAD_REQUEST)
        return (start_date, end_date), None
    period = qp.get('period', 'week')
    days = {'day': 1, 'week': 7, 'month': 30}.get(period, 7)
    return (today - timedelta(days=days - 1), today), None


def _parse_sensor_id(qp):
    """UUID du capteur (?sensor_id=…) validé EN AMONT, ou (None, err_response).

    Capteur.id est un UUIDField : filtrer directement avec une valeur non-UUID
    lève une ValidationError que DRF ne convertit pas → 500 au lieu d'un 400.
    Toute vue qui accepte sensor_id doit passer par ici."""
    raw = qp.get('sensor_id')
    if not raw:
        return None, None
    import uuid as _uuid
    try:
        return _uuid.UUID(str(raw)), None
    except (ValueError, AttributeError, TypeError):
        return None, Response({"detail": "Identifiant de capteur invalide."},
                              status=status.HTTP_400_BAD_REQUEST)


def _entre_jours(qs, debut=None, fin=None):
    """Mesures des jours LOCAUX debut..fin inclus (l'un ou l'autre peut manquer).

    Filtre par plage d'heures (minuit local -> minuit local du lendemain) et non par
    ``timestamp__date`` : ce dernier passe CHAQUE mesure de la table dans une fonction
    de conversion (SQLite), sans index. Avec un ESP32 qui envoie toutes les 2 s, la page
    Historique attendait ~0,2 s par requete et 1,5 a 2,5 s en tout (14/10/2026)."""
    tz = timezone.get_current_timezone()
    if debut is not None:
        qs = qs.filter(timestamp__gte=timezone.make_aware(_datetime.combine(debut, _time.min), tz))
    if fin is not None:
        lendemain = fin + timedelta(days=1)
        qs = qs.filter(timestamp__lt=timezone.make_aware(_datetime.combine(lendemain, _time.min), tz))
    return qs


HEURE_NUIT_DEBUT = 22      # « nuit » de l'historique = 22 h → 6 h, heure locale (comme les conseils du tableau de bord)
HEURE_NUIT_FIN = 6
JOURS_MAX_HIST = 366
ALERTES_DE_CONSO = ('DEPASSEMENT_SEUIL', 'CONSOMMATION_NOCTURNE')   # seules alertes liées à la conso d'un jour


def _capteurs_du_client(client, sensor_id=None):
    """Identifiants des capteurs du client (ou du seul capteur demandé, s'il lui appartient)."""
    ids = list(Capteur.objects.filter(client=client).values_list('id', flat=True))
    if sensor_id:
        return [i for i in ids if i == sensor_id]
    return ids


def _aggregate_jours(capteur_ids, start, end, tz=None):
    """(jours, manquants) du jour LOCAL `start` au jour `end` inclus (jamais au-delà d'aujourd'hui).

    jours : une ligne par jour où le boîtier a laissé une trace : énergie, pic, puissance moyenne (pendant la marche),
    énergie de nuit (22 h → 6 h), nombre de mesures, et `etat` : « mesure » (consommation relevée) ou « eteint » (le
    boîtier était là sans que l'appareil consomme : un VRAI 0 kWh). manquants : jours sans aucune trace (boîtier hors
    ligne : inconnu, jamais un 0 inventé).

    19/10/2026 : un agrégat par jour sur une plage d'horodatages (index, aucune fonction par ligne). L'ancien
    TruncDate faisait appeler à SQLite une fonction Python par mesure, trois fois : 4 s pour 7 jours et 10 s pour
    30 jours sur 40 000 mesures."""
    from datetime import time as _t
    from apps.sensors.models import PresenceCapteur as _Presence
    tz = tz or timezone.get_current_timezone()
    jours, manquants = [], []
    if not capteur_ids:
        return jours, manquants
    base = MesureEnergie.objects.filter(capteur_id__in=capteur_ids)
    fin = min(end, timezone.localdate())
    d = start
    while d <= fin:
        debut_j = timezone.make_aware(_datetime.combine(d, _t.min), tz)
        fin_j = timezone.make_aware(_datetime.combine(d + timedelta(days=1), _t.min), tz)
        six = timezone.make_aware(_datetime.combine(d, _t(HEURE_NUIT_FIN)), tz)
        vingt_deux = timezone.make_aware(_datetime.combine(d, _t(HEURE_NUIT_DEBUT)), tz)
        agg = base.filter(timestamp__gte=debut_j, timestamp__lt=fin_j).aggregate(
            kwh=Sum('energie'), peak=Max('puissance'), avg_w=Avg('puissance'), n=Count('id'),
            night=Sum('energie', filter=Q(timestamp__lt=six) | Q(timestamp__gte=vingt_deux)))
        if agg['n']:
            jours.append({"date": d.isoformat(), "kwh": float(agg['kwh'] or 0), "peak_w": round(float(agg['peak'] or 0)),
                          "avg_w": round(float(agg['avg_w'] or 0)), "night_kwh": float(agg['night'] or 0),
                          "n": agg['n'], "etat": "mesure"})
        elif _Presence.objects.filter(capteur_id__in=capteur_ids, heure__gte=debut_j, heure__lt=fin_j).exists():
            jours.append({"date": d.isoformat(), "kwh": 0.0, "peak_w": 0, "avg_w": 0, "night_kwh": 0.0, "n": 0,
                          "etat": "eteint"})
        else:
            manquants.append(d.isoformat())
        d += timedelta(days=1)
    return jours, manquants


def _alertes_par_jour(client, start, end, tz=None):
    """{date ISO: nombre d'alertes de consommation} : jours LOCAUX du serveur (et non ceux du navigateur)."""
    from datetime import time as _t
    from apps.alerts.models import Alerte
    tz = tz or timezone.get_current_timezone()
    debut = timezone.make_aware(_datetime.combine(start, _t.min), tz)
    fin = timezone.make_aware(_datetime.combine(end + timedelta(days=1), _t.min), tz)
    out = {}
    for quand in (Alerte.objects.filter(client=client, type__in=ALERTES_DE_CONSO, createdAt__gte=debut, createdAt__lt=fin)
                  .values_list('createdAt', flat=True)):
        j = timezone.localtime(quand, tz).date().isoformat()
        out[j] = out.get(j, 0) + 1
    return out


def _evolution_pct(courant, precedent):
    """Écart en % avec la période d'avant, ou None quand la comparaison n'a pas de sens (moins de 0,1 kWh avant,
    écart au-delà de 300 % : même règle que le tableau de bord)."""
    if precedent is None or precedent < 0.1:
        return None
    pct = (courant - precedent) / precedent * 100
    return None if abs(pct) > 300 else round(pct)


class RepartitionCapteursView(APIView):
    """Répartition de la consommation PAR CAPTEUR sur une fenêtre récente (défaut 7 jours).

    Montre « où va l'énergie » : la part de chaque appareil (kWh + %) et son pic de puissance.
    Angle absent du reste du dashboard (qui n'affiche que le total). 100 % données réelles :
    liste uniquement les capteurs ayant RÉELLEMENT mesuré sur la période (jamais de 0 fabriqué)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont une répartition par capteur."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client
        now = timezone.localtime()
        qp = request.query_params
        d_from = (qp.get('from') or '').strip()
        d_to = (qp.get('to') or '').strip()

        mode = 'preset'
        start = end = None
        jours = 7
        # Plage PERSONNALISÉE : deux dates YYYY-MM-DD, bornes incluses (comme le graphe principal).
        if d_from and d_to:
            try:
                f = _datetime.strptime(d_from, '%Y-%m-%d').date()
                t = _datetime.strptime(d_to, '%Y-%m-%d').date()
                if f > t:
                    f, t = t, f
                if (t - f).days > 366:            # borne de sécurité : 1 an max
                    f = t - timedelta(days=366)
                start = timezone.make_aware(_datetime.combine(f, _datetime.min.time()))
                end = timezone.make_aware(_datetime.combine(t, _datetime.max.time()))
                jours = (t - f).days + 1
                mode = 'custom'
            except (ValueError, TypeError):
                start = end = None

        # Sinon : PRESET en nombre de jours (Aujourd'hui = 1, 7 jours, 30 jours…).
        if start is None:
            try:
                jours = int(qp.get('days', 7))
            except (ValueError, TypeError):
                jours = 7
            jours = max(1, min(jours, 366))
            start = (now - timedelta(days=jours - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = now

        rows = (MesureEnergie.objects
                .filter(capteur__client=client, timestamp__gte=start, timestamp__lte=end)
                .values('capteur_id', 'capteur__nom')
                .annotate(kwh=Sum('energie'), peak=Max('puissance'), n=Count('id'))
                .order_by('-kwh'))
        capteurs = [{"nom": r['capteur__nom'], "kwh": float(r['kwh'] or 0),
                     "peak_w": round(float(r['peak'] or 0)), "n": r['n']} for r in rows]
        total = sum(c["kwh"] for c in capteurs)
        for c in capteurs:
            c["pct"] = round(c["kwh"] / total * 100) if total > 0 else 0

        amperage = int(getattr(client, 'amperage', 10) or 10)
        cap_w = int(float(PUISSANCE_KW.get(amperage, Decimal('2.2'))) * 1000)
        return Response({
            "mode": mode, "jours": jours,
            "debut": timezone.localtime(start).date().isoformat(),
            "fin": timezone.localtime(end).date().isoformat(),
            "total_kwh": total, "capacite_w": cap_w,
            "amperage": amperage, "capteurs": capteurs,
        })


class ConseilsView(APIView):
    """Conseils calculés sur les vraies mesures du client (apps/analytics/conseils.py). Mis en cache 5 minutes par
    client : la page le relit toutes les 30 s, et les règles parcourent 14 jours de mesures."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'client'):
            return Response({"detail": "Seuls les clients ont des conseils."}, status=status.HTTP_403_FORBIDDEN)
        from django.core.cache import cache
        from .conseils import conseils_du_client
        cle = f"aoceda:conseils:{request.user.client.pk}"
        data = cache.get(cle)
        if data is None:
            data = conseils_du_client(request.user.client)
            cache.set(cle, data, 300)
        return Response(data)


def historique_fcfa_mensuel(client):
    """Historique FCFA RÉEL par période de facturation (6 au plus), répartition
    « fixe » / « consommation » : bimestres en postpayé (la vraie facture CIE), mois
    en prépayé (coût linéaire, sans part fixe).

    Chaque période est RECALCULÉE depuis la conso RÉELLE via le moteur officiel (jamais
    une estimation périmée) → cohérente au franc près avec le héros « facture à ce jour ».
    La période en cours est partielle (« à ce jour »). Ne renvoie que les périodes
    RÉELLEMENT couvertes (depuis la 1re mesure). Le nom et les clés « mois » sont
    historiques. Partagé entre la carte « Historique » et l'outil IA historique_mensuel."""
    first = MesureEnergie.objects.filter(capteur__client=client).aggregate(m=Min('timestamp'))['m']
    if first is None:
        return []
    now = timezone.localtime()

    def _r1(x):
        return int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    periodes = []
    debut, fin = periode_contenant(client, timezone.localtime(first).date())
    while debut <= now.date():
        periodes.append((debut, fin))
        debut, fin = periode_contenant(client, fin + timedelta(days=1))
    periodes = periodes[-6:]

    out = []
    for (debut, fin) in periodes:
        en_cours = debut <= now.date() <= fin
        t1 = now if en_cours else _debut_jour(fin + timedelta(days=1))
        kwh = _kwh_consommes(client, _debut_jour(debut), t1)
        detail = calculer_facture_pour_client(kwh, client)
        fixe = _r1(detail['prime_fixe_fcfa']) + _r1(detail['taxe_fixe_fcfa'])
        total = _fcfa_affiche(detail)
        depuis = _mesure_depuis(client, debut)
        out.append({
            "annee_mois": debut.strftime("%Y-%m"),
            "mesure_depuis": depuis,       # le boîtier n'a mesuré qu'à partir de ce jour : période incomplète
            "mois_libelle": libelle_periode(debut, fin),
            "periode_type": "mois" if est_prepaye(client) else "bimestre",
            "kwh": float(kwh),
            "fixe_fcfa": fixe,
            "variable_fcfa": max(0, total - fixe),
            "total_fcfa": total,
            "en_cours": en_cours,
        })
    return out


class HistoriqueMensuelView(APIView):
    """Expose historique_fcfa_mensuel (voir sa docstring) pour la carte « Historique mensuel »."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont un historique mensuel."},
                            status=status.HTTP_403_FORBIDDEN)
        return Response({"mois": historique_fcfa_mensuel(user.client)})


class HistoriqueJournalierView(APIView):
    """Agrégation JOURNALIÈRE côté serveur pour la page Historique.

    Une ligne par jour (énergie, pic, puissance moyenne en marche, énergie de nuit 22 h → 6 h, mesures, alertes de
    consommation), les jours SANS trace du boîtier (`manquants`), la période précédente de même durée avec son écart
    (None quand il n'a pas de sens), la répartition par capteur et l'état du boîtier (en ligne, dernier contact).
    Payload minuscule, calcul par plages d'horodatages indexées (voir `_aggregate_jours`)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à l'historique."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client

        sensor_id, err = _parse_sensor_id(request.query_params)
        if err:
            return err
        ids = _capteurs_du_client(client, sensor_id)

        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        win, err = _parse_hist_window(request.query_params, today)
        if err:
            return err
        start_date, end_date = win

        jours, manquants = _aggregate_jours(ids, start_date, end_date, tz)
        par_jour = _alertes_par_jour(client, start_date, end_date, tz)
        for j in jours:
            j["alertes"] = par_jour.get(j["date"], 0)

        # Période PRÉCÉDENTE de même durée : comparaison honnête (null si aucune mesure avant ; l'écart lui-même
        # est null quand il n'a pas de sens, jamais un « ▲ 1159 % »).
        duration = (end_date - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=duration - 1)
        prev_jours, _prev_manq = _aggregate_jours(ids, prev_start, prev_end, tz)
        previous = None
        if prev_jours:
            prev_kwh = sum(j["kwh"] for j in prev_jours)
            kwh_cur = sum(j["kwh"] for j in jours)
            previous = {
                "kwh": prev_kwh,
                "peak_w": max(j["peak_w"] for j in prev_jours),
                "days": sum(1 for j in prev_jours if j["etat"] == "mesure"),
                "date_from": prev_start.isoformat(),
                "date_to": prev_end.isoformat(),
                "evolution_pct": _evolution_pct(kwh_cur, prev_kwh),
                "jours": [{"date": j["date"], "kwh": j["kwh"]} for j in prev_jours],
            }

        # Répartition PAR CAPTEUR sur la fenêtre : TOUS les capteurs liés, énergie RÉELLE mesurée, indépendante du
        # filtre sensor_id (la carte montre toujours l'ensemble).
        from datetime import time as _t
        tous = _capteurs_du_client(client)
        debut_f = timezone.make_aware(_datetime.combine(start_date, _t.min), tz)
        fin_f = timezone.make_aware(_datetime.combine(end_date + timedelta(days=1), _t.min), tz)
        sums = {r['capteur_id']: r for r in MesureEnergie.objects.filter(
            capteur_id__in=tous, timestamp__gte=debut_f, timestamp__lt=fin_f)
            .values('capteur_id').annotate(kwh=Sum('energie'), peak=Max('puissance'))}
        repartition = []
        for cap in Capteur.objects.filter(client=client).values('id', 'nom'):
            agg = sums.get(cap['id'])
            repartition.append({
                "id": str(cap['id']),
                "nom": cap['nom'],
                "kwh": float((agg or {}).get('kwh') or 0),
                "peak_w": round(float((agg or {}).get('peak') or 0)),
            })
        repartition.sort(key=lambda x: x['kwh'], reverse=True)

        contact = etat_contact(client)
        derniere = MesureEnergie.objects.filter(capteur_id__in=tous).aggregate(m=Max('timestamp'))['m']
        return Response({
            "prix_kwh": float(prix_kwh_tout_compris(client)),
            "amperage": getattr(client, 'amperage', 10),
            "date_from": start_date.isoformat(),
            "date_to": end_date.isoformat(),
            "nuit": {"debut": HEURE_NUIT_DEBUT, "fin": HEURE_NUIT_FIN},
            "jours": jours,
            "manquants": manquants,
            "previous": previous,
            "repartition": repartition,
            "en_ligne": contact["en_ligne"],
            "dernier_contact": _iso(contact["dernier_contact"]),
            "derniere_mesure": timezone.localtime(derniere).date().isoformat() if derniere else None,
        })


class HeatmapView(APIView):
    """Puissance moyenne par (jour de semaine × heure) sur les 7 derniers jours.

    Agrégation SQL (GROUP BY) → payload minuscule (168 cellules max) au lieu de
    renvoyer toutes les mesures brutes. Jamais de valeur fabriquée : une case sans
    mesure est simplement absente de la réponse.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models.functions import ExtractHour, ExtractIsoWeekDay
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à ces données."},
                            status=status.HTTP_403_FORBIDDEN)
        tz = timezone.get_current_timezone()
        since = timezone.now() - timedelta(days=7)
        qs = MesureEnergie.objects.filter(capteur__client=user.client, timestamp__gte=since)
        rows = (qs.annotate(dow=ExtractIsoWeekDay('timestamp', tzinfo=tz),
                            hr=ExtractHour('timestamp', tzinfo=tz))
                  .values('dow', 'hr')
                  .annotate(avg_w=Avg('puissance'))
                  .order_by('dow', 'hr'))
        # dow : ExtractIsoWeekDay = 1(lundi)…7(dimanche) → on renvoie 0(lundi)…6(dimanche).
        cells = [{"dow": (r['dow'] - 1), "hour": r['hr'], "avg_w": float(r['avg_w'] or 0)}
                 for r in rows if r['dow'] is not None and r['hr'] is not None]
        return Response({"cells": cells})


def _prevision_fin_de_mois(client):
    """Prévision de la facture de FIN DE PÉRIODE (fin du bimestre en postpayé, du mois en
    prépayé), fourchette honnête, additive, convergente.

    Principe : on part du coût RÉEL à ce jour (certain, = le KPI du héros) et on n'impute
    qu'au TEMPS non encore mesuré (reste d'aujourd'hui + jours capteur hors ligne + jours
    futurs) la consommation PRÉVUE par le modèle du foyer (prevision_ia, 19/10/2026 : niveaux
    habituels par appareil en semaine et au repos, effet de la chaleur du jour, correction du
    soir) ; la fourchette vient des erreurs de prévision déjà constatées.
    Chaque borne (basse/centrale/haute) est ensuite tarifée par le VRAI moteur CIE.

    Garanties dures : forecast >= coût à ce jour ; convergence exacte vers la facture réelle
    le dernier jour ; plafond physique (P souscrite × 24h × jours) → jamais de valeur absurde ;
    aucune division par un prix moyen. Part fixe (abonnement) 100 % certaine, séparée.
    Choix produit validés : fourchette (pas un point), seuil N_MIN=3 jours complets, jours
    hors ligne IMPUTÉS à la conso habituelle (divulgués), calcul 100 % côté serveur (Abidjan).
    """
    now = timezone.localtime()
    # Période de facturation (bimestre en postpayé, mois en prépayé) : les jours sont
    # numérotés de 1 (premier jour de la période) à D (dernier jour).
    per = periode_courante(client, now)
    today = per["jours_ecoules"]
    D = per["jours"]
    type_compteur = getattr(client, 'typeCompteur', 'postpaye')
    N_MIN = 3

    # Aucun capteur → état vide honnête
    if not Capteur.objects.filter(client=client).exists():
        return {"mode": "vide", "type_compteur": type_compteur, "jours_du_mois": D, "jours_ecoules": today,
                "periode": _periode_json(per)}

    # Socle RÉEL = exactement le chiffre affiché par le héros (cohérence garantie, plancher du forecast)
    fac = facture_mois_a_ce_jour(client)
    d0 = fac["detail"]
    # kWh EXACT (non arrondi) → _bill(kwh_reel) == cost_to_date au franc près quand U→0.
    kwh_reel = float(fac.get("kwh_consommes_exact", fac["kwh_consommes"]))
    cost_to_date = _fcfa_affiche(d0)
    amperage = int(getattr(client, 'amperage', 10) or 10)
    p_kw = float(PUISSANCE_KW.get(amperage, Decimal("2.2")))

    def _r1(x):
        return int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    fixe_certain = _r1(d0["prime_fixe_fcfa"]) + _r1(d0["taxe_fixe_fcfa"])
    base = {"type_compteur": type_compteur, "jours_du_mois": D, "jours_ecoules": today,
            "periode": _periode_json(per),
            "cost_to_date": cost_to_date, "fixe_certain": fixe_certain}

    # Le modèle du foyer (note technique 4.1) : niveaux habituels par capteur (semaine / repos), effet de la chaleur,
    # erreurs déjà constatées. Il n'apprend que des journées COMPLÈTES (capteur présent au moins 80 % du jour).
    from . import prevision_ia
    m = prevision_ia.modele_du_client(client, now)
    k = m.jours_complets

    # Jour d'activation du service (1re mesure ou présence) → on n'impute JAMAIS avant.
    if not m.activation:
        return dict(base, mode="trop_tot", k=0, n_min=N_MIN, offline_days=0)
    activation = min(m.activation.values())
    activation_day = max(1, (activation - per["debut"]).days + 1)

    # Ce qui n'est pas encore mesuré dans la période, prévu par le modèle :
    #  - jours passés : la part non couverte de chaque capteur (boîtier hors ligne), à sa prévision de ce jour-là ;
    #  - aujourd'hui : ce qui reste de la journée (selon le profil horaire du foyer) + le trou déjà écoulé ;
    #  - jours à venir : prévision complète, avec la température annoncée (16 jours) puis la température habituelle.
    U_kwh, U, offline_days = 0.0, 0.0, 0
    capteurs = [c for c in m.capteurs if c.id in m.activation]

    def manque(d, part_ecoulee=1.0):
        """(kWh non mesurés, part non couverte moyenne, hors ligne ?) sur la part écoulée du jour d."""
        en_service = [c for c in capteurs if d >= m.activation[c.id]]
        if not en_service:
            return 0.0, 0.0, False
        couv = [m.couverture.get((c.id, d), 0.0) for c in en_service]
        kwh = sum((1.0 - cv) * m.jour_capteur(c, d) for c, cv in zip(en_service, couv)) * part_ecoulee
        return kwh, (1.0 - sum(couv) / len(couv)) * part_ecoulee, max(couv) == 0.0

    for day in range(activation_day, today):                 # jours passés, hors aujourd'hui
        d = per["debut"] + timedelta(days=day - 1)
        kwh, part, hors_ligne = manque(d)
        U_kwh += kwh
        U += part
        offline_days += hors_ligne
    d_auj = now.date()
    reste = m.part_restante(now)                              # part de la journée encore à consommer
    kwh, part, hors_ligne = manque(d_auj, 1.0 - reste)
    U_kwh += kwh + reste * m.jour(d_auj)
    U += part + reste
    if hors_ligne and today > activation_day:
        offline_days += 1                                     # capteur hors ligne toute la journée
    futurs = [per["debut"] + timedelta(days=day - 1) for day in range(today + 1, D + 1)]
    U_kwh += sum(m.jour(d) for d in futurs)
    U += len(futurs)

    # TIER 0 : jour 1 ou pas assez de journées complètes → aucun chiffre de conso (honnête)
    if today <= 1 or k < N_MIN:
        return dict(base, mode="trop_tot", k=k, n_min=N_MIN, offline_days=offline_days)

    n = max(m.n_residus, k)
    sigma = m.sigma
    cap = max(p_kw * 24.0 * D, kwh_reel)         # plafond PHYSIQUE, jamais SOUS le réel déjà certain
    central = min(max(kwh_reel + U_kwh, kwh_reel), cap)
    se = sigma * math.sqrt((U * U) / n + U)       # erreur des niveaux appris + écart jour à jour
    z = prevision_ia.Z80                           # ~ intervalle 80 %
    low = min(max(kwh_reel, central - z * se), central)
    high = max(min(cap, central + z * se), central)

    def _bill(kwh):
        return _fcfa_affiche(calculer_facture_pour_client(max(0.0, kwh), client))
    bill_low = max(_bill(low), cost_to_date)     # INVARIANT : jamais < coût à ce jour
    bill_central = max(_bill(central), bill_low)
    bill_high = max(_bill(high), bill_central)
    variable_estime = max(0, bill_central - fixe_certain)

    # Palier de confiance (rétrogradé si beaucoup de jours manquants)
    # Dénominateur = jours observables DEPUIS l'activation, aujourd'hui INCLUS (offline_days
    # peut compter aujourd'hui via le correctif hors-ligne-du-jour) → ratio jamais > 1.
    coverage_ok = (offline_days / max(1, today - activation_day + 1)) <= 0.3
    if k >= 7 and coverage_ok and today >= (D - 2):
        tier, confiance = 2, "fiable"
    elif coverage_ok:
        tier, confiance = 1, "indicative"
    else:
        tier, confiance = 1, "indicative_trous"

    mode = "band_large" if (bill_low > 0 and (bill_high / bill_low) > 4) else "band"
    res = dict(base, mode=mode, bill_low=bill_low, bill_central=bill_central, bill_high=bill_high,
               variable_estime=variable_estime, projected_kwh=round(central, 1),
               k=k, offline_days=offline_days, tier=tier, confiance=confiance,
               **_details_prevision(m, client, futurs))

    if type_compteur == 'prepaye':
        try:
            from apps.alerts.utils import credit_prepaye_info
            info = credit_prepaye_info(client) or {}
            # Ce qu'il reste à dépenser d'ici la fin du mois, moins le crédit encore
            # disponible (l'ancien calcul retirait le TOTAL des recharges depuis toujours).
            reste_a_depenser = bill_central - cost_to_date
            restant = float(info.get('restant_fcfa') or 0)
            res["recharge_conseillee"] = max(0, int(round(reste_a_depenser - restant)))
        except Exception:
            pass
    return res


def _details_prevision(m, client, futurs):
    """Ce que la prévision a pris en compte (page Prévisions, assistant) : la météo et l'effet de la chaleur, les
    habitudes apprises par appareil, les prochains jours."""
    from . import meteo
    t_hab = m.temperature_habituelle()
    prochains = [d for d in futurs if d in m.temperatures][:meteo.JOURS_FUTURS]
    t_prevue = (sum(m.temperatures[d] for d in prochains) / len(prochains)) if prochains else None
    effet = sum(m.effet_chaleur(d) for d in futurs)
    demain = timezone.localdate() + timedelta(days=1)
    return {
        "methode": "habitudes et température" if m.meteo_disponible else "habitudes (météo indisponible)",
        "meteo": {"disponible": m.meteo_disponible, "ville": meteo.ville_du_client(client),
                  "t_habituelle": round(t_hab, 1) if t_hab is not None else None,
                  "t_prevue": round(t_prevue, 1) if t_prevue is not None else None,
                  "effet_chaleur_kwh": round(effet, 2)},
        "par_capteur": [{"nom": c.nom, "niveau_semaine": round(c.niveaux["semaine"], 3) if "semaine" in c.niveaux else None,
                         "niveau_repos": round(c.niveaux["repos"], 3) if "repos" in c.niveaux else None,
                         "kwh_par_degre": round(c.c, 3), "chaleur_apprise": c.c_brute is not None,
                         "journees": c.jours} for c in m.capteurs if c.jours],
        "prochains_jours": [{"date": (demain + timedelta(days=i)).isoformat(),
                             "kwh": round(m.jour(demain + timedelta(days=i)), 2),
                             "t_moy": m.temperatures.get(demain + timedelta(days=i))} for i in range(7)],
    }


class PrevisionView(APIView):
    """Prévision honnête de la facture de fin de mois (fourchette, part certaine séparée)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients ont accès à la prévision."},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(_prevision_fin_de_mois(user.client))


class ExportCSVView(APIView):
    """Export CSV des mesures du client (spéc. SHOULD HAVE).

    Fichier prêt pour un tableur en conventions françaises : BOM UTF-8 (sans lui,
    Excel Windows affiche « Ã© » à la place des accents), séparateur « ; »,
    horodatage LOCAL lisible, décimales à virgule (reconnues comme nombres).
    Données brutes uniquement : une ligne = une mesure, rien d'agrégé ni d'inventé.
    Réponse STREAMÉE (iterator) : un historique complet ne charge jamais toutes
    les mesures en mémoire. Validation stricte des paramètres, alignée sur le PDF :
    date malformée, plage inversée ou sensor_id non-UUID → 400, jamais un 500."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        import csv
        from django.http import StreamingHttpResponse  # pyrefly: ignore [untyped-import]

        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent exporter leurs mesures."},
                            status=status.HTTP_403_FORBIDDEN)

        queryset = MesureEnergie.objects.filter(capteur__client=user.client).select_related('capteur')

        sensor_id, err = _parse_sensor_id(request.query_params)
        if err:
            return err
        if sensor_id:
            queryset = queryset.filter(capteur_id=sensor_id)

        # Plage de dates explicite (prioritaire) : le CSV couvre alors exactement la
        # même fenêtre que le tableau à l'écran (ex. « Ce mois » = mois calendaire).
        from datetime import datetime as _dt

        def _parse_date(value):
            try:
                return _dt.strptime(value, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return None

        date_from_raw = request.query_params.get('date_from')
        date_to_raw = request.query_params.get('date_to')
        date_from = date_to = None
        period = None
        if date_from_raw or date_to_raw:
            date_from, date_to = _parse_date(date_from_raw), _parse_date(date_to_raw)
            # Une date fournie mais illisible n'est JAMAIS ignorée en silence :
            # sinon on exporterait tout l'historique en croyant exporter une plage.
            if (date_from_raw and date_from is None) or (date_to_raw and date_to is None):
                return Response({"detail": "Format de date invalide (attendu AAAA-MM-JJ)."},
                                status=status.HTTP_400_BAD_REQUEST)
            if date_from and date_to and date_from > date_to:
                return Response({"detail": "La date de début doit être antérieure ou égale à la date de fin."},
                                status=status.HTTP_400_BAD_REQUEST)
            if date_from:
                queryset = _entre_jours(queryset, debut=date_from)
            if date_to:
                queryset = _entre_jours(queryset, fin=date_to)
        else:
            period = request.query_params.get('period')
            # MÊME fenêtre que l'écran (dates CALENDAIRES, dernier jour = aujourd'hui), et
            # non plus `now - Ndays` glissant à la seconde : sinon le CSV « 7 jours » couvrait
            # 168 h glissantes ≠ 7 jours calendaires affichés → quelques mesures de bord
            # apparaissaient/manquaient. On réutilise la table de correspondance de _parse_hist_window.
            if period in ('day', 'week', 'month'):
                today = timezone.localdate()
                days = {'day': 1, 'week': 7, 'month': 30}[period]
                start_cal = today - timedelta(days=days - 1)
                queryset = _entre_jours(queryset, start_cal, today)

        # Nom de fichier explicite : la période couverte, pas un horodatage opaque.
        if date_from or date_to:
            fin = date_to or timezone.localdate()
            debut = date_from.strftime('%Y%m%d') if date_from else 'debut'
            filename = f"aoceda_mesures_{debut}_{fin.strftime('%Y%m%d')}.csv"
        else:
            suffixe = {'day': '24h', 'week': '7j', 'month': '30j'}.get(period or '', 'tout')
            filename = f"aoceda_mesures_{suffixe}_{timezone.localtime().strftime('%Y%m%d')}.csv"

        def _virgule(x, dec):
            # Virgule décimale : Excel/LibreOffice FR reconnaît un NOMBRE, pas du texte.
            return (f"{float(x):.{dec}f}").replace('.', ',')

        class _Echo:
            """Pseudo-tampon : csv.writer.writerow() retourne la ligne au lieu de la stocker."""
            def write(self, value):
                return value

        writer = csv.writer(_Echo(), delimiter=';')

        def _lignes():
            yield '﻿'  # BOM UTF-8 : accents corrects dans Excel
            yield writer.writerow(['Horodatage (heure locale)', 'Appareil', 'Puissance (W)', 'Courant (A)',
                                   'Énergie (kWh)', 'Tension (V)', 'Facteur de puissance'])
            # values_list : aucune instance de modèle par mesure (19/10/2026, export plus rapide)
            colonnes = ('timestamp', 'capteur__nom', 'puissance', 'courant', 'energie', 'tension_V', 'facteur_puissance')
            for ts, nom, pu, co, en, te, fp in queryset.order_by('timestamp').values_list(*colonnes).iterator(chunk_size=2000):
                yield writer.writerow([
                    timezone.localtime(ts).strftime('%d/%m/%Y %H:%M:%S'),
                    nom,
                    _virgule(pu, 2), _virgule(co, 3), _virgule(en, 6),
                    _virgule(te, 1), _virgule(fp, 3),
                ])

        response = StreamingHttpResponse(_lignes(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ExportJournalierCSVView(APIView):
    """Export CSV du RÉSUMÉ JOURNALIER : exactement ce que le tableau de l'historique affiche (une ligne par jour de la
    fenêtre, jours sans mesure compris, marqués « Aucune mesure »). Même fenêtre, mêmes règles que la page (19/10/2026)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        import csv
        import io
        from django.http import HttpResponse  # pyrefly: ignore [untyped-import]

        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent exporter leur historique."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client
        sensor_id, err = _parse_sensor_id(request.query_params)
        if err:
            return err
        today = timezone.localdate()
        win, err = _parse_hist_window(request.query_params, today)
        if err:
            return err
        start_date, end_date = win
        tz = timezone.get_current_timezone()
        jours, _manq = _aggregate_jours(_capteurs_du_client(client, sensor_id), start_date, end_date, tz)
        par_date = {j['date']: j for j in jours}
        alertes = _alertes_par_jour(client, start_date, end_date, tz)
        prix = float(prix_kwh_tout_compris(client))

        def fr(x, dec):
            return f"{float(x):.{dec}f}".replace('.', ',')

        sortie = io.StringIO()
        w = csv.writer(sortie, delimiter=';')
        w.writerow(['Date', 'Énergie (kWh)', 'Coût énergie estimé (FCFA, hors abonnement fixe)',
                    'Puissance moyenne en marche (W)', 'Énergie de nuit 22h-06h (kWh)', 'Pic de puissance (W)',
                    'Mesures', 'Alertes de consommation', 'État'])
        d = start_date
        while d <= min(end_date, today):
            j = par_date.get(d.isoformat())
            if j is None:
                w.writerow([d.strftime('%d/%m/%Y'), '', '', '', '', '', '', '', 'Aucune mesure (boîtier hors ligne)'])
            else:
                w.writerow([d.strftime('%d/%m/%Y'), fr(j['kwh'], 2), str(int(round(j['kwh'] * prix))),
                            str(j['avg_w']), fr(j['night_kwh'], 2), str(j['peak_w']), str(j['n']),
                            str(alertes.get(j['date'], 0)),
                            'Mesuré' if j['etat'] == 'mesure' else 'Éteint (0 kWh, boîtier en ligne)'])
            d += timedelta(days=1)
        resp = HttpResponse('\ufeff' + sortie.getvalue(), content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = (f'attachment; filename="aoceda_journalier_{start_date.strftime("%Y%m%d")}'
                                       f'_{end_date.strftime("%Y%m%d")}.csv"')
        return resp


class HistoriquePDFView(APIView):
    """Relevé PDF professionnel de l'historique journalier (MÊME fenêtre que le tableau).

    Document structuré via le socle apps.analytics.pdf : cartes d'identification
    (titulaire / document référencé), synthèse de la période en indicateurs,
    détail journalier zébré avec dépassements signalés, méthodologie explicite,
    en-tête de marque et pagination « Page X sur Y » sur chaque page.
    Coût = énergie × tarif CIE (taxes incl.), hors abonnement fixe. Indicatif."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.http import HttpResponse  # pyrefly: ignore [untyped-import]
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Spacer
        from . import pdf as pdfdoc

        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent exporter leur historique."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client
        base = MesureEnergie.objects.filter(capteur__client=client)
        sensor_id, err = _parse_sensor_id(request.query_params)
        if err:
            return err
        capteur_filtre = None
        if sensor_id:
            base = base.filter(capteur_id=sensor_id)
            capteur_filtre = Capteur.objects.filter(client=client, id=sensor_id).first()

        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        win, err = _parse_hist_window(request.query_params, today)
        if err:
            return err
        start_date, end_date = win
        jours, _manq = _aggregate_jours(_capteurs_du_client(client, sensor_id), start_date, end_date, tz)

        prix = float(prix_kwh_tout_compris(client))
        amperage = int(getattr(client, 'amperage', 10) or 10)
        cap_w = int(float(PUISSANCE_KW.get(amperage, Decimal('2.2'))) * 1000)
        type_compteur = 'Prépayé' if getattr(client, 'typeCompteur', 'postpaye') == 'prepaye' else 'Postpayé'

        st = pdfdoc.get_styles()
        ref = pdfdoc.reference_document('HIST', client)
        nb_jours_periode = (end_date - start_date).days + 1

        # 1) Identification : qui, quoi, quelle période, quel tarif, traçable.
        titulaire = [("Nom", client.nom), ("Email", client.email)]
        if getattr(client, 'numeroCIE', None):
            titulaire.append(("N° compteur CIE", client.numeroCIE))
        titulaire += [("Abonnement", f"{amperage} A (env. {pdfdoc.fmt_num(cap_w, 0)} W)"),
                      ("Type de compteur", type_compteur)]
        doc_infos = [("Référence", ref),
                     ("Période", f"du {pdfdoc.fmt_date_fr(start_date)} au {pdfdoc.fmt_date_fr(end_date)}"),
                     ("Tarif appliqué", f"env. {pdfdoc.fmt_num(prix)} F/kWh (taxes incluses)"),
                     ("Édité le", timezone.localtime().strftime('%d/%m/%Y à %H:%M'))]
        if capteur_filtre:
            doc_infos.append(("Capteur", capteur_filtre.nom))
        el = [pdfdoc.panneau_identification([("Titulaire", titulaire), ("Document", doc_infos)], st)]

        if not jours:
            el += pdfdoc.section("Synthèse de la période", st)
            el.append(Paragraph(
                "Aucune mesure reçue sur cette période : le capteur était hors ligne ou non "
                "installé. Aucune donnée n'est estimée ni reconstituée dans ce document.", st['body']))
        else:
            tot_kwh = sum(j['kwh'] for j in jours)
            tot_night = sum(j['night_kwh'] for j in jours)
            pic = max(j['peak_w'] for j in jours)
            moyenne = tot_kwh / len(jours)
            part_nuit = (tot_night / tot_kwh * 100) if tot_kwh > 0 else 0.0

            # 2) Synthèse : les chiffres clés avant le détail.
            el += pdfdoc.section("Synthèse de la période", st)
            el.append(pdfdoc.bande_kpi([
                ("Énergie consommée", f"{pdfdoc.fmt_num(tot_kwh)} kWh",
                 f"{len(jours)} jour(s) mesurés sur {nb_jours_periode}"),
                ("Coût énergie estimé", f"{pdfdoc.fmt_fcfa(tot_kwh * prix)} F",
                 "hors abonnement fixe"),
                ("Moyenne journalière", f"{pdfdoc.fmt_num(moyenne)} kWh",
                 f"env. {pdfdoc.fmt_fcfa(moyenne * prix)} F/jour"),
                ("Pic de puissance", f"{pdfdoc.fmt_num(pic, 0)} W",
                 f"souscrit : env. {pdfdoc.fmt_num(cap_w, 0)} W"),
                ("Part nocturne", f"{pdfdoc.fmt_num(part_nuit, 1)} %",
                 f"{pdfdoc.fmt_num(tot_night)} kWh entre 22h et 06h"),
            ], st))

            # 3) Détail jour par jour (tableau zébré, en-tête répété à chaque page).
            el += pdfdoc.section("Détail journalier", st)
            table_el, _ = pdfdoc.tableau_journalier(jours, prix, cap_w, st)
            el += table_el

        # 4) Méthodologie : comment lire les chiffres, sans ambiguïté.
        el += pdfdoc.section("Méthodologie et mentions", st)
        for txt in (
            "Coût énergie = énergie mesurée × tarif CIE tout compris "
            f"(env. {pdfdoc.fmt_num(prix)} F/kWh, taxes et TVA incluses), hors prime fixe de la période de facturation "
            "(bimestre en postpayé, mois en prépayé). "
            "La facture complète (abonnement inclus) figure dans l'application.",
            "Part nocturne = énergie mesurée entre 22h00 et 06h00, heure locale. "
            "Pic = puissance instantanée maximale relevée dans la journée.",
            "Un jour absent du tableau signifie qu'aucune mesure n'a été reçue ce jour-là "
            "(boîtier hors ligne) : aucune valeur n'est inventée ni extrapolée. Un jour à 0 kWh signifie que le boîtier "
            "était en ligne mais que l'appareil ne consommait pas.",
        ):
            el.append(Paragraph(txt, st['note']))
            el.append(Spacer(1, 1.5 * mm))

        contenu = pdfdoc.build_pdf("Historique de consommation", ref, el)
        resp = HttpResponse(contenu, content_type='application/pdf')
        fname = f"aoceda_historique_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pdf"
        resp['Content-Disposition'] = f'attachment; filename="{fname}"'
        return resp


class RapportMensuelPDFView(APIView):
    """Rapport mensuel PDF complet du client, le document « propre » à archiver.

    Remplace l'ancienne impression navigateur (window.print) de la page Prévisions.
    Contenu : identification, synthèse du mois, détail de la facture (grille CIE,
    mêmes moteurs de calcul que l'application, invariant somme des lignes = total),
    prévision de fin de mois (fourchette honnête ou « trop tôt » assumé), crédit
    prépayé le cas échéant, détail journalier, méthodologie. Période de facturation en
    cours : le bimestre en postpayé (arrêté n° 1355), le mois en prépayé."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.http import HttpResponse  # pyrefly: ignore [untyped-import]
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, Spacer
        from . import pdf as pdfdoc

        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent exporter leur rapport."},
                            status=status.HTTP_403_FORBIDDEN)
        client = user.client

        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        per = periode_courante(client)
        start_month = per["debut"]          # début de la période (nom historique)
        mot = "bimestre" if per["type"] == "bimestre" else "mois"
        du_mot = f"du {mot}"

        st = pdfdoc.get_styles()
        ref = pdfdoc.reference_document('RM', client)
        amperage = int(getattr(client, 'amperage', 10) or 10)
        cap_w = int(float(PUISSANCE_KW.get(amperage, Decimal('2.2'))) * 1000)
        prix = float(prix_kwh_tout_compris(client))
        prepaye = getattr(client, 'typeCompteur', 'postpaye') == 'prepaye'

        def _q(v):
            return int(Decimal(str(v)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

        # Identification (mêmes cartes que l'historique : identité visuelle commune).
        titulaire = [("Nom", client.nom), ("Email", client.email)]
        if getattr(client, 'numeroCIE', None):
            titulaire.append(("N° compteur CIE", client.numeroCIE))
        titulaire += [("Abonnement", f"{amperage} A (env. {pdfdoc.fmt_num(cap_w, 0)} W)"),
                      ("Type de compteur", 'Prépayé' if prepaye else 'Postpayé')]
        doc_infos = [("Référence", ref),
                     ("Période", f"du {pdfdoc.fmt_date_fr(start_month)} au {pdfdoc.fmt_date_fr(today)}"),
                     ("Tarif appliqué", f"env. {pdfdoc.fmt_num(prix)} F/kWh (taxes incluses)"),
                     ("Édité le", timezone.localtime().strftime('%d/%m/%Y à %H:%M'))]
        el = [pdfdoc.panneau_identification([("Titulaire", titulaire), ("Document", doc_infos)], st)]

        # Compte sans capteur : document VIDE honnête (cohérent avec le reste de l'app).
        if not Capteur.objects.filter(client=client).exists():
            el += pdfdoc.section(f"Synthèse {du_mot}", st)
            el.append(Paragraph(
                "Aucun capteur n'est associé à ce compte : il n'y a encore rien à rapporter. "
                "Ce document ne contient volontairement aucune donnée estimée.", st['body']))
            contenu = pdfdoc.build_pdf("Rapport mensuel", ref, el)
            resp = HttpResponse(contenu, content_type='application/pdf')
            resp['Content-Disposition'] = (
                f'attachment; filename="aoceda_rapport_mensuel_{today.strftime("%Y-%m")}.pdf"')
            return resp

        fac = facture_mois_a_ce_jour(client)
        d = fac["detail"]
        total = _fcfa_affiche(d)
        abonnement_fixe = _q(d["prime_fixe_fcfa"]) + _q(d["taxe_fixe_fcfa"])

        # 1) Synthèse de la période : facture à ce jour, énergie, progression, précédente
        #    (recalculée depuis ses mesures : les anciens snapshots étaient mensuels).
        p_debut, p_fin = periode_precedente(client, start_month)
        t0, t1 = _debut_jour(p_debut), _debut_jour(p_fin + timedelta(days=1))
        if MesureEnergie.objects.filter(capteur__client=client, timestamp__gte=t0, timestamp__lt=t1).exists():
            prec = _fcfa_affiche(calculer_facture_pour_client(_kwh_consommes(client, t0, t1), client))
            kpi_prec = (f"{pdfdoc.fmt_fcfa(prec)} F", libelle_periode(p_debut, p_fin))
        else:
            kpi_prec = ("—", "aucune donnée")
        pct = round(fac["jours_ecoules"] / fac["jours_du_mois"] * 100)
        el += pdfdoc.section(f"Synthèse · {fac['mois_libelle']}", st)
        el.append(pdfdoc.bande_kpi([
            ("Coût du mois, à ce jour" if prepaye else "Facture du bimestre, à ce jour",
             f"{pdfdoc.fmt_fcfa(total)} F", "TVA 18 % incluse"),
            ("Énergie consommée", f"{pdfdoc.fmt_num(float(fac['kwh_consommes']))} kWh",
             f"depuis le {pdfdoc.fmt_date_fr(start_month)}"),
            (f"Progression {du_mot}", f"{fac['jours_ecoules']}/{fac['jours_du_mois']} j", f"{pct} %"),
            ("Période précédente", kpi_prec[0], kpi_prec[1]),
        ], st))

        # 2) Détail de la facture : la décomposition officielle CIE, ligne à ligne.
        #    Composantes arrondies individuellement (HALF_UP) → leur somme = le total
        #    affiché, même invariant que _fcfa_affiche / la carte de l'application.
        el += pdfdoc.section("Détail de la facture (grille tarifaire CIE)", st)
        libelle_t1 = "Consommation" if prepaye else "Consommation tranche 1"
        lignes = [[f"{libelle_t1} : {pdfdoc.fmt_num(float(d['tranche1_kwh']))} kWh "
                   f"× {pdfdoc.fmt_num(float(d['tranche1_prix']), 0)} F/kWh",
                   pdfdoc.fmt_fcfa(_q(d['tranche1_fcfa']))]]
        if float(d['tranche2_kwh']) > 0:
            lignes.append([f"Consommation tranche 2 : {pdfdoc.fmt_num(float(d['tranche2_kwh']))} kWh "
                           f"× {pdfdoc.fmt_num(float(d['tranche2_prix']), 0)} F/kWh",
                           pdfdoc.fmt_fcfa(_q(d['tranche2_fcfa']))])
        if prepaye:
            lignes.append(["Taxes et redevances par kWh", pdfdoc.fmt_fcfa(_q(d['taxes_fcfa']))])
        else:
            lignes.append(["Prime fixe du bimestre (abonnement)", pdfdoc.fmt_fcfa(_q(d['prime_fixe_fcfa']))])
            lignes.append([f"Taxes et redevances (dont part fixe {pdfdoc.fmt_fcfa(_q(d['taxe_fixe_fcfa']))} F)",
                           pdfdoc.fmt_fcfa(_q(d['taxes_fcfa']))])
        el.append(pdfdoc.tableau_donnees(
            ["Libellé", "Montant (FCFA)"], lignes, [135 * mm, 45 * mm],
            total=[f"TOTAL {du_mot} à ce jour (TVA 18 % incluse)", pdfdoc.fmt_fcfa(total)]))
        el.append(Spacer(1, 2 * mm))
        tarif_libelle = {'social': 'tarif social', 'general': 'tarif général'}.get(
            str(d['type_tarif']), str(d['type_tarif']))
        if prepaye:
            regle = "prépaiement : un prix unique par kWh, sans tranche, prime fixe comprise dans chaque kWh"
        else:
            regle = f"tranche 1 jusqu'à {pdfdoc.fmt_num(float(d['seuil_t1_kwh']), 0)} kWh par bimestre"
        el.append(Paragraph(
            f"Grille officielle (arrêté n° 1355 du 27/12/2023) « {tarif_libelle} », abonnement "
            f"{amperage} A ; {regle}. Montant calculé sur la seule énergie réellement mesurée "
            f"depuis le {pdfdoc.fmt_date_fr(start_month)} : aucune projection n'y est incluse.",
            st['note']))

        # 3) Prévision de fin de mois : fourchette honnête, ou « trop tôt » assumé.
        prev_fin = _prevision_fin_de_mois(client)
        el += pdfdoc.section(f"Prévision de fin {du_mot}", st)
        if prev_fin.get('mode') in ('band', 'band_large'):
            el.append(pdfdoc.bande_kpi([
                ("Fourchette basse", f"{pdfdoc.fmt_fcfa(prev_fin['bill_low'])} F", ""),
                ("Montant attendu", f"{pdfdoc.fmt_fcfa(prev_fin['bill_central'])} F",
                 "estimation centrale"),
                ("Fourchette haute", f"{pdfdoc.fmt_fcfa(prev_fin['bill_high'])} F", ""),
            ], st))
            el.append(Spacer(1, 2.5 * mm))
            el.append(Paragraph(
                f"Part fixe certaine (abonnement) : <b>{pdfdoc.fmt_fcfa(prev_fin['fixe_certain'])} F</b> · "
                f"consommation estimée : env. {pdfdoc.fmt_fcfa(prev_fin['variable_estime'])} F. "
                f"Estimation basée sur {prev_fin['k']} journée(s) complète(s) de mesures réelles ; "
                f"consommation projetée env. {pdfdoc.fmt_num(prev_fin['projected_kwh'], 1)} kWh.",
                st['body']))
            if prev_fin.get('offline_days'):
                el.append(Spacer(1, 1.5 * mm))
                el.append(Paragraph(
                    f"{prev_fin['offline_days']} jour(s) sans données ont été imputés à la consommation "
                    "habituelle pour la prévision uniquement ; le montant « à ce jour » ci-dessus, lui, "
                    "n'est jamais gonflé.", st['note']))
            if prev_fin.get('mode') == 'band_large':
                el.append(Spacer(1, 1.5 * mm))
                el.append(Paragraph(
                    "Fourchette encore large : elle se resserrera après 1 à 2 journées complètes "
                    "de mesures supplémentaires.", st['note']))
        elif prev_fin.get('mode') == 'trop_tot':
            el.append(Paragraph(
                f"Pas encore assez de journées complètes de mesures ({prev_fin.get('k', 0)} sur "
                f"{prev_fin.get('n_min', 3)} requises) pour estimer la fin {du_mot} sans rien inventer. "
                f"Seul l'abonnement fixe est déjà certain : "
                f"<b>{pdfdoc.fmt_fcfa(prev_fin.get('fixe_certain', abonnement_fixe))} F</b>.", st['body']))

        # 4) Crédit prépayé : uniquement pour les compteurs prépayés.
        if prepaye:
            from apps.alerts.utils import credit_prepaye_info
            try:
                info = credit_prepaye_info(client)
            except Exception:
                # Jamais un 500 en pleine génération de document pour une info annexe :
                # sans crédit calculable, la section est simplement omise.
                info = None
            if info:
                el += pdfdoc.section("Crédit prépayé", st)
                autonomie = (f"{info['jours_restants']} j" if info.get('jours_restants') is not None else "—")
                el.append(pdfdoc.bande_kpi([
                    ("Recharges déclarées", f"{pdfdoc.fmt_fcfa(info['recharge_fcfa'])} F", "depuis le début"),
                    ("Consommé", f"{pdfdoc.fmt_fcfa(info['consomme_fcfa'])} F", ""),
                    ("Crédit restant", f"{pdfdoc.fmt_fcfa(info['restant_fcfa'])} F", ""),
                    ("Coût moyen / jour",
                     f"{pdfdoc.fmt_fcfa(info['cout_jour_fcfa'])} F" if info['cout_jour_fcfa'] is not None else "—",
                     "" if info['cout_jour_fcfa'] is not None else "pas encore connu"),
                    ("Autonomie estimée", autonomie, "au rythme actuel"),
                ], st))
                if prev_fin.get('recharge_conseillee') is not None:
                    el.append(Spacer(1, 2 * mm))
                    el.append(Paragraph(
                        "Pour finir le mois sans coupure, recharge conseillée : env. "
                        f"<b>{pdfdoc.fmt_fcfa(prev_fin['recharge_conseillee'])} F</b>.", st['body']))

        # 5) Détail journalier du mois (même tableau normalisé que l'historique).
        jours, _manq = _aggregate_jours(_capteurs_du_client(client), start_month, today, tz)
        el += pdfdoc.section(f"Consommation journalière {du_mot}", st)
        if jours:
            table_el, _ = pdfdoc.tableau_journalier(jours, prix, cap_w, st)
            el += table_el
        else:
            el.append(Paragraph(f"Aucune mesure reçue depuis le début {du_mot}.", st['body']))

        # 6) Méthodologie et mentions.
        el += pdfdoc.section("Méthodologie et mentions", st)
        for txt in (
            "Les montants sont calculés selon l'arrêté n° 1355 du 27/12/2023 (postpayé : facture "
            "par bimestre, tranches, prime fixe, taxes ; prépayé : prix unique par kWh ; TVA 18 % "
            "incluse) sur la seule énergie réellement mesurée. "
            "La somme des lignes du détail est égale au total affiché, au franc près.",
            f"La prévision de fin {du_mot} est une estimation, jamais une promesse : elle devient "
            f"le montant exact le dernier jour {du_mot}. Un jour absent du détail journalier = "
            "aucune mesure reçue ce jour-là ; aucune valeur n'est inventée.",
        ):
            el.append(Paragraph(txt, st['note']))
            el.append(Spacer(1, 1.5 * mm))

        contenu = pdfdoc.build_pdf("Rapport mensuel", ref, el)
        resp = HttpResponse(contenu, content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'attachment; filename="aoceda_rapport_mensuel_{fac["annee_mois"]}.pdf"')
        return resp


class AdminStatsView(APIView):
    """Statistiques globales de la plateforme + santé des capteurs (espace admin)."""

    def get_permissions(self):
        from apps.accounts.permissions import IsAdministrateur
        return [permissions.IsAuthenticated(), IsAdministrateur()]

    def get(self, request):
        from apps.accounts.models import Utilisateur
        from apps.sensors.models import Dispositif
        from apps.alerts.models import Alerte

        now = timezone.now()
        offline_threshold = now - timedelta(minutes=10)

        total_clients = Utilisateur.objects.filter(role='client').count()
        total_techniciens = Utilisateur.objects.filter(role='technicien').count()
        capteurs = Capteur.objects.all()
        capteurs_actifs = capteurs.filter(actif=True).count()
        capteurs_hors_ligne = capteurs.filter(
            actif=True).exclude(derniereLecture__gte=offline_threshold).count()

        mesures_24h = MesureEnergie.objects.filter(timestamp__gte=now - timedelta(hours=24)).count()
        alertes_non_lues = Alerte.objects.filter(lue=False).count()
        alertes_24h = Alerte.objects.filter(createdAt__gte=now - timedelta(hours=24)).count()

        return Response({
            "clients_total": total_clients,
            "clients_actifs": Utilisateur.objects.filter(role='client', is_active=True).count(),
            "techniciens_total": total_techniciens,
            "dispositifs_total": Dispositif.objects.count(),
            "dispositifs_connectes": Dispositif.objects.filter(estConnecté=True).count(),
            "capteurs_total": capteurs.count(),
            "capteurs_actifs": capteurs_actifs,
            "capteurs_hors_ligne": capteurs_hors_ligne,
            "mesures_24h": mesures_24h,
            "alertes_non_lues": alertes_non_lues,
            "alertes_24h": alertes_24h,
            "last_update": now.isoformat(),
        })


class TarifView(APIView):
    """Le tarif du client (prix tout compris, seuil de tranche par bimestre, cycle de facturation)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'client'):
            return Response({"detail": "Seuls les clients ont un tarif."}, status=status.HTTP_403_FORBIDDEN)
        return Response(descriptif_tarif(request.user.client))
